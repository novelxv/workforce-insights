"""Exports: the monthly HR report as an Excel workbook, and a star-schema extract for
Power BI. Both go through the same metrics layer (and suppression) as the screens, so a
number in the workbook matches the number on the dashboard."""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.formatting.rule import DataBarRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy.engine import Connection

from app.auth import Principal
from app.metrics import METRICS, Period, Spec, add_months, catalog, run

POWERBI_DIR = Path(__file__).resolve().parent / "powerbi"

INK = "1F2933"
MUTED = "6B7280"
ACCENT = "0F766E"
RULE = "D1D5DB"
HEADER_FILL = PatternFill("solid", fgColor="F3F4F6")
FORMATS = {"count": "#,##0", "percent": "0.0%", "years": "0.0", "hours": "0.0", "ratio": "0.00"}
CHANGE_FORMATS = {
    "count": "+#,##0;-#,##0;0",
    "percent": "+0.0%;-0.0%;0.0%",
    "years": "+0.0;-0.0;0.0",
    "hours": "+0.0;-0.0;0.0",
    "ratio": "+0.00;-0.00;0.00",
}


def _header(ws, row: int, labels: list[str], widths: list[int] | None = None) -> None:
    thin = Side(style="thin", color=RULE)
    for i, label in enumerate(labels, start=1):
        c = ws.cell(row=row, column=i, value=label)
        c.font = Font(bold=True, color=INK)
        c.fill = HEADER_FILL
        c.border = Border(bottom=thin)
        c.alignment = Alignment(vertical="center", wrap_text=True)
    if widths:
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w


def _title(ws, title: str, subtitle: list[str]) -> None:
    ws["A1"] = title
    ws["A1"].font = Font(bold=True, size=14, color=INK)
    for i, line in enumerate(subtitle, start=2):
        ws.cell(row=i, column=1, value=line).font = Font(color=MUTED)


def _withheld(cell) -> None:
    cell.value = "n<5"
    cell.font = Font(italic=True, color=MUTED)
    cell.alignment = Alignment(horizontal="right")


def monthly_report(conn: Connection, p: Principal, month: date | None = None) -> bytes:
    cat = catalog(conn)
    month = min(month or cat.last_month, cat.last_month)
    scope = p.department_scope

    def value(metric: str, start: date, end: date):
        start = max(start, cat.first_month)
        if end < cat.first_month:
            return None
        spec = Spec(metric=metric, period=Period(start=start, end=end))
        return run(conn, spec, scope=scope).rows[0]["value"]

    def by(metric: str, dim: str, start: date, end: date) -> dict:
        spec = Spec(
            metric=metric,
            dimensions=[dim],
            period=Period(start=max(start, cat.first_month), end=end),
        )
        return {r[dim]: r for r in run(conn, spec, scope=scope).rows}

    scope_line = (
        "Scope: departments " + ", ".join(cat.label("department", d) for d in scope)
        if scope is not None
        else "Scope: whole company"
    )
    stamp = datetime.now(UTC).strftime("%d %b %Y %H:%M UTC")
    subtitle = [
        scope_line,
        f"Prepared for {p.label} ({p.email}) on {stamp}.",
        "Synthetic data for a fictional insurer. Figures resting on fewer than 5 people are "
        "withheld (n<5).",
    ]

    wb = Workbook()
    wb.calculation.fullCalcOnLoad = True

    # --- Summary -------------------------------------------------------------------------
    ws = wb.active
    ws.title = "Summary"
    _title(ws, f"Workforce report, {month:%B %Y}", subtitle)
    prev_m, year_m = add_months(month, -1), add_months(month, -12)
    _header(
        ws,
        6,
        [
            "Metric",
            f"{month:%b %Y}",
            f"{prev_m:%b %Y}",
            "Change",
            f"{year_m:%b %Y}",
            "Change vs a year ago",
            "Basis",
        ],
        [28, 12, 12, 11, 12, 13, 72],
    )
    lines = [
        ("headcount", "month", "Headcount at month end"),
        ("hires", "month", "Hires in the month"),
        ("exits", "month", "Exits in the month"),
        ("voluntary_exits", "month", "Resignations in the month"),
        ("voluntary_turnover_rate", "ttm", "12 months to the month shown"),
        ("turnover_rate", "ttm", "12 months to the month shown"),
        ("early_exit_share", "ttm", "12 months to the month shown"),
        ("promotion_rate", "ttm", "12 months to the month shown"),
        ("avg_tenure_years", "month", "At month end"),
        ("female_share", "month", "At month end"),
        ("pkwt_share", "month", "At month end"),
        ("compa_ratio", "month", "At month end"),
    ]
    for i, (key, basis, note) in enumerate(lines, start=7):
        m = METRICS[key]
        ws.cell(row=i, column=1, value=m.label)
        for col, end in ((2, month), (3, prev_m), (5, year_m)):
            start = end if basis == "month" else add_months(end, -11)
            v = (
                value(key, start, end)
                if basis == "month" or add_months(end, -11) >= cat.first_month
                else None
            )
            c = ws.cell(row=i, column=col, value=v)
            c.number_format = FORMATS[m.unit]
        for col, a, b in ((4, "B", "C"), (6, "B", "E")):
            c = ws.cell(row=i, column=col, value=f'=IF(OR({a}{i}="",{b}{i}=""),"",{a}{i}-{b}{i})')
            c.number_format = CHANGE_FORMATS[m.unit]
        ws.cell(row=i, column=7, value=f"{note}. {m.definition}").font = Font(color=MUTED)
        for col in range(1, 7):
            ws.cell(row=i, column=col).alignment = Alignment(vertical="top")
        ws.cell(row=i, column=7).alignment = Alignment(wrap_text=True, vertical="top", indent=1)
    ws.freeze_panes = "B7"

    # --- Trend ---------------------------------------------------------------------------
    wt = wb.create_sheet("Trend")
    _title(wt, "Monthly trend", subtitle[:1])
    _header(
        wt,
        4,
        [
            "Month",
            "Headcount",
            "Hires",
            "Exits",
            "Resignations",
            "Resignations, 12 months",
            "Voluntary turnover, 12 months",
        ],
        [12, 12, 10, 10, 13, 15, 16],
    )
    start = cat.first_month
    series = {
        key: by(key, "month", start, month)
        for key in ("headcount", "hires", "exits", "voluntary_exits")
    }
    months: list[date] = []
    d = start
    while d <= month:
        months.append(d)
        d = add_months(d, 1)
    first_row = 5
    for j, m_ in enumerate(months):
        r = first_row + j
        wt.cell(row=r, column=1, value=m_).number_format = "mmm yyyy"
        for col, key in enumerate(("headcount", "hires", "exits", "voluntary_exits"), start=2):
            row = series[key].get(m_.isoformat())
            c = wt.cell(row=r, column=col)
            if row is None or row["suppressed"]:
                _withheld(c)
            else:
                c.value = row["value"]
                c.number_format = "#,##0"
        if j >= 11:
            top = r - 11
            # Same definition as the app: resignations x 12 / sum of monthly headcount.
            wt.cell(row=r, column=6, value=f"=SUM(E{top}:E{r})").number_format = "#,##0"
            wt.cell(
                row=r, column=7, value=f'=IFERROR(12*SUM(E{top}:E{r})/SUM(B{top}:B{r}),"")'
            ).number_format = "0.0%"
    last_row = first_row + len(months) - 1
    wt.freeze_panes = "B5"

    hc = LineChart()
    hc.title = "Headcount at month end"
    hc.height, hc.width = 7.5, 17
    hc.legend = None
    hc.y_axis.numFmt = "#,##0"
    hc.y_axis.majorGridlines = None
    hc.add_data(Reference(wt, min_col=2, min_row=4, max_row=last_row), titles_from_data=True)
    hc.set_categories(Reference(wt, min_col=1, min_row=5, max_row=last_row))
    hc.x_axis.number_format = "mmm yy"
    hc.series[0].graphicalProperties.line.solidFill = ACCENT
    hc.series[0].graphicalProperties.line.width = 22000
    hc.series[0].smooth = False
    wt.add_chart(hc, "I4")

    if last_row >= first_row + 11:
        vt = LineChart()
        vt.title = "Voluntary turnover, trailing 12 months"
        vt.height, vt.width = 7.5, 17
        vt.legend = None
        vt.y_axis.numFmt = "0%"
        vt.y_axis.majorGridlines = None
        vt.add_data(Reference(wt, min_col=7, min_row=first_row + 11, max_row=last_row))
        vt.set_categories(Reference(wt, min_col=1, min_row=first_row + 11, max_row=last_row))
        vt.x_axis.number_format = "mmm yy"
        vt.series[0].graphicalProperties.line.solidFill = ACCENT
        vt.series[0].graphicalProperties.line.width = 22000
        vt.series[0].smooth = False
        wt.add_chart(vt, "I21")

    # --- Departments ---------------------------------------------------------------------
    wd = wb.create_sheet("Departments")
    _title(wd, f"Departments, 12 months to {month:%B %Y}", subtitle[:1])
    cols = [
        ("Department", None, None, 26),
        ("Headcount", "headcount", "month", 11),
        ("Hires", "hires", "ttm", 9),
        ("Resignations", "voluntary_exits", "ttm", 14),
        ("Voluntary turnover", "voluntary_turnover_rate", "ttm", 12),
        ("Average tenure (years)", "avg_tenure_years", "month", 12),
        ("Women", "female_share", "month", 9),
        ("Compa-ratio", "compa_ratio", "month", 11),
        ("Overtime h/month", "avg_overtime_hours", "ttm", 11),
    ]
    _header(wd, 4, [c[0] for c in cols], [c[3] for c in cols])
    ttm = add_months(month, -11)
    data = {
        key: by(key, "department", month if basis == "month" else ttm, month)
        for _, key, basis, _ in cols
        if key
    }
    order = sorted(
        data["voluntary_turnover_rate"].values(),
        key=lambda r: (r["value"] is None, -(r["value"] or 0)),
    )
    for i, dept in enumerate(order, start=5):
        code = dept["department"]
        wd.cell(row=i, column=1, value=dept["department_label"])
        for col, (_, key, _, _) in enumerate(cols[1:], start=2):
            row = data[key].get(code)
            c = wd.cell(row=i, column=col)
            if row is None or row["suppressed"]:
                _withheld(c)
            else:
                c.value = row["value"]
                c.number_format = FORMATS[METRICS[key].unit]
    dept_last = 4 + len(order)
    wd.freeze_panes = "B5"
    wd.auto_filter.ref = f"A4:{get_column_letter(len(cols))}{dept_last}"
    wd.conditional_formatting.add(
        f"E5:E{dept_last}",
        DataBarRule(start_type="num", start_value=0, end_type="max", color=ACCENT),
    )
    bar = BarChart()
    bar.type = "bar"
    bar.title = "Voluntary turnover by department, 12 months"
    bar.height, bar.width = 11, 17
    bar.legend = None
    bar.x_axis.scaling.orientation = "maxMin"  # highest at the top, as in the table
    bar.y_axis.numFmt = "0%"
    bar.y_axis.majorGridlines = None
    bar.gapWidth = 60
    bar.add_data(Reference(wd, min_col=5, min_row=4, max_row=dept_last), titles_from_data=True)
    bar.set_categories(Reference(wd, min_col=1, min_row=5, max_row=dept_last))
    bar.series[0].graphicalProperties.solidFill = ACCENT
    bar.series[0].graphicalProperties.line.noFill = True
    wd.add_chart(bar, "K4")

    # --- Definitions ---------------------------------------------------------------------
    wdef = wb.create_sheet("Definitions")
    _title(
        wdef,
        "Metric definitions",
        ["The same definitions drive the app, this workbook and the Power BI measures."],
    )
    _header(wdef, 4, ["Metric", "Definition", "Calculation", "Measured"], [26, 70, 60, 16])
    for i, m in enumerate(METRICS.values(), start=5):
        wdef.cell(row=i, column=1, value=m.label).font = Font(bold=True)
        wdef.cell(row=i, column=2, value=m.definition)
        wdef.cell(row=i, column=3, value=m.formula)
        wdef.cell(row=i, column=4, value="End of period" if m.stock else "Across period")
        for col in (2, 3):
            wdef.cell(row=i, column=col).alignment = Alignment(wrap_text=True, vertical="top")

    for sheet in wb.worksheets:
        sheet.sheet_view.showGridLines = False
        sheet.page_setup.orientation = "landscape"
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
        sheet.sheet_properties.pageSetUpPr.fitToPage = True

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --- Power BI extract --------------------------------------------------------------------

EXTRACT = {
    "dim_department.csv": "SELECT code, name, division FROM dim_department ORDER BY code",
    "dim_location.csv": "SELECT code, name FROM dim_location ORDER BY code",
    "dim_grade.csv": "SELECT code, rank, band_min, band_max, midpoint FROM dim_grade ORDER BY rank",
    "dim_month.csv": (
        "SELECT month, year, quarter, label FROM dim_month WHERE month >= '{first}' ORDER BY month"
    ),
    # Pseudonymous: employee number only. Names and dates of birth stay in the app.
    "dim_employee.csv": (
        "SELECT employee_key, employee_id, employee_no, gender, hire_date, exit_date, exit_type,"
        " department_code, location_code, grade, valid_from, valid_to, is_current::int AS"
        " is_current FROM dim_employee ORDER BY employee_key"
    ),
    # Salary stays out; pay is represented by the ratio to the grade midpoint.
    "fact_headcount_monthly.csv": (
        "SELECT month, employee_id, employee_key, department_code, location_code, grade, gender,"
        " age_band, tenure_months, tenure_band, employment_type, pay_ratio,"
        " months_since_promotion, overtime_hours, rating, active_eom::int AS active_eom,"
        " exited::int AS exited, exit_type, hired::int AS hired, promoted::int AS promoted,"
        " transferred::int AS transferred FROM fact_headcount_monthly"
        " WHERE month >= '{first}' ORDER BY month, employee_id"
    ),
    "fact_movement.csv": (
        "SELECT date, month, employee_id, type, exit_type, from_department, to_department,"
        " from_grade, to_grade FROM fact_movement WHERE month >= '{first}' ORDER BY date, id"
    ),
}


def powerbi_extract(conn: Connection) -> bytes:
    """Zip of CSVs plus the DAX measures. Months start where the app's analysis starts,
    after the simulation's warm-up, so totals agree with the dashboard."""
    first = catalog(conn).first_month.isoformat()  # a date from the database, not user input
    raw = conn.connection.driver_connection
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, sql in EXTRACT.items():
            out = io.BytesIO()
            query = sql.format(first=first)
            with (
                raw.cursor() as cur,
                cur.copy(f"COPY ({query}) TO STDOUT WITH (FORMAT csv, HEADER)") as cp,
            ):
                for chunk in cp:
                    out.write(bytes(chunk))
            z.writestr(f"arunika-workforce/{name}", out.getvalue())
        for f in ("measures.dax", "README.md"):
            z.write(POWERBI_DIR / f, f"arunika-workforce/{f}")
    return buf.getvalue()
