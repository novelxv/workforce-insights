from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from app import auth
from app.auth import Principal
from app.config import get_settings
from app.db import get_conn

router = APIRouter(prefix="/auth", tags=["auth"])

ROLE_SCOPE = {
    "HR_ADMIN": "Every department, individual risk scores and the Power BI extract.",
    "HRBP": "Claims, Policy Administration, Customer Service and Underwriting, including "
    "individual risk scores for those departments.",
    "LEADER": "Company-wide figures. No individual scores or names.",
}


class LoginIn(BaseModel):
    email: str
    password: str


def _out(p: Principal) -> dict:
    return {
        "email": p.email,
        "role": p.role,
        "label": p.label,
        "departments": list(p.departments),
        "sees_individuals": p.sees_individuals,
        "scope": ROLE_SCOPE[p.role],
    }


@router.post("/login")
def login(body: LoginIn, response: Response, conn: Connection = Depends(get_conn)):
    row = auth.login(conn, body.email, body.password)
    auth.issue(response, row.id)
    return _out(Principal(row.id, row.email, row.role, tuple(row.departments or ()), row.label))


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(auth.COOKIE, path="/")


@router.get("/me")
def me(p: Principal = Depends(auth.current)):
    return _out(p)


@router.get("/demo-accounts")
def demo_accounts():
    """Shown on the sign-in page. Disabled outside demo mode."""
    s = get_settings()
    if not s.demo_mode:
        return {"password": None, "accounts": []}
    return {
        "password": s.demo_password,
        "accounts": [
            {"email": f"{local}@arunikalife.example", "role": role, "scope": ROLE_SCOPE[role]}
            for local, role in (("hr.admin", "HR_ADMIN"), ("hrbp", "HRBP"), ("leader", "LEADER"))
        ],
    }
