"""Daily net-revenue forecasting: honest multi-step backtest vs baselines, intervals, anomalies."""
from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

LAGS = (1, 7, 14, 28)


def daily_net_revenue(conn: sqlite3.Connection) -> pd.Series:
    df = pd.read_sql_query(
        "SELECT order_date, SUM(revenue) AS revenue FROM vw_sales WHERE is_returned = 0 GROUP BY order_date",
        conn, parse_dates=["order_date"])
    s = df.set_index("order_date")["revenue"].sort_index().asfreq("D", fill_value=0.0)
    s.name = "revenue"
    return s


def daily_orders(conn: sqlite3.Connection) -> pd.Series:
    df = pd.read_sql_query(
        "SELECT d.full_date AS order_date, COUNT(*) AS orders FROM fact_orders o "
        "JOIN dim_date d ON d.date_key = o.date_key GROUP BY d.full_date",
        conn, parse_dates=["order_date"])
    s = df.set_index("order_date")["orders"].sort_index().asfreq("D", fill_value=0)
    s.name = "orders"
    return s.astype(float)


def _calendar(idx: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame({
        "dow": idx.dayofweek,
        "is_weekend": (idx.dayofweek >= 5).astype(int),
        "month": idx.month,
        "festive": idx.month.isin([10, 11]).astype(int),
        "doy_sin": np.sin(2 * np.pi * idx.dayofyear / 365.25),
        "doy_cos": np.cos(2 * np.pi * idx.dayofyear / 365.25),
    }, index=idx)


def build_training_frame(y: pd.Series) -> tuple[pd.DataFrame, pd.Series]:
    """Features for day t use ONLY values up to t-1 (no leakage)."""
    lag = pd.DataFrame({f"lag_{k}": y.shift(k) for k in LAGS}, index=y.index)
    roll = pd.DataFrame({
        "roll_7": y.shift(1).rolling(7).mean(),
        "roll_28": y.shift(1).rolling(28).mean(),
    }, index=y.index)
    X = pd.concat([_calendar(y.index), lag, roll], axis=1)
    mask = X.notna().all(axis=1)
    return X[mask], y[mask]


def _next_row(history: np.ndarray, day: pd.Timestamp, columns: list[str]) -> pd.DataFrame:
    row = _calendar(pd.DatetimeIndex([day])).reset_index(drop=True)
    for k in LAGS:
        row[f"lag_{k}"] = history[-k]
    row["roll_7"] = history[-7:].mean()
    row["roll_28"] = history[-28:].mean()
    return row[columns]


class DemandForecaster:
    def __init__(self, seed: int = 0):
        self.model = HistGradientBoostingRegressor(
            max_iter=300, learning_rate=0.05, max_depth=5, l2_regularization=1.0, random_state=seed)
        self.columns: list[str] = []
        self.history: pd.Series | None = None

    def fit(self, y: pd.Series) -> "DemandForecaster":
        X, target = build_training_frame(y)
        self.model.fit(X, np.log1p(target))
        self.columns = list(X.columns)
        self.history = y.copy()
        return self

    def forecast(self, horizon: int) -> pd.Series:
        """Recursive multi-step forecast (predictions feed later lags)."""
        hist = self.history.to_numpy().astype(float).tolist()
        start = self.history.index[-1] + pd.Timedelta(days=1)
        days = pd.date_range(start, periods=horizon, freq="D")
        preds = []
        for d in days:
            x = _next_row(np.asarray(hist), d, self.columns)
            yhat = float(np.expm1(self.model.predict(x)[0]))
            yhat = max(yhat, 0.0)
            preds.append(yhat)
            hist.append(yhat)
        return pd.Series(preds, index=days, name="forecast")


def seasonal_naive(train: pd.Series, horizon: int) -> pd.Series:
    vals = np.resize(train.iloc[-7:].to_numpy(), horizon)
    idx = pd.date_range(train.index[-1] + pd.Timedelta(days=1), periods=horizon, freq="D")
    return pd.Series(vals, index=idx)


def moving_average(train: pd.Series, horizon: int, window: int = 28) -> pd.Series:
    idx = pd.date_range(train.index[-1] + pd.Timedelta(days=1), periods=horizon, freq="D")
    return pd.Series(float(train.iloc[-window:].mean()), index=idx)


def _metrics(y_true: pd.Series, y_pred: pd.Series) -> dict:
    e = y_true.to_numpy() - y_pred.to_numpy()
    wt, wp = y_true.resample("7D").sum(), y_pred.resample("7D").sum()
    return {
        "mae": round(float(np.abs(e).mean()), 2),
        "rmse": round(float(np.sqrt((e ** 2).mean())), 2),
        "wape_daily_pct": round(100 * float(np.abs(e).sum() / np.abs(y_true).sum()), 2),
        "wape_weekly_pct": round(100 * float(np.abs(wt - wp).sum() / wt.sum()), 2),
        "bias_pct": round(100 * float((y_pred.sum() - y_true.sum()) / y_true.sum()), 2),
    }


def backtest(y: pd.Series, holdout: int = 60, seed: int = 0) -> tuple[dict, dict]:
    """Train on everything before the last `holdout` days, forecast them all at once."""
    train, test = y.iloc[:-holdout], y.iloc[-holdout:]
    model = DemandForecaster(seed).fit(train)
    pred = model.forecast(holdout)
    sn, ma = seasonal_naive(train, holdout), moving_average(train, holdout)
    models = {
        "gradient_boosting": _metrics(test, pred),
        "seasonal_naive": _metrics(test, sn),
        "moving_average_28d": _metrics(test, ma),
    }
    rel = (np.abs(test.to_numpy() - pred.to_numpy()) / np.maximum(pred.to_numpy(), 1.0))
    report = {
        "holdout_days": holdout,
        "models": models,
        "best_model": min(models, key=lambda m: models[m]["wape_weekly_pct"]),
        "interval_rel_q80": round(float(min(np.quantile(rel, 0.8), 0.95)), 3),
    }
    return report, {"train": train, "test": test, "pred": pred}


def final_forecast(y: pd.Series, horizon: int, rel_band: float, seed: int = 0) -> pd.DataFrame:
    pred = DemandForecaster(seed).fit(y).forecast(horizon)
    return pd.DataFrame({
        "date": pred.index.strftime("%Y-%m-%d"),
        "forecast": pred.round(2).to_numpy(),
        "lower": (pred * (1 - rel_band)).clip(lower=0).round(2).to_numpy(),
        "upper": (pred * (1 + rel_band)).round(2).to_numpy(),
    })


def detect_anomalies(y: pd.Series, z_thresh: float = 3.5) -> pd.DataFrame:
    """Robust z-score of each day vs the median of the same weekday over the prior 8 weeks."""
    base = y.groupby(y.index.dayofweek).transform(lambda s: s.shift(1).rolling(8, min_periods=4).median())
    ratio = (y / base.replace(0, np.nan)).dropna().clip(lower=1e-3)
    logr = np.log(ratio)  # revenue is heavy-tailed; work on the log scale
    med = logr.median()
    mad = float(np.median(np.abs(logr - med))) or 1e-9
    z = (logr - med) / (1.4826 * mad)
    out = pd.DataFrame({"date": ratio.index, "revenue": y.loc[ratio.index].to_numpy(),
                        "expected": base.loc[ratio.index].to_numpy(), "z": z.to_numpy()})
    out = out[np.abs(out["z"]) > z_thresh].copy()
    out["kind"] = np.where(out["z"] > 0, "spike", "drop")
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    return out.round(2).reset_index(drop=True)
