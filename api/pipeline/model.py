"""Attrition risk: who is likely to resign voluntarily in the next six months.

Design choices, each to keep the model honest:

* Time-based split. Train on earlier months, tune on later ones, report on the latest
  months whose six-month outcome is known. A random split would leak an employee's future
  into their own training rows.
* Gender and age are not features. They are used only to audit the scores.
* Probabilities are calibrated (isotonic, fitted on the validation months), so "25%" means
  roughly one in four.
* Explanations come from LightGBM's own TreeSHAP contributions (pred_contrib), translated
  into sentences an HRBP can act on.
* The simulation's planted drivers are known, so the report checks the model found them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from pipeline.simulate import age_band, planted_hazard

HORIZON = 6
FEATURES = [
    "tenure_months",
    "grade_rank",
    "pay_ratio",
    "months_since_promotion",
    "overtime_3m",
    "rating",
    "manager_changed_6m",
    "on_pkwt",
    "pay_change_12m",
    "department",
    "location",
]
CATEGORICAL = ["department", "location"]
PARAMS = {
    "objective": "binary",
    "learning_rate": 0.03,
    "num_leaves": 15,
    "min_data_in_leaf": 60,
    "feature_fraction": 0.9,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "lambda_l2": 2.0,
    "metric": "average_precision",
    "verbosity": -1,
    "seed": 7,
}


@dataclass
class TrainedModel:
    version: str
    booster: lgb.Booster
    calibrator: IsotonicRegression
    metrics: dict
    fairness: dict
    importance: list[dict]
    calibration: list[dict]
    splits: dict


def frame(snapshots: list[dict], months: list[date]) -> pd.DataFrame:
    df = pd.DataFrame(snapshots)
    index = {m: i for i, m in enumerate(months)}
    df["t"] = df["month"].map(index)
    df["grade_rank"] = df["grade"].str[1].astype(int)
    df["age_band"] = df["age"].map(age_band)
    df["on_pkwt"] = (df["employment_type"] == "PKWT").astype(int)
    df["manager_changed_6m"] = df["manager_changed_6m"].astype(int)
    df = df.sort_values(["employee_id", "t"])
    lagged = df.groupby("employee_id")["salary"].shift(12)
    df["pay_change_12m"] = ((df["salary"] / lagged) - 1).round(3)
    exits = df[df["exited"]][["employee_id", "t", "exit_type"]].rename(columns={"t": "exit_t"})
    df = df.merge(exits, on="employee_id", how="left", suffixes=("", "_final"))
    soon = (df["exit_t"] > df["t"]) & (df["exit_t"] <= df["t"] + HORIZON)
    df["label"] = (soon & (df["exit_type_final"] == "voluntary")).astype(int)
    for c in CATEGORICAL:
        df[c] = df[c].astype("category")
    return df


def _top_k_stats(y: np.ndarray, p: np.ndarray, share: float = 0.1) -> dict:
    k = max(1, int(round(len(p) * share)))
    order = np.argsort(-p)[:k]
    hits = y[order].sum()
    base = y.mean()
    return {
        "flagged": int(k),
        "precision": round(float(hits / k), 3),
        "recall": round(float(hits / max(1, y.sum())), 3),
        "lift": round(float((hits / k) / base), 2) if base else None,
    }


def train(
    snapshots: list[dict], months: list[date], seed: int
) -> tuple[TrainedModel, pd.DataFrame]:
    df = frame(snapshots, months)
    last = len(months) - 1
    labelled_until = last - HORIZON
    splits = {
        "train": (3, labelled_until - 12),
        "valid": (labelled_until - 11, labelled_until - 6),
        "test": (labelled_until - 5, labelled_until),
        "score": (last, last),
    }
    active = df[df["active_eom"]]
    part = {k: active[(active["t"] >= a) & (active["t"] <= b)] for k, (a, b) in splits.items()}

    dtrain = lgb.Dataset(
        part["train"][FEATURES], part["train"]["label"], categorical_feature=CATEGORICAL
    )
    dvalid = lgb.Dataset(part["valid"][FEATURES], part["valid"]["label"], reference=dtrain)
    booster = lgb.train(
        {**PARAMS, "seed": seed},
        dtrain,
        num_boost_round=1500,
        valid_sets=[dvalid],
        callbacks=[lgb.early_stopping(80, verbose=False)],
    )
    raw_valid = booster.predict(part["valid"][FEATURES], num_iteration=booster.best_iteration)
    calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(
        raw_valid, part["valid"]["label"]
    )

    test = part["test"]
    raw_test = booster.predict(test[FEATURES], num_iteration=booster.best_iteration)
    cal_test = calibrator.predict(raw_test)
    y = test["label"].to_numpy()

    # The way the model is used: score one month, look six months ahead.
    point_t = splits["test"][0]
    point = test["t"] == point_t
    yp, pp = y[point.to_numpy()], cal_test[point.to_numpy()]

    metrics = {
        "rows": {k: int(len(v)) for k, v in part.items()},
        "best_iteration": int(booster.best_iteration),
        "test_months": [str(months[splits["test"][0]]), str(months[splits["test"][1]])],
        "base_rate": round(float(y.mean()), 4),
        "roc_auc": round(float(roc_auc_score(y, cal_test)), 3),
        "pr_auc": round(float(average_precision_score(y, cal_test)), 3),
        "brier_raw": round(float(brier_score_loss(y, raw_test)), 4),
        "brier_calibrated": round(float(brier_score_loss(y, cal_test)), 4),
        "top_10pct_all_test_months": _top_k_stats(y, cal_test),
        "point_in_time": {
            "month": str(months[point_t]),
            "employees": int(point.sum()),
            "leavers_next_6m": int(yp.sum()),
            "roc_auc": round(float(roc_auc_score(yp, pp)), 3) if 0 < yp.sum() < len(yp) else None,
            "top_10pct": _top_k_stats(yp, pp),
        },
    }

    # Calibration by decile of predicted probability.
    deciles = pd.qcut(cal_test, 10, labels=False, duplicates="drop")
    calibration = [
        {
            "bucket": int(b),
            "predicted": round(float(cal_test[deciles == b].mean()), 4),
            "observed": round(float(y[deciles == b].mean()), 4),
            "n": int((deciles == b).sum()),
        }
        for b in sorted(set(deciles))
    ]

    contrib = booster.predict(
        test[FEATURES], num_iteration=booster.best_iteration, pred_contrib=True
    )
    mean_abs = np.abs(contrib[:, :-1]).mean(axis=0)
    gain = booster.feature_importance("gain")
    importance = sorted(
        [
            {
                "feature": f,
                "mean_abs_shap": round(float(m), 4),
                "gain_share": round(float(g / gain.sum()), 4),
            }
            for f, m, g in zip(FEATURES, mean_abs, gain, strict=True)
        ],
        key=lambda r: -r["mean_abs_shap"],
    )

    metrics["ceiling"] = ceiling(test, y, point.to_numpy())
    fairness = audit(test.assign(prob=cal_test), y)
    model = TrainedModel(
        version=f"lgbm-{months[last]:%Y%m}-s{seed}",
        booster=booster,
        calibrator=calibrator,
        metrics=metrics,
        fairness=fairness,
        importance=importance,
        calibration=calibration,
        splits={k: [str(months[a]), str(months[b])] for k, (a, b) in splits.items()},
    )
    return model, part["score"]


def ceiling(test: pd.DataFrame, y: np.ndarray, point: np.ndarray) -> dict:
    """How well the true planted formula ranks the same rows, without the personal factor
    that no dataset records. The gap between this and the model is what modelling could
    still win; the gap between this and 1.0 is noise no model can remove."""
    h = np.array(
        [
            planted_hazard(
                department=str(r.department),
                pay_ratio=r.pay_ratio,
                months_since_promotion=r.months_since_promotion,
                grade_rank=r.grade_rank,
                manager_changed_6m=bool(r.manager_changed_6m),
                overtime_3m=r.overtime_3m,
                rating=r.rating,
                tenure_months=r.tenure_months,
                month=r.month.month,
            )
            for r in test.itertuples()
        ]
    )
    yp, hp = y[point], h[point]
    return {
        "roc_auc": round(float(roc_auc_score(y, h)), 3),
        "pr_auc": round(float(average_precision_score(y, h)), 3),
        "point_in_time_top_10pct": _top_k_stats(yp, hp),
    }


def audit(test: pd.DataFrame, y: np.ndarray) -> dict:
    """Score distribution and top-10% flags by gender and age band (not model inputs)."""
    k = max(1, int(round(len(test) * 0.1)))
    threshold = np.sort(test["prob"].to_numpy())[-k]
    test = test.assign(y=y, flagged=test["prob"] >= threshold)
    out: dict = {"threshold_top_10pct": round(float(threshold), 4)}
    for attr in ("gender", "age_band"):
        rows = []
        for value, g in test.groupby(attr, observed=True):
            leavers = g[g["y"] == 1]
            rows.append(
                {
                    "group": str(value),
                    "n": int(len(g)),
                    "observed_rate": round(float(g["y"].mean()), 4),
                    "mean_predicted": round(float(g["prob"].mean()), 4),
                    "flag_rate": round(float(g["flagged"].mean()), 4),
                    "recall": round(float(leavers["flagged"].mean()), 3) if len(leavers) else None,
                }
            )
        rates = [r["flag_rate"] for r in rows if r["n"] >= 100]
        out[attr] = {
            "groups": rows,
            "flag_rate_ratio_min_max": round(min(rates) / max(rates), 3)
            if rates and max(rates)
            else None,
        }
    return out


def explain(row: pd.Series, contributions: np.ndarray) -> list[dict]:
    """The three largest risk-raising factors for one person, in plain words."""
    labels = {
        "pay_ratio": lambda r: f"Paid {round(r.pay_ratio * 100)}% of the grade midpoint",
        "months_since_promotion": lambda r: (
            f"{int(r.months_since_promotion)} months since last promotion"
        ),
        "overtime_3m": lambda r: f"{r.overtime_3m:.0f} overtime hours a month (3-month average)",
        "manager_changed_6m": lambda r: "Manager changed in the last six months",
        "tenure_months": lambda r: (
            "In the first year"
            if r.tenure_months < 12
            else f"{int(r.tenure_months)} months' tenure"
        ),
        "rating": lambda r: f"Performance rating {int(r.rating)}",
        "pay_change_12m": lambda r: (
            "No pay history yet"
            if pd.isna(r.pay_change_12m)
            else f"Pay up {r.pay_change_12m * 100:.1f}% in 12 months"
        ),
        "department": lambda r: f"{r.department} has a high base rate",
        "location": lambda r: f"{r.location} office",
        "on_pkwt": lambda r: "On a fixed-term contract (PKWT)",
        "grade_rank": lambda r: f"Grade G{int(r.grade_rank)}",
    }
    pairs = sorted(zip(FEATURES, contributions[:-1], strict=True), key=lambda kv: -kv[1])
    return [
        {"feature": f, "text": labels[f](row), "contribution": round(float(c), 3)}
        for f, c in pairs[:3]
        if c > 0
    ]


def score(model: TrainedModel, current: pd.DataFrame) -> pd.DataFrame:
    raw = model.booster.predict(current[FEATURES], num_iteration=model.booster.best_iteration)
    prob = model.calibrator.predict(raw)
    contrib = model.booster.predict(
        current[FEATURES], num_iteration=model.booster.best_iteration, pred_contrib=True
    )
    out = current[["employee_id", "month"]].copy()
    out["probability"] = np.round(prob, 4)
    ranks = pd.Series(prob).rank(ascending=False, method="first").to_numpy()
    n = len(prob)
    out["risk_band"] = np.where(
        ranks <= n * 0.1, "high", np.where(ranks <= n * 0.3, "elevated", "low")
    )
    out["drivers"] = [explain(row, contrib[i]) for i, (_, row) in enumerate(current.iterrows())]
    return out
