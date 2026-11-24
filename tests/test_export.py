"""The static demo must contain every file the front-end asks for, and no secrets/PII."""
import json
import re
from pathlib import Path

import pytest

from retailpulse import export_static

WEB = Path(__file__).resolve().parent.parent / "web"


@pytest.fixture(scope="module")
def site(tmp_path_factory, built):
    out = tmp_path_factory.mktemp("site") / "site"
    export_static.export(out, paths=built[0])
    return out


def test_demo_has_core_files(site):
    for name in ["health", "me", "kpis", "summary", "monthly", "forecast", "segments", "cohort", "anomalies",
                 "basket", "named", "churn_top", "monitoring", "models", "examples", "guard_examples", "samples",
                 "openapi", "top_category_revenue", "top_product_margin"]:
        assert (site / "demo" / f"{name}.json").exists(), name
    assert (site / "index.html").exists() and (site / ".nojekyll").exists()


def test_every_example_question_replays(site):
    ex = json.loads((site / "demo/examples.json").read_text())
    assert {e["mode"] for e in ex} == {"agent", "rag"}
    assert all(e.get("events") or e.get("result") for e in ex)


def test_guard_examples_blocked_or_nulled(site):
    g = {e["sql"]: e for e in json.loads((site / "demo/guard_examples.json").read_text())}
    assert "error" in g["DROP TABLE returns"] and "error" in g["SELECT * FROM sqlite_master"]
    pii = g["SELECT email, phone FROM dim_customer LIMIT 3"]["result"]
    assert all(v is None for row in pii["rows"] for v in row)


def test_every_sample_tile_has_a_prediction(site):
    names = {p.stem for p in (site / "samples").glob("*.png")}
    got = {s["name"] for s in json.loads((site / "demo/samples.json").read_text())}
    assert names == got and names


def test_no_secrets_or_audit_in_export(site):
    files = [p for p in site.rglob("*") if p.is_file()]
    assert not any(p.suffix in {".db", ".npz", ".jsonl", ".pt"} or p.name.startswith(".env") for p in files)
    blob = "".join(p.read_text(errors="ignore") for p in (site / "demo").glob("*.json"))
    assert not re.search(r"[\w.]+@[\w.]+\.\w+", blob.replace("@context", ""))  # no e-mail addresses


def test_frontend_has_no_inline_script_or_innerhtml():
    html = (WEB / "index.html").read_text()
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>\s*\S", html)
    for js in (WEB / "js").rglob("*.js"):
        code = re.sub(r"//.*", "", js.read_text())
        assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|\beval\(", code), js
