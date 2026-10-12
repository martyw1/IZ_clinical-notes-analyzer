"""Unencrypted, complete profile ZIPs. Run with the app stopped; no secrets printed."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
import uuid
import zipfile
from contextlib import closing
import sys

FORMAT = "iz-portable-profile-zip-v1"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inventory(root):
    files = {}
    paths = []
    for directory, dirs, names in os.walk(root):
        if Path(directory) == root:
            dirs[:] = [n for n in dirs if n.lower() not in {"backups", "admin-recovery-backups", "diagnostics"}]
        paths.extend(Path(directory) / n for n in dirs + names)
    for path in paths:
        # Never follow junctions/symlinks into another profile or cloud folder.
        if path.is_symlink() or (path.stat().st_file_attributes & 0x400 if os.name == "nt" else False):
            raise ValueError("Profile contains a reparse point; backup refused")
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            if not rel.endswith(("-wal", "-shm", "-journal")):
                files[rel] = path
    return files


def configured_database(root):
    values = {}
    for line in (root / ".env").read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("\"'")
    # Portable profiles must not keep another computer's absolute directory override.
    for key in ("IZ_CNA_LOCAL_APP_DATA_DIR", "IZ_CNA_ENV_FILE"):
        if values.get(key):
            raise ValueError("Profile directory overrides require support migration")
    name = values.get("IZ_CNA_LOCAL_SQLITE_DB_PATH", values.get("LOCAL_SQLITE_DB_PATH", "clinical-notes-analyzer-v2.sqlite3"))
    path = Path(name)
    if path.is_absolute() or ".." in path.parts or not (root / path).is_file():
        raise ValueError("Database must exist inside the profile at a relative path")
    return path.as_posix()


def check_database(path):
    with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as db:
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("SQLite integrity check failed")
        if db.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("SQLite foreign-key check failed")


def check_idle(root):
    database = root / configured_database(root)
    with closing(sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)) as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='api_harness_jobs'").fetchone():
            if db.execute("SELECT 1 FROM api_harness_jobs WHERE status IN ('queued','running','writing') LIMIT 1").fetchone():
                raise ValueError("Active API job; retry later")


def safe_name(name):
    path = PurePosixPath(name)
    reserved = {"CON", "PRN", "AUX", "NUL"} | {f"{prefix}{i}" for prefix in ("COM", "LPT") for i in range(1, 10)}
    if not name or any(c in name for c in '\\:<>|?*') or path.is_absolute() or any(
        part in {"", ".", ".."} or part.endswith((".", " ")) or part.split(".")[0].upper() in reserved
        or any(ord(c) < 32 for c in part) for part in name.split("/")
    ):
        raise ValueError("Unsafe archive path")
    return path


def verify(archive, extraction=None):
    with zipfile.ZipFile(archive) as z:
        names = [i.filename for i in z.infolist()]
        if len({n.casefold() for n in names}) != len(names):
            raise ValueError("Duplicate archive paths")
        for name in names:
            safe_name(name)
        if z.getinfo("manifest.json").file_size > 16 * 1024 * 1024:
            raise ValueError("Manifest too large")
        manifest = json.loads(z.read("manifest.json"))
        if manifest.get("format") != FORMAT:
            raise ValueError("Unsupported backup format")
        expected = {"data/" + n for n in manifest["files"]} | {"manifest.json"}
        if set(names) != expected or ".env" not in manifest["files"]:
            raise ValueError("Incomplete archive")
        databases = manifest["databases"]
        if not databases or manifest["database"] not in databases:
            raise ValueError("Incomplete database inventory")
        for name in databases:
            safe_name(name)
            if name not in manifest["files"]:
                raise ValueError("Invalid database inventory")
        for name, meta in manifest["files"].items():
            safe_name(name)
            h = hashlib.sha256()
            size = 0
            out = None
            try:
                if extraction is not None:
                    target = extraction.joinpath(*PurePosixPath(name).parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    out = target.open("xb")
                with z.open("data/" + name) as source:
                    while block := source.read(1024 * 1024):
                        size += len(block)
                        if size > meta["size"]:
                            raise ValueError("Archive size mismatch")
                        h.update(block)
                        if out:
                            out.write(block)
                if size != meta["size"] or h.hexdigest() != meta["sha256"]:
                    raise ValueError("Archive hash mismatch")
            finally:
                if out:
                    out.close()
        if extraction is not None:
            db_name = configured_database(extraction)
            if db_name != manifest["database"]:
                raise ValueError("Database configuration mismatch")
            for name in manifest["databases"]:
                check_database(extraction / name)
        return manifest


def check_app_profile(root):
    # Reuse the app's existing schema, referential and encrypted-payload verifier.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    from app.desktop_profile import resolve_profile
    from app.desktop_sqlite_inspection import inspect_database
    profile = resolve_profile(root, root / ".env", "", allow_relocated_absolute=False)
    inspect_database(profile.database_path, root, profile.encryption_secret)


def backup(root, destination, version, app_check=False):
    root, destination = root.resolve(), destination.resolve()
    if destination == root or destination.is_relative_to(root):
        raise ValueError("Backup destination must be outside local data")
    db_name = configured_database(root)
    source = inventory(root)
    before = {n: (p.stat().st_size, p.stat().st_mtime_ns) for n, p in source.items()}
    databases = [n for n in source if n.endswith((".sqlite3", ".sqlite", ".db"))]
    if db_name not in databases:
        raise ValueError("Unsupported database filename")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%fZ")
    filename = "IZ-local-data-" + stamp + ".zip"
    # Plain temporary files stay outside OneDrive until a complete ZIP passes restore rehearsal.
    with tempfile.TemporaryDirectory(prefix="iz-profile-backup-") as tmp:
        work = Path(tmp)
        staged = work / "profile"
        staged.mkdir()
        for name, path in source.items():
            target = staged / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if name in databases:
                with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as src, closing(sqlite3.connect(target)) as dst:
                    src.backup(dst)
                check_database(target)
            else:
                shutil.copyfile(path, target)
        after_files = inventory(root)
        after = {n: (p.stat().st_size, p.stat().st_mtime_ns) for n, p in after_files.items()}
        if before != after:
            raise ValueError("Local data changed during backup; retry when idle")
        files = {n: {"size": (staged / n).stat().st_size, "sha256": digest(staged / n)} for n in source}
        manifest = {"format": FORMAT, "created_utc": stamp, "app_version": version,
                    "database": db_name, "databases": databases, "files": files,
                    "excluded": ["backups", "admin-recovery-backups", "diagnostics", "SQLite transient journals"]}
        archive = work / filename
        with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
            for name in files:
                z.write(staged / name, "data/" + name)
            z.writestr("manifest.json", json.dumps(manifest, indent=2))
        rehearsal = work / "rehearsal"
        rehearsal.mkdir()
        verify(archive, rehearsal)
        if app_check:
            check_app_profile(rehearsal)
        destination.mkdir(parents=True, exist_ok=True)
        partial = destination / (filename + ".partial")
        final = destination / filename
        try:
            shutil.copyfile(archive, partial)
            if digest(partial) != digest(archive):
                raise ValueError("Published backup copy failed verification")
            partial.rename(final)
        finally:
            partial.unlink(missing_ok=True)
        return final


def restore(archive, target, app_check=False):
    target = target.absolute()
    if target.exists():
        raise ValueError("Restore target already exists; preserve/rename it first")
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = target.parent / (".iz-restore-" + uuid.uuid4().hex)
    stage.mkdir()
    try:
        verify(archive, stage)
        if app_check:
            check_app_profile(stage)
        stage.rename(target)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["backup", "verify", "restore", "idle"])
    parser.add_argument("--root", type=Path)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--version", default="unknown")
    parser.add_argument("--app-check", action="store_true")
    args = parser.parse_args()
    try:
        if args.operation == "backup":
            backup(args.root, args.destination, args.version, args.app_check)
        elif args.operation == "restore":
            restore(args.archive, args.root, args.app_check)
        elif args.operation == "idle":
            check_idle(args.root)
        else:
            verify(args.archive)
        print("Portable profile ZIP: " + args.operation + " verified successfully.")
        return 0
    except Exception:
        # Do not expose filenames, clinical data, configuration or secret values.
        print("Portable profile ZIP failed. No successful backup/restore was published. Contact R3 support.", file=__import__("sys").stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
