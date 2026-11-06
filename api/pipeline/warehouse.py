"""Build the star schema in Postgres from a simulation.

    dim_department, dim_location, dim_grade, dim_month
    dim_employee            type-2 slowly changing: one row per (department, office, grade) spell
    fact_headcount_monthly  one row per employee per month they were employed, with the
                            month's movements (hired, promoted, transferred, exited) as flags
    fact_movement           hires, exits, promotions, transfers
    fact_attrition_score    written by pipeline.model

The warehouse is rebuilt from scratch on each run; it is derived data.
"""

from __future__ import annotations

import json
from datetime import date

import psycopg

from pipeline.simulate import (
    DEPARTMENTS,
    GRADE_MID,
    GRADES,
    LOCATIONS,
    Simulation,
    age_band,
    tenure_band,
)

DDL = """
DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;

CREATE TABLE dim_department (code text PRIMARY KEY, name text NOT NULL, division text NOT NULL);
CREATE TABLE dim_location (code text PRIMARY KEY, name text NOT NULL);
CREATE TABLE dim_grade (code text PRIMARY KEY, rank int NOT NULL, band_min bigint, band_max bigint,
                        midpoint bigint);
CREATE TABLE dim_month (month date PRIMARY KEY, year int NOT NULL, quarter int NOT NULL,
                        label text NOT NULL);

CREATE TABLE dim_employee (
  employee_key serial PRIMARY KEY,
  employee_id int NOT NULL,
  employee_no text NOT NULL,
  full_name text NOT NULL,
  gender char(1) NOT NULL,
  birth_date date NOT NULL,
  hire_date date NOT NULL,
  exit_date date,
  exit_type text,
  department_code text NOT NULL REFERENCES dim_department(code),
  location_code text NOT NULL REFERENCES dim_location(code),
  grade text NOT NULL REFERENCES dim_grade(code),
  valid_from date NOT NULL,
  valid_to date,
  is_current boolean NOT NULL
);
CREATE INDEX dim_employee_id ON dim_employee (employee_id);

CREATE TABLE fact_headcount_monthly (
  month date NOT NULL REFERENCES dim_month(month),
  employee_id int NOT NULL,
  employee_key int NOT NULL REFERENCES dim_employee(employee_key),
  department_code text NOT NULL,
  location_code text NOT NULL,
  grade text NOT NULL,
  gender char(1) NOT NULL,
  age numeric(4,1) NOT NULL,
  age_band text NOT NULL,
  tenure_months int NOT NULL,
  tenure_band text NOT NULL,
  employment_type text NOT NULL,
  salary bigint NOT NULL,
  pay_ratio numeric(5,3) NOT NULL,
  months_since_promotion int NOT NULL,
  overtime_hours numeric(5,1) NOT NULL,
  overtime_3m numeric(5,1) NOT NULL,
  rating int NOT NULL,
  manager_changed_6m boolean NOT NULL,
  active_eom boolean NOT NULL,
  exited boolean NOT NULL,
  exit_type text,
  hired boolean NOT NULL,
  promoted boolean NOT NULL,
  transferred boolean NOT NULL,
  PRIMARY KEY (month, employee_id)
);
CREATE INDEX fact_hc_dept ON fact_headcount_monthly (department_code, month);

CREATE TABLE fact_movement (
  id serial PRIMARY KEY,
  date date NOT NULL,
  month date NOT NULL,
  employee_id int NOT NULL,
  type text NOT NULL,
  exit_type text,
  from_department text,
  to_department text,
  from_grade text,
  to_grade text
);
CREATE INDEX fact_movement_month ON fact_movement (month, type);

CREATE TABLE fact_attrition_score (
  scored_month date NOT NULL,
  employee_id int NOT NULL,
  probability numeric(6,4) NOT NULL,
  risk_band text NOT NULL,
  drivers jsonb NOT NULL,
  model_version text NOT NULL,
  PRIMARY KEY (scored_month, employee_id)
);

CREATE TABLE model_runs (
  version text PRIMARY KEY,
  trained_at timestamptz NOT NULL DEFAULT now(),
  metrics jsonb NOT NULL,
  fairness jsonb NOT NULL,
  importance jsonb NOT NULL,
  calibration jsonb NOT NULL,
  notes text
);

CREATE TABLE users (
  id serial PRIMARY KEY,
  email text UNIQUE NOT NULL,
  password_hash text NOT NULL,
  role text NOT NULL CHECK (role IN ('HR_ADMIN', 'HRBP', 'LEADER')),
  departments text[] NOT NULL DEFAULT '{}',
  label text NOT NULL
);

CREATE TABLE ask_log (
  id serial PRIMARY KEY,
  at timestamptz NOT NULL DEFAULT now(),
  user_email text NOT NULL,
  question text NOT NULL,
  parser text NOT NULL,
  spec jsonb,
  ok boolean NOT NULL,
  error text
);
"""


def _copy(cur: psycopg.Cursor, table: str, columns: list[str], rows) -> int:
    n = 0
    with cur.copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN") as cp:
        for row in rows:
            cp.write_row(row)
            n += 1
    return n


def _month_label(m: date) -> str:
    return m.strftime("%b %Y")


def build(conn: psycopg.Connection, sim: Simulation) -> dict[str, int]:
    """Create the schema and load dimensions and facts. Returns row counts."""
    counts: dict[str, int] = {}
    with conn.cursor() as cur:
        cur.execute(DDL)
        counts["dim_department"] = _copy(
            cur,
            "dim_department",
            ["code", "name", "division"],
            [(c, n, d) for c, n, d, *_ in DEPARTMENTS],
        )
        counts["dim_location"] = _copy(
            cur, "dim_location", ["code", "name"], [(c, n) for c, n, _ in LOCATIONS]
        )
        counts["dim_grade"] = _copy(
            cur,
            "dim_grade",
            ["code", "rank", "band_min", "band_max", "midpoint"],
            [(g, int(g[1]), lo, hi, int(GRADE_MID[g])) for g, lo, hi in GRADES],
        )
        counts["dim_month"] = _copy(
            cur,
            "dim_month",
            ["month", "year", "quarter", "label"],
            [(m, m.year, (m.month - 1) // 3 + 1, _month_label(m)) for m in sim.months],
        )

        # Employee numbers in hire order; SCD2 spells from the monthly snapshots.
        people = {p.id: p for p in sim.people}
        order = sorted(people.values(), key=lambda p: (p.hire_date, p.id))
        number = {p.id: f"AL-{i:05d}" for i, p in enumerate(order, start=1)}
        spells: list[tuple] = []
        key_for: dict[tuple[int, date], int] = {}
        by_emp: dict[int, list[dict]] = {}
        for s in sim.snapshots:
            by_emp.setdefault(s["employee_id"], []).append(s)
        key = 0
        for emp_id, rows in by_emp.items():
            p = people[emp_id]
            rows.sort(key=lambda r: r["month"])
            spell_start = 0
            for i in range(1, len(rows) + 1):
                boundary = i == len(rows) or any(
                    rows[i][k] != rows[spell_start][k] for k in ("department", "location", "grade")
                )
                if not boundary:
                    continue
                key += 1
                first, last = rows[spell_start], rows[i - 1]
                current = i == len(rows) and p.exit_date is None
                spells.append(
                    (
                        key,
                        emp_id,
                        number[emp_id],
                        p.name,
                        p.gender,
                        p.birth_date,
                        p.hire_date,
                        p.exit_date,
                        p.exit_type,
                        first["department"],
                        first["location"],
                        first["grade"],
                        first["month"],
                        None if current else last["month"],
                        current,
                    )
                )
                for r in rows[spell_start:i]:
                    key_for[(emp_id, r["month"])] = key
                spell_start = i
        counts["dim_employee"] = _copy(
            cur,
            "dim_employee",
            [
                "employee_key",
                "employee_id",
                "employee_no",
                "full_name",
                "gender",
                "birth_date",
                "hire_date",
                "exit_date",
                "exit_type",
                "department_code",
                "location_code",
                "grade",
                "valid_from",
                "valid_to",
                "is_current",
            ],
            spells,
        )
        cur.execute(
            "SELECT setval(pg_get_serial_sequence('dim_employee', 'employee_key'),"
            " (SELECT max(employee_key) FROM dim_employee))"
        )

        # Movement flags on the monthly fact, so every metric can be cut by the same
        # attributes (the person's department, grade, age band... in that month).
        flags: dict[tuple[int, date], set[str]] = {}
        for m in sim.movements:
            flags.setdefault((m["employee_id"], m["date"].replace(day=1)), set()).add(m["type"])
        counts["fact_headcount_monthly"] = _copy(
            cur,
            "fact_headcount_monthly",
            [
                "month",
                "employee_id",
                "employee_key",
                "department_code",
                "location_code",
                "grade",
                "gender",
                "age",
                "age_band",
                "tenure_months",
                "tenure_band",
                "employment_type",
                "salary",
                "pay_ratio",
                "months_since_promotion",
                "overtime_hours",
                "overtime_3m",
                "rating",
                "manager_changed_6m",
                "active_eom",
                "exited",
                "exit_type",
                "hired",
                "promoted",
                "transferred",
            ],
            (
                (
                    s["month"],
                    s["employee_id"],
                    key_for[(s["employee_id"], s["month"])],
                    s["department"],
                    s["location"],
                    s["grade"],
                    s["gender"],
                    s["age"],
                    age_band(s["age"]),
                    s["tenure_months"],
                    tenure_band(s["tenure_months"]),
                    s["employment_type"],
                    int(s["salary"]),
                    s["pay_ratio"],
                    s["months_since_promotion"],
                    s["overtime_hours"],
                    s["overtime_3m"],
                    s["rating"],
                    s["manager_changed_6m"],
                    s["active_eom"],
                    s["exited"],
                    s["exit_type"],
                    "hire" in flags.get((s["employee_id"], s["month"]), ()),
                    "promotion" in flags.get((s["employee_id"], s["month"]), ()),
                    "transfer" in flags.get((s["employee_id"], s["month"]), ()),
                )
                for s in sim.snapshots
            ),
        )
        window_start = sim.months[0]
        counts["fact_movement"] = _copy(
            cur,
            "fact_movement",
            [
                "date",
                "month",
                "employee_id",
                "type",
                "exit_type",
                "from_department",
                "to_department",
                "from_grade",
                "to_grade",
            ],
            (
                (
                    m["date"],
                    m["date"].replace(day=1),
                    m["employee_id"],
                    m["type"],
                    m.get("exit_type"),
                    m["from_department"],
                    m["to_department"],
                    m["from_grade"],
                    m["to_grade"],
                )
                for m in sim.movements
                if m["date"] >= window_start and m["date"].replace(day=1) <= sim.months[-1]
            ),
        )
        cur.execute("ANALYZE")
    conn.commit()
    return counts


def to_json(value) -> str:
    return json.dumps(value, default=str)


__all__ = ["DDL", "build", "to_json"]
