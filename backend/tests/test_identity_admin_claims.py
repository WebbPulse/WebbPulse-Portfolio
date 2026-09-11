"""`get_current_user` in dual mode: the legacy HS256 token and the gateway's claims.

The gap this closes. The protected `/api/v1` admin routes verified only the
legacy HS256 token, and an identity access token is RS256, KMS signed, with a
numeric `sub`. So a frontend running in identity mode sent a token the admin
routes could not read and got 401 on every write. This asserts that both now
resolve to the same row, and that nothing about the legacy path moved.

**The claims are trusted because of where they arrive, not because this process
checked them.** Nothing here verifies an RS256 signature and the application has
no KMS access; the gateway's JWT authorizer in production, or the staging access
gate's Lambda in gate mode, is the verifier. What these tests cover is the read:
the two shapes that carry the claims, and the account checks applied to whatever
subject they name.

The two shapes are the deployment's, not the request's:

- `requestContext.authorizer.jwt.claims`, a flat string map, from API Gateway's
  own JWT authorizer in production.
- `requestContext.authorizer.lambda["jwt.claims"]`, one string of JSON, from the
  staging access gate, because a Lambda authorizer's context lands under
  `lambda` and API Gateway refuses a nested object there.

Both reach the process in the `x-amzn-request-context` header, which the Lambda
Web Adapter writes from the invoke event as plain JSON rather than base64. A
test sets that header directly, which is the one thing a real caller cannot do:
API Gateway does not forward an inbound header of that name and the adapter
overwrites it from the event regardless.
"""

import json

import pytest

PROTECTED = "/api/v1/posts/admin"


def _native_context(sub, **claims):
    """The production shape: a flat string map under `authorizer.jwt.claims`.

    Every value is a string, `exp` included, which is what API Gateway's own JWT
    authorizer produces.
    """
    return json.dumps({"authorizer": {"jwt": {"claims": {"sub": str(sub), **claims}}}})


def _gate_context(sub, **claims):
    """The staging shape: one JSON string under `authorizer.lambda["jwt.claims"]`.

    The gate stringifies the values inside it deliberately, so `exp` reads the
    same way in both environments and no caller needs a branch on which one it
    is in.
    """
    payload = json.dumps({"sub": str(sub), **claims})
    return json.dumps({"authorizer": {"lambda": {"jwt.claims": payload}}})


@pytest.mark.auth
class TestIdentityClaimsAreAccepted:
    """A verified subject in the request context resolves to the admin row."""

    def test_native_authorizer_claims_are_accepted(self, client, test_admin_user):
        """The production shape resolves, with no bearer token at all.

        A 200 rather than a 401 is the whole point: this route previously had no
        way to read this credential.
        """
        response = client.get(
            PROTECTED,
            headers={"x-amzn-request-context": _native_context(test_admin_user["id"])},
        )
        assert response.status_code == 200

    def test_gate_authorizer_claims_are_accepted(self, client, test_admin_user):
        """The staging gate's shape resolves the same way.

        Same subject, same row, different envelope. The two shapes are a
        deployment fact, so the application must not be able to tell them apart.
        """
        response = client.get(
            PROTECTED,
            headers={"x-amzn-request-context": _gate_context(test_admin_user["id"])},
        )
        assert response.status_code == 200

    def test_the_two_shapes_resolve_the_same_subject(self, client, test_admin_user):
        """Neither shape is privileged over the other."""
        native = client.get(
            PROTECTED,
            headers={"x-amzn-request-context": _native_context(test_admin_user["id"])},
        )
        gate = client.get(
            PROTECTED,
            headers={"x-amzn-request-context": _gate_context(test_admin_user["id"])},
        )
        assert native.status_code == gate.status_code == 200

    def test_a_stringified_exp_does_not_break_the_read(self, client, test_admin_user):
        """`exp` arrives as a string in both shapes and is coerced by the package.

        The gate stringifies on purpose so this is true; a reader that assumed an
        int would work in one environment and fail in the other.
        """
        response = client.get(
            PROTECTED,
            headers={
                "x-amzn-request-context": _gate_context(
                    test_admin_user["id"], exp="4102444800", roles='["admin"]'
                )
            },
        )
        assert response.status_code == 200


@pytest.mark.auth
class TestIdentityClaimsAreRefused:
    """Everything that is not a usable subject is the same 401."""

    def test_no_credential_at_all_is_refused(self, client):
        """Neither a bearer token nor a claims section.

        The case that must not have been widened by admitting the claims path.
        """
        response = client.get(PROTECTED)
        assert response.status_code in (401, 403)

    def test_an_empty_request_context_is_refused(self, client):
        """A header that is present but carries no authorizer section."""
        response = client.get(
            PROTECTED, headers={"x-amzn-request-context": json.dumps({})}
        )
        assert response.status_code in (401, 403)

    def test_an_unparseable_request_context_is_refused(self, client):
        """A header that is not JSON is refused rather than raising."""
        response = client.get(
            PROTECTED, headers={"x-amzn-request-context": "not json at all"}
        )
        assert response.status_code in (401, 403)

    def test_a_subject_that_is_not_an_integer_is_refused(self, client):
        """A `sub` this product could not have minted.

        Portfolio ids are integers from the `meta` counter, so a uuid `sub` is a
        token for somebody else's user. It answers 401 rather than raising the
        `ValueError` that would be a 500 on a request deserving a 401.
        """
        response = client.get(
            PROTECTED,
            headers={
                "x-amzn-request-context": _native_context(
                    "c7c0f5de-0000-4000-8000-000000000000"
                )
            },
        )
        assert response.status_code == 401

    def test_a_subject_naming_no_row_is_refused(self, client):
        """A well formed id that resolves to nothing."""
        response = client.get(
            PROTECTED, headers={"x-amzn-request-context": _native_context(99999999)}
        )
        assert response.status_code == 401

    def test_an_inactive_account_is_refused(self, client, test_admin_user):
        """A token minted before the account was disabled stops working now.

        The account checks are applied to the claims path rather than only at the
        identity login, and this is why: the two are independent, and a token
        already minted must not keep working for the rest of its lifetime.
        """
        from app.db import entities

        entities.users.update(test_admin_user["id"], {"is_active": False})
        response = client.get(
            PROTECTED,
            headers={"x-amzn-request-context": _native_context(test_admin_user["id"])},
        )
        assert response.status_code == 401

    def test_a_non_admin_account_is_refused(self, client, test_admin_user):
        """Being a user is not being an administrator."""
        from app.db import entities

        entities.users.update(test_admin_user["id"], {"is_admin": False})
        response = client.get(
            PROTECTED,
            headers={"x-amzn-request-context": _native_context(test_admin_user["id"])},
        )
        assert response.status_code == 401


@pytest.mark.auth
class TestTheLegacyPathIsUnchanged:
    """The HS256 token resolves exactly as it did, and still wins."""

    def test_a_legacy_token_still_works(self, client, admin_auth_headers):
        """The path every request takes in bearer mode today."""
        assert client.get(PROTECTED, headers=admin_auth_headers).status_code == 200

    def test_a_legacy_token_works_with_no_request_context(
        self, client, admin_auth_headers
    ):
        """No claims section is needed for the legacy path to resolve.

        The two credentials are independent: this is what says the claims read is
        a fallback rather than a new requirement.
        """
        assert "x-amzn-request-context" not in admin_auth_headers
        assert client.get(PROTECTED, headers=admin_auth_headers).status_code == 200

    def test_a_bad_legacy_token_is_still_refused(self, client):
        """A forged or malformed bearer token is the same 401 it always was.

        It must not fall through to the claims path and become something else:
        there are no claims on this request, so the answer is unchanged.
        """
        response = client.get(
            PROTECTED, headers={"Authorization": "Bearer not-a-real-token"}
        )
        assert response.status_code == 401

    def test_a_bad_legacy_token_does_not_shadow_valid_claims(
        self, client, test_admin_user
    ):
        """An unusable bearer token alongside verified claims resolves the claims.

        The legacy path is tried first and fails; the claims path is what then
        answers. This is the order the resolver documents, asserted rather than
        assumed.
        """
        response = client.get(
            PROTECTED,
            headers={
                "Authorization": "Bearer not-a-real-token",
                "x-amzn-request-context": _native_context(test_admin_user["id"]),
            },
        )
        assert response.status_code == 200


@pytest.mark.auth
class TestThePublicSurfaceIsUntouched:
    """Admitting the claims path opened nothing that was closed."""

    def test_a_public_read_still_serves_anonymously(self, client):
        """The site itself is unchanged for a signed out visitor."""
        assert client.get("/api/v1/posts").status_code == 200

    def test_a_public_read_ignores_a_claims_section(self, client, test_admin_user):
        """A public route does not change behaviour because claims are present."""
        response = client.get(
            "/api/v1/posts",
            headers={"x-amzn-request-context": _native_context(test_admin_user["id"])},
        )
        assert response.status_code == 200
