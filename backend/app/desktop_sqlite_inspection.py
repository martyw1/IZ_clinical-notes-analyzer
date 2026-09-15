from __future__ import annotations

import base64
import hashlib
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken

from app.desktop_identity import IdentityError, contained_path

SAFE_COUNT_TABLES: Final = (
    "users",
    "facilities",
    "patients",
    "treatment_plan_imports",
    "uploaded_documents",
    "treatment_plan_versions",
    "treatment_review_versions",
    "diagnosis_snapshots",
    "source_documents",
    "patient_snapshot_versions",
    "evaluation_runs",
    "criterion_results",
    "correction_submissions",
    "correction_work_items",
    "treatment_plan_manager_actions",
    "manager_dispositions",
    "workflow_profiles",
    "workflow_profile_versions",
    "sync_jobs",
    "sync_failures",
    "sync_checkpoints",
    "api_harness_jobs",
    "audit_logs",
)
ENCRYPTED_COLUMNS: Final = (
    ("treatment_plan_imports", "encrypted_payload", True),
    ("treatment_plan_versions", "normalized_snapshot_encrypted", True),
    ("treatment_review_versions", "normalized_snapshot_encrypted", True),
    ("diagnosis_snapshots", "normalized_snapshot_encrypted", True),
    ("patient_snapshot_versions", "snapshot_encrypted", True),
    ("patient_source_snapshots", "normalized_snapshot_encrypted", True),
    ("sync_checkpoints", "encrypted_records_json", False),
    ("app_settings", "api_client_id", False),
    ("app_settings", "api_client_secret", False),
)


class DatabaseInspectionError(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class DatabaseInspection:
    database_sha256: str
    sqlite_integrity: str
    foreign_key_violations: int
    schema_version: int
    safe_counts: dict[str, int]
    encrypted_payloads_checked: int
    encrypted_payloads_valid: int


def _readonly_connection(path: Path) -> sqlite3.Connection:
    uri = f"file:{quote(path.as_posix(), safe='/:')}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=5)
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        return connection
    except sqlite3.Error as exc:
        raise DatabaseInspectionError("database_invalid") from exc


def _tables(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {str(row[0]) for row in rows}


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()}


def _content_digest(connection: sqlite3.Connection) -> str:
    digest = hashlib.sha256(b"iz-cna-sqlite-content-v1\0")
    for statement in connection.iterdump():
        encoded = statement.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def _fernet(secret: str) -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def _decode_base64(value: str) -> bytes:
    try:
        return base64.b64decode(value.encode("ascii"), altchars=b"-_", validate=True)
    except (UnicodeEncodeError, ValueError) as exc:
        raise DatabaseInspectionError("encrypted_payload_invalid") from exc


def _decrypt_payload(value: object, cipher: Fernet, required: bool) -> bool:
    framed: bytes
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, bytes):
        framed = value
    elif isinstance(value, str) and value.startswith("enc:v1:"):
        framed = _decode_base64(value[7:])
    elif isinstance(value, str) and value.startswith("IZCNA1-TEXT:"):
        legacy = _decode_base64(value[13:])
        if not legacy.startswith(b"IZCNA1\n"):
            raise DatabaseInspectionError("encrypted_payload_invalid")
        try:
            cipher.decrypt(legacy[7:])
        except InvalidToken as exc:
            raise DatabaseInspectionError("encrypted_payload_invalid") from exc
        return True
    elif value in (None, "", b"") and not required:
        return False
    else:
        raise DatabaseInspectionError("encrypted_payload_invalid")
    if not framed.startswith(b"IZCNA1:"):
        raise DatabaseInspectionError("encrypted_payload_invalid")
    try:
        cipher.decrypt(framed[7:])
    except InvalidToken as exc:
        raise DatabaseInspectionError("encrypted_payload_invalid") from exc
    return True


def _encrypted_column_summary(
    connection: sqlite3.Connection,
    tables: set[str],
    cipher: Fernet,
) -> tuple[int, int]:
    checked = 0
    valid = 0
    for table, column, required in ENCRYPTED_COLUMNS:
        if table not in tables or column not in _columns(connection, table):
            continue
        rows = connection.execute(f'SELECT "{column}" FROM "{table}" ORDER BY rowid').fetchall()
        for row in rows:
            if _decrypt_payload(row[0], cipher, required):
                checked += 1
                valid += 1
    return checked, valid


def _encrypted_file_summary(
    connection: sqlite3.Connection,
    tables: set[str],
    data_root: Path,
    cipher: Fernet,
) -> tuple[int, int]:
    if "source_documents" not in tables or "encrypted_relative_path" not in _columns(connection, "source_documents"):
        return 0, 0
    rows = connection.execute(
        "SELECT encrypted_relative_path FROM source_documents ORDER BY id"
    ).fetchall()
    valid = 0
    for row in rows:
        relative = str(row[0])
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise DatabaseInspectionError("encrypted_payload_invalid")
        try:
            encrypted_file = contained_path(data_root, data_root / candidate, must_exist=True)
        except IdentityError as exc:
            raise DatabaseInspectionError("encrypted_payload_invalid") from exc
        if not encrypted_file.is_file() or not _decrypt_payload(encrypted_file.read_bytes(), cipher, True):
            raise DatabaseInspectionError("encrypted_payload_invalid")
        valid += 1
    return len(rows), valid


def inspect_database(path: Path, data_root: Path, encryption_secret: str) -> DatabaseInspection:
    connection = _readonly_connection(path)
    try:
        integrity_rows = [str(row[0]) for row in connection.execute("PRAGMA integrity_check").fetchall()]
        if integrity_rows != ["ok"]:
            raise DatabaseInspectionError("database_integrity_failed")
        foreign_key_violations = len(connection.execute("PRAGMA foreign_key_check").fetchall())
        if foreign_key_violations:
            raise DatabaseInspectionError("database_foreign_key_failed")
        tables = _tables(connection)
        schema_version = 0
        if "schema_migrations" in tables and "version" in _columns(connection, "schema_migrations"):
            row = connection.execute("SELECT COALESCE(MAX(version),0) FROM schema_migrations").fetchone()
            schema_version = int(row[0])
        safe_counts = {
            table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            for table in SAFE_COUNT_TABLES
            if table in tables
        }
        cipher = _fernet(encryption_secret)
        column_checked, column_valid = _encrypted_column_summary(connection, tables, cipher)
        file_checked, file_valid = _encrypted_file_summary(connection, tables, data_root, cipher)
        return DatabaseInspection(
            database_sha256=_content_digest(connection),
            sqlite_integrity="ok",
            foreign_key_violations=0,
            schema_version=schema_version,
            safe_counts=safe_counts,
            encrypted_payloads_checked=column_checked + file_checked,
            encrypted_payloads_valid=column_valid + file_valid,
        )
    except sqlite3.Error as exc:
        raise DatabaseInspectionError("database_invalid") from exc
    finally:
        connection.close()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_database(source: Path, destination: Path) -> None:
    try:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise DatabaseInspectionError("snapshot_exists") from exc
    os.close(descriptor)
    source_connection = _readonly_connection(source)
    try:
        destination_uri = f"file:{quote(destination.as_posix(), safe='/:')}?mode=rw"
        with sqlite3.connect(destination_uri, uri=True) as destination_connection:
            source_connection.backup(destination_connection)
    except sqlite3.Error as exc:
        destination.unlink(missing_ok=True)
        raise DatabaseInspectionError("snapshot_failed") from exc
    finally:
        source_connection.close()
    with destination.open("r+b") as snapshot:
        os.fsync(snapshot.fileno())
