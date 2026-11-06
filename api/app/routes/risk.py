"""Attrition risk. Scores are written by the offline pipeline; this only reads them.

Leaders get aggregates. HR admins and HRBPs (for their departments) also get the list of
people, because acting on a score means a conversation with a person, and that is HR's
job, not a line manager's.
"""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.auth import Principal, current, individuals_allowed
from app.config import get_settings
from app.db import get_conn
from app.metrics import catalog

router = APIRouter(prefix="/risk", tags=["risk"])

FEATURE_LABELS = {
    "pay_ratio": "Pay relative to grade midpoint",
    "months_since_promotion": "Time since last promotion",
    "overtime_3m": "Recent overtime",
    "manager_changed_6m": "Recent change of manager",
    "tenure_months": "Tenure",
    "rating": "Performance rating",
    "pay_change_12m": "Pay change over 12 months",
    "department": "Department base rate",
    "location": "Office",
    "on_pkwt": "Fixed-term contract",
    "grade_rank": "Grade",
}


def _latest_run(conn: Connection):
    row = conn.execute(
        text("SELECT version, trained_at, metrics FROM model_runs ORDER BY trained_at DESC LIMIT 1")
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No model has been trained yet")
    return row


@router.get("/summary")
def summary(p: Principal = Depends(current), conn: Connection = Depends(get_conn)):
    run = _latest_run(conn)
    k = get_settings().min_group_size
    cat = catalog(conn)
    scope_sql, params = "", {}
    if p.department_scope is not None:
        scope_sql = " AND h.department_code = ANY(:scope)"
        params["scope"] = list(p.department_scope)
    rows = (
        conn.execute(
            text(
                "SELECT h.department_code AS department, count(*) AS scored,"
                " count(*) FILTER (WHERE s.risk_band = 'high') AS high,"
                " count(*) FILTER (WHERE s.risk_band = 'elevated') AS elevated,"
                " avg(s.probability) AS mean_probability"
                " FROM fact_attrition_score s"
                " JOIN fact_headcount_monthly h"
                "   ON h.employee_id = s.employee_id AND h.month = s.scored_month"
                " WHERE s.scored_month = (SELECT max(scored_month) FROM fact_attrition_score)"
                f"{scope_sql} GROUP BY 1"
            ),
            params,
        )
        .mappings()
        .all()
    )
    departments = []
    for r in rows:
        small = r["scored"] < k
        departments.append(
            {
                "department": r["department"],
                "department_label": cat.label("department", r["department"]),
                "scored": r["scored"],
                "suppressed": small,
                "high": None if small else r["high"],
                "elevated": None if small else r["elevated"],
                "high_share": None if small else round(r["high"] / r["scored"], 4),
                "mean_probability": None if small else round(float(r["mean_probability"]), 4),
            }
        )
    departments.sort(key=lambda d: (d["high_share"] is None, -(d["high_share"] or 0)))

    drivers = Counter()
    flagged = 0
    for (items,) in conn.execute(
        text(
            "SELECT s.drivers FROM fact_attrition_score s"
            " JOIN fact_headcount_monthly h"
            "   ON h.employee_id = s.employee_id AND h.month = s.scored_month"
            " WHERE s.scored_month = (SELECT max(scored_month) FROM fact_attrition_score)"
            f" AND s.risk_band IN ('high', 'elevated'){scope_sql}"
        ),
        params,
    ):
        flagged += 1
        for d in items:
            drivers[d["feature"]] += 1
    scored_month = conn.execute(text("SELECT max(scored_month) FROM fact_attrition_score")).scalar()
    return {
        "model_version": run.version,
        "scored_month": scored_month.isoformat() if scored_month else None,
        "horizon_months": 6,
        "scored": sum(r["scored"] for r in rows),
        "high": sum(r["high"] for r in rows),
        "elevated": sum(r["elevated"] for r in rows),
        "flagged": flagged,
        "departments": departments,
        "drivers": [
            {
                "feature": f,
                "label": FEATURE_LABELS.get(f, f),
                "count": n,
                "share": round(n / flagged, 4) if flagged else None,
            }
            for f, n in drivers.most_common()
        ],
        "test_metrics": {
            "roc_auc": run.metrics.get("roc_auc"),
            "pr_auc": run.metrics.get("pr_auc"),
            "base_rate": run.metrics.get("base_rate"),
            "top_10pct": (run.metrics.get("point_in_time") or {}).get("top_10pct"),
        },
        "scope": list(p.department_scope) if p.department_scope is not None else None,
    }


@router.get("/employees")
def employees(
    band: str = Query("flagged", pattern="^(high|elevated|flagged|all)$"),
    department: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    p: Principal = Depends(individuals_allowed),
    conn: Connection = Depends(get_conn),
):
    params: dict = {"limit": limit}
    where = ["s.scored_month = (SELECT max(scored_month) FROM fact_attrition_score)"]
    if band == "flagged":
        where.append("s.risk_band IN ('high', 'elevated')")
    elif band != "all":
        where.append("s.risk_band = :band")
        params["band"] = band
    if p.department_scope is not None:
        if department and department not in p.department_scope:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Outside your departments")
        where.append("h.department_code = ANY(:scope)")
        params["scope"] = list(p.department_scope)
    if department:
        where.append("h.department_code = :dept")
        params["dept"] = department
    cat = catalog(conn)
    rows = (
        conn.execute(
            text(
                "SELECT e.employee_no, e.full_name, h.department_code, h.location_code, h.grade,"
                " h.tenure_months, h.employment_type, s.probability, s.risk_band, s.drivers"
                " FROM fact_attrition_score s"
                " JOIN fact_headcount_monthly h"
                "   ON h.employee_id = s.employee_id AND h.month = s.scored_month"
                " JOIN dim_employee e ON e.employee_key = h.employee_key"
                f" WHERE {' AND '.join(where)}"
                " ORDER BY s.probability DESC, e.employee_no LIMIT :limit"
            ),
            params,
        )
        .mappings()
        .all()
    )
    return {
        "employees": [
            {
                "employee_no": r["employee_no"],
                "name": r["full_name"],
                "department": r["department_code"],
                "department_label": cat.label("department", r["department_code"]),
                "location": cat.label("location", r["location_code"]),
                "grade": r["grade"],
                "tenure_months": r["tenure_months"],
                "employment_type": r["employment_type"],
                "probability": float(r["probability"]),
                "band": r["risk_band"],
                "drivers": r["drivers"],
            }
            for r in rows
        ],
        "note": (
            "A score is a prompt for a conversation about pay, workload or career, not an "
            "input to performance, promotion or disciplinary decisions."
        ),
    }


model_router = APIRouter(tags=["model"])


@model_router.get("/model")
def model_card(p: Principal = Depends(current), conn: Connection = Depends(get_conn)):
    row = (
        conn.execute(
            text(
                "SELECT version, trained_at, metrics, fairness, importance, calibration, notes"
                " FROM model_runs ORDER BY trained_at DESC LIMIT 1"
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No model has been trained yet")
    importance = [
        {**i, "label": FEATURE_LABELS.get(i["feature"], i["feature"])} for i in row["importance"]
    ]
    return {**row, "trained_at": row["trained_at"].isoformat(), "importance": importance}
