"""Synthetic portable profile restoration, corruption and path-safety checks."""
import base64
import hashlib
import importlib.util
from pathlib import Path
import sqlite3
import zipfile

from cryptography.fernet import Fernet
import pytest

spec = importlib.util.spec_from_file_location("portable_zip", Path(__file__).resolve().parents[2] / "scripts" / "portable_data_zip.py")
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def profile(root):
    root.mkdir()
    key = "synthetic-backup-key-for-test-only"
    (root / ".env").write_text("LOCAL_SQLITE_DB_PATH=data.sqlite3\nDATA_ENCRYPTION_KEY=" + key)
    with sqlite3.connect(root / "data.sqlite3") as db:
        db.execute("CREATE TABLE sentinel(value TEXT)")
        db.execute("INSERT INTO sentinel VALUES ('synthetic-preserved')")
    codec = Fernet(base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest()))
    (root / "uploads").mkdir()
    (root / "uploads" / "synthetic.enc").write_bytes(b"IZCNA1:" + codec.encrypt(b"synthetic document"))
    return codec


def test_new_computer_restore_preserves_settings_database_and_encrypted_upload(tmp_path):
    original = tmp_path / "old-user"
    codec = profile(original)
    archive = tool.backup(original, tmp_path / "cloud", "synthetic-test")
    new = tmp_path / "different-user-on-replacement-device"
    tool.restore(archive, new)
    assert (new / ".env").read_bytes() == (original / ".env").read_bytes()
    with sqlite3.connect(new / "data.sqlite3") as db:
        assert db.execute("SELECT value FROM sentinel").fetchone() == ("synthetic-preserved",)
    assert codec.decrypt((new / "uploads" / "synthetic.enc").read_bytes()[7:]) == b"synthetic document"
    assert tool.verify(archive)["app_version"] == "synthetic-test"


def test_restore_refuses_existing_profile(tmp_path):
    original = tmp_path / "original"
    profile(original)
    archive = tool.backup(original, tmp_path / "cloud", "test")
    with pytest.raises(ValueError, match="already exists"):
        tool.restore(archive, original)


def test_tampered_archive_never_publishes_restore(tmp_path):
    root = tmp_path / "original"
    profile(root)
    archive = tool.backup(root, tmp_path / "cloud", "test")
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive) as src, zipfile.ZipFile(bad, "w") as dst:
        for name in src.namelist():
            dst.writestr(name, b"tampered" if name == "data/.env" else src.read(name))
    target = tmp_path / "new"
    with pytest.raises(ValueError, match="mismatch"):
        tool.restore(bad, target)
    assert not target.exists()


@pytest.mark.parametrize("name", ["../escape", "data/../../escape", "C:/escape", "data\\escape", "/absolute", "data/file. ", "data/NUL.txt", "data/file:stream", "data/a?b"])
def test_rejects_unsafe_archive_names(name):
    with pytest.raises(ValueError):
        tool.safe_name(name)


def test_busy_job_blocks_backup_preflight(tmp_path):
    root = tmp_path / "original"
    profile(root)
    with sqlite3.connect(root / "data.sqlite3") as db:
        db.execute("CREATE TABLE api_harness_jobs(status TEXT)")
        db.execute("INSERT INTO api_harness_jobs VALUES ('running')")
    with pytest.raises(ValueError, match="Active API job"):
        tool.check_idle(root)


def test_failed_app_semantics_never_publishes_backup_or_restore(tmp_path, monkeypatch):
    root = tmp_path / "original"
    profile(root)
    archive = tool.backup(root, tmp_path / "cloud", "test")
    def fail(_root):
        raise ValueError("Synthetic app semantic failure")
    monkeypatch.setattr(tool, "check_app_profile", fail)
    with pytest.raises(ValueError, match="semantic"):
        tool.backup(root, tmp_path / "failed-cloud", "test", app_check=True)
    assert not (tmp_path / "failed-cloud").exists()
    with pytest.raises(ValueError, match="semantic"):
        tool.restore(archive, tmp_path / "new", app_check=True)
    assert not (tmp_path / "new").exists()
