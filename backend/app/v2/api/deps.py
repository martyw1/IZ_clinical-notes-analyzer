from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.v2.db import get_db
from app.v2.authorization import Role, require_role
from app.v2.models import User
from app.v2.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
DbSession = Annotated[Session, Depends(get_db)]


def current_user(request: Request, token: Annotated[str, Depends(oauth2_scheme)], db: DbSession) -> User:
    username = decode_access_token(token)
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account inactive")
    if user.auth_state == "locked_until" or user.is_locked:
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Account temporarily locked")
    if user.auth_state in {"bootstrap_required", "password_change_required"} and request.url.path not in {
        "/api/users/me",
        "/api/users/me/change-password",
    }:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Password change is required before accessing the workspace")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_admin(user: CurrentUser, db: DbSession) -> User:
    return require_role(db, user, frozenset({Role.ADMIN}), "admin")


AdminUser = Annotated[User, Depends(require_admin)]


def require_manager_or_admin(user: CurrentUser, db: DbSession) -> User:
    return require_role(db, user, frozenset({Role.ADMIN, Role.OFFICE_MANAGER}), "patient_manager")


ManagerUser = Annotated[User, Depends(require_manager_or_admin)]


def close_db_dependency() -> Iterator[Session]:
    yield from get_db()
