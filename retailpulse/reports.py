"""Static charts (PNG), an HTML report and a RESULTS.md, styled per the data-viz method:
one hue for single series, fixed categorical order, thin marks, recessive grid, direct labels,
text in ink tokens (never series colour), no dual axes."""
from __future__ import annotations

import base64
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
SEQ = LinearSegmentedColormap.from_list("seq_blue", RAMP)

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "text.color": INK, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.edgecolor": GRID, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "lines.linewidth": 2, "figure.dpi": 100,
})


def _save(fig, path: Path) -> str:
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path.name


def chart_monthly_revenue(df: pd.DataFrame, out: Path) -> str:
    fig, ax = plt.subplots(figsize=(8, 4))
    x = pd.to_datetime(df["month"] + "-01")
    ax.plot(x, df["net_revenue"] / 1e7, color=BLUE)
    for d in x[x.dt.month.isin([10, 11])]:
        ax.axvspan(d, d + pd.offsets.MonthEnd(0), color=GRID, alpha=0.7, lw=0)
    ax.set_title("Net revenue per month (shaded: Oct-Nov festive season)")
    ax.set_ylabel("₹ crore")
    ax.grid(axis="x", visible=False)
    return _save(fig, out / "monthly_revenue.png")


def chart_category(df: pd.DataFrame, out: Path) -> str:
    d = df.sort_values("net_revenue")
    fig, ax = plt.subplots(figsize=(8, 3.8))
    bars = ax.barh(d["category"], d["net_revenue"] / 1e7, color=BLUE, height=0.6)
    for b, share, m in zip(bars, d["revenue_share_pct"], d["margin_pct"]):
        ax.text(b.get_width(), b.get_y() + b.get_height() / 2, f"  {b.get_width():.1f} cr  ({share}% share, {m}% margin)",
                va="center", color=INK, fontsize=9)
    ax.set_xlim(0, d["net_revenue"].max() / 1e7 * 1.55)
    ax.set_title("Net revenue by category")
    ax.set_xlabel("₹ crore")
    ax.grid(axis="y", visible=False)
    return _save(fig, out / "category_revenue.png")


def chart_forecast(frames: dict, out: Path) -> str:
    train, test, pred = frames["train"], frames["test"], frames["pred"]
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(train.index[-45:], train.iloc[-45:] / 1e5, color=INK2, lw=1.2, label="History")
    ax.plot(test.index, test / 1e5, color=BLUE, label="Actual (holdout)")
    ax.plot(pred.index, pred / 1e5, color=ORANGE, label="Forecast")
    ax.set_title("60-day backtest: forecast vs actual daily net revenue")
    ax.set_ylabel("₹ lakh per day")
    ax.legend(frameon=False, loc="upper left")
    ax.grid(axis="x", visible=False)
    return _save(fig, out / "forecast_backtest.png")


def chart_rfm(rfm_sum: pd.DataFrame, out: Path) -> str:
    d = rfm_sum.sort_values("customers")
    fig, ax = plt.subplots(figsize=(8, 3.8))
    bars = ax.barh(d["segment"], d["customers"], color=BLUE, height=0.6)
    for b, share in zip(bars, d["customer_share_pct"]):
        ax.text(b.get_width(), b.get_y() + b.get_height() / 2, f"  {int(b.get_width()):,} ({share}%)", va="center", fontsize=9)
    ax.set_xlim(0, d["customers"].max() * 1.25)
    ax.set_title("Customers by RFM segment")
    ax.grid(axis="y", visible=False)
    return _save(fig, out / "rfm_segments.png")


def chart_cohort(ret: pd.DataFrame, out: Path) -> str:
    fig, ax = plt.subplots(figsize=(8, 5.5))
    data = ret.to_numpy(dtype=float)
    im = ax.imshow(data, cmap=SEQ, vmin=0, vmax=1, aspect="auto")
    ax.set_yticks(range(len(ret)))
    ax.set_yticklabels([str(p) for p in ret.index], fontsize=7)
    ax.set_xticks(range(len(ret.columns)))
    ax.set_xticklabels(ret.columns)
    ax.set_xlabel("Months since first order")
    ax.set_title("Cohort retention (share of cohort ordering again)")
    ax.grid(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.04)
    cb.outline.set_visible(False)
    return _save(fig, out / "cohort_retention.png")


def chart_churn(importance: pd.Series, out: Path) -> str:
    d = importance.sort_values().tail(7)
    fig, ax = plt.subplots(figsize=(8, 3.8))
    ax.barh(d.index, d.values, color=BLUE, height=0.6)
    ax.set_title("Churn model: permutation importance (drop in ROC AUC)")
    ax.grid(axis="y", visible=False)
    return _save(fig, out / "churn_importance.png")


def results_markdown(s: dict) -> str:
    k, f, c, v = s["kpis"], s["forecast"], s["churn"], s["vision"]
    g, sn, ma = (f["models"][m] for m in ("gradient_boosting", "seasonal_naive", "moving_average_28d"))
    rfm = ", ".join(f"{a}: {b:,}" for a, b in s["rfm"].items())
    return f"""# Results (auto-generated by `python -m retailpulse.cli run-all`)

Dataset: {s['data']['customers']:,} customers, {s['data']['products']:,} products, {s['data']['orders']:,} orders,
{s['data']['order_items']:,} order items (synthetic, seed {s['seed']}). Data-quality gates: **{'PASS' if s['data_quality']['ok'] else 'FAIL'}**.

## Business KPIs
| Metric | Value |
|---|---|
| Net revenue | ₹{k['net_revenue']:,.0f} |
| Net profit (margin) | ₹{k['net_profit']:,.0f} ({k['profit_margin_pct']}%) |
| Orders / customers | {k['orders']:,} / {k['customers']:,} |
| Average order value | ₹{k['avg_order_value']:,.0f} |
| Return rate | {k['return_rate_pct']}% |
| Top 20% of products earn | {s['pareto_top20_share_pct']}% of revenue |

## Demand forecast ({f['holdout_days']}-day holdout, recursive multi-step)
| Model | Weekly WAPE | Daily WAPE | MAE (₹) | Bias |
|---|---|---|---|---|
| **Gradient boosting** | **{g['wape_weekly_pct']}%** | {g['wape_daily_pct']}% | {g['mae']:,.0f} | {g['bias_pct']}% |
| Seasonal naive | {sn['wape_weekly_pct']}% | {sn['wape_daily_pct']}% | {sn['mae']:,.0f} | {sn['bias_pct']}% |
| 28-day moving average | {ma['wape_weekly_pct']}% | {ma['wape_daily_pct']}% | {ma['mae']:,.0f} | {ma['bias_pct']}% |

## Churn model (temporal validation: train cutoff {c['train_cutoff']}, test cutoff {c['test_cutoff']})
| Metric | Value |
|---|---|
| ROC AUC (model) | {c['roc_auc']} |
| ROC AUC (recency-only baseline) | {c['baseline_recency_auc']} |
| Average precision | {c['avg_precision']} (base churn rate {c['test_churn_rate_pct']}%) |
| Top-decile lift | {c['top_decile_lift']}x |
| Top features | {', '.join(c['top_features'])} |

## Customer segments (RFM)
{rfm}

## Image classifier ({v['backend']})
Accuracy on held-out synthetic product tiles: **{v['accuracy'] * 100:.1f}%** over {len(v['classes'])} classes.

## Evaluations
| Suite | Result |
|---|---|
| RAG retrieval hit@3 ({s['evals']['rag']['cases']} questions) | {s['evals']['rag']['hit_at_3']} (MRR {s['evals']['rag']['mrr']}) |
| Agent routing + guardrail refusals ({s['evals']['agent']['cases']} cases) | {s['evals']['agent']['passed']}/{s['evals']['agent']['cases']} |
"""


def html_report(s: dict, charts: list[str], reports_dir: Path) -> Path:
    k = s["kpis"]
    imgs = "".join(
        f'<figure><img alt="{n}" src="data:image/png;base64,{base64.b64encode((reports_dir / n).read_bytes()).decode()}"></figure>'
        for n in charts)
    tiles = "".join(f'<div class="tile"><span>{lab}</span><b>{val}</b></div>' for lab, val in [
        ("Net revenue", f"₹{k['net_revenue'] / 1e7:.1f} cr"), ("Net profit", f"₹{k['net_profit'] / 1e7:.1f} cr"),
        ("Orders", f"{k['orders']:,}"), ("Customers", f"{k['customers']:,}"),
        ("Avg order value", f"₹{k['avg_order_value']:,.0f}"), ("Return rate", f"{k['return_rate_pct']}%")])
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RetailPulse report</title><style>
body{{font-family:system-ui,sans-serif;background:#fcfcfb;color:#0b0b0b;margin:0;padding:16px;max-width:900px;margin-inline:auto}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin:16px 0}}
.tile{{border:1px solid #e6e5e1;border-radius:8px;padding:10px}}.tile span{{display:block;color:#52514e;font-size:12px}}.tile b{{font-size:20px}}
img{{width:100%;height:auto}}figure{{margin:16px 0}}</style></head><body>
<h1>RetailPulse report</h1><div class="tiles">{tiles}</div>{imgs}</body></html>"""
    path = reports_dir / "report.html"
    path.write_text(html, encoding="utf-8")
    return path
