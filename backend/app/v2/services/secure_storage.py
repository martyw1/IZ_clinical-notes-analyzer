from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

from app.core.config import settings

ENCRYPTION_MAGIC = b"IZCNA1:"
SECRET_TEXT_PREFIX = "enc:v1:"


def ensure_private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        return


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.effective_data_encryption_secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_bytes(raw: bytes) -> bytes:
    return ENCRYPTION_MAGIC + _fernet().encrypt(raw)


def decrypt_bytes(payload: bytes) -> bytes:
    if not payload.startswith(ENCRYPTION_MAGIC):
        raise HTTPException(status_code=500, detail="Stored payload is not encrypted")
    encrypted = payload[len(ENCRYPTION_MAGIC) :]
    try:
        return _fernet().decrypt(encrypted)
    except InvalidToken as exc:
        raise HTTPException(status_code=500, detail="Stored payload could not be decrypted") from exc


def encrypt_text_secret(value: str) -> str:
    if not value:
        return ""
    encrypted = encrypt_bytes(value.encode("utf-8"))
    return SECRET_TEXT_PREFIX + base64.urlsafe_b64encode(encrypted).decode("ascii")


def decrypt_text_secret(value: str) -> str:
    if not value:
        return ""
    if not value.startswith(SECRET_TEXT_PREFIX):
        return value
    encoded = value[len(SECRET_TEXT_PREFIX) :]
    try:
        encrypted = base64.urlsafe_b64decode(encoded.encode("ascii"))
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Stored application secret is not valid encrypted text") from exc
    return decrypt_bytes(encrypted).decode("utf-8")


def text_secret_is_encrypted(value: str) -> bool:
    return value.startswith(SECRET_TEXT_PREFIX)
