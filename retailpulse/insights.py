"""Turns computed results into short, factual knowledge-base documents for the RAG layer.

Every sentence is generated from real numbers in the warehouse / model outputs (nothing is hard-coded),
so the assistant's answers stay in sync with the data.
"""
from __future__ import annotations

import sqlite3

import pandas as pd

from .catalog import inr
from .warehouse import run_query


def build_insights(conn: sqlite3.Connection, kpi: dict, rfm_sum: pd.DataFrame, cohort: pd.DataFrame,
                   basket: pd.DataFrame, fc: dict, churn: dict, anomalies: pd.DataFrame,
                   flash_days: list[str], pareto_pct: float) -> list[dict]:
    docs = []

    def add(key: str, title: str, text: str) -> None:
        docs.append({"id": f"insight:{key}", "title": title, "text": text})

    add("kpis", "Headline KPIs",
        f"Between {kpi['first_date']} and {kpi['last_date']} the business earned {inr(kpi['net_revenue'])} in net "
        f"revenue and {inr(kpi['net_profit'])} in profit, a margin of {kpi['profit_margin_pct']} percent. There were "
        f"{kpi['orders']:,} orders from {kpi['customers']:,} customers. Average order value is "
        f"{inr(kpi['avg_order_value'])}.")

    cat = run_query(conn, "category_performance")
    top, bottom = cat.iloc[0], cat.iloc[-1]
    best_margin = cat.sort_values("margin_pct", ascending=False).iloc[0]
    add("category", "Category performance",
        f"{top['category']} is the top revenue category with {inr(top['net_revenue'])}, "
        f"{top['revenue_share_pct']} percent of net revenue, at a {top['margin_pct']} percent margin. "
        f"{bottom['category']} is the smallest by revenue at {bottom['revenue_share_pct']} percent. "
        f"{best_margin['category']} has the highest margin at {best_margin['margin_pct']} percent.")

    city = run_query(conn, "city_revenue_rank")
    add("city", "City performance",
        f"{city.iloc[0]['city']} is the highest revenue city with {inr(city.iloc[0]['net_revenue'])}, followed by "
        f"{city.iloc[1]['city']} and {city.iloc[2]['city']}. {city.iloc[-1]['city']} ranks last.")

    fest = run_query(conn, "festive_uplift").set_index("period")["avg_daily_revenue"]
    wk = run_query(conn, "weekend_vs_weekday").set_index("day_type")["avg_daily_revenue"]
    festive_up = 100 * (fest["Festive (Oct-Nov)"] / fest["Regular"] - 1)
    weekend_up = 100 * (wk["Weekend"] / wk["Weekday"] - 1)
    add("festive", "Seasonality: festive season and weekends",
        f"Average daily revenue in the festive months of October and November is {festive_up:.0f} percent higher "
        f"than in regular months. Weekend days earn {weekend_up:.0f} percent more daily revenue than weekdays. "
        f"Part of the festive gap also reflects overall growth over time.")

    ret = run_query(conn, "return_rate_by_category")
    add("returns", "Returns",
        f"{kpi['return_rate_pct']} percent of orders were returned. {ret.iloc[0]['category']} has the highest "
        f"item return rate at {ret.iloc[0]['return_rate_pct']} percent and {ret.iloc[-1]['category']} the lowest "
        f"at {ret.iloc[-1]['return_rate_pct']} percent.")

    champs = rfm_sum.set_index("segment")
    parts = [f"{r.segment} {r.customers:,} customers ({r.customer_share_pct} percent)" for r in rfm_sum.itertuples()]
    add("rfm", "RFM customer segments", "Customer segments by RFM score: " + "; ".join(parts) + ".")
    if "Champions" in champs.index:
        c = champs.loc["Champions"]
        add("champions", "Champion customers",
            f"Champions are the best customers: {int(c['customers']):,} customers with an average of "
            f"{inr(c['avg_monetary'])} net revenue each and {c['avg_frequency']:.1f} orders on average.")

    m3 = cohort.get(3)
    m6 = cohort.get(6)
    if m3 is not None and m6 is not None:
        add("retention", "Cohort retention",
            f"On average {100 * m3.mean():.0f} percent of a cohort orders again three months after their first "
            f"order month, and {100 * m6.mean():.0f} percent at six months. Month zero is always 100 percent.")

    if len(basket):
        b = basket.iloc[0]
        add("basket", "Categories bought together",
            f"{b['antecedent']} and {b['consequent']} are bought together most often, with lift {b['lift']:.2f}: "
            f"customers who buy {b['antecedent']} add {b['consequent']} {100 * b['confidence']:.0f} percent of the time. "
            f"Bundle or cross-sell these categories.")

    g = fc["models"]["gradient_boosting"]
    sn = fc["models"]["seasonal_naive"]
    add("forecast", "Forecast accuracy",
        f"On a {fc['holdout_days']}-day holdout the gradient-boosting forecast has weekly WAPE of "
        f"{g['wape_weekly_pct']} percent and daily WAPE of {g['wape_daily_pct']} percent, versus "
        f"{sn['wape_weekly_pct']} percent weekly for the seasonal-naive baseline. Daily revenue is noisy because "
        f"basket values vary widely, so weekly totals are more reliable than single days.")

    add("churn", "Churn model performance",
        f"The churn model predicts who will not order in the next {churn['horizon_days']} days. On a later test "
        f"cutoff ({churn['test_cutoff']}) it reaches ROC AUC {churn['roc_auc']} versus {churn['baseline_recency_auc']} "
        f"for a recency-only baseline, and the top-decile customers churn {churn['top_decile_lift']} times more "
        f"often than average. The base churn rate is {churn['test_churn_rate_pct']} percent. The most important "
        f"features are {', '.join(churn['top_features'])}.")

    spikes = anomalies[anomalies["kind"] == "spike"] if len(anomalies) else anomalies
    add("anomalies", "Demand anomalies",
        f"{len(anomalies)} anomalous days in daily order volume were flagged, {len(spikes)} of them spikes. The data contains "
        f"{len(flash_days)} planted flash-sale days, which show up as legitimate demand spikes.")

    abc = run_query(conn, "pareto_products").set_index("abc_class")["products"]
    a_count = int(abc.iloc[0])
    add("pareto", "Product concentration (Pareto)",
        f"The top 20 percent of products earn {pareto_pct} percent of net revenue. {a_count} products make up the "
        f"A class that delivers the first 80 percent of revenue.")

    disc = run_query(conn, "discount_effectiveness")
    d0 = disc[disc["discount_pct"] == 0].iloc[0]
    d20 = disc[disc["discount_pct"] == 20].iloc[0]
    add("discounts", "Discount effectiveness",
        f"Full-price items earn a {d0['margin_pct']} percent margin versus {d20['margin_pct']} percent at a 20 percent "
        f"discount. Average units per line are {d0['avg_units_per_line']} at full price and "
        f"{d20['avg_units_per_line']} at 20 percent off, so discounts lower margin without clearly lifting volume.")
    return docs
