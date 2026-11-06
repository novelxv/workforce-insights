import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from app import ask
from app.config import get_settings

LATEST = date(2026, 10, 1)
EVAL = Path(__file__).resolve().parents[1] / "data" / "ask_eval.jsonl"
CASES = [json.loads(line) for line in EVAL.read_text(encoding="utf8").splitlines() if line]


def _normal(spec: dict) -> dict:
    return {
        "metric": spec["metric"],
        "dimensions": sorted(spec["dimensions"]),
        "filters": {f["dimension"]: sorted(f["values"]) for f in spec["filters"]},
        "period": [spec["period"]["start"], spec["period"]["end"]],
        "order": spec["order"],
        "limit": spec["limit"],
    }


@pytest.mark.parametrize("case", CASES, ids=[c["q"] for c in CASES])
def test_rules_parser_matches_the_evaluation_set(case):
    parsed = ask.parse_rules(case["q"], LATEST)
    if case["expect"].get("unsupported"):
        assert parsed.unsupported
        return
    assert parsed.unsupported is None, parsed.unsupported
    want = {"dimensions": [], "filters": {}, "order": None, "limit": None} | case["expect"]
    want["dimensions"] = sorted(want["dimensions"])
    want["filters"] = {k: sorted(v) for k, v in want["filters"].items()}
    assert _normal(parsed.spec) == want


@pytest.mark.parametrize(
    "question,reason",
    [
        ("Who is about to resign?", ask.INDIVIDUALS),
        ("Show me the names of leavers in Claims", ask.INDIVIDUALS),
        ("Forecast headcount for 2027", ask.FORECAST),
        ("Why did turnover rise in Customer Service?", ask.WHY),
    ],
)
def test_refusals(question, reason):
    assert ask.parse_rules(question, LATEST).unsupported == reason


def test_unknown_metric_is_refused_with_a_list_of_what_exists():
    parsed = ask.parse_rules("What is our employee net promoter score?", LATEST)
    assert parsed.spec is None and "headcount" in parsed.unsupported


def test_lowercase_it_and_hr_are_words_not_departments():
    spec = ask.parse_rules("Is it true that hr turnover is high?", LATEST).spec
    assert spec["filters"] == []
    spec = ask.parse_rules("Turnover in IT", LATEST).spec
    assert spec["filters"] == [{"dimension": "department", "values": ["ITD"]}]


def test_second_dimension_joined_with_and():
    spec = ask.parse_rules("Headcount by department and gender", LATEST).spec
    assert spec["dimensions"] == ["department", "gender"]


def test_last_quarter_is_the_latest_complete_quarter():
    spec = ask.parse_rules("hires last quarter", LATEST).spec
    assert spec["period"] == {"start": "2026-07", "end": "2026-09"}
    spec = ask.parse_rules("hires last quarter", date(2026, 9, 1)).spec
    assert spec["period"] == {"start": "2026-07", "end": "2026-09"}


# --- Gemini path, with the HTTP call replaced -------------------------------------------


class _Resp:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(self._payload)}]}}]}


@pytest.fixture
def gemini_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key")


def test_gemini_spec_is_normalised(monkeypatch, gemini_key):
    sent = {}

    def fake_post(url, headers, json, timeout):
        sent["schema"] = json["generationConfig"]["responseSchema"]
        sent["prompt"] = json["contents"][0]["parts"][0]["text"]
        return _Resp(
            {
                "supported": True,
                "reason": "",
                "metric": "headcount",
                "dimensions": ["grade"],
                "filters": [{"dimension": "location", "values": ["JKT"]}],
                "period_start": "2025-01",
                "period_end": "2026-06",
                "order": "none",
                "limit": 0,
            }
        )

    monkeypatch.setattr(ask.httpx, "post", fake_post)
    parsed = ask.parse("headcount by grade in Jakarta", LATEST, date(2024, 1, 1), {})
    assert parsed.parser == "gemini"
    # Point-in-time metric without a time dimension: the period collapses to its end.
    assert parsed.spec["period"] == {"start": "2026-06", "end": "2026-06"}
    assert parsed.spec["order"] is None and parsed.spec["limit"] is None
    assert sent["schema"]["properties"]["metric"]["enum"] == list(ask.METRICS)
    assert "never see data" in sent["prompt"]


def test_gemini_refusal_is_passed_through(monkeypatch, gemini_key):
    monkeypatch.setattr(
        ask.httpx,
        "post",
        lambda *a, **k: _Resp(
            {
                "supported": False,
                "reason": "Asks about a named person.",
                "metric": "headcount",
                "dimensions": [],
                "filters": [],
                "period_start": "",
                "period_end": "",
                "order": "none",
                "limit": 0,
            }
        ),
    )
    parsed = ask.parse("How likely is Gita to resign?", LATEST, date(2024, 1, 1), {})
    assert parsed.parser == "gemini" and parsed.unsupported == "Asks about a named person."


def test_gemini_failure_falls_back_to_rules(monkeypatch, gemini_key):
    def boom(*a, **k):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(ask.httpx, "post", boom)
    parsed = ask.parse("turnover by department", LATEST, date(2024, 1, 1), {})
    assert parsed.parser == "rules" and parsed.spec["dimensions"] == ["department"]


def test_without_a_key_rules_are_used():
    assert ask.parse("headcount", LATEST, date(2024, 1, 1), {}).parser == "rules"
