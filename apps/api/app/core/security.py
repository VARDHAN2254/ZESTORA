"""Core security module for password hashing and JWT token handling.

Implements:
- Argon2id password hashing and constant-time verification.
- Signed, short-lived JWT access tokens using HS256 with strict claim verification.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import settings

# Argon2id password hasher configured with OWASP-recommended parameters
password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    type=Type.ID,
)

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


class SecurityError(Exception):
    """Base exception for authentication and token security failures."""


class TokenError(SecurityError):
    """Base exception for JWT processing failures."""


class TokenExpiredError(TokenError):
    """Raised when a JWT access token has expired."""


class InvalidTokenError(TokenError):
    """Raised when a JWT access token is malformed, has an invalid signature, or is missing claims."""


def validate_password_length(password: str) -> None:
    """Validate password length and string type.

    Raises:
        ValueError: If password is not a string or length is outside [8, 128].
    """
    if not isinstance(password, str):
        raise TypeError("Password must be a string.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
        )
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"Password must not exceed {MAX_PASSWORD_LENGTH} characters.")


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id.

    Args:
        password: The plaintext password string to hash.

    Returns:
        The Argon2id hash string including salt and algorithm parameters.

    Raises:
        TypeError: If password is not a string.
        ValueError: If password length is invalid.
    """
    validate_password_length(password)
    return password_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Safely verify a plaintext password against an Argon2id hash.

    Handles invalid password hashes, mismatched formats, and corrupted input
    gracefully without leaking internal exception details.

    Args:
        plain_password: The plaintext candidate password.
        hashed_password: The stored Argon2id hash string.

    Returns:
        True if the password matches, False otherwise.
    """
    if not isinstance(plain_password, str) or not isinstance(hashed_password, str):
        return False
    if not plain_password or not hashed_password:
        return False

    try:
        return password_hasher.verify(hashed_password, plain_password)
    except VerifyMismatchError:
        return False
    except (InvalidHashError, VerificationError):
        return False
    except Exception:  # noqa: BLE001
        return False


def create_access_token(
    subject: str | uuid.UUID,
    extra_claims: dict[str, Any] | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Generate a signed JWT access token.

    Args:
        subject: The unique identifier for the user (sub claim).
        extra_claims: Optional supplementary claims to include in the token payload.
        expires_delta: Optional custom token expiration duration.

    Returns:
        Encoded and signed JWT string.
    """
    settings.validate_production_jwt_secret()

    now = datetime.now(UTC)
    if expires_delta is not None:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }

    if extra_claims:
        # Prevent overriding critical standard claims
        sanitized_extra = {
            k: v for k, v in extra_claims.items() if k not in ("sub", "iat", "exp")
        }
        payload.update(sanitized_extra)

    return jwt.encode(
        payload,
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and strictly validate a signed JWT access token.

    Enforces:
    - Algorithm constraint to prevent algorithm substitution attacks (none, RS256, etc.).
    - Valid signature against configured JWT_SECRET.
    - Required standard claims ('sub', 'iat', 'exp').
    - Active (non-expired) timestamp.

    Args:
        token: The encoded JWT token string.

    Returns:
        The decoded claims dictionary.

    Raises:
        TokenExpiredError: If the token expiration timestamp is in the past.
        InvalidTokenError: If the token is invalid, malformed, or missing required claims.
    """
    if not token or not isinstance(token, str):
        raise InvalidTokenError("Token must be a non-empty string.")

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            options={
                "require": ["exp", "iat", "sub"],
                "verify_exp": True,
                "verify_iat": True,
                "verify_signature": True,
            },
        )
        return payload
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError("Access token has expired.") from exc
    except (jwt.InvalidTokenError, jwt.DecodeError) as exc:
        raise InvalidTokenError(f"Invalid access token: {exc}") from exc
