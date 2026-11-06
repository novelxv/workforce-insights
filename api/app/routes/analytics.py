from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app import ask
from app.auth import Principal, current
from app.config import get_settings
from app.db import get_conn
from app.metrics import (
    DIMENSIONS,
    METRICS,
    Period,
    Spec,
    SpecError,
    add_months,
    catalog,
    run,
)

router = APIRouter(tags=["analytics"])


def _spec_error(exc: SpecError) -> HTTPException:
    return HTTPException(
        422,
        {"message": exc.message, "suggestions": exc.suggestions},
    )


@router.get("/meta")
def meta(p: Principal = Depends(current), conn: Connection = Depends(get_conn)):
    """The semantic layer as the client sees it: metrics with their definitions,
    dimensions with the values the caller may use, and the months with data."""
    cat = catalog(conn)
    domains = dict(cat.domains)
    if p.department_scope is not None:
        domains["department"] = {
            k: v for k, v in domains["department"].items() if k in p.department_scope
        }
    return {
        "first_month": cat.first_month.isoformat(),
        "last_month": cat.last_month.isoformat(),
        "min_group_size": get_settings().min_group_size,
        "scope": list(p.department_scope) if p.department_scope is not None else None,
        "metrics": [
            {
                "key": m.key,
                "label": m.label,
                "unit": m.unit,
                "definition": m.definition,
                "formula": m.formula,
                "point_in_time": m.stock,
                "higher_is_better": m.higher_is_better,
            }
            for m in METRICS.values()
        ],
        "dimensions": [
            {
                "key": d.key,
                "label": d.label,
                "time": d.time,
                "values": None
                if d.time
                else [{"code": c, "label": lbl} for c, lbl in domains.get(d.key, {}).items()],
            }
            for d in DIMENSIONS.values()
        ],
        "examples": ask.EXAMPLES,
    }


@router.post("/query")
def query(spec: Spec, p: Principal = Depends(current), conn: Connection = Depends(get_conn)):
    try:
        result = run(
            conn, spec, scope=p.department_scope, min_group_size=get_settings().min_group_size
        )
    except SpecError as exc:
        raise _spec_error(exc) from exc
    return result.as_dict()


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=300)


@router.post("/ask")
def ask_question(
    body: AskIn, p: Principal = Depends(current), conn: Connection = Depends(get_conn)
):
    cat = catalog(conn)
    parsed = ask.parse(body.question, cat.last_month, cat.first_month, cat.domains)
    response: dict = {"question": body.question, "parser": parsed.parser}
    error: str | None = None
    if parsed.unsupported:
        response |= {
            "status": "unsupported",
            "message": parsed.unsupported,
            "suggestions": ask.EXAMPLES[:4],
        }
        error = parsed.unsupported
    else:
        try:
            spec = Spec.model_validate(parsed.spec)
            result = run(
                conn, spec, scope=p.department_scope, min_group_size=get_settings().min_group_size
            )
            response |= {"status": "ok", "result": result.as_dict()}
        except (SpecError, ValueError) as exc:
            message = exc.message if isinstance(exc, SpecError) else "Could not read that question"
            suggestions = exc.suggestions if isinstance(exc, SpecError) else ask.EXAMPLES[:4]
            response |= {
                "status": "invalid",
                "message": message,
                "suggestions": suggestions,
                "spec": parsed.spec,
            }
            error = message
    conn.execute(
        text(
            "INSERT INTO ask_log (user_email, question, parser, spec, ok, error)"
            " VALUES (:u, :q, :p, CAST(:s AS jsonb), :ok, :e)"
        ),
        {
            "u": p.email,
            "q": body.question,
            "p": parsed.parser,
            "s": json.dumps(parsed.spec) if parsed.spec else None,
            "ok": error is None,
            "e": error,
        },
    )
    conn.commit()
    return response


# --- Dashboard ----------------------------------------------------------------------------

KPIS = [
    "headcount",
    "hires",
    "voluntary_turnover_rate",
    "early_exit_share",
    "avg_tenure_years",
    "female_share",
]


@router.get("/dashboard")
def dashboard(p: Principal = Depends(current), conn: Connection = Depends(get_conn)):
    """Last 12 months against the 12 before, plus the breakdowns on the overview page."""
    cat = catalog(conn)
    k = get_settings().min_group_size
    end = cat.last_month
    cur = Period(start=add_months(end, -11), end=end)
    prev = Period(start=add_months(end, -23), end=add_months(end, -12))
    trend = Period(start=max(cat.first_month, add_months(end, -23)), end=end)

    def q(metric: str, period: Period, dims: list[str] | None = None, order=None) -> dict:
        spec = Spec(metric=metric, dimensions=dims or [], period=period, order=order)
        return run(conn, spec, scope=p.department_scope, min_group_size=k).as_dict()

    kpis = []
    for key in KPIS:
        now = q(key, cur)
        before = q(key, prev) if prev.end >= cat.first_month else None
        m = METRICS[key]
        kpis.append(
            {
                "key": key,
                "label": m.label,
                "unit": m.unit,
                "definition": m.definition,
                "higher_is_better": m.higher_is_better,
                "value": now["rows"][0]["value"],
                "previous": before["rows"][0]["value"] if before else None,
                "period": now["description"],
            }
        )
    return {
        "period": {"start": cur.start.isoformat(), "end": cur.end.isoformat()},
        "previous_period": {"start": prev.start.isoformat(), "end": prev.end.isoformat()},
        "scope": list(p.department_scope) if p.department_scope is not None else None,
        "kpis": kpis,
        "headcount_trend": q("headcount", trend, ["month"]),
        "resignations_trend": q("voluntary_exits", trend, ["month"]),
        "hires_trend": q("hires", trend, ["month"]),
        "turnover_by_department": q("voluntary_turnover_rate", cur, ["department"], "value_desc"),
        "turnover_by_tenure": q("voluntary_turnover_rate", cur, ["tenure_band"]),
        "turnover_by_age": q("voluntary_turnover_rate", cur, ["age_band"]),
    }


# --- Cohort retention ---------------------------------------------------------------------

CHECKPOINTS = [3, 6, 9, 12, 18, 24]


def _months_between(later: date, earlier: date) -> int:
    return (later.year - earlier.year) * 12 + later.month - earlier.month


def _anniversary(d: date, months: int) -> date:
    first = add_months(d, months)
    last_day = (add_months(first, 1) - first).days
    return first.replace(day=min(d.day, last_day))


@router.get("/cohorts")
def cohorts(p: Principal = Depends(current), conn: Connection = Depends(get_conn)):
    """Share of each quarter's hires still employed 3, 6, 9, 12, 18 and 24 months later.
    A checkpoint that has not been reached yet for a cohort is left empty, not zero."""
    cat = catalog(conn)
    k = get_settings().min_group_size
    sql = (
        "SELECT DISTINCT ON (e.employee_id) e.employee_id, e.hire_date, e.exit_date"
        " FROM fact_movement m JOIN dim_employee e ON e.employee_id = m.employee_id"
        " WHERE m.type = 'hire' AND m.date >= :first"
    )
    # Cohorts start after the simulation's warm-up months, like every other figure.
    params: dict = {"first": cat.first_month}
    if p.department_scope is not None:
        sql += " AND m.to_department = ANY(:scope)"
        params["scope"] = list(p.department_scope)
    groups: dict[date, list[tuple[date, date | None]]] = {}
    for r in conn.execute(text(sql), params):
        q_start = date(r.hire_date.year, (r.hire_date.month - 1) // 3 * 3 + 1, 1)
        groups.setdefault(q_start, []).append((r.hire_date, r.exit_date))

    latest = cat.last_month
    out = []
    pooled: dict[int, list[int]] = {c: [0, 0] for c in CHECKPOINTS}
    for q_start in sorted(groups):
        members = groups[q_start]
        q_end = add_months(q_start, 2)
        points = []
        for c in CHECKPOINTS:
            # Observable only once every member of the cohort has had c months.
            if _months_between(latest, q_end) < c:
                points.append({"months": c, "retained": None})
                continue
            stayed = sum(
                1 for hire, exit_ in members if exit_ is None or exit_ >= _anniversary(hire, c)
            )
            pooled[c][0] += stayed
            pooled[c][1] += len(members)
            points.append(
                {
                    "months": c,
                    "retained": None if len(members) < k else round(stayed / len(members), 4),
                }
            )
        out.append(
            {
                "cohort": q_start.isoformat(),
                "label": f"Q{(q_start.month - 1) // 3 + 1} {q_start.year}",
                "hires": len(members),
                "suppressed": len(members) < k,
                "points": points,
            }
        )
    return {
        "checkpoints": CHECKPOINTS,
        "cohorts": out,
        "pooled": [
            {"months": c, "retained": round(s / n, 4) if n >= k else None, "hires": n}
            for c, (s, n) in pooled.items()
        ],
        "scope": list(p.department_scope) if p.department_scope is not None else None,
    }
