from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from cryptography.fernet import Fernet, InvalidToken

MAGIC: Final = b"IZCNABK1:"
MAX_HEADER_BYTES: Final = 16_384
HEADER_KEYS: Final = frozenset(
    {
        "format_version",
        "source_schema",
        "target_schema",
        "app_build",
        "created_at",
        "database_sha256",
        "plaintext_size",
        "ciphertext_sha256",
        "encryption",
    }
)


@dataclass(frozen=True, slots=True)
class BackupEnvelopeError(Exception):
    reason: str

    def __str__(self) -> str:
        return f"backup envelope rejected: {self.reason}"


@dataclass(frozen=True, slots=True)
class BackupRequest:
    database_path: Path
    local_app_data_dir: Path
    encryption_secret: str
    source_schema: int
    target_schema: int
    app_build: str


@dataclass(frozen=True, slots=True)
class BackupResult:
    path: Path
    database_sha256: str
    ciphertext_sha256: str


@dataclass(frozen=True, slots=True)
class BackupPayload:
    database_bytes: bytes
    database_sha256: str
    source_schema: int
    target_schema: int


def create_backup(request: BackupRequest) -> BackupResult:
    plaintext = request.database_path.read_bytes()
    database_sha256 = hashlib.sha256(plaintext).hexdigest()
    token = _fernet(request.encryption_secret).encrypt(plaintext)
    ciphertext_sha256 = hashlib.sha256(token).hexdigest()
    created_at = datetime.now(timezone.utc).isoformat()
    header = {
        "app_build": request.app_build,
        "ciphertext_sha256": ciphertext_sha256,
        "created_at": created_at,
        "database_sha256": database_sha256,
        "encryption": "fernet-sha256-v1",
        "format_version": 1,
        "plaintext_size": len(plaintext),
        "source_schema": request.source_schema,
        "target_schema": request.target_schema,
    }
    header_bytes = json.dumps(header, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    backup_dir = request.local_app_data_dir.resolve() / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = created_at.replace("-", "").replace(":", "").replace("+00:00", "Z").replace(".", "")
    path = backup_dir / f"migration-{request.source_schema}-to-{request.target_schema}-{timestamp}.izcnabackup"
    path.write_bytes(MAGIC + len(header_bytes).to_bytes(4, "big") + header_bytes + token)
    return BackupResult(path=path, database_sha256=database_sha256, ciphertext_sha256=ciphertext_sha256)


def read_backup(path: Path, encryption_secret: str) -> BackupPayload:
    envelope = path.read_bytes()
    if not envelope.startswith(MAGIC):
        raise BackupEnvelopeError("invalid magic")
    if len(envelope) < len(MAGIC) + 4:
        raise BackupEnvelopeError("truncated framing")
    header_length = int.from_bytes(envelope[len(MAGIC) : len(MAGIC) + 4], "big")
    if header_length < 2 or header_length > MAX_HEADER_BYTES:
        raise BackupEnvelopeError("header length outside bounds")
    header_start = len(MAGIC) + 4
    token_start = header_start + header_length
    if token_start >= len(envelope):
        raise BackupEnvelopeError("truncated payload")
    try:
        decoded = json.loads(envelope[header_start:token_start].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BackupEnvelopeError("header is not canonical JSON") from exc
    header = _validated_header(decoded)
    token = envelope[token_start:]
    if hashlib.sha256(token).hexdigest() != header["ciphertext_sha256"]:
        raise BackupEnvelopeError("ciphertext hash mismatch")
    try:
        plaintext = _fernet(encryption_secret).decrypt(token)
    except InvalidToken as exc:
        raise BackupEnvelopeError("authentication failed") from exc
    if len(plaintext) != header["plaintext_size"]:
        raise BackupEnvelopeError("plaintext size mismatch")
    database_sha256 = hashlib.sha256(plaintext).hexdigest()
    if database_sha256 != header["database_sha256"]:
        raise BackupEnvelopeError("database hash mismatch")
    return BackupPayload(
        database_bytes=plaintext,
        database_sha256=database_sha256,
        source_schema=header["source_schema"],
        target_schema=header["target_schema"],
    )


def validate_sqlite_file(path: Path) -> None:
    try:
        with closing(sqlite3.connect(path)) as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    except sqlite3.DatabaseError as exc:
        raise BackupEnvelopeError("plaintext is not a valid SQLite database") from exc
    if integrity != ("ok",) or foreign_keys:
        raise BackupEnvelopeError("SQLite integrity validation failed")


def _fernet(secret: str) -> Fernet:
    if not secret:
        raise BackupEnvelopeError("encryption secret is empty")
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _validated_header(decoded: object) -> dict[str, str | int]:
    if not isinstance(decoded, dict) or set(decoded) != HEADER_KEYS:
        raise BackupEnvelopeError("header keys are invalid")
    integer_keys = ("format_version", "source_schema", "target_schema", "plaintext_size")
    text_keys = ("app_build", "created_at", "database_sha256", "ciphertext_sha256", "encryption")
    if any(not isinstance(decoded[key], int) or isinstance(decoded[key], bool) for key in integer_keys):
        raise BackupEnvelopeError("header integer type is invalid")
    if any(not isinstance(decoded[key], str) for key in text_keys):
        raise BackupEnvelopeError("header text type is invalid")
    if decoded["format_version"] != 1 or decoded["encryption"] != "fernet-sha256-v1":
        raise BackupEnvelopeError("header version is unsupported")
    if decoded["plaintext_size"] < 0:
        raise BackupEnvelopeError("plaintext size is invalid")
    return decoded
