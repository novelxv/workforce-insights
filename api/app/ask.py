"""Ask: a question in plain English (or simple Indonesian) becomes a metrics `Spec`.

Two parsers produce the same structure:

- Gemini, when a key is configured. Its response is constrained by a JSON schema whose
  enums are the metric, dimension and value codes from the semantic layer. It sees the
  catalogue and the question, never data, and never writes SQL.
- A rules parser for the common phrasings, used when there is no key or the call fails.

Either way the spec then goes through `metrics.check`, so an invented metric, value or
period is rejected before a query runs. Questions about individuals and forecasts are
refused with a pointer to where that information lives.

Conventions both parsers follow (also given to the model):
- No period: the 12 months ending with the latest month of data.
- "last year" is the previous calendar year; "past year" / "last 12 months" is trailing.
- "this year" / "YTD" runs from January to the latest month.
- "last quarter" is the latest complete quarter.
- Stock metrics (headcount, shares, averages at a point) use the end of the period.
- "which X has the highest ..." ranks every X; "top N" keeps N.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date

import httpx

from app.config import get_settings
from app.metrics import DIMENSIONS, METRICS, STATIC_DOMAINS, add_months

log = logging.getLogger(__name__)


@dataclass
class Parsed:
    parser: str
    spec: dict | None = None
    unsupported: str | None = None
    error: str | None = None
    notes: list[str] = field(default_factory=list)


EXAMPLES = [
    "Voluntary turnover by department",
    "Headcount trend over the last 24 months",
    "How many people resigned in 2025?",
    "Women in workforce by grade",
    "Top 5 departments by resignations in the past 6 months",
    "Compa-ratio by gender",
]

INDIVIDUALS = (
    "Ask answers questions about groups, not individuals. Individual attrition scores are "
    "on the Risk page, for HR roles, with the reasons behind each score."
)
FORECAST = (
    "Ask reports what has already happened; it does not forecast. The Risk page estimates "
    "who is more likely than average to resign in the next six months."
)
WHY = (
    "Ask returns figures, not causes. Try breaking the figure down (by department, tenure "
    "or grade) or see the drivers on the Risk page."
)

# --- Vocabulary -----------------------------------------------------------------------------

MONTHS = {
    "january": 1, "jan": 1, "januari": 1, "february": 2, "feb": 2, "februari": 2,
    "march": 3, "mar": 3, "maret": 3, "april": 4, "apr": 4, "may": 5, "mei": 5,
    "june": 6, "jun": 6, "juni": 6, "july": 7, "jul": 7, "juli": 7, "august": 8, "aug": 8,
    "agustus": 8, "september": 9, "sep": 9, "sept": 9, "october": 10, "oct": 10,
    "oktober": 10, "november": 11, "nov": 11, "december": 12, "dec": 12, "desember": 12,
}  # fmt: skip
MONTH_RE = "(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + ")"
NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "eighteen": 18, "twenty-four": 24,
    "satu": 1, "dua": 2, "tiga": 3, "enam": 6,
}  # fmt: skip
NUM_RE = r"(\d+|" + "|".join(sorted(NUMBERS, key=len, reverse=True)) + ")"

DEPARTMENTS: dict[str, list[str]] = {
    "ACT": ["actuarial", "actuaries", "aktuaria"],
    "UW": ["underwriting", "underwriters"],
    "CLM": ["claims", "claim", "klaim"],
    "POL": ["policy administration", "policy admin", "policy servicing"],
    "CSV": [
        "customer service",
        "customer care",
        "contact centre",
        "contact center",
        "call centre",
        "call center",
    ],
    "ITD": ["information technology", "it department", "it team"],
    "GAF": ["general affairs"],
    "BAN": ["bancassurance", "banca"],
    "AGY": ["agency development", "agency"],
    "MKT": ["marketing & product", "marketing and product", "marketing"],
    "FIN": ["finance & accounting", "finance and accounting", "finance", "accounting", "keuangan"],
    "INV": ["investment", "investments", "investasi"],
    "CMP": ["compliance", "aml/cft", "kepatuhan"],
    "RSK": ["risk management", "risk team", "manajemen risiko"],
    "LGL": ["legal", "hukum"],
    "IAU": ["internal audit", "audit"],
    "HRD": ["human capital", "human resources", "hr department", "hr team"],
}
# Short acronyms only count in capitals, so "it" and "hr" in a sentence are left alone.
DEPARTMENT_ACRONYMS = {"IT": "ITD", "HR": "HRD", "SDM": "HRD", "UW": "UW", "GA": "GAF"}
DIVISIONS = ["technical", "operations", "distribution", "finance", "governance", "support"]
# Words that name a division even without the word "division".
DIVISION_ALONE = {"technical", "operations", "distribution", "governance"}
LOCATIONS = {
    "JKT": ["jakarta", "head office"], "SBY": ["surabaya"], "BDG": ["bandung"],
    "MDN": ["medan"], "MKS": ["makassar"],
}  # fmt: skip
FEMALE = ["women", "woman", "female", "females", "ladies", "perempuan", "wanita"]
MALE = ["men", "man", "male", "males", "pria", "laki-laki"]
PKWT = [
    "pkwt",
    "fixed-term",
    "fixed term",
    "contract staff",
    "contractors",
    "contract workers",
    "kontrak",
]
PKWTT = ["pkwtt", "permanent", "tetap"]
AGE_PATTERNS = {
    "<25": [r"(under|below|younger than|less than) 25", r"<\s?25", r"gen z"],
    "25-34": [r"25\s?(-|–|to)\s?34"],
    "35-44": [r"35\s?(-|–|to)\s?44"],
    "45-54": [r"45\s?(-|–|to)\s?54"],
    "55+": [r"(over|above|older than) 55", r"55\s?\+"],
}
TENURE_PATTERNS = {
    "<1y": [r"(less than|under) (a|one|1) years?( of service| tenure)?", r"<\s?1\s?y"],
    "1-3y": [r"1\s?(-|–|to)\s?3 years?"],
    "3-5y": [r"3\s?(-|–|to)\s?5 years?"],
    "5-10y": [r"5\s?(-|–|to)\s?10 years?"],
    "10y+": [r"(over|more than) 10 years?", r"10\s?\+ years?"],
}

# Single words that name a metric only when nothing more specific is in the question:
# "women" is the female-share metric in "what share are women?" but a filter in
# "resignations among women".
WEAK_METRIC = {
    "women": "female_share",
    "woman": "female_share",
    "female": "female_share",
    "tenure": "avg_tenure_years",
    "masa kerja": "avg_tenure_years",
}
EXTRA_METRIC = {
    "avg_tenure_years": ["average tenure", "avg tenure", "rata-rata masa kerja"],
    "exits": ["people left", "left", "keluar", "exit", "leaver", "separation"],
    "voluntary_exits": ["resignation", "resign", "resigning", "mengundurkan diri"],
    "hires": ["joined", "hiring", "new employees", "karyawan baru"],
    "avg_overtime_hours": ["overtime per person"],
}
HEADCOUNT_CUES = [
    "how many people",
    "how many employees",
    "how many staff",
    "employees",
    "staff",
    "people",
    "karyawan",
    "pegawai",
    "workforce",
    "berapa orang",
]
DIM_PREFIX = (
    r"(?:by|per|across|for each|for every|in each|each|every|split by|broken down by|"
    r"breakdown by|break down by|grouped by|which|what|top \d+|bottom \d+|lowest \d+|"
    r"highest \d+|\d+)"
)
TIME_CUES = {
    "month": [
        "monthly",
        "trend",
        "over time",
        "month by month",
        "month-on-month",
        "bulanan",
        "tren",
    ],
    "quarter": ["quarterly", "quarter by quarter"],
    "year": ["yearly", "year by year", "year-on-year", "tahunan"],
}
EXTRA_DIM = {
    "location": ["branches", "branch offices"],
    "age_band": ["age groups", "ages"],
    "tenure_band": ["tenure bands"],
    "department": ["departemen"],
}


def _w(phrase: str) -> str:
    """A phrase as a regex that only matches whole words."""
    return r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])"


def _any(phrases) -> str:
    return "(?:" + "|".join(_w(p) for p in sorted(phrases, key=len, reverse=True)) + ")"


class Text:
    """The question with matched phrases blanked out, so each phrase is used once."""

    def __init__(self, question: str):
        o = " " + re.sub(r"\s+", " ", question.replace("’", "'")).strip() + " "
        self.o = o
        self.t = o.lower() if len(o.lower()) == len(o) else o

    def find(self, pattern: str, *, case: bool = False) -> re.Match | None:
        return re.search(pattern, self.o if case else self.t)

    def take(self, pattern: str, *, case: bool = False) -> re.Match | None:
        m = self.find(pattern, case=case)
        if m:
            a, b = m.span()
            self.t = self.t[:a] + " " * (b - a) + self.t[b:]
            self.o = self.o[:a] + " " * (b - a) + self.o[b:]
        return m

    def has(self, pattern: str) -> bool:
        return self.find(pattern) is not None


# --- Periods ----------------------------------------------------------------------------


def _num(s: str) -> int:
    return int(s) if s.isdigit() else NUMBERS[s]


def _period(t: Text, latest: date) -> tuple[date, date] | None:
    y = latest.year

    if m := t.take(rf"(?:last|past|previous|the last|the past|terakhir) {NUM_RE} months?"):
        n = _num(m.group(1))
        return add_months(latest, -(n - 1)), latest
    if m := t.take(rf"{NUM_RE} bulan terakhir"):
        n = _num(m.group(1))
        return add_months(latest, -(n - 1)), latest
    if m := t.take(rf"(?:last|past|previous) {NUM_RE} years?"):
        n = _num(m.group(1))
        return add_months(latest, -(12 * n - 1)), latest
    if t.take(
        r"(?:the )?(?:past year|last twelve months|trailing 12 months|rolling 12 months"
        r"|ttm|setahun terakhir)"
    ):
        return add_months(latest, -11), latest
    if t.take(r"(?:last year|previous year|tahun lalu)"):
        return date(y - 1, 1, 1), date(y - 1, 12, 1)
    if t.take(r"(?:this year|year to date|year-to-date|ytd|so far this year|tahun ini)"):
        return date(y, 1, 1), latest
    if t.take(r"(?:last|previous) quarter|kuartal lalu"):
        q_start = date(y, (latest.month - 1) // 3 * 3 + 1, 1)
        end = latest if latest.month % 3 == 0 else add_months(q_start, -1)
        return add_months(end, -2), end
    if t.take(r"this quarter|kuartal ini"):
        return date(y, (latest.month - 1) // 3 * 3 + 1, 1), latest
    if m := t.take(r"(?<![a-z0-9])q([1-4])(?: (\d{4}))?(?![a-z0-9])"):
        year = int(m.group(2)) if m.group(2) else y
        start = date(year, (int(m.group(1)) - 1) * 3 + 1, 1)
        return start, add_months(start, 2)
    if t.take(r"(?:last|previous|this) month|bulan lalu|bulan ini"):
        return latest, latest
    if m := t.take(rf"between {MONTH_RE}(?: (\d{{4}}))? and {MONTH_RE} (\d{{4}})"):
        y2 = int(m.group(4))
        return date(int(m.group(2) or y2), MONTHS[m.group(1)], 1), date(y2, MONTHS[m.group(3)], 1)
    if m := t.take(
        rf"from {MONTH_RE}(?: (\d{{4}}))? (?:to|until|through|till) {MONTH_RE}"
        rf"(?: (\d{{4}}))?"
    ):
        y2 = int(m.group(4) or m.group(2) or y)
        return date(int(m.group(2) or y2), MONTHS[m.group(1)], 1), date(y2, MONTHS[m.group(3)], 1)
    if m := t.take(rf"(?:since|sejak) {MONTH_RE} (\d{{4}})"):
        return date(int(m.group(2)), MONTHS[m.group(1)], 1), latest
    if m := t.take(r"(?:since|sejak) (\d{4})"):
        return date(int(m.group(1)), 1, 1), latest
    if m := t.take(rf"(?:at the end of|end of|as of|as at|per) {MONTH_RE} (\d{{4}})"):
        d = date(int(m.group(2)), MONTHS[m.group(1)], 1)
        return d, d
    if m := t.take(rf"(?:in |during |for )?{MONTH_RE} (\d{{4}})"):
        d = date(int(m.group(2)), MONTHS[m.group(1)], 1)
        return d, d
    if m := t.take(r"(?:in |during |for |over |tahun )?(20\d\d)(?![0-9])"):
        year = int(m.group(1))
        return date(year, 1, 1), date(year, 12, 1)
    return None


# --- Rules parser -----------------------------------------------------------------------


def parse_rules(question: str, latest: date) -> Parsed:
    t = Text(question)
    out = Parsed(parser="rules")

    # Refusals first.
    if t.has(r"(?<![a-z])(who|whom|names?|nama)(?![a-z])") or t.has(
        r"which (employees|people|staff|persons?|individuals)|list (of )?(the )?"
        r"(people|employees|staff)|individual"
    ):
        out.unsupported = INDIVIDUALS
        return out
    if t.has(
        r"(?<![a-z])(will|forecast|predict|prediction|projection|projected|expected to|"
        r"next (year|month|quarter|six months))(?![a-z])"
    ):
        out.unsupported = FORECAST
        return out
    if t.has(r"^ why |(?<![a-z])why (is|are|did|do|does|has|have)(?![a-z])|mengapa|kenapa"):
        out.unsupported = WHY
        return out

    period = _period(t, latest)

    order: str | None = None
    limit: int | None = None
    if m := t.find(
        r"(?:top|highest|largest|biggest|most) (\d+)|(\d+) (?:highest|largest|"
        r"biggest|worst)"
    ):
        order, limit = "value_desc", int(m.group(1) or m.group(2))
    elif m := t.find(r"(?:bottom|lowest|smallest|fewest|least) (\d+)|(\d+) (?:lowest|smallest)"):
        order, limit = "value_asc", int(m.group(1) or m.group(2))

    # Dimensions: "by department", "per month", "which office", "monthly", "trend".
    found: list[tuple[int, str]] = []
    for key, dim in DIMENSIONS.items():
        alts = [s for s in dim.synonyms if s not in TIME_CUES.get(key, [])] + EXTRA_DIM.get(key, [])
        pattern = rf"(?<![a-z0-9]){DIM_PREFIX} (?:our |the |all |different )?{_any(alts)}"
        if m := t.take(pattern):
            found.append((m.start(), key))
            if m.group(0).lstrip().startswith(("which", "what")) and order is None:
                order = (
                    "value_asc"
                    if t.has(_any(["lowest", "least", "fewest", "smallest"]))
                    else "value_desc"
                )
    # "by department and gender": a second dimension joined to a phrase already taken.
    # Taken phrases are blanked to spaces, so two spaces mark where one ended.
    if found:
        for key, dim in DIMENSIONS.items():
            if any(k == key for _, k in found):
                continue
            alts = [s for s in dim.synonyms if s not in TIME_CUES.get(key, [])]
            alts += EXTRA_DIM.get(key, [])
            if m := t.take(rf"(?<=  )(?:and|&) (?:by )?(?:the )?{_any(alts)}"):
                found.append((m.start(), key))
    for key, cues in TIME_CUES.items():
        if not any(k == key for _, k in found) and (m := t.take(_any(cues))):
            found.append((m.start(), key))
    found.sort()
    dimensions = [k for _, k in found]
    if order is None and dimensions and not DIMENSIONS[dimensions[0]].time:
        if t.has(
            _any(
                [
                    "highest",
                    "most",
                    "largest",
                    "biggest",
                    "worst",
                    "rank",
                    "ranked",
                    "ranking",
                    "tertinggi",
                ]
            )
        ):
            order = "value_desc"
        elif t.has(_any(["lowest", "least", "fewest", "smallest", "terendah"])):
            order = "value_asc"

    # Filters.
    filters: dict[str, list[str]] = {}

    def add(dim: str, value: str) -> None:
        if value not in filters.setdefault(dim, []):
            filters[dim].append(value)

    for div in DIVISIONS:
        if t.take(rf"{_w(div)} (?:division|directorate)|(?:division|divisi) {_w(div)}") or (
            div in DIVISION_ALONE and t.take(_w(div))
        ):
            add("division", div.capitalize())
    for code, names in DEPARTMENTS.items():
        if t.take(_any(names)):
            add("department", code)
    for acronym, code in DEPARTMENT_ACRONYMS.items():
        if t.take(rf"(?<![A-Za-z0-9]){acronym}(?![A-Za-z0-9])", case=True):
            add("department", code)
    for code, names in LOCATIONS.items():
        if t.take(_any(names)):
            add("location", code)
    while m := t.take(r"(?<![a-z0-9])(?:g|grade )([1-7])(?![a-z0-9])"):
        add("grade", f"G{m.group(1)}")
    for band, patterns in AGE_PATTERNS.items():
        if any(t.take(rf"(?<![a-z0-9])(?:aged |age )?{p}(?![a-z0-9])") for p in patterns):
            add("age_band", band)
    for band, patterns in TENURE_PATTERNS.items():
        if any(t.take(rf"(?<![a-z0-9]){p}(?![a-z0-9])") for p in patterns):
            add("tenure_band", band)
    if t.take(_any(PKWTT)):
        add("employment_type", "PKWTT")
    if t.take(_any(PKWT)):
        add("employment_type", "PKWT")
    share_cue = t.has(
        _any(["share", "percentage", "percent", "proportion", "ratio", "%", "persentase", "porsi"])
    )
    female, male = t.find(_any(FEMALE)), t.find(_any(MALE))

    # Metric: the longest specific phrase wins; weak words and generic cues are fallbacks.
    metric: str | None = None
    best = 0
    for key, m_ in METRICS.items():
        for phrase in [*m_.synonyms, *EXTRA_METRIC.get(key, [])]:
            if phrase in WEAK_METRIC:
                continue
            if len(phrase) > best and t.has(_w(phrase)):
                metric, best = key, len(phrase)
    first_year = t.has(_any(["first year", "first-year", "first 12 months", "tahun pertama"]))
    voluntary = t.has(r"voluntar|resign|(?<![a-z])quit|mengundurkan")
    rate = t.has(_any(["rate", "rates", "tingkat"]))
    if metric in ("exits", "voluntary_exits", "turnover_rate", "voluntary_turnover_rate") and (
        first_year
    ):
        metric = "early_exit_share"
    if metric == "turnover_rate" and voluntary:
        metric = "voluntary_turnover_rate"
    if metric == "exits" and voluntary:
        metric = "voluntary_exits"
    if rate and metric in ("exits", "voluntary_exits", "promotions"):
        metric = {
            "exits": "turnover_rate",
            "voluntary_exits": "voluntary_turnover_rate",
            "promotions": "promotion_rate",
        }[metric]
    if metric in (None, "headcount") and share_cue and "PKWT" in filters.get("employment_type", []):
        metric = "pkwt_share"
    if metric in (None, "headcount") and share_cue and female:
        metric = "female_share"
    if metric is None:
        for word, key in WEAK_METRIC.items():
            if t.has(_w(word)):
                metric = key
                break
    if metric is None and t.has(_any(HEADCOUNT_CUES)):
        metric = "headcount"
    if metric is None:
        out.unsupported = (
            "That is not one of the defined metrics. Try headcount, hires, exits, "
            "resignations, turnover, promotions, tenure, overtime, compa-ratio or the "
            "share of women or fixed-term staff."
        )
        return out

    # Gender: both sexes named is a breakdown; one is a filter, unless the metric is
    # itself the share of women.
    if metric != "female_share":
        if female and male and "gender" not in dimensions:
            dimensions.append("gender")
        elif female and not male:
            add("gender", "F")
        elif male and not female:
            add("gender", "M")
    if metric == "pkwt_share":
        filters.pop("employment_type", None)
    if len(filters.get("employment_type", [])) == 2:
        filters.pop("employment_type")
        if "employment_type" not in dimensions:
            dimensions.append("employment_type")
    dimensions = dimensions[:2]

    start, end = period or (add_months(latest, -11), latest)
    if METRICS[metric].stock and not any(DIMENSIONS[d].time for d in dimensions):
        start = end
    out.spec = {
        "metric": metric,
        "dimensions": dimensions,
        "filters": [{"dimension": d, "values": v} for d, v in filters.items()],
        "period": {"start": start.isoformat()[:7], "end": end.isoformat()[:7]},
        "order": order if dimensions else None,
        "limit": limit if dimensions else None,
    }
    return out


# --- Gemini parser ----------------------------------------------------------------------

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

PROMPT = """You translate questions from HR leaders at an Indonesian life insurer into a
query specification for its workforce analytics. You do not answer the question and you
never see data. Only use the metrics, dimensions and codes listed below. If the question
asks about named or individual employees, asks for a forecast, asks why something
happened, or needs a metric that is not listed, set supported to false and say why in
reason.

Latest month with data: {latest}. Data starts: {first}.

Metrics:
{metrics}

Dimensions (break the metric down by at most two):
{dimensions}

Filter values by dimension (use the codes on the left):
{values}

Conventions:
- No period mentioned: the 12 months ending with the latest month.
- "last year" is the previous calendar year; "past year" or "last 12 months" is trailing.
- "this year" or "YTD" is January of the latest year to the latest month.
- "last quarter" is the latest complete quarter.
- Metrics marked [point in time] are measured at the end of the period; for those, with no
  month/quarter/year dimension, set period_start equal to period_end.
- "which department has the highest X" means dimension department, order value_desc,
  limit 0. "top 5" means limit 5. Otherwise order none and limit 0.
- "trend", "monthly" or "over time" means the month dimension.
- A word like "women" or "Jakarta" in the question is a filter unless the metric itself
  is the share of women, or the question compares groups ("men and women", "by office").
- Indonesian is fine: "karyawan" employees, "per departemen" by department, "tahun ini"
  this year, "tahun lalu" last year.

Question: {question}
"""


def _gemini_schema() -> dict:
    values = sorted(
        {v for d in STATIC_DOMAINS.values() for v in d}
        | set(DEPARTMENTS)
        | set(LOCATIONS)
        | {f"G{i}" for i in range(1, 8)}
        | {d.capitalize() for d in DIVISIONS}
    )
    return {
        "type": "OBJECT",
        "properties": {
            "supported": {"type": "BOOLEAN"},
            "reason": {"type": "STRING"},
            "metric": {"type": "STRING", "enum": list(METRICS)},
            "dimensions": {"type": "ARRAY", "items": {"type": "STRING", "enum": list(DIMENSIONS)}},
            "filters": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "dimension": {
                            "type": "STRING",
                            "enum": [d for d in DIMENSIONS if not DIMENSIONS[d].time],
                        },
                        "values": {"type": "ARRAY", "items": {"type": "STRING", "enum": values}},
                    },
                    "required": ["dimension", "values"],
                },
            },
            "period_start": {"type": "STRING", "description": "YYYY-MM"},
            "period_end": {"type": "STRING", "description": "YYYY-MM"},
            "order": {"type": "STRING", "enum": ["none", "value_desc", "value_asc"]},
            "limit": {"type": "INTEGER"},
        },
        "required": [
            "supported",
            "reason",
            "metric",
            "dimensions",
            "filters",
            "period_start",
            "period_end",
            "order",
            "limit",
        ],
    }


def _prompt(question: str, latest: date, first: date, domains: dict[str, dict[str, str]]) -> str:
    metrics = "\n".join(
        f"- {m.key}: {m.label}{' [point in time]' if m.stock else ''}. {m.definition}"
        for m in METRICS.values()
    )
    dims = "\n".join(f"- {d.key}: {d.label}" for d in DIMENSIONS.values())
    values = "\n".join(
        f"- {dim}: " + "; ".join(f"{code} = {label}" for code, label in vals.items())
        for dim, vals in domains.items()
    )
    return PROMPT.format(
        latest=latest.strftime("%Y-%m (%B %Y)"),
        first=first.strftime("%Y-%m"),
        metrics=metrics,
        dimensions=dims,
        values=values,
        question=question,
    )


def parse_llm(
    question: str, latest: date, first: date, domains: dict[str, dict[str, str]]
) -> Parsed | None:
    """Ask Gemini for a spec. None when no key is set or the call fails."""
    s = get_settings()
    if not s.gemini_api_key:
        return None
    body = {
        "contents": [{"parts": [{"text": _prompt(question, latest, first, domains)}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": _gemini_schema(),
        },
    }
    try:
        resp = httpx.post(
            ENDPOINT.format(model=s.llm_model),
            headers={"x-goog-api-key": s.gemini_api_key},
            json=body,
            timeout=s.llm_timeout_seconds,
        )
        resp.raise_for_status()
        data = json.loads(resp.json()["candidates"][0]["content"]["parts"][0]["text"])
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        log.warning("Gemini parse failed, falling back to rules: %s", exc)
        return None
    out = Parsed(parser="gemini")
    if not data.get("supported", False):
        out.unsupported = str(data.get("reason") or "That question is outside what Ask covers.")
        return out
    metric = data.get("metric")
    dims = [d for d in data.get("dimensions", []) if d in DIMENSIONS][:2]
    start, end = data.get("period_start", ""), data.get("period_end", "")
    if metric in METRICS and METRICS[metric].stock and not any(DIMENSIONS[d].time for d in dims):
        start = end
    order = data.get("order")
    limit = data.get("limit") or None
    out.spec = {
        "metric": metric,
        "dimensions": dims,
        "filters": [f for f in data.get("filters", []) if f.get("values")],
        "period": {"start": start, "end": end},
        "order": order if order in ("value_desc", "value_asc") and dims else None,
        "limit": limit if dims and limit else None,
    }
    return out


def parse(question: str, latest: date, first: date, domains: dict[str, dict[str, str]]) -> Parsed:
    question = question.strip()[:300]
    return parse_llm(question, latest, first, domains) or parse_rules(question, latest)
