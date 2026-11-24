"""SQLite star-schema warehouse: build, validate (data quality), and run named SQL."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pandas as pd

from .config import SQL_DIR, Paths

SCHEMA = """
CREATE TABLE dim_customer (
    customer_key INTEGER PRIMARY KEY, city TEXT NOT NULL, age INTEGER, age_band TEXT,
    signup_date TEXT, email TEXT, phone TEXT
);
CREATE TABLE dim_product (
    product_key INTEGER PRIMARY KEY, product_name TEXT NOT NULL, category TEXT NOT NULL,
    unit_price REAL NOT NULL CHECK (unit_price > 0), unit_cost REAL NOT NULL CHECK (unit_cost >= 0)
);
CREATE TABLE dim_date (
    date_key INTEGER PRIMARY KEY, full_date TEXT NOT NULL, year INTEGER, quarter INTEGER, month INTEGER,
    month_name TEXT, week_of_year INTEGER, day_of_week INTEGER, day_name TEXT,
    is_weekend INTEGER, is_festive_season INTEGER
);
CREATE TABLE fact_orders (
    order_id INTEGER PRIMARY KEY,
    customer_key INTEGER NOT NULL REFERENCES dim_customer(customer_key),
    date_key INTEGER NOT NULL REFERENCES dim_date(date_key),
    channel TEXT, payment_method TEXT, is_returned INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE fact_order_items (
    item_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES fact_orders(order_id),
    product_key INTEGER NOT NULL REFERENCES dim_product(product_key),
    quantity INTEGER NOT NULL CHECK (quantity > 0), discount_pct INTEGER NOT NULL DEFAULT 0,
    revenue REAL NOT NULL, cost REAL NOT NULL
);
CREATE TABLE returns (
    order_id INTEGER PRIMARY KEY REFERENCES fact_orders(order_id), return_date TEXT, reason TEXT
);
CREATE INDEX ix_orders_customer ON fact_orders(customer_key);
CREATE INDEX ix_orders_date ON fact_orders(date_key);
CREATE INDEX ix_items_order ON fact_order_items(order_id);
CREATE INDEX ix_items_product ON fact_order_items(product_key);

CREATE VIEW vw_sales AS
SELECT i.item_id, o.order_id, o.customer_key, c.city, c.age_band,
       d.full_date AS order_date, d.year, d.month, d.month_name, d.quarter,
       d.is_weekend, d.is_festive_season, o.channel, o.payment_method,
       p.product_key, p.category, p.product_name,
       i.quantity, i.discount_pct, i.revenue, i.cost, i.revenue - i.cost AS profit, o.is_returned
FROM fact_order_items i
JOIN fact_orders o ON o.order_id = i.order_id
JOIN dim_customer c ON c.customer_key = o.customer_key
JOIN dim_product p ON p.product_key = i.product_key
JOIN dim_date d ON d.date_key = o.date_key;
"""


def connect(db_path, readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        conn = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _dim_date(dates: pd.Series) -> pd.DataFrame:
    idx = pd.date_range(dates.min(), dates.max(), freq="D")
    return pd.DataFrame({
        "date_key": idx.strftime("%Y%m%d").astype(int),
        "full_date": idx.strftime("%Y-%m-%d"),
        "year": idx.year, "quarter": idx.quarter, "month": idx.month,
        "month_name": idx.strftime("%b"),
        "week_of_year": idx.isocalendar().week.to_numpy().astype(int),
        "day_of_week": idx.dayofweek, "day_name": idx.strftime("%a"),
        "is_weekend": (idx.dayofweek >= 5).astype(int),
        "is_festive_season": idx.month.isin([10, 11]).astype(int),
    })


def build_warehouse(paths: Paths) -> dict:
    raw = paths.raw_dir
    customers = pd.read_csv(raw / "customers.csv")
    products = pd.read_csv(raw / "products.csv")
    orders = pd.read_csv(raw / "orders.csv", parse_dates=["order_date"])
    items = pd.read_csv(raw / "order_items.csv")
    returns = pd.read_csv(raw / "returns.csv")

    if paths.db_path.exists():
        paths.db_path.unlink()
    paths.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(paths.db_path)
    conn.executescript(SCHEMA)

    dim_customer = customers.rename(columns={"customer_id": "customer_key"})
    dim_customer["age_band"] = pd.cut(
        dim_customer["age"], bins=[17, 24, 34, 44, 54, 64],
        labels=["18-24", "25-34", "35-44", "45-54", "55-64"]).astype(str)
    dim_customer = dim_customer[["customer_key", "city", "age", "age_band", "signup_date", "email", "phone"]]

    dim_product = products.rename(columns={"product_id": "product_key"})[
        ["product_key", "product_name", "category", "unit_price", "unit_cost"]]

    dim_date = _dim_date(orders["order_date"])

    fact_orders = pd.DataFrame({
        "order_id": orders.order_id,
        "customer_key": orders.customer_id,
        "date_key": orders.order_date.dt.strftime("%Y%m%d").astype(int),
        "channel": orders.channel,
        "payment_method": orders.payment_method,
        "is_returned": orders.order_id.isin(returns.order_id).astype(int),
    })

    m = items.merge(products[["product_id", "unit_price", "unit_cost"]], on="product_id")
    fact_items = pd.DataFrame({
        "item_id": m.item_id, "order_id": m.order_id, "product_key": m.product_id,
        "quantity": m.quantity, "discount_pct": m.discount_pct,
        "revenue": (m.quantity * m.unit_price * (1 - m.discount_pct / 100)).round(2),
        "cost": (m.quantity * m.unit_cost).round(2),
    }).sort_values("item_id")

    for name, df in [("dim_customer", dim_customer), ("dim_product", dim_product), ("dim_date", dim_date),
                     ("fact_orders", fact_orders), ("fact_order_items", fact_items), ("returns", returns)]:
        df.to_sql(name, conn, if_exists="append", index=False, chunksize=20000)
    conn.commit()

    dq = validate_warehouse(conn)
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("dim_customer", "dim_product", "dim_date", "fact_orders", "fact_order_items", "returns")}
    conn.close()
    return {"counts": counts, "data_quality": dq}


def validate_warehouse(conn: sqlite3.Connection) -> dict:
    """Data-quality gates. Every check must be zero for the warehouse to be 'ok'."""
    q = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    checks = {
        "orphan_foreign_keys": len(conn.execute("PRAGMA foreign_key_check").fetchall()),
        "negative_money_rows": q("SELECT COUNT(*) FROM fact_order_items WHERE revenue < 0 OR cost < 0"),
        "orders_without_items": q("SELECT COUNT(*) FROM fact_orders o LEFT JOIN fact_order_items i "
                                  "ON i.order_id = o.order_id WHERE i.item_id IS NULL"),
        "orders_before_signup": q("SELECT COUNT(*) FROM fact_orders o JOIN dim_customer c USING (customer_key) "
                                  "JOIN dim_date d USING (date_key) WHERE d.full_date < c.signup_date"),
        "returns_without_order": q("SELECT COUNT(*) FROM returns r LEFT JOIN fact_orders o "
                                   "ON o.order_id = r.order_id WHERE o.order_id IS NULL"),
    }
    return {"ok": all(v == 0 for v in checks.values()), "checks": checks}


def load_queries(path: Path | None = None) -> dict[str, str]:
    text = Path(path or SQL_DIR / "analysis_queries.sql").read_text(encoding="utf-8")
    parts = re.split(r"^-- name:\s*(\w+)\s*$", text, flags=re.M)
    return {parts[i]: parts[i + 1].strip().rstrip(";") for i in range(1, len(parts), 2)}


def run_query(conn: sqlite3.Connection, name: str) -> pd.DataFrame:
    queries = load_queries()
    if name not in queries:
        raise KeyError(f"Unknown query '{name}'. Available: {sorted(queries)}")
    return pd.read_sql_query(queries[name], conn)
