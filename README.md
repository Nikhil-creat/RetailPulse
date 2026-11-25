# RetailPulse

[![CI](https://github.com/Nikhil-creat/RetailPulse/actions/workflows/ci.yml/badge.svg)](https://github.com/Nikhil-creat/RetailPulse/actions)
[![Live demo](https://img.shields.io/badge/live%20demo-GitHub%20Pages-2a78d6)](https://nikhil-creat.github.io/RetailPulse/)

**Live demo (static, pre-computed):** https://nikhil-creat.github.io/RetailPulse/ . Deploy it on your own domain with Cloudflare Pages: [docs/DEPLOY_CLOUDFLARE.md](docs/DEPLOY_CLOUDFLARE.md).

End-to-end retail analytics with a guarded AI layer: a **SQL star-schema warehouse**, business analytics
(RFM, cohorts, market basket), **demand forecasting**, a **churn model**, a **grounded RAG assistant**, a
**tool-using agent**, an **image classifier (CNN)**, and a **secured API**, packaged with Docker, tests and CI.

<p align="center"><img src="docs/assets/overview-light.png" width="48%" alt="Overview"> <img src="docs/assets/overview-dark.png" width="48%" alt="Overview, dark mode"></p>
<p align="center"><img src="docs/assets/forecast.png" width="48%" alt="Forecast with backtest"> <img src="docs/assets/assistant.png" width="48%" alt="Agent and guardrail refusal"></p>

> All data is **synthetic** (generated with a fixed seed so results are reproducible). It has planted
> structure (seasonality, flash sales, churners, category affinity) so the analytics have something real
> to find. Nothing here claims real-world business impact. See [docs/LIMITATIONS.md](docs/LIMITATIONS.md).

## Architecture

```mermaid
flowchart LR
  G[Data generator] --> W[(SQLite star schema<br/>+ data-quality gates)]
  W --> A[Analytics<br/>RFM / cohorts / basket]
  W --> F[Forecast + anomalies]
  W --> C[Churn model]
  A & F & C --> K[Insights -> Knowledge base]
  K --> R[RAG: cited answers or abstain]
  W --> S[SafeSQL guard]
  S --> AG[Agent: allow-listed tools]
  R --> AG
  V[CNN / MLP image classifier] --> SV
  AG & R & S --> SV[Service layer]
  SV --> API[Secured API]
  SV --> D[Streamlit dashboard]
  SV --> CLI
  API --> L[(Hash-chained audit log)]
```

## The web app (v2)

A dependency-free web app served by the API itself (`python -m retailpulse.cli serve`, then open `/`). Every page has a
real URL (`/demand-forecast/`, `/ai-assistant/`, ...), a unique title, description, canonical, one `<h1>`, breadcrumbs,
structured data (JSON-LD), social share card and internal links, and a custom 404. The HTML is complete before any
JavaScript runs, so crawlers and link previews see it. Nine pages: **Overview, Customers (RFM, cohorts, churn, customer 360), Forecast (backtest + anomalies), Assistant
(streaming agent + cited RAG + guardrail tests), Explorer (SQL library + attack console), Vision (CNN/MLP), Trust & MLOps
(drift PSI, model registry, audit chain), API reference (from OpenAPI), About**.
Header and footer on every page; dark mode; installable PWA; keyboard and screen-reader support; charts have tooltips
and a table view. No CDN and no inline scripts: a strict Content-Security-Policy is enforced. Server data is rendered with
`textContent` only (a test enforces no `innerHTML`). JavaScript is ~100 KB in total, split per page and loaded on demand; there is
no bundler and no source map.

The same UI runs as a **static demo** (`export-static`): it replays real pre-computed outputs of the example questions.
Free-form questions, uploads and the audit log need the live backend. The export also writes `sitemap.xml`, `robots.txt`,
`llms.txt`, `404.html`, Cloudflare `_headers` and an optional `CNAME`.

## What is in it

| Layer | What it does | Where |
|---|---|---|
| Warehouse | Star schema, constraints, indexes, view, 5 data-quality gates | `retailpulse/warehouse.py` |
| SQL | 15 business questions (CTEs, window functions, LAG, RANK, Pareto) | `sql/analysis_queries.sql` |
| Analytics | RFM segments, cohort retention, category lift, Pareto | `retailpulse/analytics.py` |
| Forecast | Gradient boosting, recursive multi-step, backtest vs 2 baselines, intervals, anomaly detection | `retailpulse/forecasting.py` |
| Churn | Temporal validation (no leakage), recency baseline, permutation importance, value-at-risk | `retailpulse/churn.py` |
| RAG | TF-IDF retrieval, citations, abstains when unsure, optional LLM rewrite | `retailpulse/rag.py` |
| Agent | Rule planner (+ optional LLM planner validated against an allow-list), step budget, audit | `retailpulse/agent.py` |
| Vision | Synthetic product tiles; PyTorch CNN (optional) + NumPy MLP fallback, pickle-free weights | `retailpulse/vision/` |
| Security | Read-only SQL guard, PII masking, injection detection, roles, rate limit, hashed API keys, audit chain, CSP | `retailpulse/security.py` |
| API | Roles, rate limits, request IDs, JSON logs, `/metrics`, OpenAPI 3.1, SSE streaming, safe static serving | `retailpulse/api.py` |
| Web | Real-URL app (vanilla ES modules), PWA, per-page SEO, demo export | `web/`, `retailpulse/seo.py`, `export_static.py` |
| MCP | Read-only Model Context Protocol server over stdio (7 guarded tools) | `retailpulse/mcp_server.py` |
| LLM routing | Optional Groq/Gemini model discovery, offline fallback, keys never logged | `retailpulse/model_router.py` |
| MLOps | PSI drift monitoring, model registry with promotion gates | `retailpulse/monitoring.py`, `registry.py` |
| Ops | Dockerfile (non-root, read-only FS), compose, GitHub Actions CI | repo root |

## Results (seed 42, full-size run; regenerate with `run-all`)

| Area | Result | Honest reading |
|---|---|---|
| Data | 5,000 customers, 200 products, 50,371 orders, 94,846 items; quality gates pass | synthetic |
| Forecast (60-day holdout) | weekly WAPE **19.9%** vs 33.6% seasonal-naive vs 33.1% moving-average | beats baselines; **under-forecasts by ~18%**; weekly totals are usable, single days are noisy |
| Churn (later test cutoff) | ROC AUC **0.705** vs 0.655 recency-only; top-decile lift 1.77x | modest signal; synthetic churn is partly random by construction |
| Anomalies | all 6 planted flash-sale days detected (24 flagged in total) | detector also flags other days |
| RAG | hit@3 = 1.00 on 18 questions (MRR 0.90) | small, self-written eval set; likely optimistic |
| Agent | 13/13 routing + refusal cases | rule-based cases written by the author |
| Vision | 98.1% on held-out synthetic tiles | easy task by design; not real photos |
| Tests | 142 pass, 1 skipped (PyTorch CNN test needs torch) | |

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q                       # 142 tests
python -m retailpulse.cli run-all         # ~7 s: data -> warehouse -> models -> reports
python -m retailpulse.cli ask "How is churn defined?"
python -m retailpulse.cli agent "top 5 categories by profit"
python -m retailpulse.cli serve           # dev mode (no keys): UI at http://127.0.0.1:8000
# production-style: roles are viewer < analyst < admin
python -m retailpulse.cli make-key --name me --role admin   # prints the key once + the hash line for .env
cp .env.example .env                      # paste the line into RP_API_KEYS and keep RP_ENV=prod
python -m retailpulse.cli export-static --out site --site-url https://your-domain.com --base-path ""   # static site
python -m retailpulse.cli mcp                               # MCP server on stdio (IDE / assistant clients)
python -m retailpulse.cli models                            # optional: which hosted LLMs your keys can reach
```

Optional: `pip install -r requirements-extra.txt` then `streamlit run dashboard/app.py`; train the CNN with
`python -m retailpulse.cli train-cnn` after installing CPU PyTorch.

### Docker

```bash
cp .env.example .env     # set RP_API_KEYS
docker compose up --build
```

### API

```bash
KEY=rp_...   # from make-key
curl -H "Authorization: Bearer $KEY" localhost:8000/v1/kpis
curl -H "Authorization: Bearer $KEY" "localhost:8000/v1/top?dimension=city&metric=profit&n=3"
curl -H "Authorization: Bearer $KEY" -H "content-type: application/json" \
     -d '{"question":"top 3 categories by revenue"}' localhost:8000/v1/agent
```

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness (public) |
| GET | `/v1/kpis`, `/monthly`, `/top`, `/forecast`, `/segments`, `/cohort`, `/anomalies`, `/basket`, `/named/{name}` | analytics (viewer) |
| GET | `/v1/monitoring`, `/v1/models` | drift report, model registry (viewer) |
| GET | `/v1/churn/top`, `/v1/customers/{key}` | customer risk and 360 (analyst; no PII) |
| POST | `/v1/sql`, `/v1/agent`, `/v1/agent/stream` | guarded SQL, agent, SSE agent stream (analyst) |
| POST | `/v1/ask`, `/v1/classify` | RAG with citations; image -> top-3 (viewer) |
| GET | `/v1/audit/verify`, `/v1/audit/tail`, `/metrics` | audit chain, Prometheus (admin) |
| GET | `/openapi.json` | generated OpenAPI 3.1 |

### MCP (use RetailPulse from an AI assistant or IDE)

```json
{ "mcpServers": { "retailpulse": { "command": "python", "args": ["-m", "retailpulse.cli", "mcp"], "cwd": "/path/to/RetailPulse" } } }
```
Tools: `kpis`, `top_n`, `forecast`, `churn_risk`, `search_docs`, `run_sql`, `list_models`. All read-only, schema-validated,
audited, and `run_sql` goes through the same SQL guard. Verified at protocol level and over real stdio; not yet tried
with a specific commercial client.

## Security in one paragraph

Every SQL path (agent, API, dashboard) goes through one guard: single read-only `SELECT/WITH`, read-only
connection, SQLite authorizer allow-listing tables and functions, PII columns read as NULL, time limit and
row cap. Outputs are PII-masked. API keys are stored only as hashes; requests are rate-limited and size-capped;
production refuses to start without keys; every action lands in a tamper-evident hash-chained log.
Details and known gaps: [SECURITY.md](SECURITY.md).

## Docs

- [Deploy on Cloudflare Pages](docs/DEPLOY_CLOUDFLARE.md) | [Changelog](CHANGELOG.md) | [Contributing](CONTRIBUTING.md)
- [Architecture decisions](docs/ARCHITECTURE.md) | [Limitations](docs/LIMITATIONS.md) | [Security](SECURITY.md)
- [Learning guide: skills, exercises, interview prep](docs/LEARNING_GUIDE.md)
- [Power BI guide](docs/POWERBI_GUIDE.md) | [Resume + credentials](docs/RESUME_AND_CERTIFICATES.md)
- [Push to GitHub from your phone (Termux)](docs/TERMUX_GITHUB_GUIDE.md)

## Layout

```
retailpulse/   package (see table)     sql/        15 named queries
web/           SPA + PWA + samples     dashboard/  optional Streamlit app
tests/         142 tests + ASGI client docs/       guides
tools/         social-card + favicon generator
.github/       CI, Pages, Dependabot   .devcontainer/  Codespaces
```

License: MIT
