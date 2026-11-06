from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.engine import Connection

from app.auth import Principal, current, hr_admin
from app.db import get_conn
from app.exports import monthly_report, powerbi_extract
from app.metrics import catalog

router = APIRouter(prefix="/exports", tags=["exports"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/monthly-report.xlsx")
def report(
    month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    p: Principal = Depends(current),
    conn: Connection = Depends(get_conn),
):
    last = catalog(conn).last_month
    m = min(date(int(month[:4]), int(month[5:7]), 1), last) if month else last
    body = monthly_report(conn, p, m)
    name = f"arunika-workforce-report-{m:%Y-%m}.xlsx"
    return Response(
        body, media_type=XLSX, headers={"content-disposition": f'attachment; filename="{name}"'}
    )


@router.get("/powerbi.zip")
def powerbi(p: Principal = Depends(hr_admin), conn: Connection = Depends(get_conn)):
    return Response(
        powerbi_extract(conn),
        media_type="application/zip",
        headers={"content-disposition": 'attachment; filename="arunika-workforce-powerbi.zip"'},
    )
