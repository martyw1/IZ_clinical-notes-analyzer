from __future__ import annotations

"""Encrypted local-file storage for clinical documents.

The app is intentionally local-first, so uploaded PHI lands on the user's
machine. This module keeps the storage contract small: callers hand it bytes,
and it writes an encrypted payload with private filesystem permissions where
the operating system supports them.
"""

import base64
import hashlib
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

from app.core.config import settings

ENCRYPTION_MAGIC = b'IZCNA1\n'
SECRET_TEXT_PREFIX = 'IZCNA1-TEXT:'
PRIVATE_DIR_MODE = 0o700
PRIVATE_FILE_MODE = 0o600


def ensure_private_directory(path: Path) -> None:
    """Create a directory that is private to the current user when possible."""
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, PRIVATE_DIR_MODE)
    except OSError:
        # Windows records ACLs differently; chmod is best-effort there.
        return


def _fernet() -> Fernet:
    """Build a stable Fernet key from the configured local encryption secret."""
    secret = settings.effective_data_encryption_secret.encode('utf-8')
    digest = hashlib.sha256(secret).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_bytes(raw: bytes) -> bytes:
    """Encrypt document bytes and prefix them with an app-specific marker."""
    return ENCRYPTION_MAGIC + _fernet().encrypt(raw)


def decrypt_bytes(payload: bytes) -> bytes:
    """Decrypt modern stored files while still reading legacy plaintext files."""
    if not payload.startswith(ENCRYPTION_MAGIC):
        return payload
    encrypted = payload[len(ENCRYPTION_MAGIC) :]
    try:
        return _fernet().decrypt(encrypted)
    except InvalidToken as exc:
        raise HTTPException(status_code=500, detail='Stored clinical note could not be decrypted with the configured data key') from exc


def write_secure_file(path: Path, raw: bytes) -> None:
    """Write encrypted bytes and restrict file permissions best-effort."""
    ensure_private_directory(path.parent)
    path.write_bytes(encrypt_bytes(raw))
    try:
        os.chmod(path, PRIVATE_FILE_MODE)
    except OSError:
        return


def read_secure_file(path: Path) -> bytes:
    """Read a stored file and return plaintext bytes to trusted backend callers."""
    return decrypt_bytes(path.read_bytes())


def stored_payload_is_encrypted(path: Path) -> bool:
    """Return whether a file on disk uses the encrypted storage marker."""
    try:
        with path.open('rb') as handle:
            return handle.read(len(ENCRYPTION_MAGIC)) == ENCRYPTION_MAGIC
    except OSError:
        return False


def encrypt_text_secret(value: str) -> str:
    """Encrypt a short application secret for storage in the local database."""
    if not value:
        return ''
    encrypted = encrypt_bytes(value.encode('utf-8'))
    return SECRET_TEXT_PREFIX + base64.urlsafe_b64encode(encrypted).decode('ascii')


def decrypt_text_secret(value: str) -> str:
    """Decrypt a database secret, while tolerating legacy plaintext values."""
    if not value:
        return ''
    if not value.startswith(SECRET_TEXT_PREFIX):
        return value
    encoded = value[len(SECRET_TEXT_PREFIX) :]
    try:
        encrypted = base64.urlsafe_b64decode(encoded.encode('ascii'))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=500, detail='Stored application secret is not valid encrypted text') from exc
    return decrypt_bytes(encrypted).decode('utf-8')


def text_secret_is_encrypted(value: str) -> bool:
    """Return whether a database secret is using the encrypted text envelope."""
    return bool(value and value.startswith(SECRET_TEXT_PREFIX))
