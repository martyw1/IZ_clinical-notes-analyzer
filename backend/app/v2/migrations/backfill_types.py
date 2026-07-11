from __future__ import annotations

import base64
import hashlib
import sqlite3
from dataclasses import dataclass

from cryptography.fernet import Fernet

type JsonPrimitive = str | int | float | bool | None
type JsonValue = JsonPrimitive | list[JsonValue] | dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class BackfillError(Exception):
    reason: str

    def __str__(self) -> str:
        return f"legacy clinical backfill failed: {self.reason}"


def encrypt_bytes(value: bytes, secret: str) -> bytes:
    return b"IZCNA1:" + Fernet(fernet_key(secret)).encrypt(value)


def fernet_key(secret: str) -> bytes:
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())


def iso_text(value: JsonPrimitive) -> str:
    text = str(value or "").strip()
    return text or "2026-07-10T00:00:00+00:00"


def user_id(connection: sqlite3.Connection, legacy_id: JsonPrimitive, fallback: int) -> int:
    try:
        numeric = int(str(legacy_id))
    except ValueError:
        return fallback
    exists = connection.execute("SELECT 1 FROM users WHERE id=?", (numeric,)).fetchone()
    return numeric if exists else fallback
