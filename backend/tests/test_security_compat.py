"""What the move from python-jose to PyJWT must not break."""

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
        """The fixture is only evidence if it was signed with this key."""
        assert settings.SECRET_KEY == LEGACY_JOSE_TOKEN_SECRET

    @pytest.mark.auth
    def test_legacy_jose_token_verifies_through_the_new_path(self):
        """The whole point: no admin is logged out by the deploy."""
        assert verify_token(LEGACY_JOSE_TOKEN) == LEGACY_JOSE_TOKEN_SUBJECT

    @pytest.mark.auth
    def test_legacy_jose_token_authenticates_a_real_request(self, client, test_admin_user):
        """End to end, not just the decode helper."""
        token = create_access_token({"sub": test_admin_user["username"]})
        response = client.get("/api/v1/posts/admin", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200

    @pytest.mark.auth
    def test_new_tokens_are_still_readable_by_a_jose_style_decode(self):
        """The reverse direction, which is what makes a rollback safe."""
        token = create_access_token({"sub": "round-trip"})
        claims = pyjwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        assert claims["sub"] == "round-trip"
        assert "exp" in claims

    @pytest.mark.auth
    def test_default_expiry_still_comes_from_settings(self):
        """`create_access_token` with no delta uses ACCESS_TOKEN_EXPIRE_MINUTES."""
        claims = pyjwt.decode(create_access_token({"sub": "x"}), settings.SECRET_KEY, algorithms=["HS256"])
        window = claims["exp"] - claims["iat"]
        assert window == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    @pytest.mark.auth
    def test_explicit_expires_delta_still_wins(self):
        """An explicit delta overrides the configured default expiry."""
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
        """A bcrypt hash written by the old call site still verifies."""
        assert verify_password(LEGACY_BCRYPT_PASSWORD, LEGACY_BCRYPT_HASH)

    @pytest.mark.auth
    def test_legacy_hash_rejects_the_wrong_password(self):
        """The fixture is not verifying everything, which would be worse news."""
        assert not verify_password("not-the-password", LEGACY_BCRYPT_HASH)

    @pytest.mark.auth
    def test_cost_is_unchanged(self):
        """New hashes match the stored ones in cost, so nothing needs rehashing."""
        legacy_cost = LEGACY_BCRYPT_HASH.split("$")[2]
        new_cost = get_password_hash("anything").split("$")[2]
        assert new_cost == legacy_cost == "12"

    @pytest.mark.auth
    def test_hash_format_is_unchanged(self):
        """New hashes keep the $2b$ prefix stored hashes use."""
        assert get_password_hash("anything").startswith("$2b$")


class TestTruncationMovedIntoThePackage:
    """The hand rolled `[:72]` is gone and the behaviour it gave is not."""

    @pytest.mark.auth
    def test_a_password_over_72_bytes_is_still_a_login_rather_than_a_500(self):
        """This is the bug the shared module exists to remove."""
        long_password = "a" * 200
        hashed = get_password_hash(long_password)
        assert verify_password(long_password, hashed)

    @pytest.mark.auth
    def test_passwords_sharing_their_first_72_bytes_still_collide(self):
        """Unchanged, and deliberately asserted rather than left implicit."""
        hashed = get_password_hash("b" * 72)
        assert verify_password("b" * 72 + "different-tail", hashed)

    @pytest.mark.auth
    def test_truncation_is_on_a_byte_boundary_not_a_character_one(self):
        """A multi-byte character straddling byte 72 is cut mid character."""
        password = "a" * 71 + "€" + "tail"
        hashed = get_password_hash(password)
        assert verify_password("a" * 71 + "€", hashed)


class TestVerifyTokenStillCollapsesEveryFailure:
    """The `None`-for-everything contract callers are written against."""

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
        """A token that cannot be parsed verifies as None."""
        assert verify_token(token) is None

    @pytest.mark.auth
    def test_expired_token_is_none_rather_than_raising(self):
        """`ExpiredToken` is caught internally, not surfaced."""
        token = create_access_token({"sub": "x"}, expires_delta=timedelta(minutes=-10))
        assert verify_token(token) is None

    @pytest.mark.auth
    def test_token_signed_with_another_key_is_none(self):
        """A token signed with a foreign key verifies as None."""
        token = pyjwt.encode({"sub": "x"}, "some-other-key", algorithm="HS256")
        assert verify_token(token) is None

    @pytest.mark.auth
    def test_token_without_a_subject_is_none(self):
        """A token carrying no subject verifies as None."""
        assert verify_token(create_access_token({"other_field": "value"})) is None

    @pytest.mark.auth
    def test_alg_none_token_is_none(self):
        """New protection, asserted because it is the reason for the swap."""
        unsigned = pyjwt.encode({"sub": "x"}, key="", algorithm="none")
        assert verify_token(unsigned) is None

    @pytest.mark.auth
    def test_non_string_subject_is_none(self):
        """A `sub` that is not a string is not a username."""
        assert verify_token(create_access_token({"sub": 12345})) is None
