"""Central configuration.

Paths are explicit (``Paths``) so tests and Docker can run in any folder.
Every limit is overridable with an ``RP_*`` environment variable.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
SQL_DIR = ROOT / "sql"
DOCS_DIR = ROOT / "docs"

SEED = int(os.getenv("RP_SEED", "42"))
ENV = os.getenv("RP_ENV", "dev")  # dev | prod

# Guardrail limits
SQL_MAX_ROWS = int(os.getenv("RP_SQL_MAX_ROWS", "200"))
SQL_TIMEOUT_S = float(os.getenv("RP_SQL_TIMEOUT_S", "3"))
AGENT_MAX_STEPS = int(os.getenv("RP_AGENT_MAX_STEPS", "5"))
RATE_LIMIT_PER_MIN = int(os.getenv("RP_RATE_LIMIT_PER_MIN", "120"))
MAX_BODY_BYTES = int(os.getenv("RP_MAX_BODY_BYTES", "262144"))
MAX_IMAGE_BYTES = 200_000


@dataclass(frozen=True)
class Paths:
    data_dir: Path
    artifacts_dir: Path

    @classmethod
    def default(cls) -> "Paths":
        return cls(
            Path(os.getenv("RP_DATA_DIR", ROOT / "data")),
            Path(os.getenv("RP_ARTIFACTS_DIR", ROOT / "artifacts")),
        )

    @classmethod
    def under(cls, root) -> "Paths":
        root = Path(root)
        return cls(root / "data", root / "artifacts")

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "warehouse.db"

    @property
    def reports_dir(self) -> Path:
        return self.artifacts_dir / "reports"

    @property
    def models_dir(self) -> Path:
        return self.artifacts_dir / "models"

    @property
    def powerbi_dir(self) -> Path:
        return self.artifacts_dir / "powerbi"

    @property
    def kb_path(self) -> Path:
        return self.artifacts_dir / "kb.json"

    @property
    def summary_path(self) -> Path:
        return self.artifacts_dir / "summary.json"

    @property
    def audit_log(self) -> Path:
        return Path(os.getenv("RP_AUDIT_LOG", self.artifacts_dir / "audit.jsonl"))

    @property
    def registry_path(self) -> Path:
        return self.artifacts_dir / "model_registry.json"

    @property
    def monitoring_path(self) -> Path:
        return self.artifacts_dir / "monitoring.json"

    @property
    def forecast_csv(self) -> Path:
        return self.artifacts_dir / "forecast.csv"

    @property
    def rfm_csv(self) -> Path:
        return self.artifacts_dir / "rfm.csv"

    @property
    def churn_csv(self) -> Path:
        return self.artifacts_dir / "churn_scores.csv"

    def ensure(self) -> None:
        for d in (self.raw_dir, self.reports_dir, self.models_dir, self.powerbi_dir):
            d.mkdir(parents=True, exist_ok=True)
