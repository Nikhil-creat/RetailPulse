"""Model/data monitoring: Population Stability Index (PSI) drift checks.

PSI compares a reference distribution with a current one using the reference's quantile bins.
Rule of thumb used in industry: < 0.10 stable, 0.10-0.25 moderate shift, > 0.25 significant shift.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

STABLE, MODERATE = 0.10, 0.25


def psi(reference, current, bins: int = 10) -> float:
    e = np.asarray(reference, dtype=float)
    a = np.asarray(current, dtype=float)
    e, a = e[~np.isnan(e)], a[~np.isnan(a)]
    if len(e) < 2 or len(a) < 2:
        return 0.0
    edges = np.unique(np.quantile(e, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:  # (near-)constant reference: compare share equal to that constant
        return float(abs(np.mean(a == e[0]) - 1.0))
    edges[0], edges[-1] = -np.inf, np.inf
    pe = np.histogram(e, edges)[0] / len(e)
    pa = np.histogram(a, edges)[0] / len(a)
    pe, pa = np.clip(pe, 1e-4, None), np.clip(pa, 1e-4, None)
    return float(np.sum((pa - pe) * np.log(pa / pe)))


def status_of(value: float) -> str:
    return "stable" if value < STABLE else "moderate" if value < MODERATE else "significant"


def drift_table(reference: pd.DataFrame, current: pd.DataFrame, columns: list[str]) -> list[dict]:
    rows = []
    for c in columns:
        v = psi(reference[c], current[c])
        rows.append({"feature": c, "psi": round(v, 4), "status": status_of(v)})
    return sorted(rows, key=lambda r: -r["psi"])


def build_report(orders: pd.DataFrame, feat_train: pd.DataFrame, feat_now: pd.DataFrame,
                 feature_cols: list[str]) -> dict:
    """Two views: (1) churn-feature drift between the training population and today's customers,
    (2) order-value drift between the first 12 months and the latest 90 days."""
    last = orders["order_date"].max()
    ref = orders[orders["order_date"] < orders["order_date"].min() + pd.Timedelta(days=365)]["value"]
    cur = orders[orders["order_date"] > last - pd.Timedelta(days=90)]["value"]
    value_psi = psi(ref, cur)
    feats = drift_table(feat_train, feat_now, feature_cols)
    worst = max([r["psi"] for r in feats] + [value_psi])
    return {
        "thresholds": {"stable_below": STABLE, "significant_from": MODERATE},
        "order_value": {"psi": round(value_psi, 4), "status": status_of(value_psi),
                        "reference": "first 12 months", "current": "last 90 days"},
        "churn_features": feats,
        "overall_status": status_of(worst),
        "note": "Informational. Some drift is expected here by construction (growth trend, rolling windows); "
                "in production, significant drift should trigger investigation or retraining.",
    }
