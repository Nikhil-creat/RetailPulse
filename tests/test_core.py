import numpy as np
import pandas as pd

from retailpulse import analytics, churn, forecasting, warehouse


def _conn(built):
    paths, _ = built
    return warehouse.connect(paths.db_path, readonly=True)


def test_data_quality_gates_pass(built):
    _, summary = built
    assert summary["data_quality"]["ok"], summary["data_quality"]


def test_all_15_named_queries_run(built):
    conn = _conn(built)
    names = warehouse.load_queries()
    assert len(names) == 15
    for n in names:
        df = warehouse.run_query(conn, n)
        assert len(df) > 0, n


def test_revenue_reconciles_between_sql_and_pandas(built):
    paths, _ = built
    conn = _conn(built)
    sql_total = conn.execute("SELECT SUM(revenue) FROM vw_sales WHERE is_returned = 0").fetchone()[0]
    items = pd.read_csv(paths.raw_dir / "order_items.csv")
    prods = pd.read_csv(paths.raw_dir / "products.csv")
    returns = pd.read_csv(paths.raw_dir / "returns.csv")
    m = items.merge(prods, on="product_id")
    m = m[~m.order_id.isin(returns.order_id)]
    expected = (m.quantity * m.unit_price * (1 - m.discount_pct / 100)).round(2).sum()
    assert abs(sql_total - expected) < 1.0
    assert abs(analytics.kpis(conn)["net_revenue"] - expected) < 1.0


def test_rfm_covers_every_customer_with_valid_scores(built):
    conn = _conn(built)
    r = analytics.rfm(conn)
    assert r["customer_key"].is_unique
    assert set(r[["R", "F", "M"]].to_numpy().ravel()) <= {1, 2, 3, 4, 5}
    assert r["segment"].notna().all()
    # lowest recency days should score highest R
    assert r.loc[r["R"] == 5, "recency_days"].max() <= r.loc[r["R"] == 1, "recency_days"].min()


def test_cohort_month_zero_is_100pct_and_bounded(built):
    ret = analytics.cohort_retention(_conn(built))
    assert np.allclose(ret[0].dropna(), 1.0)
    vals = ret.to_numpy(dtype=float)
    assert np.nanmax(vals) <= 1.0 and np.nanmin(vals) >= 0.0


def test_basket_finds_planted_affinity(built):
    b = analytics.market_basket(_conn(built))
    top_pairs = {frozenset((r.antecedent, r.consequent)) for r in b.head(4).itertuples()}
    assert frozenset(("Fashion", "Beauty")) in top_pairs
    assert (b["lift"] > 1.1).any()


def test_forecast_features_have_no_leakage(built):
    y = forecasting.daily_net_revenue(_conn(built))
    X1, _ = forecasting.build_training_frame(y)
    t = y.index[200]
    y2 = y.copy()
    y2.loc[t] = y2.loc[t] * 100 + 1e6  # change ONLY day t's own value
    X2, _ = forecasting.build_training_frame(y2)
    pd.testing.assert_series_equal(X1.loc[t], X2.loc[t])           # day t's features can't see day t
    assert not X1.loc[t + pd.Timedelta(days=1)].equals(X2.loc[t + pd.Timedelta(days=1)])  # but t+1 can


def test_forecast_output_shape_and_bands(built):
    paths, summary = built
    fc = pd.read_csv(paths.forecast_csv)
    assert len(fc) == summary["forecast"]["horizon_days"]
    assert (fc["lower"] <= fc["forecast"]).all() and (fc["forecast"] <= fc["upper"]).all()
    assert (fc["forecast"] >= 0).all()


def test_model_beats_naive_baselines_on_weekly_error(built):
    m = built[1]["forecast"]["models"]
    assert m["gradient_boosting"]["wape_weekly_pct"] < m["seasonal_naive"]["wape_weekly_pct"]
    assert m["gradient_boosting"]["wape_weekly_pct"] < m["moving_average_28d"]["wape_weekly_pct"]


def test_anomaly_detector_catches_a_planted_spike(built):
    y = forecasting.daily_orders(_conn(built))
    y2 = y.copy()
    day = y2.index[400]
    y2.loc[day] = y2.loc[day] * 6
    out = forecasting.detect_anomalies(y2)
    assert day.strftime("%Y-%m-%d") in set(out["date"])


def test_churn_features_have_no_future_leakage(built):
    orders = churn.load_orders(_conn(built))
    cutoff = orders["order_date"].max() - pd.Timedelta(days=120)
    full = churn.build_features(orders, cutoff)
    truncated = churn.build_features(orders[orders["order_date"] <= cutoff], cutoff)
    pd.testing.assert_frame_equal(full, truncated)


def test_churn_model_beats_chance_and_scores_are_valid(built):
    paths, summary = built
    c = summary["churn"]
    assert c["roc_auc"] > 0.6
    scores = pd.read_csv(paths.churn_csv)
    assert scores["churn_risk"].between(0, 1).all()
    assert scores["value_at_risk"].is_monotonic_decreasing
    assert "email" not in " ".join(scores.columns).lower()
