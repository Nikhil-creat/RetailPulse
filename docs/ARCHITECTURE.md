# Architecture decisions

| Decision | Why | Trade-off |
|---|---|---|
| SQLite star schema (not a flat CSV) | Teaches dimensional modelling; one place for business logic; SQL is the interface the agent and API share | Single writer, no concurrency |
| `vw_sales` view joins everything | Analyses stay short and consistent; "net revenue excludes returned orders" is defined once | Hides the joins from beginners (read the view first) |
| Data-quality gates fail the pipeline | A silent bad load is worse than a loud failure | Strict synthetic data only |
| Named SQL file loaded by `-- name:` | SQL stays SQL (editable in any editor), tested as a unit | Tiny custom parser |
| Forecast target on `log1p`, recursive multi-step | Revenue is heavy-tailed; honest multi-step evaluation (predictions feed later lags) | Errors accumulate; under-forecast bias |
| Backtest vs seasonal-naive and moving average | A model is only "good" relative to a simple baseline | One window |
| Temporal validation for churn | Random splits leak the future and inflate AUC | Fewer training rows |
| Features computed "as of" a cutoff, with a leakage test | The classic bug in churn/forecast projects | Slightly more code |
| TF-IDF RAG with abstention and citations | Deterministic, no API needed, explainable, testable | Weaker semantic matching than embeddings |
| LLM is optional and sandboxed by validation | The system must work offline and must not trust model output | Less fluent default answers |
| Agent can only call allow-listed tools with schemas | Limits blast radius of prompt injection | Less flexible than free-form tool use |
| One `SafeSQL` guard for all entry points | Security logic in one place, tested once | A single point to get right |
| Authorizer + read-only connection + text checks | Defence in depth: each layer catches what another misses (e.g. comma-joins) | Some valid exotic SQL is rejected |
| Hash-chained audit log | Cheap tamper evidence without a database | Tail truncation undetected |
| NumPy MLP fallback with `.npz` weights | Works without PyTorch; loading weights cannot execute code | Lower capacity than a CNN |
| Service layer between UI/API/agent and data | One tested facade; UIs stay thin | One more layer to read |
| Route registry (`route()` decorator) | One definition gives routing, role check, rate limit and the generated OpenAPI 3.1 doc, so docs cannot drift | Small custom framework layer on Starlette |
| Vanilla ES-module SPA, no build step, no CDN | Zero supply-chain surface, strict CSP works, runs from any static host | More hand-written DOM code than React |
| Live/demo adapter in `web/js/api.js` | The same UI serves the real backend and GitHub Pages | Demo only replays pre-computed examples |
| Static export through the real service | Demo numbers are genuine outputs, not mock data | Needs a pipeline run first |
| SSE for the agent stream | Steps show as each tool finishes; plain HTTP, proxy-friendly | One-way only |
| PSI drift + JSON model registry with gates | Shows MLOps practice without a platform dependency | File-based; not multi-user |

## Data flow

`data_gen` -> CSVs -> `warehouse.build_warehouse` (schema, load, quality gates) -> `analytics`, `forecasting`, `churn`, `vision`
-> `insights` turns computed numbers into knowledge-base documents -> `rag.KnowledgeBase` -> `service.RetailPulseService`
-> `api` (which also serves `web/`) / `dashboard` / `cli` / `agent`. `export_static` calls the same service to write the Pages demo. `pipeline.run_all` orchestrates it and writes `artifacts/` (CSVs, `summary.json`,
charts, `RESULTS.md`, Power BI CSVs).

## Extending it

- Swap TF-IDF for embeddings behind `KnowledgeBase.search` (keep the abstain threshold and citation format).
- Add a promo calendar table and use it as a forecast feature (the main fix for the under-forecast bias).
- Replace SQLite with Postgres: keep `SafeSQL`'s ideas (read-only role, statement timeout, allow-listed views).
- Add per-resource scopes, key expiry and rotation to `ApiKeyStore` (roles viewer/analyst/admin already exist).
