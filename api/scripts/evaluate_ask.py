"""Score the Ask parsers against data/ask_eval.jsonl.

    python -m scripts.evaluate_ask                  # rules parser, all splits
    python -m scripts.evaluate_ask --split dev
    python -m scripts.evaluate_ask --llm            # Gemini (needs GEMINI_API_KEY)

A question counts as correct only if every part of the spec matches: metric,
dimensions, filters, period, order and limit; or, for questions that should be refused,
if the parser refuses. The expected periods assume data up to October 2026.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import date
from pathlib import Path

from app import ask
from app.metrics import STATIC_DOMAINS

DATA = Path(__file__).resolve().parents[1] / "data" / "ask_eval.jsonl"
LATEST = date(2026, 10, 1)
FIRST = date(2024, 1, 1)


def normalise(spec: dict | None, unsupported: bool) -> dict:
    if unsupported or spec is None:
        return {"unsupported": True}
    filters = spec.get("filters") or {}
    if isinstance(filters, list):
        filters = {f["dimension"]: f["values"] for f in filters}
    period = spec.get("period")
    if isinstance(period, dict):
        period = [period["start"], period["end"]]
    return {
        "metric": spec.get("metric"),
        "dimensions": sorted(spec.get("dimensions") or []),
        "filters": {k: sorted(v) for k, v in sorted(filters.items())},
        "period": [str(p)[:7] for p in period],
        "order": spec.get("order"),
        "limit": spec.get("limit"),
    }


def domains() -> dict[str, dict[str, str]]:
    d = {k: dict(v) for k, v in STATIC_DOMAINS.items()}
    d["department"] = {code: names[0].title() for code, names in ask.DEPARTMENTS.items()}
    d["location"] = {code: names[0].title() for code, names in ask.LOCATIONS.items()}
    d["grade"] = {f"G{i}": f"G{i}" for i in range(1, 8)}
    d["division"] = {x.capitalize(): x.capitalize() for x in ask.DIVISIONS}
    return d


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "heldout"])
    parser.add_argument("--llm", action="store_true")
    args = parser.parse_args()

    rows = [json.loads(line) for line in DATA.read_text(encoding="utf8").splitlines() if line]
    if args.split:
        rows = [r for r in rows if r["split"] == args.split]
    score: dict[str, list[int]] = {}
    failures = []
    for r in rows:
        if args.llm:
            parsed = ask.parse_llm(r["q"], LATEST, FIRST, domains())
            if parsed is None:
                raise SystemExit("Gemini call failed or GEMINI_API_KEY is not set")
            time.sleep(4)  # stay inside the free tier's per-minute limit
        else:
            parsed = ask.parse_rules(r["q"], LATEST)
        got = normalise(parsed.spec, parsed.unsupported is not None)
        want = (
            normalise(None, True)
            if r["expect"].get("unsupported")
            else normalise(
                {"dimensions": [], "filters": {}, "order": None, "limit": None} | r["expect"], False
            )
        )
        ok = got == want
        score.setdefault(r["split"], []).append(int(ok))
        if not ok:
            diff = {
                k: (want.get(k), got.get(k))
                for k in set(want) | set(got)
                if want.get(k) != got.get(k)
            }
            failures.append((r["split"], r["q"], diff))

    name = "gemini" if args.llm else "rules"
    for split, marks in score.items():
        print(f"{name} {split}: {sum(marks)}/{len(marks)} correct ({sum(marks) / len(marks):.0%})")
    for split, q, diff in failures:
        print(f"  [{split}] {q}")
        for k, (want, got) in diff.items():
            print(f"      {k}: expected {want!r}, got {got!r}")


if __name__ == "__main__":
    main()
