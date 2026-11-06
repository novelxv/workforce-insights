"""The semantic layer.

Every number the dashboard, the Ask box and the Excel report show is one of the metrics
below, computed by one compiler over `fact_headcount_monthly`. "Turnover" therefore means
the same thing on every screen, and nobody (including the language model behind Ask)
writes SQL: a question becomes a `Spec`, the spec is checked against this catalogue, and
the compiler emits a parameterised query from whitelisted fragments.

Small groups are suppressed: a value based on fewer than `min_group_size` people is
withheld, and for additive metrics a second cell is withheld when exactly one would be,
so the hidden value cannot be recovered by subtracting the visible ones from a total.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.engine import Connection

Unit = Literal["count", "percent", "years", "hours", "ratio"]


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    unit: Unit
    definition: str
    formula: str
    value: str  # SQL aggregate over h (fact_headcount_monthly)
    population: str  # SQL aggregate: how many people the value rests on
    stock: bool = False  # measured at the end of the period, not summed across it
    additive: bool = False  # counts that add up across groups
    higher_is_better: bool | None = None
    synonyms: tuple[str, ...] = ()


ACTIVE = "COUNT(*) FILTER (WHERE h.active_eom)"
PEOPLE = "COUNT(DISTINCT h.employee_id)"

METRICS: dict[str, Metric] = {
    m.key: m
    for m in [
        Metric(
            "headcount",
            "Headcount",
            "count",
            "Employees on the payroll on the last day of the period.",
            "count of employees active at month end, in the last month of the period",
            ACTIVE,
            ACTIVE,
            stock=True,
            additive=True,
            synonyms=(
                "headcount",
                "head count",
                "fte",
                "workforce size",
                "jumlah karyawan",
                "number of employees",
                "size of the workforce",
            ),
        ),
        Metric(
            "hires",
            "Hires",
            "count",
            "People who joined during the period.",
            "count of employee-months flagged as the hire month",
            "COUNT(*) FILTER (WHERE h.hired)",
            PEOPLE,
            additive=True,
            synonyms=(
                "hires",
                "hired",
                "new joiners",
                "joiners",
                "recruits",
                "new hires",
                "onboarded",
                "rekrutmen",
            ),
        ),
        Metric(
            "exits",
            "Exits",
            "count",
            "People who left for any reason: resignation, dismissal, contract end or retirement.",
            "count of employee-months flagged as the exit month",
            "COUNT(*) FILTER (WHERE h.exited)",
            PEOPLE,
            additive=True,
            higher_is_better=False,
            synonyms=("exits", "leavers", "left", "separations", "terminations", "departures"),
        ),
        Metric(
            "voluntary_exits",
            "Resignations",
            "count",
            "People who resigned. Excludes dismissals, contract ends and retirement.",
            "count of exits with exit type 'voluntary'",
            "COUNT(*) FILTER (WHERE h.exited AND h.exit_type = 'voluntary')",
            PEOPLE,
            additive=True,
            higher_is_better=False,
            synonyms=(
                "resignations",
                "resigned",
                "voluntary exits",
                "voluntary leavers",
                "quit",
                "quits",
                "resign",
            ),
        ),
        Metric(
            "turnover_rate",
            "Turnover rate",
            "percent",
            "Exits for any reason relative to average headcount, annualised so periods of "
            "different length compare.",
            "exits / average monthly headcount × 12 / months in period",
            f"12.0 * COUNT(*) FILTER (WHERE h.exited) / NULLIF({ACTIVE}, 0)",
            PEOPLE,
            higher_is_better=False,
            synonyms=("turnover", "attrition", "churn", "turnover rate", "attrition rate"),
        ),
        Metric(
            "voluntary_turnover_rate",
            "Voluntary turnover rate",
            "percent",
            "Resignations relative to average headcount, annualised. The figure most "
            "retention targets are set against.",
            "resignations / average monthly headcount × 12 / months in period",
            "12.0 * COUNT(*) FILTER (WHERE h.exited AND h.exit_type = 'voluntary')"
            f" / NULLIF({ACTIVE}, 0)",
            PEOPLE,
            higher_is_better=False,
            synonyms=(
                "voluntary turnover",
                "voluntary attrition",
                "resignation rate",
                "regretted attrition",
                "quit rate",
            ),
        ),
        Metric(
            "early_exit_share",
            "First-year exits",
            "percent",
            "Share of all exits that happened in the person's first 12 months. A high value "
            "points at hiring or onboarding rather than at pay or careers.",
            "exits with tenure under 12 months / all exits",
            "COUNT(*) FILTER (WHERE h.exited AND h.tenure_months < 12)::numeric"
            " / NULLIF(COUNT(*) FILTER (WHERE h.exited), 0)",
            "COUNT(*) FILTER (WHERE h.exited)",
            higher_is_better=False,
            synonyms=(
                "first year attrition",
                "first-year attrition",
                "early attrition",
                "early exits",
                "new hire turnover",
                "first year exits",
            ),
        ),
        Metric(
            "promotion_rate",
            "Promotion rate",
            "percent",
            "Promotions relative to average headcount, annualised.",
            "promotions / average monthly headcount × 12 / months in period",
            f"12.0 * COUNT(*) FILTER (WHERE h.promoted) / NULLIF({ACTIVE}, 0)",
            PEOPLE,
            synonyms=("promotion rate", "rate of promotion"),
        ),
        Metric(
            "promotions",
            "Promotions",
            "count",
            "Moves up at least one grade during the period.",
            "count of employee-months flagged as a promotion",
            "COUNT(*) FILTER (WHERE h.promoted)",
            PEOPLE,
            additive=True,
            synonyms=("promotions", "promoted", "promotion", "promosi"),
        ),
        Metric(
            "transfers",
            "Internal transfers",
            "count",
            "Moves into a department from another department.",
            "count of employee-months flagged as a transfer in",
            "COUNT(*) FILTER (WHERE h.transferred)",
            PEOPLE,
            additive=True,
            synonyms=("transfers", "internal moves", "mutations", "mutasi", "moved"),
        ),
        Metric(
            "avg_tenure_years",
            "Average tenure",
            "years",
            "Average length of service of the people on payroll at the end of the period.",
            "mean of tenure in months / 12, employees active at the last month end",
            "AVG(h.tenure_months) FILTER (WHERE h.active_eom) / 12.0",
            ACTIVE,
            stock=True,
            synonyms=("tenure", "length of service", "years of service", "masa kerja", "how long"),
        ),
        Metric(
            "female_share",
            "Women in workforce",
            "percent",
            "Share of headcount who are women, at the end of the period.",
            "women active at month end / headcount",
            "AVG((h.gender = 'F')::int) FILTER (WHERE h.active_eom)",
            ACTIVE,
            stock=True,
            synonyms=(
                "female share",
                "women",
                "female",
                "gender ratio",
                "gender balance",
                "gender split",
                "percentage of women",
                "female representation",
            ),
        ),
        Metric(
            "pkwt_share",
            "Fixed-term share",
            "percent",
            "Share of headcount on fixed-term contracts (PKWT), at the end of the period.",
            "employees on PKWT active at month end / headcount",
            "AVG((h.employment_type = 'PKWT')::int) FILTER (WHERE h.active_eom)",
            ACTIVE,
            stock=True,
            synonyms=(
                "pkwt share",
                "fixed-term share",
                "contract staff",
                "contractors",
                "fixed term",
                "kontrak",
            ),
        ),
        Metric(
            "compa_ratio",
            "Compa-ratio",
            "ratio",
            "Average salary as a multiple of the grade-band midpoint (1.00 = at midpoint), "
            "at the end of the period.",
            "mean of salary / grade midpoint, employees active at the last month end",
            "AVG(h.pay_ratio) FILTER (WHERE h.active_eom)",
            ACTIVE,
            stock=True,
            synonyms=(
                "compa ratio",
                "compa-ratio",
                "pay ratio",
                "pay vs midpoint",
                "pay positioning",
                "salary vs band",
            ),
        ),
        Metric(
            "avg_overtime_hours",
            "Overtime per person",
            "hours",
            "Average overtime hours per employee per month across the period.",
            "mean of monthly overtime hours over employee-months",
            "AVG(h.overtime_hours)",
            PEOPLE,
            higher_is_better=False,
            synonyms=("overtime", "lembur", "overtime hours", "extra hours"),
        ),
    ]
}


@dataclass(frozen=True)
class Dimension:
    key: str
    label: str
    expr: str
    time: bool = False
    period_end: str | None = None  # for quarter/year: the last month of each bucket
    synonyms: tuple[str, ...] = ()


DIMENSIONS: dict[str, Dimension] = {
    d.key: d
    for d in [
        Dimension(
            "department",
            "Department",
            "h.department_code",
            synonyms=(
                "department",
                "departments",
                "dept",
                "team",
                "teams",
                "unit",
                "function",
                "departemen",
                "divisi",
            ),
        ),
        Dimension(
            "division",
            "Division",
            "dd.division",
            synonyms=("division", "divisions", "business unit", "directorate"),
        ),
        Dimension(
            "location",
            "Office",
            "h.location_code",
            synonyms=(
                "location",
                "locations",
                "office",
                "offices",
                "branch",
                "branches",
                "city",
                "cities",
                "region",
                "site",
                "kota",
                "cabang",
            ),
        ),
        Dimension(
            "grade",
            "Grade",
            "h.grade",
            synonyms=("grade", "grades", "level", "levels", "band", "seniority"),
        ),
        Dimension(
            "gender",
            "Gender",
            "h.gender::text",
            synonyms=("gender", "sex", "men and women", "male and female"),
        ),
        Dimension(
            "age_band",
            "Age band",
            "h.age_band",
            synonyms=("age", "age band", "age group", "age groups", "generation", "usia"),
        ),
        Dimension(
            "tenure_band",
            "Tenure band",
            "h.tenure_band",
            synonyms=("tenure", "tenure band", "length of service", "years of service"),
        ),
        Dimension(
            "employment_type",
            "Contract type",
            "h.employment_type",
            synonyms=(
                "contract type",
                "employment type",
                "pkwt",
                "contract",
                "permanent vs fixed-term",
                "status",
            ),
        ),
        Dimension(
            "month",
            "Month",
            "h.month",
            time=True,
            synonyms=("month", "monthly", "per month", "each month", "over time", "trend", "bulan"),
        ),
        Dimension(
            "quarter",
            "Quarter",
            "date_trunc('quarter', h.month)::date",
            time=True,
            period_end="(date_trunc('quarter', h.month) + interval '2 months')::date",
            synonyms=("quarter", "quarterly", "per quarter", "each quarter"),
        ),
        Dimension(
            "year",
            "Year",
            "date_trunc('year', h.month)::date",
            time=True,
            period_end="(date_trunc('year', h.month) + interval '11 months')::date",
            synonyms=("year", "yearly", "annual", "per year", "each year", "tahun"),
        ),
    ]
}

STATIC_DOMAINS: dict[str, dict[str, str]] = {
    "gender": {"F": "Women", "M": "Men"},
    "age_band": {b: b for b in ("<25", "25-34", "35-44", "45-54", "55+")},
    "tenure_band": {b: b for b in ("<1y", "1-3y", "3-5y", "5-10y", "10y+")},
    "employment_type": {"PKWT": "Fixed-term (PKWT)", "PKWTT": "Permanent (PKWTT)"},
}


# --- Catalogue: the values each dimension can take, and the months with data -------------


@dataclass
class Catalog:
    domains: dict[str, dict[str, str]]  # dimension -> {code: label}
    first_month: date
    last_month: date
    loaded_at: float = field(default_factory=time.monotonic)

    def label(self, dimension: str, value) -> str:
        if isinstance(value, date):
            if dimension == "quarter":
                return f"Q{(value.month - 1) // 3 + 1} {value.year}"
            if dimension == "year":
                return str(value.year)
            return value.strftime("%b %Y")
        return self.domains.get(dimension, {}).get(str(value), str(value))


_catalog: Catalog | None = None


def catalog(conn: Connection, max_age: float = 600) -> Catalog:
    global _catalog
    if _catalog is not None and time.monotonic() - _catalog.loaded_at < max_age:
        return _catalog
    domains = {k: dict(v) for k, v in STATIC_DOMAINS.items()}
    domains["department"] = {
        r.code: r.name for r in conn.execute(text("SELECT code, name FROM dim_department"))
    }
    domains["division"] = {
        r.division: r.division
        for r in conn.execute(text("SELECT DISTINCT division FROM dim_department ORDER BY 1"))
    }
    domains["location"] = {
        r.code: r.name for r in conn.execute(text("SELECT code, name FROM dim_location"))
    }
    domains["grade"] = {
        r.code: r.code for r in conn.execute(text("SELECT code FROM dim_grade ORDER BY rank"))
    }
    first, last = conn.execute(text("SELECT min(month), max(month) FROM dim_month")).one()
    # The simulation starts from an existing workforce: its first two months have exits
    # but no backfill hires yet. Analysis starts after that warm-up.
    first = add_months(first, 2)
    _catalog = Catalog(domains, first, last)
    return _catalog


def reset_catalog() -> None:
    global _catalog
    _catalog = None


# --- Spec ---------------------------------------------------------------------------------


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


def _month(value) -> date:
    if isinstance(value, date):
        return value.replace(day=1)
    s = str(value)
    return date(int(s[:4]), int(s[5:7]), 1)


class Filter(BaseModel):
    dimension: str
    values: list[str] = Field(min_length=1, max_length=20)


class Period(BaseModel):
    start: date
    end: date

    @field_validator("start", "end", mode="before")
    @classmethod
    def first_of_month(cls, v):
        return _month(v)


class Spec(BaseModel):
    metric: str
    dimensions: list[str] = Field(default_factory=list, max_length=2)
    filters: list[Filter] = Field(default_factory=list, max_length=6)
    period: Period
    order: Literal["value_desc", "value_asc"] | None = None
    limit: int | None = Field(default=None, ge=1, le=50)


class SpecError(ValueError):
    def __init__(self, message: str, suggestions: list[str] | None = None):
        super().__init__(message)
        self.message = message
        self.suggestions = suggestions or []


def check(spec: Spec, cat: Catalog, scope: tuple[str, ...] | None = None) -> Spec:
    """Validate a spec against the catalogue and the caller's scope; clamp the period."""
    if spec.metric not in METRICS:
        raise SpecError(f"'{spec.metric}' is not a defined metric", list(METRICS)[:6])
    for d in spec.dimensions:
        if d not in DIMENSIONS:
            raise SpecError(f"'{d}' is not a dimension", list(DIMENSIONS))
    if len(set(spec.dimensions)) != len(spec.dimensions):
        raise SpecError("A dimension is listed twice")
    if sum(DIMENSIONS[d].time for d in spec.dimensions) > 1:
        raise SpecError("Use one time dimension at a time (month, quarter or year)")
    seen: set[str] = set()
    for f in spec.filters:
        if f.dimension not in DIMENSIONS or DIMENSIONS[f.dimension].time:
            raise SpecError(
                f"Cannot filter on '{f.dimension}'. Use the period for time.",
                [d for d in DIMENSIONS if not DIMENSIONS[d].time],
            )
        if f.dimension in seen:
            raise SpecError(f"'{f.dimension}' is filtered twice")
        seen.add(f.dimension)
        domain = cat.domains[f.dimension]
        unknown = [v for v in f.values if v not in domain]
        if unknown:
            raise SpecError(
                f"Unknown {DIMENSIONS[f.dimension].label.lower()}: {', '.join(unknown)}",
                list(domain)[:20],
            )
        if f.dimension == "department" and scope is not None:
            outside = [v for v in f.values if v not in scope]
            if outside:
                raise SpecError(f"Outside your departments: {', '.join(outside)}", list(scope))
    start = max(spec.period.start, cat.first_month)
    end = min(spec.period.end, cat.last_month)
    if start > end:
        raise SpecError(
            f"No data for that period. Data covers {cat.first_month:%b %Y} to "
            f"{cat.last_month:%b %Y}."
        )
    return spec.model_copy(update={"period": Period(start=start, end=end)})


# --- Compiler -----------------------------------------------------------------------------


@dataclass
class Compiled:
    sql: str
    params: dict


def compile_spec(spec: Spec, scope: tuple[str, ...] | None = None) -> Compiled:
    m = METRICS[spec.metric]
    params: dict = {"start": spec.period.start, "end": spec.period.end}
    cols = [f"{DIMENSIONS[d].expr} AS d{i}" for i, d in enumerate(spec.dimensions)]
    where = ["h.month BETWEEN :start AND :end"]
    if m.stock:
        time_dim = next((d for d in spec.dimensions if DIMENSIONS[d].time), None)
        if time_dim is None:
            where.append("h.month = :end")
        elif DIMENSIONS[time_dim].period_end:
            where.append(f"h.month = LEAST({DIMENSIONS[time_dim].period_end}, :end)")
    for j, f in enumerate(spec.filters):
        where.append(f"{DIMENSIONS[f.dimension].expr} = ANY(:f{j})")
        params[f"f{j}"] = list(f.values)
    if scope is not None:
        where.append("h.department_code = ANY(:scope)")
        params["scope"] = list(scope)
    sql = (
        f"SELECT {', '.join([*cols, f'{m.value} AS value', f'{m.population} AS population'])}\n"
        "FROM fact_headcount_monthly h\n"
        "JOIN dim_department dd ON dd.code = h.department_code\n"
        "WHERE " + "\n  AND ".join(where)
    )
    if spec.dimensions:
        group = ", ".join(f"d{i}" for i in range(len(spec.dimensions)))
        sql += f"\nGROUP BY {group}\nORDER BY {group}"
    return Compiled(sql, params)


# --- Execution and suppression ------------------------------------------------------------


@dataclass
class Result:
    spec: Spec
    metric: Metric
    rows: list[dict]
    suppressed: int
    sql: str
    params: dict
    description: str

    def as_dict(self) -> dict:
        m = self.metric
        return {
            "spec": self.spec.model_dump(mode="json"),
            "description": self.description,
            "metric": {
                "key": m.key,
                "label": m.label,
                "unit": m.unit,
                "definition": m.definition,
                "formula": m.formula,
                "higher_is_better": m.higher_is_better,
            },
            "dimensions": [{"key": d, "label": DIMENSIONS[d].label} for d in self.spec.dimensions],
            "rows": self.rows,
            "suppressed": self.suppressed,
            "sql": self.sql,
            "params": {
                k: (v.isoformat() if isinstance(v, date) else v) for k, v in self.params.items()
            },
        }


def suppress(rows: list[dict], k: int, additive: bool, dims: list[str] | None = None) -> int:
    """Withhold values resting on fewer than k people. Returns how many were withheld.

    For additive metrics, a slice (the whole table, or one row or column of a two-way
    table) with exactly one hidden cell gives that cell away: the slice total is available
    from another query. The smallest visible cell in such a slice is hidden too, repeated
    until no slice has a lone hidden cell.
    """
    for r in rows:
        if r["population"] < k:
            r["value"], r["suppressed"] = None, True
    if additive:
        dims = dims or []
        slicers = [lambda r: ()] if len(dims) < 2 else [lambda r, d=d: r[d] for d in dims]
        changed = True
        while changed:
            changed = False
            for key in slicers:
                slices: dict = {}
                for r in rows:
                    slices.setdefault(key(r), []).append(r)
                for cells in slices.values():
                    hidden = [c for c in cells if c["suppressed"]]
                    visible = [c for c in cells if not c["suppressed"]]
                    if len(hidden) == 1 and visible:
                        smallest = min(visible, key=lambda c: c["population"])
                        smallest["value"], smallest["suppressed"] = None, True
                        changed = True
    return sum(r["suppressed"] for r in rows)


def describe(spec: Spec, cat: Catalog) -> str:
    """The spec in words, shown as "Interpreted as ..." under every answer."""
    m = METRICS[spec.metric]
    head = m.label
    if spec.dimensions:
        head += " by " + " and ".join(DIMENSIONS[d].label.lower() for d in spec.dimensions)
    parts = [head]
    for f in spec.filters:
        names = ", ".join(cat.label(f.dimension, v) for v in f.values)
        parts.append(f"{DIMENSIONS[f.dimension].label.lower()} {names}")
    s, e = spec.period.start, spec.period.end
    if m.stock and not any(DIMENSIONS[d].time for d in spec.dimensions):
        parts.append(f"at the end of {e:%b %Y}")
    elif s == e:
        parts.append(f"in {s:%b %Y}")
    else:
        parts.append(f"{s:%b %Y} to {e:%b %Y}")
    if spec.order and spec.limit:
        parts.append(f"{'highest' if spec.order == 'value_desc' else 'lowest'} {spec.limit}")
    return ", ".join(parts)


ORDERED = {"age_band", "tenure_band", "grade", "gender", "employment_type"}


def _natural(cat: Catalog, dim: str, value) -> tuple:
    """Sort key that puts bands in their own order ("<1y" before "10y+"), time in
    calendar order and named groups alphabetically."""
    if DIMENSIONS[dim].time:
        return (0, str(value))
    if dim in ORDERED:
        keys = list(cat.domains.get(dim, {}))
        return (keys.index(value) if value in keys else len(keys), "")
    return (0, cat.label(dim, value))


def run(
    conn: Connection,
    spec: Spec,
    *,
    scope: tuple[str, ...] | None = None,
    min_group_size: int = 5,
) -> Result:
    cat = catalog(conn)
    spec = check(spec, cat, scope)
    compiled = compile_spec(spec, scope)
    m = METRICS[spec.metric]
    rows: list[dict] = []
    for r in conn.execute(text(compiled.sql), compiled.params).mappings():
        row: dict = {}
        for i, d in enumerate(spec.dimensions):
            v = r[f"d{i}"]
            row[d] = v.isoformat() if isinstance(v, date) else v
            row[f"{d}_label"] = cat.label(d, v)
        value = r["value"]
        row["value"] = None if value is None else round(float(value), 4)
        row["population"] = int(r["population"] or 0)
        row["suppressed"] = False
        rows.append(row)
    if not spec.dimensions and not rows:
        rows = [{"value": None, "population": 0, "suppressed": False}]
    rows.sort(key=lambda r: tuple(_natural(cat, d, r[d]) for d in spec.dimensions))
    hidden = suppress(rows, min_group_size, m.additive, spec.dimensions)
    if spec.order:
        visible = [r for r in rows if r["value"] is not None]
        visible.sort(key=lambda r: r["value"], reverse=spec.order == "value_desc")
        rows = visible + [r for r in rows if r["value"] is None]
    if spec.limit:
        rows = rows[: spec.limit]
    return Result(spec, m, rows, hidden, compiled.sql, compiled.params, describe(spec, cat))
