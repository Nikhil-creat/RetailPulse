"""Synthetic retail data generator with realistic structure.

Patterns built in (so the analytics have something real to find):
  * growth trend, weekend lift, Oct-Nov festive season, 6 flash-sale spikes
  * heavy-tailed customer activity and ~35% of customers who stop buying
  * category affinity inside baskets (e.g. Fashion <-> Beauty)
  * ~5% of orders returned
Customer e-mail / phone values are synthetic and exist only to exercise the
PII guardrails.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import config

CITIES = ["Hyderabad", "Warangal", "Bengaluru", "Chennai", "Mumbai", "Delhi", "Pune", "Vizag"]
CITY_P = [0.20, 0.08, 0.18, 0.12, 0.14, 0.12, 0.09, 0.07]

# category -> (min price, max price, gross margin)
CATEGORIES = {
    "Electronics": (3000, 60000, 0.12),
    "Fashion": (400, 5000, 0.45),
    "Grocery": (50, 800, 0.18),
    "Home": (300, 15000, 0.32),
    "Beauty": (150, 3000, 0.55),
    "Sports": (400, 12000, 0.35),
}
AFFINITY = {
    "Electronics": "Home", "Home": "Grocery", "Grocery": "Home",
    "Fashion": "Beauty", "Beauty": "Fashion", "Sports": "Fashion",
}
RETURN_REASONS = ["Damaged item", "Wrong size", "Not as described", "Changed mind"]


def generate(n_customers: int = 5000, n_products: int = 200, n_orders: int = 50_000,
             seed: int | None = None, start: str = "2024-06-01", end: str = "2026-10-31") -> dict:
    rng = np.random.default_rng(config.SEED if seed is None else seed)
    days = pd.date_range(start, end, freq="D")
    n_days = len(days)

    # ---- day weights: trend x weekend x festive x flash sales
    t = np.arange(n_days) / n_days
    w = (1.0 + 0.6 * t) * np.where(days.dayofweek >= 5, 1.3, 1.0) * np.where(days.month.isin([10, 11]), 1.8, 1.0)
    flash_idx = np.sort(rng.choice(n_days, size=6, replace=False))
    w[flash_idx] *= 4.0

    # ---- customers: signup, activity window, churn
    signup_idx = rng.integers(-150, int(n_days * 0.85), n_customers)
    lo = np.maximum(signup_idx, 0)
    churner = rng.random(n_customers) < 0.35
    churn_idx = np.where(churner, lo + rng.integers(60, n_days, n_customers), n_days - 1)
    hi = np.minimum(churn_idx, n_days - 1)
    activity = rng.lognormal(0.0, 0.8, n_customers)
    lam = activity * (hi - lo + 1)
    lam = lam * (n_orders / lam.sum())
    counts = rng.poisson(lam)

    cust_parts, date_parts = [], []
    for i in np.nonzero(counts)[0]:
        sl = w[lo[i]: hi[i] + 1]
        idx = rng.choice(np.arange(lo[i], hi[i] + 1), size=counts[i], p=sl / sl.sum())
        date_parts.append(idx)
        cust_parts.append(np.full(counts[i], i + 1))
    date_idx = np.concatenate(date_parts)
    cust_ids = np.concatenate(cust_parts)
    order = np.argsort(date_idx, kind="stable")
    date_idx, cust_ids = date_idx[order], cust_ids[order]
    n = len(date_idx)

    ids = np.arange(1, n_customers + 1)
    customers = pd.DataFrame({
        "customer_id": ids,
        "city": rng.choice(CITIES, n_customers, p=CITY_P),
        "age": rng.integers(18, 65, n_customers),
        "signup_date": (pd.Timestamp(start) + pd.to_timedelta(signup_idx, unit="D")).strftime("%Y-%m-%d"),
        "email": [f"customer{i:05d}@example.com" for i in ids],
        "phone": [f"9{v:09d}" for v in rng.integers(0, 10**9, n_customers)],
    })

    # ---- products
    cat_list = list(CATEGORIES)
    cats = rng.permutation(np.resize(cat_list, n_products))
    prices = np.array([np.exp(rng.uniform(np.log(CATEGORIES[c][0]), np.log(CATEGORIES[c][1]))) for c in cats]).round(2)
    margins = np.array([CATEGORIES[c][2] for c in cats])
    products = pd.DataFrame({
        "product_id": np.arange(1, n_products + 1),
        "product_name": [f"{c} Item {i:03d}" for i, c in enumerate(cats, start=1)],
        "category": cats,
        "unit_price": prices,
        "unit_cost": (prices * (1 - margins)).round(2),
    })

    orders = pd.DataFrame({
        "order_id": np.arange(1, n + 1),
        "customer_id": cust_ids,
        "order_date": days[date_idx].strftime("%Y-%m-%d"),
        "channel": rng.choice(["web", "app", "store"], n, p=[0.35, 0.45, 0.20]),
        "payment_method": rng.choice(["UPI", "Card", "COD", "Wallet"], n, p=[0.45, 0.25, 0.20, 0.10]),
    })

    # ---- order items with category affinity
    prod_by_cat = {c: products.loc[products.category == c, "product_id"].to_numpy() for c in cat_list}
    cat_of = dict(zip(products.product_id, products.category))
    n_items = rng.choice([1, 2, 3, 4], size=n, p=[0.45, 0.30, 0.17, 0.08])
    first = rng.integers(1, n_products + 1, n)
    o_ids, p_ids = [], []
    for oid in range(1, n + 1):
        p0 = int(first[oid - 1])
        o_ids.append(oid)
        p_ids.append(p0)
        partner = prod_by_cat[AFFINITY[cat_of[p0]]]
        for _ in range(int(n_items[oid - 1]) - 1):
            pid = int(partner[rng.integers(len(partner))]) if rng.random() < 0.4 else int(rng.integers(1, n_products + 1))
            o_ids.append(oid)
            p_ids.append(pid)
    items = pd.DataFrame({
        "item_id": np.arange(1, len(o_ids) + 1),
        "order_id": o_ids,
        "product_id": p_ids,
        "quantity": rng.choice([1, 2, 3], len(o_ids), p=[0.70, 0.22, 0.08]),
        "discount_pct": rng.choice([0, 5, 10, 15, 20], len(o_ids), p=[0.55, 0.15, 0.15, 0.10, 0.05]),
    })

    # ---- returns (~5% of orders)
    returned = rng.random(n) < 0.05
    ret_orders = orders[returned]
    returns = pd.DataFrame({
        "order_id": ret_orders.order_id.to_numpy(),
        "return_date": (pd.to_datetime(ret_orders.order_date) + pd.to_timedelta(rng.integers(3, 15, len(ret_orders)), unit="D")).dt.strftime("%Y-%m-%d"),
        "reason": rng.choice(RETURN_REASONS, len(ret_orders)),
    })

    return {
        "customers": customers, "products": products, "orders": orders,
        "order_items": items, "returns": returns,
        "meta": {"flash_sale_days": [d.strftime("%Y-%m-%d") for d in days[flash_idx]]},
    }


def write_csvs(data: dict, raw_dir: Path) -> None:
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    for name in ("customers", "products", "orders", "order_items", "returns"):
        data[name].to_csv(raw_dir / f"{name}.csv", index=False)
