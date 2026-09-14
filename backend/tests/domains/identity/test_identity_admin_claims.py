"""`get_current_user` in dual mode: the legacy HS256 token and the gateway's claims."""

import json

import pytest

PROTECTED = "/api/v1/posts/admin"


def _native_context(sub, **claims):
    """The production shape: a flat string map under `authorizer.jwt.claims`."""
    return json.dumps({"authorizer": {"jwt": {"claims": {"sub": str(sub), **claims}}}})


def _gate_context(sub, **claims):
    """The staging shape: one JSON string under `authorizer.lambda["jwt.claims"]`."""
    payload = json.dumps({"sub": str(sub), **claims})
    return json.dumps({"authorizer": {"lambda": {"jwt.claims": payload}}})


@pytest.mark.auth
class TestIdentityClaimsAreAccepted:
    """A verified subject in the request context resolves to the admin row."""

    def test_native_authorizer_claims_are_accepted(self, client, test_admin_user):
        """The production shape resolves, with no bearer token at all."""
        response = client.get(
            PROTECTED,
            headers={"x-amzn-request-context": _native_context(test_admin_user["id"])},
        )
        assert response.status_code == 200

    def test_gate_authorizer_claims_are_accepted(self, client, test_admin_user):
        """The staging gate's shape resolves the same way."""
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
        """`exp` arrives as a string in both shapes and is coerced by the package."""
        response = client.get(
            PROTECTED,
            headers={
                "x-amzn-request-context": _gate_context(test_admin_user["id"], exp="4102444800", roles='["admin"]')
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
        response = client.get(PROTECTED, headers={"x-amzn-request-context": json.dumps({})})
        assert response.status_code in (401, 403)

    def test_an_unparseable_request_context_is_refused(self, client):
        """A header that is not JSON is refused rather than raising."""
        response = client.get(PROTECTED, headers={"x-amzn-request-context": "not json at all"})
        assert response.status_code in (401, 403)

    def test_a_subject_that_is_not_an_integer_is_refused(self, client):
        """A `sub` this product could not have minted."""
        response = client.get(
            PROTECTED,
            headers={"x-amzn-request-context": _native_context("c7c0f5de-0000-4000-8000-000000000000")},
        )
        assert response.status_code == 401

    def test_a_subject_naming_no_row_is_refused(self, client):
        """A well formed id that resolves to nothing."""
        response = client.get(PROTECTED, headers={"x-amzn-request-context": _native_context(99999999)})
        assert response.status_code == 401

    def test_an_inactive_account_is_refused(self, client, test_admin_user):
        """A token minted before the account was disabled stops working now."""
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

    def test_a_legacy_token_works_with_no_request_context(self, client, admin_auth_headers):
        """No claims section is needed for the legacy path to resolve."""
        assert "x-amzn-request-context" not in admin_auth_headers
        assert client.get(PROTECTED, headers=admin_auth_headers).status_code == 200

    def test_a_bad_legacy_token_is_still_refused(self, client):
        """A forged or malformed bearer token is the same 401 it always was."""
        response = client.get(PROTECTED, headers={"Authorization": "Bearer not-a-real-token"})
        assert response.status_code == 401

    def test_a_bad_legacy_token_does_not_shadow_valid_claims(self, client, test_admin_user):
        """An unusable bearer token alongside verified claims resolves the claims."""
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
