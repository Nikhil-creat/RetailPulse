# Limitations and honest caveats

Read this before you put numbers on a resume or in an interview.

## Data
- Everything is synthetic. Patterns were planted by the generator, so "finding" them proves the pipeline works,
  not that the method would work on messy real data.
- The generator makes churn partly random; the churn model's ceiling is therefore low (AUC about 0.70).

## Forecasting
- Daily revenue is heavy-tailed (basket values vary a lot). Daily WAPE is about 24%; weekly about 20%.
- The model **under-forecasts by about 18%** on the holdout. Likely cause: growth plus flash-sale spikes the lag features can't anticipate. A production fix would add promo calendars as features.
- Prediction bands are empirical (from backtest errors), not guaranteed coverage.
- One holdout window only. Rolling-origin cross-validation would be a stronger evaluation.

## Churn
- Labels are "no order in the next 90 days". That definition changes the results; it is a business choice.
- Only customers active in the previous 180 days are scored.

## RAG and agent
- Retrieval is TF-IDF with a small stemmer, not embeddings. It is fast and explainable, but weaker on paraphrases. The 18-question eval was written by the same person who wrote the documents, so hit@3 = 1.0 is optimistic.
- The knowledge base is built from the project's own outputs; it cannot answer questions about anything else (it abstains instead).
- The default agent planner is rule-based. It handles the patterns it was written for; the optional LLM planner broadens that but was **not exercised in tests** (no API key in the build environment, only its validator is tested).
- Without `ANTHROPIC_API_KEY` answers are extractive (stitched from retrieved sentences), so they read less fluently.

## Vision
- The classifier is trained on synthetic icons. 98% accuracy shows the pipeline works; it says nothing about real product photos.
- The PyTorch CNN is included and tested only when `torch` is installed; the build environment had no PyTorch, so the shipped metrics come from the NumPy MLP fallback.

## Web app and demo
- The UI was verified with a headless Chromium (page loads, no console/CSP errors, mobile overflow check, hover tooltips, table toggle, agent streaming, SQL attack chips, vision samples, theme toggle) on desktop and a 390 px phone. It was **not** tested on real iOS/Android browsers, Safari or Firefox, and no formal screen-reader pass (NVDA/VoiceOver) was done; accessibility is by construction (semantic HTML, labels, focus rings, reduced motion), not audited.
- The PWA service worker was not exercised in tests (headless runs block it). Test installability once on your phone.
- The static demo replays only the example questions, the example SQL and the sample image tiles. Everything else needs the live backend.
- Anomaly table in the UI shows the strongest 12 flagged days; the pipeline flags 24.

## SEO and deployment
- **No LocalBusiness structured data, on purpose.** RetailPulse is a software portfolio project; it has no storefront, address or opening hours, and inventing them would be false structured data that search engines can penalise. The page declares a WebApplication, WebPage/BreadcrumbList and its author (name and public profile links only). If you run a real local business, add that markup for that business, not for this project.
- A custom domain needs a domain you own; none is configured. Until you set `SITE_URL`, canonical tags point at the GitHub Pages address.
- `robots.txt` is only honoured by crawlers at the root of a host. On the GitHub Pages project address (`/RetailPulse/`) the file exists but crawlers will not read it; Cloudflare or a custom domain fixes that.
- Structured data is written per page at build time. After in-app navigation the old page's JSON-LD is removed rather than left wrong, which is fine for crawlers (they fetch each URL fresh) but means it is absent during a single-page session.
- Lighthouse, a formal accessibility audit and Search Console were **not** run here. What was checked: unique titles/descriptions, one `<h1>` per page, alt text, canonicals matching the sitemap, valid JSON-LD, working internal links, zero console errors/warnings in a headless browser on all ten pages at two URL depths, and no source maps. Rankings and "Core Web Vitals" scores were not measured.
- "Bundle size" is already small (about 100 KB of JavaScript in 13 files, loaded per page, no bundler, no source maps); there was nothing large to reduce. A test fails if it grows past 120 KB.
- The Cloudflare and GitHub Pages workflows have never run; the Cloudflare guide has not been followed on a real account.
- The earlier v3.0.0/v3.1.0 commits on GitHub added a `src/retailpulse/` tree whose "CNN" was a hand-weighted formula over three numbers and whose "hybrid RAG" lacked abstention. They were not carried over under those names; the real classifier is `retailpulse/vision/` and the real retriever is `retailpulse/rag.py`.

## Engineering
- SQLite is great for a portfolio project and single-node use; it is not a multi-writer production warehouse.
- The Streamlit dashboard, Dockerfile and compose file were **not executed** in the authoring environment (Streamlit not installable; no Docker daemon). They were syntax-checked, and everything they call is covered by tests. Run them once yourself and fix anything environment-specific.
- The API uses Starlette (the framework underneath FastAPI) because FastAPI was not installable where this was built. Porting to FastAPI is mostly decorator changes; you would gain automatic OpenAPI docs.
- The CI and Pages workflows have not run yet; they will on your first push. The Pages job rebuilds the full dataset (seed 42), so demo numbers match the README.
- Role keys, rate limiting and the audit ledger are per-process and file-based; they suit one container, not a scaled-out deployment.

- The scenario planner is an assumption-driven what-if model (constant elasticity, no competitor or mix effects). The executive brief is rule-based with fixed thresholds in `retailpulse/brief.py`; it is not a causal analysis.
