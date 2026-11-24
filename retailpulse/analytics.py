"""Business analytics on the warehouse: KPIs, RFM, cohort retention, market basket, Pareto."""
from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd


def kpis(conn: sqlite3.Connection) -> dict:
    r = conn.execute(
        """SELECT SUM(CASE WHEN is_returned = 0 THEN revenue ELSE 0 END),
                  SUM(revenue),
                  SUM(CASE WHEN is_returned = 0 THEN profit ELSE 0 END),
                  COUNT(DISTINCT order_id), COUNT(DISTINCT customer_key),
                  MIN(order_date), MAX(order_date)
           FROM vw_sales"""
    ).fetchone()
    net, gross, profit, orders, customers, first, last = r
    returned = conn.execute("SELECT COUNT(*) FROM fact_orders WHERE is_returned = 1").fetchone()[0]
    net_orders = orders - returned
    return {
        "net_revenue": round(float(net), 2),
        "gross_revenue": round(float(gross), 2),
        "net_profit": round(float(profit), 2),
        "profit_margin_pct": round(100 * float(profit) / float(net), 2),
        "orders": int(orders),
        "customers": int(customers),
        "avg_order_value": round(float(net) / net_orders, 2),
        "return_rate_pct": round(100 * returned / orders, 2),
        "first_date": first,
        "last_date": last,
    }


def _quintile(value: pd.Series, tiebreak: pd.Series, higher_is_better: bool) -> pd.Series:
    """1-5 score. Ties are broken by a secondary metric (deterministic, not arbitrary)."""
    key = value.rank(pct=True) + 1e-6 * tiebreak.rank(pct=True)
    ranks = key.rank(method="first")
    labels = [1, 2, 3, 4, 5] if higher_is_better else [5, 4, 3, 2, 1]
    return pd.qcut(ranks, 5, labels=labels).astype(int)


def _segment(r: int, f: int) -> str:
    if r >= 4 and f >= 4:
        return "Champions"
    if f >= 4 and r >= 2:
        return "Loyal"
    if r >= 4 and f <= 2:
        return "New / Promising"
    if r >= 3 and f >= 2:
        return "Potential Loyalist"
    if r <= 2 and f >= 3:
        return "At Risk"
    if r <= 2 and f <= 2:
        return "Hibernating"
    return "Needs Attention"


def rfm(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query(
        """SELECT customer_key, MAX(order_date) AS last_order,
                  COUNT(DISTINCT order_id) AS frequency, SUM(revenue) AS monetary
           FROM vw_sales WHERE is_returned = 0 GROUP BY customer_key""",
        conn, parse_dates=["last_order"])
    snapshot = df["last_order"].max() + pd.Timedelta(days=1)
    df["recency_days"] = (snapshot - df["last_order"]).dt.days
    df["R"] = _quintile(df["recency_days"], df["frequency"], higher_is_better=False)
    df["F"] = _quintile(df["frequency"], df["monetary"], higher_is_better=True)
    df["M"] = _quintile(df["monetary"], df["frequency"], higher_is_better=True)
    df["segment"] = [_segment(r, f) for r, f in zip(df["R"], df["F"])]
    df["monetary"] = df["monetary"].round(2)
    return df.drop(columns="last_order")


def rfm_summary(rfm_df: pd.DataFrame) -> pd.DataFrame:
    g = rfm_df.groupby("segment").agg(
        customers=("customer_key", "count"),
        avg_monetary=("monetary", "mean"),
        avg_frequency=("frequency", "mean"),
        avg_recency_days=("recency_days", "mean"),
    ).round(2)
    g["customer_share_pct"] = (100 * g["customers"] / g["customers"].sum()).round(1)
    return g.sort_values("customers", ascending=False).reset_index()


def cohort_retention(conn: sqlite3.Connection, max_months: int = 12) -> pd.DataFrame:
    """Share of each first-order-month cohort that orders again N months later."""
    o = pd.read_sql_query(
        "SELECT DISTINCT customer_key, substr(order_date, 1, 7) AS ym FROM vw_sales", conn)
    o["period"] = pd.PeriodIndex(o["ym"], freq="M")
    first = o.groupby("customer_key")["period"].min().rename("cohort")
    o = o.join(first, on="customer_key")
    o["offset"] = ((o["period"].dt.year - o["cohort"].dt.year) * 12
                   + (o["period"].dt.month - o["cohort"].dt.month)).astype(int)
    counts = o.groupby(["cohort", "offset"])["customer_key"].nunique().unstack(fill_value=0)
    retention = counts.div(counts[0], axis=0)
    last = o["period"].max()
    for cohort in retention.index:
        observable = (last - cohort).n
        retention.loc[cohort, retention.columns > observable] = np.nan
    return retention.loc[:, retention.columns <= max_months]


def market_basket(conn: sqlite3.Connection) -> pd.DataFrame:
    """Category-pair support / confidence / lift across orders."""
    df = pd.read_sql_query("SELECT DISTINCT order_id, category FROM vw_sales", conn)
    basket = pd.crosstab(df["order_id"], df["category"]).clip(upper=1)
    b = basket.to_numpy().astype(int)
    n = len(b)
    co = b.T @ b
    diag = np.diag(co)
    cats = list(basket.columns)
    rows = []
    for i, a in enumerate(cats):
        for j, c in enumerate(cats):
            if i == j or co[i, j] == 0:
                continue
            conf = co[i, j] / diag[i]
            rows.append({
                "antecedent": a, "consequent": c,
                "support": round(co[i, j] / n, 4),
                "confidence": round(conf, 4),
                "lift": round(conf / (diag[j] / n), 3),
            })
    return pd.DataFrame(rows).sort_values("lift", ascending=False).reset_index(drop=True)


def pareto_share(conn: sqlite3.Connection, top_fraction: float = 0.2) -> float:
    """Share of net revenue earned by the top `top_fraction` of products (%)."""
    rev = pd.read_sql_query(
        "SELECT SUM(revenue) AS rev FROM vw_sales WHERE is_returned = 0 GROUP BY product_key", conn
    )["rev"].sort_values(ascending=False)
    k = max(1, int(np.ceil(top_fraction * len(rev))))
    return round(100 * float(rev.iloc[:k].sum() / rev.sum()), 1)
