from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

from app.v2.security import verify_password


def test_powershell_local_recovery_is_effective_audited_and_write_only(tmp_path: Path) -> None:
    # Given: safe generated local-client configuration and no existing database.
    app_data = tmp_path / "local-app-data"
    app_data.mkdir()
    (app_data / ".env").write_text(
        "\n".join(
            (
                "ENVIRONMENT=local-client",
                "SECRET_KEY=synthetic-secret-key-12345678901234567890",
                "DATA_ENCRYPTION_KEY=synthetic-data-key-12345678901234567890",
                "LOCAL_SQLITE_DB_PATH=clinical-notes-analyzer-v2.sqlite3",
                "BOOTSTRAP_ADMIN_USERNAME=admin",
                "BOOTSTRAP_ADMIN_PASSWORD=SyntheticBootstrapPass123",
            )
        ),
        encoding="utf-8",
    )
    temporary_password = "SyntheticRecoveryPass789"
    root = Path(__file__).resolve().parents[2]

    # When: the authorized PowerShell recovery surface is executed.
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-File",
            str(root / "scripts" / "update-local-admin.ps1"),
            "-Value",
            temporary_password,
            "-AppDataRoot",
            str(app_data),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then: recovery succeeds without echoing the credential and persists audited password-change-required state.
    assert result.returncode == 0, result.stderr
    assert temporary_password not in result.stdout
    assert temporary_password not in result.stderr
    with sqlite3.connect(app_data / "clinical-notes-analyzer-v2.sqlite3") as connection:
        user = connection.execute(
            "SELECT password_hash,auth_state,must_reset_password,is_locked,locked_until FROM users WHERE username='admin'"
        ).fetchone()
        actions = {row[0] for row in connection.execute("SELECT action FROM audit_logs")}
    assert user is not None
    assert verify_password(temporary_password, str(user[0]))
    assert tuple(user[1:]) == ("password_change_required", 1, 0, None)
    assert "auth.local_admin.recovered" in actions
