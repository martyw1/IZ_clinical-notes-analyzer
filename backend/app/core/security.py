from datetime import datetime, timedelta, timezone
from typing import Any

from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

# New passwords use bcrypt while existing pbkdf2 hashes continue to verify.
pwd_context = CryptContext(schemes=['bcrypt', 'pbkdf2_sha256'], deprecated='auto')
ALGORITHM = 'HS256'
MIN_PASSWORD_LENGTH = 12


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    issued_at = datetime.now(timezone.utc)
    to_encode: dict[str, Any] = {'sub': subject, 'iat': issued_at, 'exp': expire, 'typ': 'access'}
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def password_policy_error(password: str, *, username: str | None = None) -> str | None:
    """Return a user-safe password policy error, or None when accepted."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f'Password must be at least {MIN_PASSWORD_LENGTH} characters.'
    if username and password.strip().lower() == username.strip().lower():
        return 'Password cannot be the same as the username.'
    if password.strip().lower() in {'password', 'password123', 'admin', 'change-me'}:
        return 'Password is too common.'
    if not any(character.isalpha() for character in password) or not any(character.isdigit() for character in password):
        return 'Password must include at least one letter and one number.'
    return None
