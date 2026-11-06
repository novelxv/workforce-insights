from datetime import date

import pytest

from app.metrics import (
    DIMENSIONS,
    METRICS,
    Catalog,
    Period,
    Spec,
    SpecError,
    check,
    compile_spec,
    describe,
    suppress,
)

CAT = Catalog(
    domains={
        "department": {"CLM": "Claims", "CSV": "Customer Service", "ITD": "Information Technology"},
        "division": {"Operations": "Operations", "Technical": "Technical"},
        "location": {"JKT": "Jakarta", "SBY": "Surabaya"},
        "grade": {f"G{i}": f"G{i}" for i in range(1, 8)},
        "gender": {"F": "Women", "M": "Men"},
        "age_band": {"<25": "<25", "25-34": "25-34"},
        "tenure_band": {"<1y": "<1y"},
        "employment_type": {"PKWT": "Fixed-term (PKWT)", "PKWTT": "Permanent (PKWTT)"},
    },
    first_month=date(2024, 1, 1),
    last_month=date(2026, 10, 1),
)


def spec(**kw) -> Spec:
    kw.setdefault("period", Period(start="2025-11", end="2026-10"))
    return Spec(**kw)


def test_every_metric_and_dimension_is_described():
    for m in METRICS.values():
        assert m.definition.endswith(".") and m.formula and m.synonyms
    assert all(d.label for d in DIMENSIONS.values())


def test_values_are_bound_never_interpolated():
    s = spec(metric="exits", filters=[{"dimension": "department", "values": ["CLM", "CSV"]}])
    c = compile_spec(s)
    assert "CLM" not in c.sql and ":f0" in c.sql
    assert c.params["f0"] == ["CLM", "CSV"]
    assert c.params["start"] == date(2025, 11, 1) and c.params["end"] == date(2026, 10, 1)


def test_hrbp_scope_is_always_applied():
    c = compile_spec(spec(metric="hires"), scope=("CLM", "CSV"))
    assert "h.department_code = ANY(:scope)" in c.sql
    assert c.params["scope"] == ["CLM", "CSV"]


def test_stock_metric_reads_the_last_month_only_without_a_time_dimension():
    assert "h.month = :end" in compile_spec(spec(metric="headcount")).sql
    by_month = compile_spec(spec(metric="headcount", dimensions=["month"])).sql
    assert "h.month = :end" not in by_month
    by_quarter = compile_spec(spec(metric="headcount", dimensions=["quarter"])).sql
    assert "LEAST(" in by_quarter  # last available month of each quarter


def test_flow_metric_sums_across_the_period():
    sql = compile_spec(spec(metric="voluntary_exits")).sql
    assert "h.month = :end" not in sql
    assert "h.exit_type = 'voluntary'" in sql


def test_check_rejects_unknown_metric_dimension_and_value():
    with pytest.raises(SpecError):
        check(spec(metric="nps"), CAT)
    with pytest.raises(SpecError):
        check(spec(metric="exits", dimensions=["salary"]), CAT)
    with pytest.raises(SpecError) as e:
        check(spec(metric="exits", filters=[{"dimension": "department", "values": ["X'--"]}]), CAT)
    assert "CLM" in e.value.suggestions


def test_check_rejects_departments_outside_scope():
    s = spec(metric="exits", filters=[{"dimension": "department", "values": ["ITD"]}])
    with pytest.raises(SpecError, match="Outside your departments"):
        check(s, CAT, scope=("CLM",))


def test_check_rejects_time_filters_and_two_time_dimensions():
    with pytest.raises(SpecError):
        check(spec(metric="exits", filters=[{"dimension": "month", "values": ["2026-01"]}]), CAT)
    with pytest.raises(SpecError):
        check(spec(metric="exits", dimensions=["month", "quarter"]), CAT)


def test_check_clamps_the_period_to_the_data():
    s = check(spec(metric="exits", period=Period(start="2020-01", end="2030-12")), CAT)
    assert s.period.start == date(2024, 1, 1) and s.period.end == date(2026, 10, 1)
    with pytest.raises(SpecError, match="No data"):
        check(spec(metric="exits", period=Period(start="2019-01", end="2019-12")), CAT)


def _rows(*populations, dims=None):
    rows = []
    for i, p in enumerate(populations):
        r = {"value": float(p), "population": p, "suppressed": False}
        for j, d in enumerate(dims or []):
            r[d] = (i // 2, i % 2)[j]
        rows.append(r)
    return rows


def test_small_groups_are_withheld():
    rows = _rows(40, 3, 12)
    assert suppress(rows, 5, additive=False) == 1
    assert rows[1]["value"] is None and rows[1]["suppressed"]


def test_lone_hidden_cell_in_additive_breakdown_takes_the_next_smallest_with_it():
    rows = _rows(40, 3, 12)
    assert suppress(rows, 5, additive=True) == 2
    assert [r["suppressed"] for r in rows] == [False, True, True]


def test_two_way_table_protects_rows_and_columns():
    # department x gender: (A,F)=11 (A,M)=9 (B,F)=2 (B,M)=6 (C,F)=6 (C,M)=7
    rows = _rows(11, 9, 2, 6, 6, 7, dims=["department", "gender"])
    suppress(rows, 5, additive=True, dims=["department", "gender"])
    hidden = {(r["department"], r["gender"]) for r in rows if r["suppressed"]}
    by_row: dict = {}
    by_col: dict = {}
    for d, g in hidden:
        by_row[d] = by_row.get(d, 0) + 1
        by_col[g] = by_col.get(g, 0) + 1
    assert (1, 0) in hidden  # the small cell itself
    assert all(n != 1 for n in by_row.values()) and all(n != 1 for n in by_col.values())


def test_rates_are_not_complementary_suppressed():
    rows = _rows(40, 3, 12)
    assert suppress(rows, 5, additive=False) == 1


def test_describe_reads_like_a_sentence():
    s = spec(
        metric="voluntary_turnover_rate",
        dimensions=["department"],
        filters=[{"dimension": "location", "values": ["JKT"]}],
        order="value_desc",
        limit=5,
    )
    assert describe(s, CAT) == (
        "Voluntary turnover rate by department, office Jakarta, Nov 2025 to Oct 2026, highest 5"
    )
    assert describe(spec(metric="headcount"), CAT) == "Headcount, at the end of Oct 2026"
