from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest

from app.v2.migrations.backup import BackupEnvelopeError, BackupRequest, create_backup, read_backup
from v2_migration_fixtures import SYNTHETIC_SECRET


def test_backup_uses_exact_framing_and_round_trips_database_bytes(tmp_path) -> None:
    # Given: a valid synthetic SQLite database under local application data.
    database_path = tmp_path / "synthetic.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE synthetic(id INTEGER PRIMARY KEY, safe_value TEXT NOT NULL)")
        connection.execute("INSERT INTO synthetic(safe_value) VALUES('safe')")
    plaintext = database_path.read_bytes()

    # When: an encrypted pre-migration backup is created and parsed.
    result = create_backup(BackupRequest(database_path, tmp_path, SYNTHETIC_SECRET, 0, 1, "test-build"))
    envelope = result.path.read_bytes()
    header_length = int.from_bytes(envelope[9:13], "big")
    header = json.loads(envelope[13 : 13 + header_length])
    recovered = read_backup(result.path, SYNTHETIC_SECRET)

    # Then: the exact framing, canonical hashes, and plaintext database bytes match.
    assert envelope[:9] == b"IZCNABK1:"
    assert set(header) == {
        "format_version", "source_schema", "target_schema", "app_build", "created_at",
        "database_sha256", "plaintext_size", "ciphertext_sha256", "encryption",
    }
    assert header["database_sha256"] == hashlib.sha256(plaintext).hexdigest()
    assert recovered.database_bytes == plaintext
    assert result.path.parent == tmp_path / "backups"


@pytest.mark.parametrize("mutation", ("tamper", "wrong-key", "oversized-header"))
def test_backup_rejects_tamper_wrong_key_and_malformed_framing(tmp_path, mutation) -> None:
    # Given: an encrypted backup of a valid synthetic SQLite database.
    database_path = tmp_path / "synthetic.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE synthetic(id INTEGER PRIMARY KEY)")
    result = create_backup(BackupRequest(database_path, tmp_path, SYNTHETIC_SECRET, 0, 1, "test-build"))

    # When: the envelope is tampered, opened with the wrong key, or given an excessive header length.
    payload = bytearray(result.path.read_bytes())
    secret = SYNTHETIC_SECRET
    if mutation == "tamper":
        payload[-1] ^= 1
    elif mutation == "wrong-key":
        secret = "incorrect-secret"
    else:
        payload[9:13] = (10_000_000).to_bytes(4, "big")
    result.path.write_bytes(payload)

    # Then: parsing fails closed with a typed envelope error.
    with pytest.raises(BackupEnvelopeError):
        read_backup(result.path, secret)
