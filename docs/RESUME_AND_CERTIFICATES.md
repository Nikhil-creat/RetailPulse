# Resume, LinkedIn and credentials: what you can truthfully say

## Rules
1. Say **synthetic** data. Interviewers respect honesty and will ask.
2. Only claim what you can demo and explain. Do the exercises in `LEARNING_GUIDE.md` first.
3. Numbers come from `artifacts/reports/RESULTS.md`; re-run and copy them if they change.
4. Do not claim production use, real customers, business impact or a certification you did not earn.

## Resume entry (Projects)
**RetailPulse: Retail Analytics + Guarded AI Platform** | Python, SQL, scikit-learn, Starlette, JavaScript (ES modules), Docker, GitHub Actions/Pages | github.com/Nikhil-creat/RetailPulse (live demo link)
- Designed a SQLite star-schema warehouse (6 tables + analytics view) with automated data-quality gates and 15 analytical SQL queries (CTEs, window functions) on 50K+ synthetic orders.
- Built RFM segmentation, cohort retention and market-basket analysis; forecast daily revenue with gradient boosting, cutting weekly WAPE from 33.6% (seasonal-naive baseline) to 19.9% on a 60-day holdout, with leakage tests and a documented under-forecast bias.
- Trained a temporally validated churn model (ROC AUC 0.705 vs 0.655 recency baseline) with value-at-risk ranking.
- Implemented a grounded RAG assistant (citations, abstains when unsure) and a tool-using agent with allow-listed tools, step budget and prompt-injection refusals; evaluated on 18 retrieval and 13 agent cases.
- Secured the system: read-only SQL guard (authorizer allow-list, PII nulling, timeout), hashed API keys with viewer/analyst/admin roles, rate limiting, strict CSP, hash-chained audit log; 113 automated tests, CI via GitHub Actions, non-root read-only Docker image.
- Built a 9-page, dependency-free web app (dark mode, installable PWA, accessible charts with tooltips and table views, streaming agent over SSE) served by the API, plus a static GitHub Pages demo exported from the real pipeline.
- Added MLOps basics: PSI drift monitoring and a model registry with promotion gates, Prometheus metrics, request IDs and OpenAPI 3.1 generated from the route registry.

Short version (4 bullets) for one-page resumes: warehouse + SQL, forecast + churn, RAG + agent, security + tests/CI.

## 60-second pitch
"RetailPulse is a retail analytics platform I built on synthetic data. It has a SQL star-schema warehouse, customer segmentation, a demand forecast that beats a naive baseline by about 14 points of weekly error, and a churn model. On top of that I added a RAG assistant and an agent that can only call allow-listed, read-only tools, and I tested the security controls with attack cases. I'm upfront that the data is synthetic and that the forecast under-forecasts by about 18%; I wrote that down in the limitations and I know how I'd fix it with a promo calendar."

## LinkedIn "Featured" blurb
Retail analytics + guarded AI (RAG, agent, CNN) on a SQL star schema, with a 9-page web app and live demo. 113 tests, CI, Docker. Synthetic data; limitations documented.

## About certificates
A certificate is issued by the organisation that taught or assessed you. Nobody can "generate" one for you, and a self-made certificate would be a fake credential. These are real routes (check each provider's current terms, prices and whether a certificate is free):
| Skill in this project | Real learning + credential options |
|---|---|
| Pandas, SQL, intro ML | Kaggle Learn courses (free completion certificates) |
| Power BI / data analysis | Microsoft Learn PL-300 learning path (learning is free; the exam is paid) |
| ML fundamentals | NPTEL courses (free to learn; proctored certification exam has a fee) |
| Cloud, containers | Google Cloud Skills Boost labs and badges |
| Git/GitHub Actions | GitHub Skills (free hands-on courses) |
| Your own project | The repo, README, CI badge and a short write-up *are* your proof of work |

Tip: complete 2 or 3 credentials that match the modules you actually studied, then add them under Certifications with the issuer and date.
