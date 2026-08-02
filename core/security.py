"""Password hashing (bcrypt) and JWT creation/decoding (HS256).

Security rules enforced here:
- Passwords are never stored or logged in plaintext (only bcrypt hashes).
- The JWT secret comes from the environment (config.JWT_SECRET); there is no
  hardcoded fallback, so token operations fail fast if it is missing.
"""

from datetime import datetime, timedelta, timezone

from typing import Any, Optional, Union

import bcrypt
import jwt

from config import JWT_ALGORITHM, JWT_EXPIRES_MINUTES, JWT_SECRET

# The 72-byte limit is a bcrypt-internal constraint.
_BCRYPT_MAX_BYTES = 72


def _jwt_secret() -> str:
    if not JWT_SECRET:
        raise RuntimeError("JWT_SECRET environment variable is not set")
    return JWT_SECRET


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt (returns the hash as a str)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    """Return True if password matches the stored bcrypt hash, False otherwise."""
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except ValueError:
        # Malformed hash: never raise to the caller, just report a mismatch.
        return False


def create_token(
    subject: Union[str, int],
    username: str,
    role: str,
    expires_minutes: Optional[int] = None,
) -> str:
    """Create a signed HS256 JWT for a user.

    Default expiry comes from config.JWT_EXPIRES_MINUTES. Passing a negative
    expires_minutes yields an already-expired token (used by tests).
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=expires_minutes or JWT_EXPIRES_MINUTES)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "username": username,
        "role": role,
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT, returning its payload.

    Raises jwt.InvalidTokenError (incl. ExpiredSignatureError) on any failure.
    """
    return jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALGORITHM])
