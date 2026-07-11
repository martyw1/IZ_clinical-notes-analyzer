from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

ALGORITHM = "HS256"
MIN_PASSWORD_LENGTH = 12

pwd_context = CryptContext(schemes=["bcrypt", "pbkdf2_sha256"], deprecated="auto")


@dataclass(frozen=True, slots=True)
class AccessTokenSubject:
    username: str
    password_epoch: str


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def password_epoch(password_changed_at: datetime | None) -> str:
    if password_changed_at is None:
        return ""
    if password_changed_at.tzinfo is None:
        return password_changed_at.replace(tzinfo=timezone.utc).isoformat()
    return password_changed_at.astimezone(timezone.utc).isoformat()


def create_access_token(subject: str, password_changed_at: datetime | None) -> str:
    issued_at = datetime.now(timezone.utc)
    expire = issued_at + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": subject,
        "pce": password_epoch(password_changed_at),
        "iat": issued_at,
        "exp": expire,
        "typ": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> AccessTokenSubject | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None
    subject = payload.get("sub") if isinstance(payload, dict) else None
    token_epoch = payload.get("pce") if isinstance(payload, dict) else None
    if not isinstance(subject, str) or not subject or not isinstance(token_epoch, str):
        return None
    return AccessTokenSubject(username=subject, password_epoch=token_epoch)


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
