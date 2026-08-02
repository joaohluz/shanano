"""Unit tests for core.security (bcrypt hashing + JWT) and core.user_service."""
import pytest
import jwt

from core.security import (
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from core.user_service import UsernameTakenError


class TestPasswordHashing:
    def test_hash_and_verify_roundtrip(self):
        hashed = hash_password("super-secret")
        assert hashed != "super-secret"
        assert verify_password("super-secret", hashed) is True

    def test_wrong_password_rejected(self):
        hashed = hash_password("super-secret")
        assert verify_password("wrong-password", hashed) is False

    def test_hashes_are_salted(self):
        # Same password should never produce the same hash twice.
        assert hash_password("same-pass") != hash_password("same-pass")

    def test_verify_with_malformed_hash_returns_false(self):
        assert verify_password("anything", "not-a-bcrypt-hash") is False


class TestJWT:
    def test_create_and_decode_roundtrip(self):
        token = create_token(subject=7, username="alice", role="user")
        payload = decode_token(token)
        assert payload["sub"] == "7"
        assert payload["username"] == "alice"
        assert payload["role"] == "user"
        assert "exp" in payload
        assert "iat" in payload

    def test_decode_rejects_garbage(self):
        with pytest.raises(jwt.InvalidTokenError):
            decode_token("not.a.jwt")

    def test_decode_rejects_expired_token(self):
        token = create_token(
            subject=1, username="alice", role="user", expires_minutes=-1
        )
        with pytest.raises(jwt.ExpiredSignatureError):
            decode_token(token)

    def test_missing_secret_raises(self, monkeypatch):
        # Simulate an unset JWT_SECRET: token operations must fail fast.
        import core.security as security
        monkeypatch.setattr(security, "JWT_SECRET", "")
        with pytest.raises(RuntimeError, match="JWT_SECRET"):
            create_token(subject=1, username="alice", role="user")
        with pytest.raises(RuntimeError, match="JWT_SECRET"):
            decode_token("x.y.z")


class TestUsernameTakenError:
    def test_is_exception(self):
        assert issubclass(UsernameTakenError, Exception)
