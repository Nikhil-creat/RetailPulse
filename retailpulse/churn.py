"""Customer churn model with temporal validation (train on an earlier cutoff, test on a later one)."""
from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import average_precision_score, roc_auc_score

FEATURES = ["recency_days", "frequency", "monetary", "avg_order_value", "tenure_days",
            "return_rate", "avg_categories", "orders_last_90", "orders_prev_90",
            "avg_gap_days", "overdue_ratio"]
HORIZON_DAYS = 90
ACTIVE_WINDOW_DAYS = 180


def load_orders(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """SELECT order_id, customer_key, order_date, SUM(revenue) AS value,
                  MAX(is_returned) AS is_returned, COUNT(DISTINCT category) AS n_cat
           FROM vw_sales GROUP BY order_id, customer_key, order_date""",
        conn, parse_dates=["order_date"])


def build_features(orders: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """Features using ONLY orders on or before `as_of`; keeps customers active in the last 180 days."""
    past = orders[orders["order_date"] <= as_of]
    g = past.groupby("customer_key")
    f = pd.DataFrame({
        "recency_days": (as_of - g["order_date"].max()).dt.days,
        "frequency": g.size(),
        "monetary": g["value"].sum(),
        "avg_order_value": g["value"].mean(),
        "tenure_days": (as_of - g["order_date"].min()).dt.days,
        "return_rate": g["is_returned"].mean(),
        "avg_categories": g["n_cat"].mean(),
    })
    last90 = past[past["order_date"] > as_of - pd.Timedelta(days=90)].groupby("customer_key").size()
    prev90 = past[(past["order_date"] > as_of - pd.Timedelta(days=180))
                  & (past["order_date"] <= as_of - pd.Timedelta(days=90))].groupby("customer_key").size()
    # how overdue is the customer relative to their own buying rhythm?
    f["avg_gap_days"] = (f["tenure_days"] / (f["frequency"] - 1).where(f["frequency"] > 1)).fillna(365.0)
    f["overdue_ratio"] = f["recency_days"] / f["avg_gap_days"].clip(lower=1.0)
    f["orders_last_90"] = last90.reindex(f.index).fillna(0)
    f["orders_prev_90"] = prev90.reindex(f.index).fillna(0)
    return f[f["recency_days"] <= ACTIVE_WINDOW_DAYS]


def make_labels(orders: pd.DataFrame, customers: pd.Index, as_of: pd.Timestamp) -> np.ndarray:
    """1 = churned (no order in the next 90 days after `as_of`)."""
    fut = orders[(orders["order_date"] > as_of)
                 & (orders["order_date"] <= as_of + pd.Timedelta(days=HORIZON_DAYS))]
    return (~customers.isin(set(fut["customer_key"]))).astype(int)


def train_and_evaluate(orders: pd.DataFrame, seed: int = 0) -> dict:
    max_date = orders["order_date"].max().normalize()
    test_asof = max_date - pd.Timedelta(days=HORIZON_DAYS)
    train_asof = test_asof - pd.Timedelta(days=HORIZON_DAYS)

    Xtr = build_features(orders, train_asof)
    ytr = make_labels(orders, Xtr.index, train_asof)
    Xte = build_features(orders, test_asof)
    yte = make_labels(orders, Xte.index, test_asof)
    if len(set(yte)) < 2 or len(set(ytr)) < 2:
        raise ValueError("Churn labels have a single class; need more data.")

    model = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_depth=4, random_state=seed)
    model.fit(Xtr[FEATURES], ytr)
    p = model.predict_proba(Xte[FEATURES])[:, 1]

    k = max(1, int(len(p) * 0.1))
    top = np.argsort(-p)[:k]
    perm = permutation_importance(model, Xte[FEATURES], yte, scoring="roc_auc", n_repeats=5, random_state=seed)
    importance = pd.Series(perm.importances_mean, index=FEATURES).sort_values(ascending=False)

    now = build_features(orders, max_date)
    risk = model.predict_proba(now[FEATURES])[:, 1]
    annual_value = now["monetary"] / np.maximum(now["tenure_days"], 90) * 365
    scores = pd.DataFrame({
        "customer_key": now.index.to_numpy(),
        "churn_risk": risk.round(4),
        "recency_days": now["recency_days"].to_numpy(),
        "frequency": now["frequency"].to_numpy(),
        "value_at_risk": (risk * annual_value.to_numpy()).round(2),
    }).sort_values("value_at_risk", ascending=False).reset_index(drop=True)

    metrics = {
        "train_cutoff": str(train_asof.date()), "test_cutoff": str(test_asof.date()),
        "horizon_days": HORIZON_DAYS, "train_customers": int(len(Xtr)), "test_customers": int(len(Xte)),
        "test_churn_rate_pct": round(100 * float(yte.mean()), 1),
        "roc_auc": round(float(roc_auc_score(yte, p)), 3),
        "avg_precision": round(float(average_precision_score(yte, p)), 3),
        "baseline_recency_auc": round(float(roc_auc_score(yte, Xte["recency_days"])), 3),
        "top_decile_lift": round(float(yte[top].mean() / yte.mean()), 2),
        "top_features": [str(i) for i in importance.index[:3]],
    }
    return {"metrics": metrics, "importance": importance, "scores": scores, "model": model,
            "features": {"train": Xtr, "now": now}}
