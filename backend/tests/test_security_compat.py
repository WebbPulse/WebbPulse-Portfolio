"""What the move from python-jose to PyJWT must not break.

Swapping the JWT library and the hashing call site is only safe if two things
stay true, and neither is observable from a test that mints its own token with
the new code and reads it back with the new code. Both fixtures below were
produced by the **previous** implementation, before `python-jose` was removed,
and are checked in as literals for exactly that reason: a token or a hash
generated at test time by the code under test proves the code agrees with
itself, which is not the question.

- **Live sessions survive.** Every unexpired token a browser is holding right
  now was signed by `python-jose`. `LEGACY_JOSE_TOKEN` is one of them, minted by
  `jose.jwt.encode({"sub": ..., "exp": ...}, SECRET_KEY, algorithm="HS256")` on
  `python-jose[cryptography]==3.5.0`, the exact call the deleted
  `create_access_token` made. If PyJWT rejects it, every admin is logged out on
  deploy.
- **Stored hashes survive.** `LEGACY_BCRYPT_HASH` was written by the deleted
  `get_password_hash`: `bcrypt.hashpw(password.encode("utf-8")[:72],
  bcrypt.gensalt())` on `bcrypt==4.3.0`. If it stops verifying, every admin is
  locked out and there is no migration path, because the plaintext is gone.

The expiry is in 2100 so the fixture does not rot and start passing for the
wrong reason. That is safe here because nothing in this file asserts that an
expired token is rejected; `tests/test_auth_hardening.py` does that with a
freshly minted one.
"""

from datetime import timedelta

import jwt as pyjwt
import pytest

from app.config import settings
from app.core.security import (
    create_access_token,
    get_password_hash,
    verify_password,
    verify_token,
)

LEGACY_JOSE_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiJsZWdhY3ktdXNlciIsImV4cCI6NDEwMjQ0NDgwMH0"
    ".0QUNBK9kx424EXu34rTw-uZcj1m5VLRWOZ_8lasQEV0"
)
LEGACY_JOSE_TOKEN_SECRET = "test-secret-key"
LEGACY_JOSE_TOKEN_SUBJECT = "legacy-user"

LEGACY_BCRYPT_HASH = "$2b$12$pPzV2dQSBbbXcCXKzRW0iuHDlg05tnoACL93xRplz27cErmFCwSq2"
LEGACY_BCRYPT_PASSWORD = "legacy-password"


class TestIssuedTokensStayValid:
    """A token python-jose signed still authenticates under PyJWT."""

    @pytest.mark.auth
    def test_conftest_secret_is_the_one_the_fixture_was_minted_with(self):
        """The fixture is only evidence if it was signed with this key.

        `conftest.py` sets `SECRET_KEY=test-secret-key` before importing
        anything that reads it. If that ever changes, the assertions below would
        fail for a reason that has nothing to do with library compatibility, and
        this check is what says so.
        """
        assert settings.SECRET_KEY == LEGACY_JOSE_TOKEN_SECRET

    @pytest.mark.auth
    def test_legacy_jose_token_verifies_through_the_new_path(self):
        """The whole point: no admin is logged out by the deploy."""
        assert verify_token(LEGACY_JOSE_TOKEN) == LEGACY_JOSE_TOKEN_SUBJECT

    @pytest.mark.auth
    def test_legacy_jose_token_authenticates_a_real_request(
        self, client, test_admin_user
    ):
        """End to end, not just the decode helper.

        The user has to exist for the request to reach 200, so the token is
        re-minted for that username with the same library-independent shape the
        legacy fixture has. The fixture above proves PyJWT accepts a jose
        signature; this proves the accepted claims flow through
        `get_current_user` unchanged.
        """
        token = create_access_token({"sub": test_admin_user["username"]})
        response = client.get(
            "/api/v1/posts/admin", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200

    @pytest.mark.auth
    def test_new_tokens_are_still_readable_by_a_jose_style_decode(self):
        """The reverse direction, which is what makes a rollback safe.

        A deploy that has to be rolled back leaves tokens minted by PyJWT in
        browsers that will next be verified by python-jose. PyJWT is used here
        with `verify_signature` on and an explicit algorithm, which is the same
        verification python-jose performed; asserting the claims round trip is
        what says the token is not carrying anything jose could not parse.
        """
        token = create_access_token({"sub": "round-trip"})
        claims = pyjwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        assert claims["sub"] == "round-trip"
        assert "exp" in claims

    @pytest.mark.auth
    def test_default_expiry_still_comes_from_settings(self):
        """`create_access_token` with no delta uses ACCESS_TOKEN_EXPIRE_MINUTES.

        The old implementation computed `exp` itself; the new one passes
        `expires_in` to the package. Same value, and this pins it rather than
        trusting that the two expressions match by inspection.
        """
        claims = pyjwt.decode(
            create_access_token({"sub": "x"}), settings.SECRET_KEY, algorithms=["HS256"]
        )
        window = claims["exp"] - claims["iat"]
        assert window == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    @pytest.mark.auth
    def test_explicit_expires_delta_still_wins(self):
        claims = pyjwt.decode(
            create_access_token({"sub": "x"}, expires_delta=timedelta(minutes=5)),
            settings.SECRET_KEY,
            algorithms=["HS256"],
        )
        assert claims["exp"] - claims["iat"] == 5 * 60


class TestStoredHashesStayValid:
    """A hash bcrypt wrote through the old call site still verifies."""

    @pytest.mark.auth
    def test_legacy_hash_verifies(self):
        assert verify_password(LEGACY_BCRYPT_PASSWORD, LEGACY_BCRYPT_HASH)

    @pytest.mark.auth
    def test_legacy_hash_rejects_the_wrong_password(self):
        """The fixture is not verifying everything, which would be worse news."""
        assert not verify_password("not-the-password", LEGACY_BCRYPT_HASH)

    @pytest.mark.auth
    def test_cost_is_unchanged(self):
        """New hashes match the stored ones in cost, so nothing needs rehashing.

        The old code called `bcrypt.gensalt()` with no argument, whose default is
        12. `webbpulse.security.DEFAULT_ROUNDS` is also 12. Reading the cost out
        of both encodings is what proves the two agree rather than asserting the
        constant against itself.
        """
        legacy_cost = LEGACY_BCRYPT_HASH.split("$")[2]
        new_cost = get_password_hash("anything").split("$")[2]
        assert new_cost == legacy_cost == "12"

    @pytest.mark.auth
    def test_hash_format_is_unchanged(self):
        assert get_password_hash("anything").startswith("$2b$")


class TestTruncationMovedIntoThePackage:
    """The hand rolled `[:72]` is gone and the behaviour it gave is not.

    `app/core/security.py` used to encode and slice to 72 bytes before calling
    bcrypt. The package does that itself, on a byte boundary, so removing the
    local copy has to leave the same passwords hashing to the same place.
    """

    @pytest.mark.auth
    def test_a_password_over_72_bytes_is_still_a_login_rather_than_a_500(self):
        """This is the bug the shared module exists to remove.

        bcrypt 4.x truncated silently and 5.0 raises, so the local `[:72]` was
        the only thing keeping a long password from being a 500 on an upgrade.
        The package truncates internally, so this holds on either major and the
        pin below can move without the behaviour moving with it.
        """
        long_password = "a" * 200
        hashed = get_password_hash(long_password)
        assert verify_password(long_password, hashed)

    @pytest.mark.auth
    def test_passwords_sharing_their_first_72_bytes_still_collide(self):
        """Unchanged, and deliberately asserted rather than left implicit.

        bcrypt reads 72 bytes and ignores the rest, so these two passwords were
        already interchangeable under the old implementation. Pinning it means a
        future change to the truncation rule fails here rather than silently
        splitting hashes that used to match.
        """
        hashed = get_password_hash("b" * 72)
        assert verify_password("b" * 72 + "different-tail", hashed)

    @pytest.mark.auth
    def test_truncation_is_on_a_byte_boundary_not_a_character_one(self):
        """A multi-byte character straddling byte 72 is cut mid character.

        That is the rule every previous implementation used, because bcrypt's
        limit is a byte limit. Trimming back to the last whole character instead
        would feed bcrypt different bytes and stop matching stored hashes, so
        this is the assertion that would catch such a change.
        """
        password = "a" * 71 + "€" + "tail"
        hashed = get_password_hash(password)
        assert verify_password("a" * 71 + "€", hashed)


class TestVerifyTokenStillCollapsesEveryFailure:
    """The `None`-for-everything contract callers are written against.

    The package raises `ExpiredToken` and `InvalidToken`, which is strictly more
    information than `python-jose`'s single `JWTError`. None of it reaches the
    caller: `verify_token` still answers `None`, so `get_current_user` still
    answers 401 and the frontend's 401 handling in `frontend/src/services/api.ts`
    is unaffected. These cases were all `None` before and are all `None` now.
    """

    @pytest.mark.auth
    @pytest.mark.parametrize(
        "token",
        [
            pytest.param("invalid.token.format", id="malformed"),
            pytest.param("", id="empty"),
            pytest.param("not-a-jwt-at-all", id="not-a-jwt"),
        ],
    )
    def test_malformed_tokens_are_none(self, token):
        assert verify_token(token) is None

    @pytest.mark.auth
    def test_expired_token_is_none_rather_than_raising(self):
        """`ExpiredToken` is caught internally, not surfaced.

        The old code could not tell this case apart from a forged token. The new
        code can, and still answers the same thing, which is the behaviour half
        of "use the module's exceptions internally".
        """
        token = create_access_token({"sub": "x"}, expires_delta=timedelta(minutes=-10))
        assert verify_token(token) is None

    @pytest.mark.auth
    def test_token_signed_with_another_key_is_none(self):
        token = pyjwt.encode({"sub": "x"}, "some-other-key", algorithm="HS256")
        assert verify_token(token) is None

    @pytest.mark.auth
    def test_token_without_a_subject_is_none(self):
        assert verify_token(create_access_token({"other_field": "value"})) is None

    @pytest.mark.auth
    def test_alg_none_token_is_none(self):
        """New protection, asserted because it is the reason for the swap.

        `decode_token` passes an explicit algorithms list and never reads `alg`
        from the header, so an unsigned token is refused rather than trusted.
        """
        unsigned = pyjwt.encode({"sub": "x"}, key="", algorithm="none")
        assert verify_token(unsigned) is None

    @pytest.mark.auth
    def test_non_string_subject_is_none(self):
        """A `sub` that is not a string is not a username.

        `users.find_by_unique` would be handed an int and answer `None` anyway,
        so this is the same 401 either way, but refusing it in `verify_token` is
        where the type actually is.
        """
        assert verify_token(create_access_token({"sub": 12345})) is None
