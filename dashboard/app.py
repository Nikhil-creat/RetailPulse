"""Streamlit dashboard:  streamlit run dashboard/app.py

NOTE: written against the Streamlit API but NOT executed in the build environment (Streamlit was
not installable there). Run it once locally; the data layer it calls is covered by the test-suite.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from retailpulse import analytics  # noqa: E402
from retailpulse.catalog import DIMENSIONS, METRICS, inr  # noqa: E402
from retailpulse.config import Paths  # noqa: E402
from retailpulse.service import RetailPulseService  # noqa: E402

st.set_page_config(page_title="RetailPulse", page_icon="📈", layout="wide")


@st.cache_resource
def get_service():
    return RetailPulseService(Paths.default())


try:
    svc = get_service()
except FileNotFoundError:
    st.error("Warehouse not built yet. Run:  python -m retailpulse.cli run-all")
    st.stop()

summary = svc.summary()
st.title("RetailPulse")
st.caption("Retail analytics, forecasting and guarded AI over a SQL star schema (synthetic data).")

tab_overview, tab_customers, tab_forecast, tab_ask, tab_vision = st.tabs(
    ["Overview", "Customers", "Forecast", "Ask the data", "Image classifier"])

with tab_overview:
    k = svc.kpis()
    c = st.columns(5)
    c[0].metric("Net revenue", inr(k["net_revenue"]))
    c[1].metric("Net profit", inr(k["net_profit"]), f"{k['profit_margin_pct']}% margin")
    c[2].metric("Orders", f"{k['orders']:,}")
    c[3].metric("Customers", f"{k['customers']:,}")
    c[4].metric("Return rate", f"{k['return_rate_pct']}%")

    monthly = pd.DataFrame(svc.safe_query(
        "SELECT printf('%04d-%02d', year, month) AS month, ROUND(SUM(revenue),2) AS revenue "
        "FROM vw_sales WHERE is_returned = 0 GROUP BY year, month ORDER BY year, month")["rows"],
        columns=["month", "revenue"]).set_index("month")
    st.subheader("Net revenue per month")
    st.line_chart(monthly)

    left, right = st.columns(2)
    dim = left.selectbox("Break down by", list(DIMENSIONS), index=0)
    metric = right.selectbox("Metric", list(METRICS), index=0)
    res = svc.top_n(dim, metric, 10)
    st.bar_chart(pd.DataFrame(res["rows"], columns=res["columns"]).set_index(dim))

with tab_customers:
    seg = pd.DataFrame(svc.segments()["rows"])
    st.subheader("RFM segments")
    st.bar_chart(seg.set_index("segment")["customers"])
    st.dataframe(seg, use_container_width=True)
    st.subheader("Highest value-at-risk customers (anonymous keys only)")
    st.dataframe(pd.DataFrame(svc.churn_top(20)["rows"]), use_container_width=True)
    ch = summary["churn"]
    st.caption(f"Churn model: ROC AUC {ch['roc_auc']} vs recency-only baseline {ch['baseline_recency_auc']} "
               f"(temporal validation, test cutoff {ch['test_cutoff']}).")

with tab_forecast:
    horizon = st.slider("Days ahead", 7, 60, 30)
    fc = pd.DataFrame(svc.forecast(horizon)["rows"]).set_index("date")
    st.line_chart(fc[["lower", "forecast", "upper"]])
    g = summary["forecast"]["models"]["gradient_boosting"]
    st.caption(f"Backtest weekly WAPE {g['wape_weekly_pct']}%, bias {g['bias_pct']}%. "
               "Bands are empirical, not guaranteed coverage. Weekly totals are more reliable than single days.")

with tab_ask:
    mode = st.radio("Mode", ["Agent (tools)", "Knowledge base (RAG)"], horizontal=True)
    q = st.text_input("Ask a question", "What are the top 5 categories by profit?", max_chars=500)
    if st.button("Ask") and q.strip():
        if mode.startswith("Agent"):
            out = svc.run_agent(q, actor="dashboard")
            st.write(out["answer"])
            if out["steps"]:
                st.json(out["steps"])
        else:
            out = svc.ask(q, actor="dashboard")
            st.write(out["answer"])
            for s in out["sources"]:
                st.caption(f"[{s['n']}] {s['title']} (score {s['score']})")

with tab_vision:
    up = st.file_uploader("Upload a PNG/JPEG product tile", type=["png", "jpg", "jpeg"])
    if up is not None:
        try:
            res = svc.classify_image(up.getvalue(), actor="dashboard")
            st.image(up, width=160)
            st.table(pd.DataFrame(res["predictions"]))
            st.caption(f"Backend: {res['backend']}. Trained on synthetic icons, so real photos will not classify well.")
        except ValueError as e:
            st.warning(str(e))
