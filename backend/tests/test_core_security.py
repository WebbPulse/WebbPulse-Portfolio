"""
Unit tests for the core security module
"""

from datetime import timedelta

import pytest

from app.config import settings
from app.core.security import (
    create_access_token,
    get_password_hash,
    verify_password,
    verify_token,
)


class TestPasswordSecurity:
    """Test class for password security functions"""

    @pytest.mark.unit
    def test_password_hashing(self):
        """Test password hashing functionality"""
        password = "testpassword123"
        hashed = get_password_hash(password)

        assert hashed != password

        assert hashed.startswith("$2b$")

        assert verify_password(password, hashed)
        assert not verify_password("wrongpassword", hashed)

    @pytest.mark.unit
    def test_password_hash_uniqueness(self):
        """Test that password hashes are unique for same password"""
        password = "samepassword"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)

        assert hash1 != hash2

        assert verify_password(password, hash1)
        assert verify_password(password, hash2)

    @pytest.mark.unit
    def test_password_verification_edge_cases(self):
        """Test password verification with edge cases"""
        password = "testpassword"
        hashed = get_password_hash(password)

        assert not verify_password("", hashed)

        with pytest.raises(TypeError):
            verify_password(None, hashed)

        long_password = "a" * 1000
        long_hashed = get_password_hash(long_password)
        assert verify_password(long_password, long_hashed)

    @pytest.mark.unit
    def test_password_special_characters(self):
        """Test password hashing with special characters"""
        special_password = "p@ssw0rd!@#$%^&*()_+-=[]{}|;':\",./<>?"
        hashed = get_password_hash(special_password)

        assert verify_password(special_password, hashed)
        assert not verify_password("p@ssw0rd!@#$%^&*()_+-=[]{}|;':\",./<>", hashed)

    @pytest.mark.unit
    def test_password_unicode_characters(self):
        """Test password hashing with unicode characters"""
        unicode_password = "pässwörd测试🔐"
        hashed = get_password_hash(unicode_password)

        assert verify_password(unicode_password, hashed)
        assert not verify_password("pässwörd测试", hashed)


class TestTokenSecurity:
    """Test class for JWT token functions"""

    @pytest.mark.unit
    def test_create_access_token(self):
        """Test access token creation"""
        data = {"sub": "testuser"}
        token = create_access_token(data=data)

        assert isinstance(token, str)
        assert len(token) > 0

        parts = token.split(".")
        assert len(parts) == 3

    @pytest.mark.unit
    def test_create_access_token_with_expires_delta(self):
        """Test access token creation with custom expiration"""
        data = {"sub": "testuser"}
        expires_delta = timedelta(minutes=30)
        token = create_access_token(data=data, expires_delta=expires_delta)

        assert isinstance(token, str)
        assert len(token) > 0

    @pytest.mark.unit
    def test_verify_token_success(self):
        """Test successful token verification"""
        data = {"sub": "testuser"}
        token = create_access_token(data=data)

        username = verify_token(token)
        assert username == "testuser"

    @pytest.mark.unit
    def test_verify_token_invalid_format(self):
        """Test token verification with invalid format"""
        invalid_token = "invalid.token.format"
        username = verify_token(invalid_token)
        assert username is None

    @pytest.mark.unit
    def test_verify_token_missing_subject(self):
        """Test token verification with missing subject"""
        data = {"other_field": "value"}
        token = create_access_token(data=data)

        username = verify_token(token)
        assert username is None

    @pytest.mark.unit
    def test_verify_token_expired(self):
        """Test token verification with expired token"""
        data = {"sub": "testuser"}
        expires_delta = timedelta(minutes=-10)
        token = create_access_token(data=data, expires_delta=expires_delta)

        username = verify_token(token)
        assert username is None

    @pytest.mark.unit
    def test_verify_token_wrong_algorithm(self):
        """Test token verification with wrong algorithm"""
        invalid_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0dXNlciJ9.invalid_signature"
        username = verify_token(invalid_token)
        assert username is None

    @pytest.mark.unit
    def test_token_with_additional_data(self):
        """Test token creation and verification with additional data"""
        data = {
            "sub": "testuser",
            "email": "test@example.com",
            "is_admin": True,
            "user_id": 123,
        }
        token = create_access_token(data=data)

        username = verify_token(token)
        assert username == "testuser"

    @pytest.mark.unit
    def test_token_expiration_time(self):
        """Test that tokens have correct expiration time"""
        data = {"sub": "testuser"}
        token = create_access_token(data=data)

        import jwt

        decoded = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

        assert "exp" in decoded

        assert decoded["exp"] > 0

    @pytest.mark.unit
    def test_token_round_trip(self):
        """Test complete token creation and verification round trip"""
        original_data = {"sub": "testuser", "email": "test@example.com"}
        token = create_access_token(data=original_data)

        username = verify_token(token)
        assert username == original_data["sub"]

        new_token = create_access_token(data=original_data)
        new_username = verify_token(new_token)
        assert new_username == original_data["sub"]

        assert verify_token(token) == original_data["sub"]
        assert verify_token(new_token) == original_data["sub"]


class TestSecurityConstants:
    """Test class for security constants and configuration"""

    @pytest.mark.unit
    def test_algorithm_constant(self):
        """Test that ALGORITHM constant is set correctly"""
        assert settings.ALGORITHM == "HS256"

    @pytest.mark.unit
    def test_access_token_expire_minutes(self):
        """Test that ACCESS_TOKEN_EXPIRE_MINUTES is set"""
        assert isinstance(settings.ACCESS_TOKEN_EXPIRE_MINUTES, int)
        assert settings.ACCESS_TOKEN_EXPIRE_MINUTES > 0

    @pytest.mark.unit
    def test_secret_key_exists(self):
        """Test that SECRET_KEY is configured"""
        assert settings.SECRET_KEY is not None
        assert len(settings.SECRET_KEY) > 0


class TestSecurityIntegration:
    """Test class for security integration scenarios"""

    @pytest.mark.integration
    def test_password_and_token_integration(self):
        """Test integration between password hashing and token creation"""
        username = "testuser"
        password = "securepassword123"

        hashed_password = get_password_hash(password)

        assert verify_password(password, hashed_password)

        token_data = {"sub": username}
        token = create_access_token(data=token_data)

        extracted_username = verify_token(token)
        assert extracted_username == username

    @pytest.mark.integration
    def test_multiple_users_security(self):
        """Test security with multiple users"""
        users = [
            {"username": "user1", "password": "password1"},
            {"username": "user2", "password": "password2"},
            {"username": "admin", "password": "adminpass"},
        ]

        for user in users:
            hashed = get_password_hash(user["password"])

            assert verify_password(user["password"], hashed)
            assert not verify_password("wrongpassword", hashed)

            token = create_access_token(data={"sub": user["username"]})
            extracted_username = verify_token(token)
            assert extracted_username == user["username"]

    @pytest.mark.integration
    def test_security_performance(self):
        """Test security functions performance with multiple operations"""
        import time

        start_time = time.time()
        for i in range(10):
            password = f"password{i}"
            hashed = get_password_hash(password)
            assert verify_password(password, hashed)

        hashing_time = time.time() - start_time
        assert hashing_time < 10

        start_time = time.time()
        for i in range(100):
            token = create_access_token(data={"sub": f"user{i}"})
            username = verify_token(token)
            assert username == f"user{i}"

        token_time = time.time() - start_time
        assert token_time < 1
