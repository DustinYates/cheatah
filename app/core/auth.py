"""JWT authentication utilities."""

from datetime import datetime, timedelta
from typing import Any

from jose import JWTError, jwt

from app.settings import settings

# Validate JWT secret key at startup
_DEFAULT_SECRET = "dev-secret-key-change-in-production"

if settings.environment == "production" and settings.jwt_secret_key == _DEFAULT_SECRET:
    raise RuntimeError(
        "SECURITY ERROR: JWT_SECRET_KEY environment variable must be set in production. "
        "Cannot use default secret key."
    )


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token.

    Args:
        data: Data to encode in the token
        expires_delta: Optional expiration time delta

    Returns:
        Encoded JWT token
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.jwt_access_token_expire_minutes
        )
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )
    return encoded_jwt


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decode and verify a JWT access token.

    Args:
        token: JWT token to decode

    Returns:
        Decoded token payload or None if invalid
    """
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        return payload
    except JWTError:
        return None

