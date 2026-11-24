# Changelog

## 2.0.0
- Web app: 9-page SPA (overview, customers, forecast, assistant, explorer, vision, trust & MLOps, API, about), dark mode, installable PWA, keyboard and screen-reader support, CSP-safe (no inline script/style).
- Static demo mode (GitHub Pages) that replays real pre-computed outputs.
- Roles (viewer < analyst < admin), request IDs, JSON access logs, Prometheus `/metrics`, generated OpenAPI 3.1, SSE streaming agent.
- SQL guard: SQLite authorizer allow-list, PII columns returned as NULL, CTE-shadowing and `sqlite_*` blocked.
- MLOps: PSI drift monitoring and a model registry with promotion gates.
- Analytics: cohorts, anomalies, market-basket lift, customer 360.
- `export-static` CLI command; Pages workflow; devcontainer; Dependabot.

## 1.0.0
- Star-schema warehouse, forecasting, churn, RAG, tool-using agent, vision classifier, secured API, Docker, CI.
