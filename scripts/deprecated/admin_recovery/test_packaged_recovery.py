from __future__ import annotations

import hashlib
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import time
from contextlib import closing
from pathlib import Path

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.v2.services.audit_store import verify_audit_chain

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / 'dist/windows-release/IZ-Clinical-Notes-Analyzer-v2.0.0-beta.3/app'
RECOVERY = ROOT / 'output/admin-recovery/Reset-IZ-Admin.exe'


def test_packaged_missing_installation_exits_safely(tmp_path: Path) -> None:
    environment = {key: value for key, value in os.environ.items() if not key.startswith('IZ_CNA_')}
    environment['LOCALAPPDATA'] = str(tmp_path)
    completed = subprocess.run([str(RECOVERY)], input='\n', text=True, capture_output=True, env=environment, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    assert completed.returncode == 1
    assert not list(tmp_path.iterdir())


def test_original_package_login_recovery_and_password_change(tmp_path: Path) -> None:
    local = tmp_path / 'Windows Profile With Spaces' / 'AppData' / 'Local'
    install = local / 'Programs/IZ Clinical Notes Analyzer'
    data = local / 'IZ Clinical Notes Analyzer'
    shutil.copytree(PACKAGE / 'runtime', install / 'runtime')
    data.mkdir(parents=True)
    env_file = data / '.env'
    env_file.write_text('ENVIRONMENT=local-client\nSECRET_KEY=SyntheticSigningKeyForRecoveryTest123456789\nDATA_ENCRYPTION_KEY=SyntheticEncryptionKeyForRecoveryTest123456789\nBOOTSTRAP_ADMIN_USERNAME=admin\nBOOTSTRAP_ADMIN_PASSWORD=SyntheticInitialCredential123\nLOCAL_SQLITE_DB_PATH=clinical-notes-analyzer.sqlite3\nLLM_ENABLED=false\nEMR_API_ENABLED=false\n', encoding='utf-8-sig')
    settings_before = hashlib.sha256(env_file.read_bytes()).digest()
    environment = {key: value for key, value in os.environ.items() if not key.startswith('IZ_CNA_')}
    environment['LOCALAPPDATA'] = str(local)
    environment['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
    with closing(socket.socket()) as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    runtime_environment = dict(environment, IZ_CNA_ENV_FILE=str(env_file), IZ_CNA_PORT=str(port), IZ_CNA_LOCAL_APP_DATA_DIR=str(data))
    process = subprocess.Popen([str(install / 'runtime/IZClinicalNotesAnalyzer.exe')], env=runtime_environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=3, trust_env=False) as client:
            deadline = time.monotonic() + 45
            ready = False
            while time.monotonic() < deadline:
                try:
                    ready = client.get('/api/version').status_code == 200
                except httpx.TransportError:
                    ready = False
                if ready:
                    break
                time.sleep(0.2)
            assert ready, 'Original packaged runtime did not start in the isolated profile'
            initial = client.post('/api/auth/login', json={'username': 'admin', 'password': 'SyntheticInitialCredential123'})
            assert initial.status_code == 200
            previous_token = initial.json()['access_token']
            assert client.post('/api/auth/login', json={'username': 'admin', 'password': 'IncorrectSyntheticCredential123'}).status_code == 401
            database = data / 'clinical-notes-analyzer.sqlite3'
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("CREATE TABLE recovery_preservation_sentinel (value TEXT NOT NULL)")
                connection.execute("INSERT INTO recovery_preservation_sentinel VALUES ('synthetic-preserve-me')")
                connection.commit()
            cancelled = subprocess.run([str(RECOVERY)], input='CANCEL\n', text=True, capture_output=True, env=environment, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
            assert cancelled.returncode == 0
            assert not (data / 'admin-recovery-backups').exists()
            for unused in range(4):
                client.post('/api/auth/login', json={'username': 'admin', 'password': 'IncorrectSyntheticCredential123'})
            assert client.post('/api/auth/login', json={'username': 'admin', 'password': 'SyntheticInitialCredential123'}).status_code == 423
            completed = subprocess.run([str(RECOVERY)], input='RESET\n\n', text=True, capture_output=True, env=environment, timeout=45, creationflags=subprocess.CREATE_NO_WINDOW)
            assert completed.returncode == 0, 'Packaged recovery failed (output withheld to protect generated credential)'
            match = re.search(r'Temporary password: (\S+)', completed.stdout)
            assert match is not None
            temporary = match.group(1)
            recovered = client.post('/api/auth/login', json={'username': 'admin', 'password': temporary})
            assert recovered.status_code == 200
            assert recovered.json()['must_reset_password'] is True
            assert client.get('/api/users/me', headers={'Authorization': f'Bearer {previous_token}'}).status_code == 401
            changed = client.post('/api/users/me/change-password', headers={'Authorization': 'Bearer ' + recovered.json()['access_token']}, json={'current_password': temporary, 'new_password': 'SyntheticChosenCredential456'})
            assert changed.status_code == 200
            assert changed.json()['must_reset_password'] is False
            assert client.post('/api/auth/login', json={'username': 'admin', 'password': 'SyntheticChosenCredential456'}).status_code == 200
            assert client.post('/api/auth/login', json={'username': 'admin', 'password': temporary}).status_code == 401
            repeated = subprocess.run([str(RECOVERY)], input='RESET\n\n', text=True, capture_output=True, env=environment, timeout=45, creationflags=subprocess.CREATE_NO_WINDOW)
            assert repeated.returncode == 0
            second_match = re.search(r'Temporary password: (\S+)', repeated.stdout)
            assert second_match is not None
            assert second_match.group(1) != temporary
            assert client.post('/api/auth/login', json={'username': 'admin', 'password': second_match.group(1)}).status_code == 200
            assert client.post('/api/auth/login', json={'username': 'admin', 'password': 'SyntheticChosenCredential456'}).status_code == 401
            assert hashlib.sha256(env_file.read_bytes()).digest() == settings_before
            with closing(sqlite3.connect(database)) as connection:
                assert connection.execute('SELECT value FROM recovery_preservation_sentinel').fetchone()[0] == 'synthetic-preserve-me'
                assert connection.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
            engine = create_engine(f'sqlite:///{database.as_posix()}')
            with Session(engine) as session:
                assert verify_audit_chain(session)[0]
            engine.dispose()
            assert len(list((data / 'admin-recovery-backups').glob('*.sqlite3'))) == 2
    finally:
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, check=False, creationflags=subprocess.CREATE_NO_WINDOW)
        process.wait(timeout=10)
