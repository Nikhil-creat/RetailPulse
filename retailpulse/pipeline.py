"""End-to-end pipeline: generate -> warehouse -> analytics -> forecast -> churn -> vision -> KB -> reports."""
from __future__ import annotations

import json
import time
from contextlib import closing, contextmanager
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import (analytics, churn, config, data_gen, evals, forecasting, insights, monitoring, rag, registry,
               reports, warehouse)
from .config import Paths
from .vision import baseline

QUICK = dict(n_customers=1500, n_products=100, n_orders=15_000)
FULL = dict(n_customers=5000, n_products=200, n_orders=50_000)
FORECAST_HORIZON = 60
PII_COLUMNS = {"email", "phone"}


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (pd.Timestamp,)):
        return str(o)
    raise TypeError(f"Not serializable: {type(o)}")


def export_powerbi(conn, out_dir) -> list[str]:
    """Star-schema CSVs ready for Power BI. PII columns are dropped from the export."""
    written = []
    for table in ("dim_customer", "dim_product", "dim_date", "fact_orders", "fact_order_items", "returns"):
        df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
        df = df.drop(columns=[c for c in df.columns if c in PII_COLUMNS])
        df.to_csv(out_dir / f"{table}.csv", index=False)
        written.append(f"{table}.csv")
    return written


def run_all(paths: Paths | None = None, quick: bool = False, seed: int | None = None, verbose: bool = True) -> dict:
    paths = paths or Paths.default()
    paths.ensure()
    sizes = QUICK if quick else FULL
    seed = config.SEED if seed is None else seed
    timings: dict[str, float] = {}

    @contextmanager
    def step(name: str):
        if verbose:
            print(f"[{name}] ...", flush=True)
        t0 = time.monotonic()
        yield
        timings[name] = round(time.monotonic() - t0, 1)

    summary: dict = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     "seed": seed, "quick_mode": quick}

    with step("generate+warehouse"):
        data = data_gen.generate(seed=seed, **sizes)
        data_gen.write_csvs(data, paths.raw_dir)
        built = warehouse.build_warehouse(paths)
        summary["data"] = {"customers": built["counts"]["dim_customer"], "products": built["counts"]["dim_product"],
                           "orders": built["counts"]["fact_orders"], "order_items": built["counts"]["fact_order_items"]}
        summary["data_quality"] = built["data_quality"]
        if not built["data_quality"]["ok"]:
            raise RuntimeError(f"Data-quality gate failed: {built['data_quality']['checks']}")

    with closing(warehouse.connect(paths.db_path)) as conn:
        with step("analytics"):
            kpi = analytics.kpis(conn)
            rfm = analytics.rfm(conn)
            rfm_sum = analytics.rfm_summary(rfm)
            cohort = analytics.cohort_retention(conn)
            basket = analytics.market_basket(conn)
            pareto = analytics.pareto_share(conn)
            rfm.to_csv(paths.rfm_csv, index=False)
            summary.update(kpis=kpi, pareto_top20_share_pct=pareto,
                           rfm=dict(zip(rfm_sum["segment"], rfm_sum["customers"].astype(int))))

        with step("forecast"):
            y = forecasting.daily_net_revenue(conn)
            fc_report, frames = forecasting.backtest(y, holdout=60, seed=0)
            final = forecasting.final_forecast(y, FORECAST_HORIZON, fc_report["interval_rel_q80"])
            final.to_csv(paths.forecast_csv, index=False)
            anomalies = forecasting.detect_anomalies(forecasting.daily_orders(conn))
            planted = set(data["meta"]["flash_sale_days"])
            summary["forecast"] = {**fc_report, "horizon_days": FORECAST_HORIZON}
            summary["anomalies"] = {"count": int(len(anomalies)), "spikes": int((anomalies["kind"] == "spike").sum()),
                                    "flash_days_planted": len(planted),
                                    "flash_days_detected": len(planted & set(anomalies["date"]))}

        with step("churn"):
            res = churn.train_and_evaluate(churn.load_orders(conn), seed=0)
            res["scores"].to_csv(paths.churn_csv, index=False)
            summary["churn"] = res["metrics"]

        with step("vision"):
            vis = baseline.train_baseline(paths.models_dir, n_per_class=250 if quick else 400, seed=0)
            summary["vision"] = {k: v for k, v in vis.items() if k != "confusion_matrix"}

        with step("monitoring+registry"):
            orders_df = churn.load_orders(conn)
            drift = monitoring.build_report(orders_df, res["features"]["train"], res["features"]["now"], churn.FEATURES)
            paths.monitoring_path.write_text(json.dumps(drift, indent=2), encoding="utf-8")
            summary["monitoring"] = {"overall_status": drift["overall_status"],
                                     "order_value_psi": drift["order_value"]["psi"]}
            fp = registry.fingerprint(paths.raw_dir / "orders.csv", paths.raw_dir / "order_items.csv")
            fm = fc_report["models"]
            gb = fm["gradient_boosting"]
            summary["registry"] = [
                registry.register(
                    paths.registry_path, "demand_forecaster",
                    {"algo": "HistGradientBoostingRegressor", "lags": list(forecasting.LAGS), "target": "log1p(revenue)"},
                    {"wape_weekly_pct": gb["wape_weekly_pct"], "wape_daily_pct": gb["wape_daily_pct"], "bias_pct": gb["bias_pct"]},
                    fp, {"beats_seasonal_naive": gb["wape_weekly_pct"] < fm["seasonal_naive"]["wape_weekly_pct"],
                         "beats_moving_average": gb["wape_weekly_pct"] < fm["moving_average_28d"]["wape_weekly_pct"]}),
                registry.register(
                    paths.registry_path, "churn_classifier",
                    {"algo": "HistGradientBoostingClassifier", "features": churn.FEATURES, "horizon_days": churn.HORIZON_DAYS},
                    {k: res["metrics"][k] for k in ("roc_auc", "avg_precision", "top_decile_lift")},
                    fp, {"beats_recency_baseline": res["metrics"]["roc_auc"] > res["metrics"]["baseline_recency_auc"],
                         "auc_above_0_6": res["metrics"]["roc_auc"] > 0.6}),
                registry.register(
                    paths.registry_path, "vision_classifier",
                    {"backend": vis["backend"], "classes": vis["classes"]},
                    {"accuracy": vis["accuracy"]}, fp, {"accuracy_above_0_9": vis["accuracy"] > 0.9}),
            ]

        with step("knowledge-base"):
            docs = rag.STATIC_DOCS + insights.build_insights(
                conn, kpi, rfm_sum, cohort, basket, fc_report, res["metrics"], anomalies,
                data["meta"]["flash_sale_days"], pareto)
            kb = rag.KnowledgeBase(docs)
            kb.save(paths.kb_path)
            summary["evals"] = {"rag": rag.eval_retrieval(kb, evals.RAG_CASES, k=3), "agent": evals.eval_agent_plans()}

        with step("reports"):
            charts = [
                reports.chart_monthly_revenue(warehouse.run_query(conn, "monthly_revenue"), paths.reports_dir),
                reports.chart_category(warehouse.run_query(conn, "category_performance"), paths.reports_dir),
                reports.chart_forecast(frames, paths.reports_dir),
                reports.chart_rfm(rfm_sum, paths.reports_dir),
                reports.chart_cohort(cohort, paths.reports_dir),
                reports.chart_churn(res["importance"], paths.reports_dir),
            ]
            export_powerbi(conn, paths.powerbi_dir)

    summary["timings_s"] = timings
    (paths.reports_dir / "RESULTS.md").write_text(reports.results_markdown(summary), encoding="utf-8")
    reports.html_report(summary, charts, paths.reports_dir)
    paths.summary_path.write_text(json.dumps(summary, indent=2, default=_json_default), encoding="utf-8")
    if verbose:
        print(f"Done in {sum(timings.values()):.1f}s. Artifacts: {paths.artifacts_dir}")
    return summary
