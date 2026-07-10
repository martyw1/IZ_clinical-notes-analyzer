from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.config import settings
from app.v2.db import SessionLocal, init_database
from app.v2.models import User
from app.v2.security import hash_password, password_policy_error
from app.v2.services.audit_store import record_audit_event


@dataclass(frozen=True, slots=True)
class LocalAdminRecoveryError(RuntimeError):
    reason: str

    def __str__(self) -> str:
        return self.reason


def recover_local_admin(new_password: str) -> None:
    policy_error = password_policy_error(new_password, username=settings.bootstrap_admin_username)
    if policy_error:
        raise LocalAdminRecoveryError(policy_error)
    init_database()
    with SessionLocal() as db:
        administrator = db.execute(
            select(User).where(User.username == settings.bootstrap_admin_username)
        ).scalar_one_or_none()
        if administrator is None or administrator.role != "admin":
            raise LocalAdminRecoveryError("Local administrator account is unavailable")
        administrator.password_hash = hash_password(new_password)
        administrator.password_changed_at = datetime.now(timezone.utc)
        administrator.must_reset_password = True
        administrator.auth_state = "password_change_required"
        administrator.failed_login_attempts = 0
        administrator.is_locked = False
        administrator.locked_until = None
        administrator.recovery_required = True
        db.commit()
        record_audit_event(
            db,
            action="auth.local_admin.recovered",
            actor=administrator,
            target_entity_type="user",
            target_entity_id=str(administrator.id),
            details={"resulting_state": "password_change_required"},
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    new_password = sys.stdin.readline().rstrip("\r\n")
    if not new_password:
        raise LocalAdminRecoveryError("Temporary administrator password is required")
    recover_local_admin(new_password)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
