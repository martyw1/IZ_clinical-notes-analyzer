from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from typing import Literal, assert_never

from app.v2.migrations.errors import MigrationStateError
from app.v2.migrations.registry import MIGRATIONS

BASELINE_STATEMENTS = (
    "CREATE TABLE users(id INTEGER PRIMARY KEY,role TEXT,is_active INTEGER,must_reset_password INTEGER,"
    "is_locked INTEGER,recovery_required INTEGER)",
    "CREATE TABLE app_settings(id INTEGER PRIMARY KEY,treatment_plan_loc_change_window_validated INTEGER,"
    "emr_api_enabled INTEGER,alleva_treatment_plan_sync_enabled INTEGER,"
    "alleva_treatment_plan_sync_approved INTEGER,alleva_treatment_plan_endpoint_mapping_validated INTEGER)",
    "CREATE TABLE api_harness_jobs(id INTEGER PRIMARY KEY,raw_sensitive_mode_used INTEGER,cancel_requested INTEGER)",
    "CREATE TABLE workflow_profiles(id INTEGER PRIMARY KEY,is_active INTEGER)",
)
OBJECT_PATTERN = re.compile(r"^\s*CREATE\s+(?:UNIQUE\s+)?(TABLE|INDEX|TRIGGER)\s+([A-Za-z_][A-Za-z0-9_]*)", re.I)
LITERAL_PATTERN = re.compile(r"('(?:''|[^'])*')")


@dataclass(frozen=True, slots=True)
class SchemaObject:
    kind: Literal["table", "index", "trigger"]
    name: str


def verify_required_schema(connection: sqlite3.Connection, expected_version: int) -> None:
    with closing(sqlite3.connect(":memory:")) as reference:
        for statement in BASELINE_STATEMENTS:
            reference.execute(statement)
        objects = _apply_reference_migrations(reference, expected_version)
        for schema_object in objects:
            _verify_object(connection, reference, schema_object)


def _apply_reference_migrations(connection: sqlite3.Connection, expected_version: int) -> tuple[SchemaObject, ...]:
    objects: list[SchemaObject] = []
    for migration in MIGRATIONS[:expected_version]:
        for statement in migration.statements:
            connection.execute(statement)
            match = OBJECT_PATTERN.match(statement)
            if match is None:
                raise MigrationStateError("migration statement does not declare a verifiable schema object")
            objects.append(SchemaObject(_object_kind(match.group(1)), match.group(2)))
    return tuple(objects)


def _verify_object(
    actual: sqlite3.Connection,
    reference: sqlite3.Connection,
    schema_object: SchemaObject,
) -> None:
    expected_sql = _object_sql(reference, schema_object)
    actual_sql = _object_sql(actual, schema_object)
    if _normalized_sql(actual_sql) != _normalized_sql(expected_sql):
        raise MigrationStateError("required database structure has altered SQL semantics")
    match schema_object.kind:
        case "table":
            _verify_table_semantics(actual, reference, schema_object.name)
        case "index":
            _verify_index_semantics(actual, reference, schema_object.name)
        case "trigger":
            return
        case unreachable:
            assert_never(unreachable)


def _object_kind(value: str) -> Literal["table", "index", "trigger"]:
    kinds: dict[str, Literal["table", "index", "trigger"]] = {
        "table": "table",
        "index": "index",
        "trigger": "trigger",
    }
    kind = kinds.get(value.casefold())
    if kind is None:
        raise MigrationStateError("migration statement declares an unsupported schema object")
    return kind


def _object_sql(connection: sqlite3.Connection, schema_object: SchemaObject) -> str:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type=? AND name=?",
        (schema_object.kind, schema_object.name),
    ).fetchone()
    if row is None or row[0] is None:
        raise MigrationStateError("required database structure is missing an object")
    return str(row[0])


def _verify_table_semantics(actual: sqlite3.Connection, reference: sqlite3.Connection, table: str) -> None:
    if _table_info(actual, table) != _table_info(reference, table):
        raise MigrationStateError("required database structure has altered column or primary-key semantics")
    if _foreign_keys(actual, table) != _foreign_keys(reference, table):
        raise MigrationStateError("required database structure has altered foreign-key semantics")


def _verify_index_semantics(actual: sqlite3.Connection, reference: sqlite3.Connection, index: str) -> None:
    if _index_definition(actual, index) != _index_definition(reference, index):
        raise MigrationStateError("required database structure has altered index semantics")


def _table_info(connection: sqlite3.Connection, table: str) -> tuple[tuple[int, str, str, int, str | None, int], ...]:
    return tuple(
        (int(row[0]), str(row[1]), str(row[2]).casefold(), int(row[3]), None if row[4] is None else str(row[4]), int(row[5]))
        for row in connection.execute(f'PRAGMA table_info("{table}")')
    )


def _foreign_keys(connection: sqlite3.Connection, table: str) -> tuple[tuple[int, int, str, str, str, str, str, str], ...]:
    return tuple(
        (int(row[0]), int(row[1]), str(row[2]), str(row[3]), str(row[4]), str(row[5]), str(row[6]), str(row[7]))
        for row in connection.execute(f'PRAGMA foreign_key_list("{table}")')
    )


def _index_definition(connection: sqlite3.Connection, index: str) -> tuple[int, str, int, tuple[str, ...]]:
    row = connection.execute(
        "SELECT il.[unique],il.origin,il.partial FROM pragma_index_list((SELECT tbl_name FROM sqlite_master WHERE name=?)) il "
        "WHERE il.name=?",
        (index, index),
    ).fetchone()
    if row is None:
        raise MigrationStateError("required database structure is missing an index")
    columns = tuple(str(item[2]) for item in connection.execute(f'PRAGMA index_info("{index}")'))
    return int(row[0]), str(row[1]), int(row[2]), columns


def _normalized_sql(sql: str) -> str:
    parts = LITERAL_PATTERN.split(sql.strip())
    normalized: list[str] = []
    for position, part in enumerate(parts):
        if position % 2:
            normalized.append(part)
            continue
        compact = re.sub(r"\s+", " ", part.casefold())
        normalized.append(re.sub(r"\s*([(),=<>])\s*", r"\1", compact))
    return "".join(normalized).strip()
