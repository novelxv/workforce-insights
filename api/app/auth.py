"""Cookie sessions and roles.

HR_ADMIN   every aggregate, individual risk scores, the Power BI extract
HRBP       aggregates and individual scores for their departments only
LEADER     aggregates across the company; never individual scores or names
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.config import get_settings
from app.db import get_conn

COOKIE = "insights_session"


@dataclass(frozen=True)
class Principal:
    user_id: int
    email: str
    role: str
    departments: tuple[str, ...]
    label: str

    @property
    def sees_individuals(self) -> bool:
        return self.role in ("HR_ADMIN", "HRBP")

    @property
    def department_scope(self) -> tuple[str, ...] | None:
        """Departments this person is limited to, or None for the whole company."""
        return self.departments if self.role == "HRBP" else None


def issue(response: Response, user_id: int) -> None:
    s = get_settings()
    token = jwt.encode(
        {"sub": str(user_id), "exp": datetime.now(UTC) + timedelta(minutes=s.jwt_ttl_minutes)},
        s.jwt_secret,
        algorithm="HS256",
    )
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        max_age=s.jwt_ttl_minutes * 60,
    )


def login(conn: Connection, email: str, password: str):
    row = conn.execute(
        text(
            "SELECT id, email, password_hash, role, departments, label FROM users WHERE email = :e"
        ),
        {"e": email.strip().lower()},
    ).first()
    if row is None or not bcrypt.checkpw(password.encode(), row.password_hash.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email or password is incorrect")
    return row


def current(request: Request, conn: Connection = Depends(get_conn)) -> Principal:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    try:
        sub = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])["sub"]
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has ended") from exc
    row = conn.execute(
        text("SELECT id, email, role, departments, label FROM users WHERE id = :i"), {"i": int(sub)}
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account no longer exists")
    return Principal(row.id, row.email, row.role, tuple(row.departments or ()), row.label)


def individuals_allowed(p: Principal = Depends(current)) -> Principal:
    if not p.sees_individuals:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Individual scores are limited to HR")
    return p


def hr_admin(p: Principal = Depends(current)) -> Principal:
    if p.role != "HR_ADMIN":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only HR analytics admins can do this")
    return p
