"""End-to-end through the HTTP layer against a built warehouse.

Needs TEST_DATABASE_URL pointing at a database loaded by `python -m pipeline.build`
(CI builds one in a Postgres service container). Skipped otherwise.
"""

import io
import os
import zipfile

import pytest

if not os.environ.get("TEST_DATABASE_URL"):
    pytest.skip("TEST_DATABASE_URL not set", allow_module_level=True)
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

from fastapi.testclient import TestClient  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

from app.main import app  # noqa: E402

PASSWORD = os.environ.get("DEMO_PASSWORD", "arunika-demo")


def client(email: str | None) -> TestClient:
    c = TestClient(app)
    if email:
        r = c.post("/auth/login", json={"email": email, "password": PASSWORD})
        assert r.status_code == 200, r.text
    return c


@pytest.fixture(scope="module")
def admin():
    return client("hr.admin@arunikalife.example")


@pytest.fixture(scope="module")
def hrbp():
    return client("hrbp@arunikalife.example")


@pytest.fixture(scope="module")
def leader():
    return client("leader@arunikalife.example")


def test_sign_in_is_required():
    anon = client(None)
    assert anon.get("/dashboard").status_code == 401
    assert (
        anon.post(
            "/auth/login", json={"email": "hr.admin@arunikalife.example", "password": "wrong"}
        ).status_code
        == 401
    )


def test_dashboard_kpis_agree_with_the_query_endpoint(admin):
    d = admin.get("/dashboard").json()
    kpi = {k["key"]: k for k in d["kpis"]}
    q = admin.post(
        "/query",
        json={
            "metric": "voluntary_turnover_rate",
            "period": {"start": d["period"]["start"], "end": d["period"]["end"]},
        },
    ).json()
    assert q["rows"][0]["value"] == kpi["voluntary_turnover_rate"]["value"]
    assert 0.05 < kpi["voluntary_turnover_rate"]["value"] < 0.35
    assert kpi["headcount"]["value"] > 500


def test_hrbp_sees_only_their_departments(hrbp):
    d = hrbp.get("/dashboard").json()
    depts = {r["department"] for r in d["turnover_by_department"]["rows"]}
    assert depts == {"CLM", "POL", "CSV", "UW"}
    r = hrbp.post(
        "/query",
        json={
            "metric": "headcount",
            "filters": [{"dimension": "department", "values": ["ITD"]}],
            "period": {"start": "2026-01", "end": "2026-01"},
        },
    )
    assert r.status_code == 422


def test_individual_scores_are_hr_only(admin, hrbp, leader):
    assert leader.get("/risk/employees").status_code == 403
    assert hrbp.get("/risk/employees?department=ITD").status_code == 403
    people = hrbp.get("/risk/employees?band=all&limit=500").json()["employees"]
    assert people and {p["department"] for p in people} <= {"CLM", "POL", "CSV", "UW"}
    top = admin.get("/risk/employees?band=high").json()["employees"]
    assert top[0]["probability"] >= top[-1]["probability"]
    assert all(len(p["drivers"]) <= 3 for p in top)


def test_leader_gets_risk_aggregates(leader):
    s = leader.get("/risk/summary").json()
    assert s["scored"] > 500
    assert s["high"] == pytest.approx(s["scored"] * 0.1, abs=1)


def test_ask_answers_logs_and_refuses(leader, admin):
    ok = leader.post("/ask", json={"question": "Voluntary turnover by department"}).json()
    assert ok["status"] == "ok" and len(ok["result"]["rows"]) > 5
    assert "SELECT" in ok["result"]["sql"]
    no = leader.post("/ask", json={"question": "Which employees will resign?"}).json()
    assert no["status"] == "unsupported"


def test_small_groups_are_suppressed_end_to_end(admin):
    r = admin.post(
        "/query",
        json={
            "metric": "headcount",
            "dimensions": ["department", "gender"],
            "filters": [{"dimension": "division", "values": ["Governance"]}],
            "period": {"start": "2026-10", "end": "2026-10"},
        },
    ).json()
    for row in r["rows"]:
        if row["population"] < 5:
            assert row["value"] is None and row["suppressed"]


def test_cohort_checkpoints_not_yet_reached_are_empty(admin):
    c = admin.get("/cohorts").json()
    last = c["cohorts"][-1]
    assert last["points"][-1]["retained"] is None
    first = c["cohorts"][0]
    values = [p["retained"] for p in first["points"] if p["retained"] is not None]
    assert values == sorted(values, reverse=True)  # retention never rises


def test_excel_report_opens_and_has_the_expected_sheets(hrbp):
    r = hrbp.get("/exports/monthly-report.xlsx")
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Summary", "Trend", "Departments", "Definitions"]
    assert "Claims" in wb["Summary"]["A2"].value  # HRBP scope is printed
    assert len(wb["Trend"]._charts) == 2 and len(wb["Departments"]._charts) == 1


def test_powerbi_extract_is_admin_only_and_pseudonymous(admin, leader):
    assert leader.get("/exports/powerbi.zip").status_code == 403
    z = zipfile.ZipFile(io.BytesIO(admin.get("/exports/powerbi.zip").content))
    names = {n.split("/")[-1] for n in z.namelist()}
    assert {"fact_headcount_monthly.csv", "measures.dax", "README.md"} <= names
    header = z.read("arunika-workforce/dim_employee.csv").decode().splitlines()[0]
    assert "full_name" not in header and "birth_date" not in header
    fact = z.read("arunika-workforce/fact_headcount_monthly.csv").decode().splitlines()[0]
    assert "salary" not in fact.split(",")
