"""Simulate 36 months of a fictional insurer's workforce, month by month.

The point of simulating rather than downloading a public dataset is that the causes of
attrition are known. Every month each active employee gets a voluntary-exit hazard built
from the drivers below, plus an unobserved personal factor. docs/simulation.md lists them
with their multipliers, so the attrition model's findings can be checked against the
truth instead of being taken on trust.

Planted drivers of voluntary exit (multiplicative on a department base rate):
    pay below the grade midpoint, long time since promotion, a recent manager change,
    sustained overtime, strong performers who are underpaid, first-year tenure, the
    weeks after the annual bonus, and an unobserved personal factor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np

DEPARTMENTS: list[tuple[str, str, str, float, int]] = [
    # code, name, division, monthly base voluntary-exit rate, initial headcount
    ("ACT", "Actuarial", "Technical", 0.006, 22),
    ("UW", "Underwriting", "Technical", 0.008, 45),
    ("CLM", "Claims", "Technical", 0.010, 70),
    ("POL", "Policy Administration", "Operations", 0.013, 80),
    ("CSV", "Customer Service", "Operations", 0.016, 95),
    ("ITD", "Information Technology", "Operations", 0.011, 55),
    ("GAF", "General Affairs", "Operations", 0.007, 22),
    ("BAN", "Bancassurance", "Distribution", 0.017, 140),
    ("AGY", "Agency Development", "Distribution", 0.014, 70),
    ("MKT", "Marketing & Product", "Distribution", 0.009, 18),
    ("FIN", "Finance & Accounting", "Finance", 0.006, 32),
    ("INV", "Investment", "Finance", 0.007, 12),
    ("CMP", "Compliance & AML/CFT", "Governance", 0.006, 16),
    ("RSK", "Risk Management", "Governance", 0.006, 10),
    ("LGL", "Legal", "Governance", 0.005, 7),
    ("IAU", "Internal Audit", "Governance", 0.006, 10),
    ("HRD", "Human Capital", "Support", 0.007, 20),
]
FRONTLINE = {"POL", "CSV", "BAN", "AGY", "CLM"}
# Calibrates overall voluntary turnover to roughly 15-18% a year, typical for an insurer
# with a large bancassurance and service frontline.
BASE_SCALE = 0.65
LOCATIONS = [("JKT", "Jakarta", 0.5), ("SBY", "Surabaya", 0.15), ("BDG", "Bandung", 0.13),
             ("MDN", "Medan", 0.12), ("MKS", "Makassar", 0.10)]  # fmt: skip
LOCATION_PAY = {"JKT": 1.0, "SBY": 0.93, "BDG": 0.9, "MDN": 0.88, "MKS": 0.86}
# grade, band min, band max (Jakarta, monthly rupiah)
GRADES = [
    ("G1", 4_500_000, 8_000_000),
    ("G2", 6_500_000, 11_500_000),
    ("G3", 9_500_000, 17_000_000),
    ("G4", 14_500_000, 25_000_000),
    ("G5", 20_000_000, 36_000_000),
    ("G6", 30_000_000, 52_000_000),
    ("G7", 45_000_000, 80_000_000),
]
GRADE_MID = {g: (lo + hi) / 2 for g, lo, hi in GRADES}
GRADE_MIX_FRONTLINE = [0.45, 0.3, 0.15, 0.06, 0.03, 0.01, 0.0]
GRADE_MIX_OTHER = [0.12, 0.3, 0.3, 0.14, 0.09, 0.04, 0.01]
OVERTIME_BASE = {"CLM": 22, "CSV": 26, "POL": 18, "ITD": 20, "BAN": 14, "AGY": 12, "FIN": 16}

FEMALE = [
    "Ayu", "Dewi", "Sari", "Rina", "Putri", "Nadia", "Intan", "Wulan", "Fitri", "Maya", "Siti",
    "Anisa", "Citra", "Dian", "Indah", "Kartika", "Lestari", "Nurul", "Ratna", "Melati",
    "Novita", "Gita", "Clara", "Monica", "Grace", "Tiara", "Aulia", "Zahra", "Ratih", "Widya",
]  # fmt: skip
MALE = [
    "Budi", "Agus", "Andi", "Rizky", "Dimas", "Fajar", "Hendra", "Irfan", "Joko", "Bayu",
    "Arif", "Eko", "Galih", "Hadi", "Ilham", "Lukman", "Nugroho", "Rahmat", "Teguh", "Wahyu",
    "Yusuf", "Reza", "Daniel", "Kevin", "Yohanes", "Togar", "Faisal", "Taufik", "Gilang",
    "Aditya",
]  # fmt: skip
SURNAMES = [
    "Pratama", "Saputra", "Wijaya", "Santoso", "Hidayat", "Siregar", "Nasution", "Harahap",
    "Lubis", "Sinaga", "Tanjung", "Chaniago", "Rahman", "Halim", "Gunawan", "Setiawan",
    "Kusuma", "Permana", "Ramadhan", "Hakim", "Nugraha", "Hartono", "Utomo", "Sitompul",
    "Manurung", "Sembiring", "Ginting", "Wenas", "Lim", "Tan", "Adnyana", "Suardana",
]  # fmt: skip

# The planted effects, also printed in docs/simulation.md.
EFFECTS = {
    "pay_below_90pct_of_midpoint": 1.8,
    "pay_90_to_100pct_of_midpoint": 1.25,
    "pay_above_110pct_of_midpoint": 0.8,
    "no_promotion_36_months": 1.5,
    "manager_changed_last_6_months": 1.4,
    "overtime_over_30h_3m_avg": 1.6,
    "high_performer_paid_below_midpoint": 1.5,
    "low_performer": 1.3,
    "tenure_under_12_months": 1.6,
    "tenure_3_to_10_years": 0.7,
    "tenure_over_10_years": 0.5,
    "april_may_after_bonus": 1.3,
    "personal_factor_lognormal_sigma": 0.45,
}


def move(when, employee_id, kind, *, from_grade=None, to_grade=None, from_dept=None, to_dept=None,
         exit_type=None) -> dict:  # fmt: skip
    return {
        "date": when,
        "employee_id": employee_id,
        "type": kind,
        "exit_type": exit_type,
        "from_grade": from_grade,
        "to_grade": to_grade,
        "from_department": from_dept,
        "to_department": to_dept,
    }


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


@dataclass
class Person:
    id: int
    name: str
    gender: str
    birth_date: date
    hire_date: date
    department: str
    location: str
    grade: str
    salary: float
    employment_type: str
    rating: int
    personal: float  # unobserved propensity to leave
    overtime_bias: float
    last_promotion: date
    manager_id: int | None = None
    manager_changed: date | None = None
    exit_date: date | None = None
    exit_type: str | None = None
    overtime: list[float] = field(default_factory=list)


@dataclass
class Simulation:
    people: list[Person]
    snapshots: list[dict]
    movements: list[dict]
    months: list[date]


def _midpoint(p: Person) -> float:
    return GRADE_MID[p.grade] * LOCATION_PAY[p.location]


def months_between(later: date, earlier: date) -> int:
    return (later.year - earlier.year) * 12 + later.month - earlier.month


def planted_hazard(
    *,
    department: str,
    pay_ratio: float,
    months_since_promotion: int,
    grade_rank: int,
    manager_changed_6m: bool,
    overtime_3m: float,
    rating: int,
    tenure_months: int,
    month: int,
) -> float:
    """The monthly voluntary-exit hazard implied by the planted drivers, before the
    unobserved personal factor. The simulator uses it, and the model report uses it as a
    ceiling: no model can rank better than the formula that generated the data."""
    h = BASE_SCALE * next(d[3] for d in DEPARTMENTS if d[0] == department)
    if pay_ratio < 0.9:
        h *= EFFECTS["pay_below_90pct_of_midpoint"]
    elif pay_ratio < 1.0:
        h *= EFFECTS["pay_90_to_100pct_of_midpoint"]
    elif pay_ratio > 1.1:
        h *= EFFECTS["pay_above_110pct_of_midpoint"]
    if months_since_promotion > 36 and grade_rank <= 5:
        h *= EFFECTS["no_promotion_36_months"]
    if manager_changed_6m:
        h *= EFFECTS["manager_changed_last_6_months"]
    if overtime_3m > 30:
        h *= EFFECTS["overtime_over_30h_3m_avg"]
    if rating >= 4 and pay_ratio < 1.0:
        h *= EFFECTS["high_performer_paid_below_midpoint"]
    if rating <= 2:
        h *= EFFECTS["low_performer"]
    if tenure_months < 12:
        h *= EFFECTS["tenure_under_12_months"]
    elif 36 <= tenure_months < 120:
        h *= EFFECTS["tenure_3_to_10_years"]
    elif tenure_months >= 120:
        h *= EFFECTS["tenure_over_10_years"]
    if month in (4, 5):
        h *= EFFECTS["april_may_after_bonus"]
    return h


def _hazard(p: Person, month: date) -> float:
    h = planted_hazard(
        department=p.department,
        pay_ratio=p.salary / _midpoint(p),
        months_since_promotion=months_between(month, p.last_promotion),
        grade_rank=int(p.grade[1]),
        manager_changed_6m=bool(
            p.manager_changed and months_between(month, p.manager_changed) <= 6
        ),
        overtime_3m=float(np.mean(p.overtime[-3:])) if p.overtime else 0.0,
        rating=p.rating,
        tenure_months=months_between(month, p.hire_date),
        month=month.month,
    )
    return min(h * p.personal, 0.25)


def simulate(end_month: date, months: int = 36, seed: int = 20261106) -> Simulation:
    rng = np.random.default_rng(seed)
    start = add_months(end_month, -(months - 1))
    month_list = [add_months(start, i) for i in range(months)]
    people: list[Person] = []

    def new_person(dept: str, at: date, tenure_years: float | None = None) -> Person:
        frontline = dept in FRONTLINE
        mix = GRADE_MIX_FRONTLINE if frontline else GRADE_MIX_OTHER
        grade = GRADES[rng.choice(len(GRADES), p=mix)][0]
        rank = int(grade[1])
        loc = (
            LOCATIONS[rng.choice(len(LOCATIONS), p=[w for *_, w in LOCATIONS])][0]
            if frontline
            else "JKT"
        )
        gender = "F" if rng.random() < (0.58 if frontline else 0.48) else "M"
        hire = at if tenure_years is None else add_months(at, -int(tenure_years * 12))
        age_at_hire = rng.uniform(21, 26) + (rank - 1) * 2.2 + rng.uniform(0, 4)
        birth = date(
            hire.year - int(age_at_hire), int(rng.integers(1, 13)), int(rng.integers(1, 28))
        )
        lo, hi = next((g[1], g[2]) for g in GRADES if g[0] == grade)
        salary = (lo + (hi - lo) * rng.beta(2.2, 2.6)) * LOCATION_PAY[loc]
        promo_gap = int(rng.integers(0, 48))
        p = Person(
            id=len(people) + 1,
            name=f"{rng.choice(FEMALE if gender == 'F' else MALE)} {rng.choice(SURNAMES)}",
            gender=gender,
            birth_date=birth,
            hire_date=hire,
            department=dept,
            location=loc,
            grade=grade,
            salary=salary,
            employment_type="PKWT" if frontline and rank <= 2 and rng.random() < 0.6 else "PKWTT",
            rating=int(rng.choice([1, 2, 3, 4, 5], p=[0.04, 0.14, 0.56, 0.21, 0.05])),
            personal=float(np.exp(rng.normal(0, EFFECTS["personal_factor_lognormal_sigma"]))),
            overtime_bias=float(rng.normal(0, 7)),
            last_promotion=max(hire, add_months(at, -promo_gap)),
        )
        people.append(p)
        return p

    # Initial workforce, with history before the window.
    for code, _name, _div, _base, n in DEPARTMENTS:
        for _ in range(n):
            new_person(code, start, tenure_years=float(rng.gamma(2.0, 2.6)))
    _assign_managers(people, rng)

    snapshots: list[dict] = []
    movements: list[dict] = []
    for i, month in enumerate(month_list):
        month_end = date(add_months(month, 1).year, add_months(month, 1).month, 1).toordinal() - 1
        active = [p for p in people if p.exit_date is None and p.hire_date.toordinal() <= month_end]
        # Annual cycle: ratings in February, pay review and promotions in April.
        if month.month == 2:
            for p in active:
                if rng.random() < 0.35:
                    p.rating = int(np.clip(p.rating + rng.choice([-1, 1]), 1, 5))
        if month.month == 4:
            for p in active:
                raise_pct = {1: 0.0, 2: 0.025, 3: 0.045, 4: 0.065, 5: 0.085}[p.rating] + rng.normal(
                    0, 0.008
                )
                p.salary *= 1 + max(0.0, raise_pct)
                rank = int(p.grade[1])
                months_since = (
                    (month.year - p.last_promotion.year) * 12 + month.month - p.last_promotion.month
                )
                chance = {1: 0.0, 2: 0.02, 3: 0.08, 4: 0.22, 5: 0.35}[p.rating] * (
                    1.4 if months_since > 30 else 1.0
                )
                if rank < 7 and rng.random() < chance:
                    old = p.grade
                    p.grade = f"G{rank + 1}"
                    p.salary = max(p.salary * 1.12, GRADES[rank][1] * LOCATION_PAY[p.location])
                    p.last_promotion = month
                    movements.append(
                        move(
                            month,
                            p.id,
                            "promotion",
                            from_grade=old,
                            to_grade=p.grade,
                            from_dept=p.department,
                            to_dept=p.department,
                        )
                    )
        # Occasional transfers and manager changes (reorgs, managers leaving).
        for p in active:
            if rng.random() < 0.003:
                old = p.department
                p.department = rng.choice([d[0] for d in DEPARTMENTS if d[0] != old])
                p.manager_changed = month
                movements.append(
                    move(
                        month,
                        p.id,
                        "transfer",
                        from_grade=p.grade,
                        to_grade=p.grade,
                        from_dept=old,
                        to_dept=p.department,
                    )
                )
            elif rng.random() < 0.012:
                p.manager_changed = month
        # Overtime for the month: department base, personal bias, quarter-end peaks.
        for p in active:
            peak = (
                8 if month.month in (3, 6, 9, 12) and p.department in ("FIN", "CLM", "ACT") else 0
            )
            p.overtime.append(
                max(
                    0.0,
                    OVERTIME_BASE.get(p.department, 8) + p.overtime_bias + peak + rng.normal(0, 5),
                )
            )

        # Exits.
        exiting: list[Person] = []
        for p in active:
            age = (month - p.birth_date).days / 365.25
            if age >= 58.5:
                p.exit_type = "retirement"
            elif rng.random() < _hazard(p, month):
                p.exit_type = "voluntary"
            elif rng.random() < (0.004 if p.rating == 1 else 0.0006):
                p.exit_type = "involuntary"
            elif (
                p.employment_type == "PKWT"
                and month.month == p.hire_date.month
                and rng.random() < 0.12
            ):
                p.exit_type = "contract_end"
            if p.exit_type:
                last_day = date(month.year, month.month, int(rng.integers(1, 29)))
                p.exit_date = last_day
                exiting.append(p)
                movements.append(
                    move(
                        last_day,
                        p.id,
                        "exit",
                        exit_type=p.exit_type,
                        from_grade=p.grade,
                        from_dept=p.department,
                    )
                )
        # Reports of leavers get a new manager.
        gone = {p.id for p in exiting}
        leaving_now = gone
        for p in active:
            if p.manager_id in gone and p.exit_date is None:
                p.manager_changed = month

        # Snapshot at month end, including the month someone left.
        for p in active:
            tenure = (month.year - p.hire_date.year) * 12 + month.month - p.hire_date.month
            mc = (
                p.manager_changed
                and (month.year - p.manager_changed.year) * 12
                + month.month
                - p.manager_changed.month
                <= 6
            )
            snapshots.append(
                {
                    "month": month,
                    "employee_id": p.id,
                    "department": p.department,
                    "location": p.location,
                    "grade": p.grade,
                    "gender": p.gender,
                    "age": round((month - p.birth_date).days / 365.25, 1),
                    "tenure_months": tenure,
                    "employment_type": p.employment_type,
                    "salary": round(p.salary, -3),
                    "pay_ratio": round(p.salary / _midpoint(p), 3),
                    "months_since_promotion": (month.year - p.last_promotion.year) * 12
                    + month.month
                    - p.last_promotion.month,
                    "overtime_hours": round(p.overtime[-1], 1),
                    "overtime_3m": round(float(np.mean(p.overtime[-3:])), 1),
                    "rating": p.rating,
                    "manager_changed_6m": bool(mc),
                    "active_eom": p.exit_date is None,
                    "exited": p.id in leaving_now,
                    "exit_type": p.exit_type if p.id in leaving_now else None,
                }
            )

        # Hiring: backfill most exits within a month or two, plus growth in distribution.
        if i < months - 1:
            for p in exiting:
                if (p.exit_type != "retirement" or rng.random() < 0.7) and rng.random() < 0.97:
                    hire_at = add_months(month, int(rng.integers(1, 3)))
                    if hire_at <= month_list[-1]:
                        _schedule_hire(people, p.department, hire_at, new_person, movements, rng)
            for dept in ("BAN", "AGY"):
                if rng.random() < 0.8:
                    _schedule_hire(people, dept, add_months(month, 1), new_person, movements, rng)

    return Simulation(people=people, snapshots=snapshots, movements=movements, months=month_list)


def _schedule_hire(people, dept, at, factory, movements, rng):
    p = factory(dept, at)
    p.hire_date = date(at.year, at.month, int(rng.integers(1, 20)))
    p.last_promotion = p.hire_date
    leaders = [
        x
        for x in people
        if x.department == dept and x.exit_date is None and x.grade >= "G4" and x is not p
    ]
    p.manager_id = leaders[int(rng.integers(0, len(leaders)))].id if leaders else None
    movements.append(move(p.hire_date, p.id, "hire", to_grade=p.grade, to_dept=dept))


def _assign_managers(people: list[Person], rng: np.random.Generator) -> None:
    by_dept: dict[str, list[Person]] = {}
    for p in people:
        by_dept.setdefault(p.department, []).append(p)
    for members in by_dept.values():
        leaders = [m for m in members if m.grade >= "G4"] or members[:1]
        for m in members:
            others = [x for x in leaders if x is not m]
            m.manager_id = others[int(rng.integers(0, len(others)))].id if others else None


def age_band(age: float) -> str:
    if age < 25:
        return "<25"
    if age < 35:
        return "25-34"
    if age < 45:
        return "35-44"
    if age < 55:
        return "45-54"
    return "55+"


def tenure_band(months: int) -> str:
    if months < 12:
        return "<1y"
    if months < 36:
        return "1-3y"
    if months < 60:
        return "3-5y"
    if months < 120:
        return "5-10y"
    return "10y+"


__all__ = ["EFFECTS", "Simulation", "age_band", "simulate", "tenure_band"]
