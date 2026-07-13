from __future__ import annotations

import re
import sqlite3
from typing import TypeAlias

from app.v2.migrations.errors import MigrationStateError
from app.v2.migrations.schema_core import (
    APP_SETTING_EXTENSIONS,
    APP_SETTING_LEGACY_SOURCES,
    APP_SETTING_NORMALIZED_EXTENSIONS,
)

_TEMP_TABLE = "app_settings_v5_normalized"
_NORMALIZED_NAMES = {name for name, _definition in APP_SETTING_NORMALIZED_EXTENSIONS}
ColumnRow: TypeAlias = tuple[int, str, str, int, str | None, int]


def apply_v5_schema_compatibility(connection: sqlite3.Connection) -> None:
    apply_app_setting_extensions(connection)
    _normalize_audit_log_details_column(connection)


def apply_app_setting_extensions(connection: sqlite3.Connection) -> None:
    existing = _column_rows(connection)
    added: set[str] = set()
    for name, definition in APP_SETTING_EXTENSIONS:
        if name not in existing:
            connection.execute(f'ALTER TABLE app_settings ADD COLUMN "{name}" {definition}')
            added.add(name)
    for target, source in APP_SETTING_LEGACY_SOURCES:
        if target in added and source in existing:
            connection.execute(
                f'UPDATE app_settings SET "{target}"="{source}" '
                f'WHERE "{source}" IS NOT NULL AND TRIM("{source}")<>\'\''
            )
    _normalize_app_setting_table(connection)


def verify_app_setting_extensions(connection: sqlite3.Connection) -> None:
    rows = _column_rows(connection)
    for name, definition in APP_SETTING_NORMALIZED_EXTENSIONS:
        row = rows.get(name)
        expected_type, expected_default = _definition_contract(definition)
        if row is None or str(row[2]).casefold() != expected_type.casefold() or int(row[3]) != 1:
            raise MigrationStateError("normalized application-setting column semantics are invalid")
        if str(row[4]) != expected_default:
            raise MigrationStateError("normalized application-setting column default is invalid")


def _normalize_app_setting_table(connection: sqlite3.Connection) -> None:
    rows = _column_rows(connection)
    needs_rebuild = False
    for name, definition in APP_SETTING_NORMALIZED_EXTENSIONS:
        row = rows[name]
        expected_type, expected_default = _definition_contract(definition)
        if str(row[2]).casefold() != expected_type.casefold() or int(row[3]) != 1:
            raise MigrationStateError("normalized application-setting column semantics are invalid")
        actual_default = None if row[4] is None else str(row[4])
        if actual_default is None:
            needs_rebuild = True
        elif actual_default != expected_default:
            raise MigrationStateError("normalized application-setting column default is invalid")
    if needs_rebuild:
        _rebuild_app_setting_table(connection, rows)
    verify_app_setting_extensions(connection)


def _rebuild_app_setting_table(
    connection: sqlite3.Connection,
    rows: dict[str, ColumnRow],
) -> None:
    if _table_exists(connection, _TEMP_TABLE):
        raise MigrationStateError("application-setting migration staging table already exists")
    table_row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='app_settings'"
    ).fetchone()
    if table_row is None or table_row[0] is None:
        raise MigrationStateError("application-setting table definition is unavailable")
    definitions, suffix = _normalized_table_definitions(str(table_row[0]))
    schema_objects = tuple(
        str(row[0])
        for row in connection.execute(
            "SELECT sql FROM sqlite_master WHERE tbl_name='app_settings' "
            "AND type IN ('index','trigger') AND sql IS NOT NULL ORDER BY type,name"
        )
    )
    connection.execute(f'CREATE TABLE "{_TEMP_TABLE}" ({definitions}){suffix}')
    columns = ",".join(f'"{name}"' for name in rows)
    connection.execute(
        f'INSERT INTO "{_TEMP_TABLE}" ({columns}) SELECT {columns} FROM app_settings'
    )
    connection.execute("DROP TABLE app_settings")
    connection.execute(f'ALTER TABLE "{_TEMP_TABLE}" RENAME TO app_settings')
    for statement in schema_objects:
        connection.execute(statement)


def _normalized_table_definitions(create_sql: str) -> tuple[str, str]:
    open_index = create_sql.find("(")
    close_index = _matching_parenthesis(create_sql, open_index)
    clauses = _split_clauses(create_sql[open_index + 1 : close_index])
    replaced: set[str] = set()
    normalized: list[str] = []
    definitions = dict(APP_SETTING_NORMALIZED_EXTENSIONS)
    for clause in clauses:
        name = _leading_identifier(clause)
        if name in _NORMALIZED_NAMES:
            normalized.append(f'"{name}" {definitions[name]}')
            replaced.add(name)
        else:
            normalized.append(clause.strip())
    if replaced != _NORMALIZED_NAMES:
        raise MigrationStateError("application-setting table definition is incomplete")
    suffix = create_sql[close_index + 1 :].strip()
    return ",".join(normalized), f" {suffix}" if suffix else ""


def _matching_parenthesis(value: str, open_index: int) -> int:
    if open_index < 0:
        raise MigrationStateError("application-setting table definition is malformed")
    depth = 0
    quote = ""
    position = open_index
    while position < len(value):
        character = value[position]
        if quote:
            if character == quote:
                if position + 1 < len(value) and value[position + 1] == quote:
                    position += 1
                else:
                    quote = ""
        elif character in "'\"`":
            quote = character
        elif character == "[":
            quote = "]"
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return position
        position += 1
    raise MigrationStateError("application-setting table definition is malformed")


def _split_clauses(value: str) -> tuple[str, ...]:
    clauses: list[str] = []
    start = 0
    depth = 0
    quote = ""
    position = 0
    while position < len(value):
        character = value[position]
        if quote:
            if character == quote:
                if position + 1 < len(value) and value[position + 1] == quote:
                    position += 1
                else:
                    quote = ""
        elif character in "'\"`":
            quote = character
        elif character == "[":
            quote = "]"
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        elif character == "," and depth == 0:
            clauses.append(value[start:position])
            start = position + 1
        position += 1
    if quote or depth != 0:
        raise MigrationStateError("application-setting table definition is malformed")
    clauses.append(value[start:])
    return tuple(clauses)


def _leading_identifier(clause: str) -> str:
    match = re.match(r'\s*(?:"([^"]+)"|`([^`]+)`|\[([^]]+)\]|([A-Za-z_][A-Za-z0-9_]*))', clause)
    if match is None:
        return ""
    return next((value for value in match.groups() if value is not None), "").casefold()


def _definition_contract(definition: str) -> tuple[str, str]:
    type_name, separator, default = definition.partition(" NOT NULL DEFAULT ")
    if not separator:
        raise MigrationStateError("normalized application-setting definition is invalid")
    return type_name, default


def _column_rows(connection: sqlite3.Connection) -> dict[str, ColumnRow]:
    return {
        str(row[1]).casefold(): (
            int(row[0]),
            str(row[1]),
            str(row[2]),
            int(row[3]),
            None if row[4] is None else str(row[4]),
            int(row[5]),
        )
        for row in connection.execute("PRAGMA table_info('app_settings')")
    }


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def _normalize_audit_log_details_column(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "audit_logs"):
        return
    columns = {str(row[1]).casefold() for row in connection.execute("PRAGMA table_info('audit_logs')")}
    if "details" in columns and "details_json" not in columns:
        return
    if "details_json" in columns and "details" not in columns:
        connection.execute("ALTER TABLE audit_logs RENAME COLUMN details_json TO details")
        return
    raise MigrationStateError("audit-log details column is missing or ambiguous")
