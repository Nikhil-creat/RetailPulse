"""Executive brief: rule-based findings computed from warehouse queries (no LLM, no invented numbers).

Every finding carries the numbers it was computed from (`evidence`), a recommended action and a question the
guarded agent can answer in more depth. Thresholds are explicit constants so the logic is auditable.
"""
from __future__ import annotations

GROWTH_WATCH_PCT = -5.0        # YoY change below this is flagged as a risk
CONCENTRATION_PCT = 50.0       # one category above this share of revenue is a concentration risk
CHURN_TOP_N = 50               # customers considered for the win-back list
DISCOUNT_LIFT_MIN_PCT = 3.0    # a discount "works" only if units per line rise by at least this much


def _pct(new: float, old: float) -> float | None:
    return round((new / old - 1) * 100, 1) if old else None


def _inr_cr(x: float) -> str:
    return f"₹{x / 1e7:,.2f} cr"


def build_brief(svc) -> dict:
    findings: list[dict] = []

    def add(fid, severity, title, detail, evidence, action, question):
        findings.append({"id": fid, "severity": severity, "title": title, "detail": detail,
                         "evidence": evidence, "action": action, "question": question})

    k = svc.kpis()
    monthly = svc.monthly()["rows"]  # [month, net_revenue, orders, profit]
    by_month = {r[0]: r for r in monthly}

    # 1. Year-on-year growth of the latest month and of the trailing quarter
    last = monthly[-1][0]
    prev_year = f"{int(last[:4]) - 1}{last[4:]}"
    if prev_year in by_month:
        yoy = _pct(by_month[last][1], by_month[prev_year][1])
        q_now = sum(r[1] for r in monthly[-3:])
        q_prev_months = [by_month.get(f"{int(r[0][:4]) - 1}{r[0][4:]}") for r in monthly[-3:]]
        q_yoy = _pct(q_now, sum(r[1] for r in q_prev_months)) if all(q_prev_months) else None
        sev = "risk" if (yoy is not None and yoy < GROWTH_WATCH_PCT) else "good"
        add("growth", sev, f"Revenue {'up' if (yoy or 0) >= 0 else 'down'} {abs(yoy or 0):.1f}% year on year in {last}",
            f"Net revenue in {last} was {_inr_cr(by_month[last][1])} against {_inr_cr(by_month[prev_year][1])} in {prev_year}."
            + (f" The trailing quarter is {q_yoy:+.1f}% year on year." if q_yoy is not None else ""),
            {"month": last, "net_revenue": by_month[last][1], "prior_year_revenue": by_month[prev_year][1], "yoy_pct": yoy, "quarter_yoy_pct": q_yoy},
            "Compare the latest month with the promo calendar before drawing conclusions: festive timing moves revenue between months.",
            "What was net revenue per month and how does it compare with last year?")

    # 2. Category concentration versus profit contribution
    rev = svc.top_n("category", "revenue", 10)["rows"]
    prof = dict(svc.top_n("category", "profit", 10)["rows"])
    margin = dict(svc.top_n("category", "margin", 10)["rows"])
    total_rev = sum(r[1] for r in rev) or 1
    total_prof = sum(prof.values()) or 1
    top_cat, top_rev = rev[0]
    share = top_rev / total_rev * 100
    profit_share = prof.get(top_cat, 0) / total_prof * 100
    if share >= CONCENTRATION_PCT:
        add("concentration", "risk", f"{top_cat} is {share:.0f}% of revenue but only {profit_share:.0f}% of profit",
            f"{top_cat} earns a {margin.get(top_cat, 0):.1f}% margin. Revenue is concentrated in a low-margin category, so a price war or "
            "supply shock there hits the top line hard while contributing little profit.",
            {"category": top_cat, "revenue_share_pct": round(share, 1), "profit_share_pct": round(profit_share, 1), "margin_pct": margin.get(top_cat)},
            "Protect the margin on this category (supplier terms, bundling) and grow the higher-margin ones.",
            f"How do revenue, profit and margin compare across categories, and what is the margin of {top_cat}?")

    # 3. Highest-margin category headroom
    best_cat, best_margin = max(margin.items(), key=lambda kv: kv[1])
    best_share = next((r[1] for r in rev if r[0] == best_cat), 0) / total_rev * 100
    add("margin_leader", "opportunity", f"{best_cat} has the best margin ({best_margin:.1f}%) on {best_share:.1f}% of revenue",
        f"Each extra rupee of revenue here earns about {best_margin / max(min(margin.values()), 0.1):.0f}x the profit of a rupee in the lowest-margin category.",
        {"category": best_cat, "margin_pct": best_margin, "revenue_share_pct": round(best_share, 1)},
        "Test targeted promotion and cross-sell into this category before blanket discounts.",
        f"Which products drive {best_cat} revenue?")

    # 4. Do discounts lift volume? (units per line item by discount depth)
    de = svc.named("discount_effectiveness")["rows"]  # [discount_pct, lines, avg_units, margin_pct, net_revenue]
    base = next((r for r in de if r[0] == 0), None)
    deepest = max(de, key=lambda r: r[0]) if de else None
    if base and deepest and deepest[0] > 0:
        lift = _pct(deepest[2], base[2])
        works = lift is not None and lift >= DISCOUNT_LIFT_MIN_PCT
        add("discounts", "good" if works else "watch",
            f"Discounts {'lift' if works else 'do not lift'} basket size in this data",
            f"Units per line item are {base[2]:.2f} at 0% discount and {deepest[2]:.2f} at {deepest[0]}%, while margin falls from "
            f"{base[3]:.1f}% to {deepest[3]:.1f}%.",
            {"units_per_line_0": base[2], "units_per_line_max": deepest[2], "lift_pct": lift, "margin_0": base[3], "margin_max": deepest[3], "max_discount_pct": deepest[0]},
            "Cap discount depth or switch to targeted offers and re-measure with a holdout group." if not works else "Keep discounts targeted; the lift is measurable.",
            "How effective are discounts on units and margin?")

    # 5. Churn exposure
    churn = svc.churn_top(CHURN_TOP_N)["rows"]
    at_risk = [c for c in churn if c["churn_risk"] >= 0.8]
    if at_risk:
        value = sum(c["value_at_risk"] for c in at_risk)
        add("churn", "risk", f"{len(at_risk)} high-value customers are very likely to churn ({_inr_cr(value)} at risk)",
            f"Among the top {len(churn)} customers by value at risk, {len(at_risk)} have a churn score of 0.8 or more.",
            {"customers": len(at_risk), "value_at_risk": round(value, 2), "top_customer_key": at_risk[0]["customer_key"], "threshold": 0.8},
            "Start a personal win-back campaign for these customers this week; review their customer 360 first.",
            "Which customers have the highest churn risk and value at risk?")

    # 6. Forecast outlook with its honest error band
    f = svc.forecast(30)
    hist = f["history"][-30:]
    if hist and f["rows"]:
        recent = sum(h["revenue"] for h in hist) / len(hist)
        outlook = sum(r["forecast"] for r in f["rows"]) / len(f["rows"])
        chg = _pct(outlook, recent)
        add("forecast", "info", f"Next 30 days: about {_inr_cr(sum(r['forecast'] for r in f['rows']))} (daily average {chg:+.1f}% vs the last {len(hist)} days)",
            f"The backtested weekly error of this model is {f['backtest_wape_weekly_pct']:.1f}% (WAPE). Treat it as a planning range, not a promise.",
            {"forecast_total": round(sum(r["forecast"] for r in f["rows"]), 2), "avg_daily_change_pct": chg, "backtest_wape_weekly_pct": f["backtest_wape_weekly_pct"],
             "lower_total": round(sum(r["lower"] for r in f["rows"]), 2), "upper_total": round(sum(r["upper"] for r in f["rows"]), 2)},
            "Plan stock and staffing against the lower bound, and review the forecast weekly rather than daily.",
            "Forecast revenue for the next 30 days.")

    # 7. Recent demand anomalies
    an = svc.anomalies()["rows"]
    recent_an = [a for a in an if a["date"] >= (hist[0]["date"] if hist else "0000")] if an else []
    if an:
        add("anomalies", "watch" if recent_an else "info", f"{len(an)} demand anomalies detected overall, {len(recent_an)} in the last 30 days",
            "Anomalies are days whose order count departs sharply from the expected level (robust z-score).",
            {"total": len(an), "recent": len(recent_an), "latest": an[-1]["date"]},
            "Check promotions, stock-outs and data-quality events on the flagged dates.",
            "Which days had anomalous demand?")

    order = {"risk": 0, "watch": 1, "opportunity": 2, "info": 3, "good": 4}
    findings.sort(key=lambda x: order.get(x["severity"], 9))
    return {"generated_from": {"first_date": k["first_date"], "last_date": k["last_date"], "orders": k["orders"]},
            "method": "Rule-based analysis of warehouse queries. Every figure is computed, none is generated by a language model.",
            "findings": findings}
