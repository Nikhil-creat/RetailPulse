"""Business-logic facade used by the API, dashboard, CLI and agent (framework-independent)."""
from __future__ import annotations

import contextlib
import io
import json

import numpy as np
import pandas as pd
from PIL import Image

from . import analytics, config, registry, warehouse
from .agent import AnalyticsAgent
from .catalog import top_n_sql
from .config import Paths
from .errors import NotFound
from .llm import LLMClient
from .rag import KnowledgeBase
from .security import AuditLedger, SafeSQL
from .vision import baseline, cnn_torch
from .vision.synth_images import CLASSES, SIZE
from .warehouse import connect


class RetailPulseService:
    def __init__(self, paths: Paths | None = None, ledger: AuditLedger | None = None, llm: LLMClient | None = None):
        self.paths = paths or Paths.default()
        if not self.paths.db_path.exists() or not self.paths.kb_path.exists():
            raise FileNotFoundError("Warehouse not built yet. Run: python -m retailpulse.cli run-all")
        self.sql = SafeSQL(self.paths.db_path)
        self.kb = KnowledgeBase.load(self.paths.kb_path)
        self.ledger = ledger or AuditLedger(self.paths.audit_log)
        self.llm = llm or LLMClient.from_env()
        self._vision = None
        self._cache: dict = {}

    # ---- analytics
    def summary(self) -> dict:
        return json.loads(self.paths.summary_path.read_text(encoding="utf-8"))

    def kpis(self) -> dict:
        with contextlib.closing(connect(self.paths.db_path, readonly=True)) as conn:
            return analytics.kpis(conn)

    def top_n(self, dimension: str, metric: str = "revenue", n: int = 5, ascending: bool = False) -> dict:
        return self.sql.query(top_n_sql(dimension, metric, n, ascending))

    def safe_query(self, sql: str, actor: str = "service") -> dict:
        self.ledger.append(actor, "sql_query", {"sql": sql[:300]})
        return self.sql.query(sql)

    def forecast(self, horizon: int = 30) -> dict:
        df = pd.read_csv(self.paths.forecast_csv)
        horizon = max(1, min(int(horizon), len(df)))
        wape = self.summary()["forecast"]["models"]["gradient_boosting"]["wape_weekly_pct"]
        hist = self.sql.query("SELECT order_date AS date, ROUND(SUM(revenue), 2) AS revenue FROM vw_sales "
                              "WHERE is_returned = 0 GROUP BY order_date ORDER BY order_date DESC LIMIT 45")
        history = [{"date": r[0], "revenue": r[1]} for r in reversed(hist["rows"])]
        return {"rows": df.head(horizon).to_dict("records"), "backtest_wape_weekly_pct": wape, "history": history}

    def segments(self) -> dict:
        rfm = pd.read_csv(self.paths.rfm_csv)
        return {"rows": analytics.rfm_summary(rfm).to_dict("records")}

    def churn_top(self, n: int = 20) -> dict:
        df = pd.read_csv(self.paths.churn_csv).head(max(1, min(int(n), 50)))
        return {"rows": df.to_dict("records")}

    # ---- AI
    def ask(self, question: str, actor: str = "service") -> dict:
        self.ledger.append(actor, "rag_ask", {"question": question[:300]})
        return self.kb.answer(question, llm=self.llm)

    def run_agent(self, question: str, actor: str = "service") -> dict:
        return AnalyticsAgent(self, ledger=self.ledger, llm=self.llm).run(question, actor=actor)

    def classify_image(self, data: bytes, actor: str = "service") -> dict:
        if len(data) > config.MAX_IMAGE_BYTES:
            raise ValueError("Image too large.")
        try:
            img = Image.open(io.BytesIO(data))
            if img.format not in ("PNG", "JPEG"):
                raise ValueError("Only PNG or JPEG images are accepted.")
            if img.width * img.height > 4_000_000:
                raise ValueError("Image dimensions too large.")
            img = img.convert("RGB").resize((SIZE, SIZE), Image.Resampling.LANCZOS)
        except (OSError, Image.DecompressionBombError):
            raise ValueError("Could not read the image.") from None
        x = np.asarray(img)[None]
        backend, proba = self._predict(x)
        top = np.argsort(-proba[0])[:3]
        self.ledger.append(actor, "classify_image", {"backend": backend})
        return {"backend": backend,
                "predictions": [{"category": CLASSES[i], "probability": round(float(proba[0][i]), 4)} for i in top]}

    def _predict(self, x: np.ndarray):
        if self._vision is None:
            cnn_path = self.paths.models_dir / cnn_torch.WEIGHTS_FILE
            if cnn_torch.torch_available() and cnn_path.exists():
                self._vision = ("torch-cnn", cnn_torch.load_cnn(cnn_path))
            else:
                self._vision = ("numpy-mlp", baseline.NumpyMLP.load(self.paths.models_dir / baseline.WEIGHTS_FILE))
        backend, model = self._vision
        proba = cnn_torch.predict_proba(model, x) if backend == "torch-cnn" else model.predict_proba(x)
        return backend, proba

    # ---- v2 analytics
    def named(self, name: str) -> dict:
        queries = warehouse.load_queries()
        if name not in queries:
            raise NotFound(f"Unknown query '{name}'.")
        return self.sql.query(queries[name])

    def named_list(self) -> list[str]:
        return sorted(warehouse.load_queries())

    def monthly(self) -> dict:
        return self.named("monthly_revenue")

    def cohort(self) -> dict:
        if "cohort" not in self._cache:
            with contextlib.closing(connect(self.paths.db_path, readonly=True)) as conn:
                ret = analytics.cohort_retention(conn)
            self._cache["cohort"] = {
                "cohorts": [str(c) for c in ret.index], "months": [int(m) for m in ret.columns],
                "values": [[None if pd.isna(v) else round(float(v), 4) for v in row] for row in ret.to_numpy()]}
        return self._cache["cohort"]

    def anomalies(self) -> dict:
        if "anomalies" not in self._cache:
            from . import forecasting
            with contextlib.closing(connect(self.paths.db_path, readonly=True)) as conn:
                df = forecasting.detect_anomalies(forecasting.daily_orders(conn))
            self._cache["anomalies"] = {"rows": df.to_dict("records"), "unit": "orders per day"}
        return self._cache["anomalies"]

    def basket(self, n: int = 15) -> dict:
        if "basket" not in self._cache:
            with contextlib.closing(connect(self.paths.db_path, readonly=True)) as conn:
                self._cache["basket"] = analytics.market_basket(conn).to_dict("records")
        return {"rows": self._cache["basket"][: max(1, min(int(n), 30))]}

    def customer360(self, key) -> dict:
        try:
            key = int(key)
        except (TypeError, ValueError):
            raise ValueError("customer key must be an integer.") from None
        with contextlib.closing(connect(self.paths.db_path, readonly=True)) as conn:
            head = conn.execute(
                "SELECT city, age_band, COUNT(DISTINCT order_id), "
                "ROUND(SUM(CASE WHEN is_returned = 0 THEN revenue ELSE 0 END), 2), MIN(order_date), MAX(order_date), "
                "SUM(quantity) FROM vw_sales WHERE customer_key = ?", (key,)).fetchone()
            if head is None or head[2] == 0:
                raise NotFound("Customer not found.")
            cats = conn.execute(
                "SELECT category, ROUND(SUM(revenue), 2) FROM vw_sales WHERE customer_key = ? AND is_returned = 0 "
                "GROUP BY category ORDER BY 2 DESC LIMIT 3", (key,)).fetchall()
            hist = conn.execute(
                "SELECT substr(order_date, 1, 7), COUNT(DISTINCT order_id) FROM vw_sales WHERE customer_key = ? "
                "GROUP BY 1 ORDER BY 1 DESC LIMIT 12", (key,)).fetchall()
        out = {"customer_key": key, "city": head[0], "age_band": head[1], "orders": head[2], "net_revenue": head[3],
               "first_order": head[4], "last_order": head[5], "units": head[6],
               "top_categories": [{"category": c, "net_revenue": r} for c, r in cats],
               "orders_by_month": [{"month": m, "orders": n} for m, n in reversed(hist)],
               "segment": None, "rfm": None, "churn": None}
        rfm = pd.read_csv(self.paths.rfm_csv)
        r = rfm[rfm["customer_key"] == key]
        if len(r):
            r = r.iloc[0]
            out["segment"] = str(r["segment"])
            out["rfm"] = {"R": int(r["R"]), "F": int(r["F"]), "M": int(r["M"]), "recency_days": int(r["recency_days"])}
        ch = pd.read_csv(self.paths.churn_csv)
        c = ch[ch["customer_key"] == key]
        if len(c):
            c = c.iloc[0]
            out["churn"] = {"risk": float(c["churn_risk"]), "value_at_risk": float(c["value_at_risk"])}
        return out

    def monitoring(self) -> dict:
        return json.loads(self.paths.monitoring_path.read_text(encoding="utf-8"))

    def models(self) -> dict:
        return {"latest": registry.latest_by_model(self.paths.registry_path),
                "history": registry.load(self.paths.registry_path)[-12:]}

    def audit_tail(self, n: int = 30) -> dict:
        lines = []
        if self.ledger.path.exists():
            with self.ledger.path.open("r", encoding="utf-8") as fh:
                lines = fh.readlines()[-max(1, min(int(n), 200)):]
        ok, bad = self.ledger.verify()
        return {"chain_ok": ok, "first_bad_line": bad, "entries": [json.loads(x) for x in lines if x.strip()]}

    def health(self) -> dict:
        ok, bad = self.ledger.verify()
        return {"status": "ok", "audit_chain_ok": ok, "llm_enabled": self.llm.enabled}
