from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

ALGORITHM = "HS256"
MIN_PASSWORD_LENGTH = 12

pwd_context = CryptContext(schemes=["bcrypt", "pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(subject: str) -> str:
    issued_at = datetime.now(timezone.utc)
    expire = issued_at + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "iat": issued_at, "exp": expire, "typ": "access"}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None
    subject = payload.get("sub") if isinstance(payload, dict) else None
    return subject if isinstance(subject, str) and subject else None


def password_policy_error(password: str, *, username: str | None = None) -> str | None:
    normalized = password.strip().lower()
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if username and normalized == username.strip().lower():
        return "Password cannot be the same as the username."
    if normalized in {"password", "password123", "admin", "change-me"}:
        return "Password is too common."
    if not any(character.isalpha() for character in password) or not any(character.isdigit() for character in password):
        return "Password must include at least one letter and one number."
    return None
