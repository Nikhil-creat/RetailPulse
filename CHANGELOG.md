# Changelog

## 3.2.0

- Live mode for the static site: `--api-url`/`RP_API_URL` (meta `rp-api`, CSP `connect-src` allow-list), opt-in CORS via `RP_CORS_ORIGINS` (exact origins, no wildcard), "Demo data · sign in for live" state with no 401 console errors, Hugging Face Space deploy (`deploy/huggingface`, `tools/deploy_hf_space.sh`, `docs/DEPLOY_LIVE_BACKEND.md`).
- Real page URLs (`/demand-forecast/`, `/ai-assistant/`, ...) with complete HTML per page: unique title, meta description, canonical, Open Graph/Twitter tags, one `<h1>`, breadcrumbs, JSON-LD (WebSite, WebApplication, Person, WebPage, BreadcrumbList), related-page links and alt text. Custom `404.html`. Old `#/page` links still work.
- Crawler files: `sitemap.xml`, `robots.txt`, `llms.txt`, multi-size `favicon.ico`, nine 1200x630 social cards (`tools/make_social_images.py`).
- Cloudflare Pages deployment: `_headers` (CSP and friends), `cloudflare.yml`, `wrangler.jsonc` (Workers static assets, `not_found_handling: 404-page`), `docs/DEPLOY_CLOUDFLARE.md`; `--site-url`, `--base-path`, `--cname` options for `export-static`.
- Static site no longer probes a non-existent backend (removed a console error on every page load).
- Read-only MCP server (`cli mcp`, 7 tools) and optional Groq/Gemini model router (`cli models`), both stdlib-only and tested.
- Fixes: restored the CI workflow, threat-model `SECURITY.md` and `.env.example` that v3.0.0 overwrote; removed the shadow `src/retailpulse/` package that made CI fail with `No module named 'retailpulse.ai'`; Dockerfile now copies `web/`.
- 142 tests (was 113).

## 3.0.0 / 3.1.0 (intermediate pushes)
- Added `src/retailpulse/{ai,mcp}` prototypes and replaced CI/SECURITY/.env. Superseded by 3.2.0, which keeps the useful ideas (model discovery, MCP tool surface) inside the real package and drops the rest.

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
