"""Allow-listed building blocks for 'ask a question' tools (no user text is ever interpolated into SQL)."""
from __future__ import annotations

DIMENSIONS = {
    "category": "category",
    "city": "city",
    "channel": "channel",
    "payment": "payment_method",
    "product": "product_name",
    "age_band": "age_band",
    "month": "printf('%04d-%02d', year, month)",
}
METRICS = {
    "revenue": "ROUND(SUM(revenue), 2)",
    "profit": "ROUND(SUM(profit), 2)",
    "orders": "COUNT(DISTINCT order_id)",
    "units": "SUM(quantity)",
    "margin": "ROUND(100.0 * SUM(profit) / SUM(revenue), 1)",
}
MONEY_METRICS = {"revenue", "profit"}


def top_n_sql(dimension: str, metric: str, n: int = 5, ascending: bool = False) -> str:
    if dimension not in DIMENSIONS:
        raise ValueError(f"Unknown dimension '{dimension}'. Options: {sorted(DIMENSIONS)}")
    if metric not in METRICS:
        raise ValueError(f"Unknown metric '{metric}'. Options: {sorted(METRICS)}")
    n = max(1, min(int(n), 20))
    order = "ASC" if ascending else "DESC"
    return (f"SELECT {DIMENSIONS[dimension]} AS {dimension}, {METRICS[metric]} AS {metric} "
            f"FROM vw_sales WHERE is_returned = 0 GROUP BY 1 ORDER BY 2 {order} LIMIT {n}")


def inr(x: float) -> str:
    x = float(x)
    if abs(x) >= 1e7:
        return f"₹{x / 1e7:.2f} crore"
    if abs(x) >= 1e5:
        return f"₹{x / 1e5:.2f} lakh"
    return f"₹{x:,.0f}"
