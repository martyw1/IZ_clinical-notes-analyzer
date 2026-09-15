from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from app.desktop_identity import (
    IdentityError,
    authorized_paths_equal,
    contained_path,
    current_user_sid,
    data_identity,
    validated_path,
)

DEFAULT_DATABASE_NAME: Final = "clinical-notes-analyzer-v2.sqlite3"
ENVIRONMENT_LIMIT: Final = 1_048_576
ENVIRONMENT_NAMES: Final = (
    "IZ_CNA_ENV_FILE",
    "IZ_CNA_LOCAL_APP_DATA_DIR",
    "IZ_CNA_LOCAL_SQLITE_DB_PATH",
    "LOCAL_SQLITE_DB_PATH",
    "IZ_CNA_DATA_ENCRYPTION_KEY",
    "DATA_ENCRYPTION_KEY",
    "IZ_CNA_SECRET_KEY",
    "SECRET_KEY",
)


@dataclass(frozen=True, slots=True)
class ProfileIdentity:
    data_root: Path
    environment_file: Path
    database_path: Path
    database_relative_path: str
    environment_sha256: str
    encryption_secret: str
    data_identity: str


def _read_environment(path: Path) -> tuple[dict[str, str], str]:
    raw = path.read_bytes()
    if len(raw) > ENVIRONMENT_LIMIT:
        raise IdentityError("environment_file_invalid")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IdentityError("environment_file_invalid") from exc
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        normalized_name = name.strip()
        if normalized_name:
            values.setdefault(normalized_name, value.strip().strip("\"'"))
    for name in ENVIRONMENT_NAMES:
        if name in os.environ:
            values[name] = os.environ[name]
    return values, hashlib.sha256(raw).hexdigest()


def _setting(values: dict[str, str], canonical: str, generated: str, default: str = "") -> str:
    if canonical in values:
        return values[canonical]
    return values.get(generated, default)


def _resolve_configured_root(
    values: dict[str, str],
    data_root: Path,
    allow_relocated_absolute: bool,
) -> tuple[Path, bool]:
    configured_root = values.get("IZ_CNA_LOCAL_APP_DATA_DIR", "").strip()
    if not configured_root:
        return data_root, False
    configured = validated_path(configured_root, must_exist=not allow_relocated_absolute)
    if authorized_paths_equal(configured, data_root):
        return configured, False
    if not allow_relocated_absolute:
        raise IdentityError("data_root_mismatch")
    return configured, True


def _resolve_database(
    values: dict[str, str],
    data_root: Path,
    configured_root: Path,
    relocated: bool,
    database_must_exist: bool,
) -> Path:
    value = _setting(
        values,
        "IZ_CNA_LOCAL_SQLITE_DB_PATH",
        "LOCAL_SQLITE_DB_PATH",
        DEFAULT_DATABASE_NAME,
    )
    configured_database = Path(value).expanduser()
    if configured_database.is_absolute() and relocated:
        try:
            embedded = contained_path(configured_root, configured_database, must_exist=False)
        except IdentityError as exc:
            raise IdentityError("database_outside_data_root") from exc
        candidate = data_root / Path(os.path.relpath(embedded, configured_root))
    else:
        candidate = configured_database if configured_database.is_absolute() else data_root / configured_database
    try:
        database = contained_path(data_root, candidate, must_exist=database_must_exist)
    except IdentityError as exc:
        reason = "database_missing" if exc.reason == "path_missing" else "database_outside_data_root"
        raise IdentityError(reason) from exc
    if database_must_exist and not database.is_file():
        raise IdentityError("database_invalid")
    if not database_must_exist and database.exists() and not database.is_file():
        raise IdentityError("database_invalid")
    return database


def resolve_profile(
    data_root_value: str,
    environment_file_value: str,
    expected_database_path: str,
    *,
    allow_relocated_absolute: bool = False,
    allow_missing_database: bool = False,
) -> ProfileIdentity:
    try:
        data_root = validated_path(data_root_value, must_exist=True)
        if not data_root.is_dir():
            raise IdentityError("data_root_invalid")
        environment_file = contained_path(data_root, environment_file_value, must_exist=True)
    except IdentityError as exc:
        reason = "environment_file_missing" if exc.reason == "path_missing" else exc.reason
        raise IdentityError(reason) from exc
    expected_environment = (data_root / ".env").resolve(strict=True)
    if not authorized_paths_equal(environment_file, expected_environment):
        raise IdentityError("environment_path_mismatch")
    values, environment_sha256 = _read_environment(environment_file)
    configured_root, relocated = _resolve_configured_root(values, data_root, allow_relocated_absolute)
    configured_environment = values.get("IZ_CNA_ENV_FILE", "").strip()
    if configured_environment:
        configured_path = validated_path(
            configured_environment,
            must_exist=not (allow_relocated_absolute and relocated),
        )
        source_environment = (configured_root / ".env").resolve(strict=False)
        accepted_relocation = (
            allow_relocated_absolute
            and relocated
            and authorized_paths_equal(configured_path, source_environment)
        )
        if not authorized_paths_equal(configured_path, environment_file) and not accepted_relocation:
            raise IdentityError("environment_path_mismatch")
    database_path = _resolve_database(values, data_root, configured_root, relocated, not allow_missing_database)
    relative = Path(os.path.relpath(database_path, data_root)).as_posix()
    if expected_database_path:
        try:
            expected = contained_path(data_root, expected_database_path, must_exist=False)
        except IdentityError as exc:
            raise IdentityError("database_path_mismatch") from exc
        if not authorized_paths_equal(expected, database_path):
            raise IdentityError("database_path_mismatch")
    secret = _setting(values, "IZ_CNA_DATA_ENCRYPTION_KEY", "DATA_ENCRYPTION_KEY").strip()
    if not secret:
        secret = _setting(values, "IZ_CNA_SECRET_KEY", "SECRET_KEY").strip()
    if not secret:
        raise IdentityError("encryption_key_missing")
    return ProfileIdentity(
        data_root=data_root,
        environment_file=environment_file,
        database_path=database_path,
        database_relative_path=relative,
        environment_sha256=environment_sha256,
        encryption_secret=secret,
        data_identity=data_identity(current_user_sid(), data_root, relative),
    )
