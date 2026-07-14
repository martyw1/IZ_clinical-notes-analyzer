from __future__ import annotations

import base64
import binascii
import hashlib
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias

from cryptography.fernet import Fernet, InvalidToken

from app.v2.services.secure_storage import LEGACY_SECRET_TEXT_PREFIX, SECRET_TEXT_PREFIX

MigrationReason: TypeAlias = Literal["source_missing", "schema_invalid", "credential_invalid", "database_unavailable"]


@dataclass(frozen=True, slots=True)
class LegacyProfile:
    vendor_name: str
    api_enabled: bool
    client_id: str
    client_secret: str
    token_url: str
    token_auth_style: str
    timeout_seconds: int
    api_base_url: str
    openapi_url: str
    api_version: str
    sync_enabled: bool
    sync_approved: bool
    mapping_validated: bool
    sync_limit: int


@dataclass(frozen=True, slots=True)
class LegacySourceRejected:
    reason: MigrationReason


LegacyReadResult: TypeAlias = LegacyProfile | LegacySourceRejected


def read_legacy_profile(path: Path, encryption_secret: str) -> LegacyReadResult:
    if not path.is_file():
        return LegacySourceRejected("source_missing")
    try:
        uri = f"{path.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            connection.execute("BEGIN")
            columns = {str(item[1]) for item in connection.execute("PRAGMA table_info('app_settings')")}
            required = _legacy_columns()
            if not required.issubset(columns):
                return LegacySourceRejected("schema_invalid")
            source = connection.execute(
                f"SELECT {','.join(sorted(required))} FROM app_settings ORDER BY id LIMIT 1"
            ).fetchone()
            if source is None:
                return LegacySourceRejected("schema_invalid")
            profile = _parse_legacy_row(source, encryption_secret)
            connection.rollback()
            return profile
    except sqlite3.DatabaseError:
        return LegacySourceRejected("database_unavailable")
    except (binascii.Error, InvalidToken, UnicodeDecodeError, ValueError):
        return LegacySourceRejected("credential_invalid")


def _legacy_columns() -> frozenset[str]:
    return frozenset(
        {
            "id", "emr_vendor_name", "emr_api_enabled", "api_client_id", "api_client_secret",
            "api_oauth_token_url", "api_token_auth_style", "emr_api_timeout_seconds",
            "alleva_api_base_url", "alleva_openapi_url", "alleva_api_version",
            "alleva_treatment_plan_sync_enabled", "alleva_treatment_plan_sync_approved",
            "alleva_treatment_plan_endpoint_mapping_validated", "alleva_treatment_plan_sync_limit",
        }
    )


def _parse_legacy_row(row: sqlite3.Row, encryption_secret: str) -> LegacyProfile:
    client_id = str(row["api_client_id"]).strip()
    if not client_id or len(client_id) > 255 or client_id.startswith((SECRET_TEXT_PREFIX, LEGACY_SECRET_TEXT_PREFIX)):
        raise ValueError
    if any(ord(character) < 32 or ord(character) == 127 for character in client_id):
        raise ValueError
    return LegacyProfile(
        vendor_name=str(row["emr_vendor_name"]).strip() or "Alleva REST API",
        api_enabled=_legacy_bool(row["emr_api_enabled"]),
        client_id=client_id,
        client_secret=_decrypt_v1_secret(str(row["api_client_secret"]), encryption_secret),
        token_url=str(row["api_oauth_token_url"]).strip(),
        token_auth_style=str(row["api_token_auth_style"]).strip(),
        timeout_seconds=max(1, min(int(row["emr_api_timeout_seconds"]), 300)),
        api_base_url=str(row["alleva_api_base_url"]).strip(),
        openapi_url=str(row["alleva_openapi_url"]).strip(),
        api_version=str(row["alleva_api_version"]).strip(),
        sync_enabled=_legacy_bool(row["alleva_treatment_plan_sync_enabled"]),
        sync_approved=_legacy_bool(row["alleva_treatment_plan_sync_approved"]),
        mapping_validated=_legacy_bool(row["alleva_treatment_plan_endpoint_mapping_validated"]),
        sync_limit=max(1, min(int(row["alleva_treatment_plan_sync_limit"]), 5000)),
    )


def _decrypt_v1_secret(value: str, encryption_secret: str) -> str:
    if not value.startswith(LEGACY_SECRET_TEXT_PREFIX):
        raise ValueError
    encoded = value[len(LEGACY_SECRET_TEXT_PREFIX) :].encode("ascii")
    payload = base64.b64decode(encoded, altchars=b"-_", validate=True)
    magic = b"IZCNA1\n"
    if not payload.startswith(magic):
        raise ValueError
    key = base64.urlsafe_b64encode(hashlib.sha256(encryption_secret.encode("utf-8")).digest())
    secret = Fernet(key).decrypt(payload[len(magic) :]).decode("utf-8")
    if not secret or len(secret) > 4096 or any(ord(character) < 32 for character in secret):
        raise ValueError
    return secret


def _legacy_bool(value: str | int) -> bool:
    numeric = int(value)
    if numeric not in (0, 1):
        raise ValueError
    return bool(numeric)
