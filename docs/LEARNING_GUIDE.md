# Learning guide: build skills from this project

Do not just run the project. For each module: **read the code, do the exercise, answer the checkpoint out loud.**
If you can explain a module without looking, you can defend it in an interview. Suggested pace: one module per 1-2 days.

Setup once: `pip install -r requirements-dev.txt && python -m retailpulse.cli run-all --quick && python -m pytest -q`

---
## Module 1: SQL and dimensional modelling
**Learn:** facts vs dimensions, surrogate keys, foreign keys, views, CTEs, window functions (`SUM() OVER`, `RANK`, `LAG`).
**Read:** `retailpulse/warehouse.py` (SCHEMA, `vw_sales`), `sql/analysis_queries.sql`.
**Do:**
1. Run each query: `python -c "from retailpulse import warehouse as w; c=w.connect('data/warehouse.db'); print(w.run_query(c,'mom_growth'))"`.
2. Write 3 new queries: revenue by `age_band`; top product per category (use `ROW_NUMBER() OVER (PARTITION BY ...)`); 3-month moving average revenue.
3. Add them to the SQL file with `-- name:` headers. The test `test_all_15_named_queries_run` should then fail (it expects 15). Update it and say why.
**Checkpoint:** Why is `is_returned` on the order table but `revenue` on the item table? What is the grain of `fact_order_items`?

## Module 2: Data quality and testing
**Learn:** constraints, referential integrity, reconciliation tests, why pipelines should fail loudly.
**Read:** `validate_warehouse`, `tests/test_core.py::test_revenue_reconciles_between_sql_and_pandas`.
**Do:** break the data on purpose (set one `unit_price` negative in a raw CSV, rebuild) and watch the gate stop the pipeline. Add a new quality check (e.g. return date before order date).
**Checkpoint:** Why recompute revenue in pandas inside a test instead of trusting the SQL?

## Module 3: Customer analytics (RFM, cohorts, basket)
**Learn:** quintile scoring, segmentation rules, cohort retention, support/confidence/lift.
**Read:** `retailpulse/analytics.py`.
**Do:** change the segment rules; add a "Big Spenders" segment using M; compute lift by city. Look at `artifacts/reports/cohort_retention.png` and write 3 sentences of business interpretation.
**Checkpoint:** What does lift = 1.4 mean? Why can retention for recent cohorts look low?

## Module 4: Forecasting
**Learn:** lag/rolling features, leakage, recursive forecasting, baselines, WAPE vs MAPE, bias.
**Read:** `retailpulse/forecasting.py`, `test_forecast_features_have_no_leakage`.
**Do:** (a) add a feature (e.g. lag_364) and see if weekly WAPE improves; (b) add a promo flag using `meta["flash_sale_days"]`, and see whether the -18% bias shrinks; (c) try `holdout=30` and `holdout=90`.
**Checkpoint:** Why do we compare against seasonal-naive? Why is bias a problem even with a decent WAPE? What would make the leakage test fail?

## Module 5: Churn modelling
**Learn:** label definition, temporal split, ROC AUC vs average precision, lift, permutation importance.
**Read:** `retailpulse/churn.py`.
**Do:** change `HORIZON_DAYS` to 60 and 120; explain why the metrics move. Add a feature; use permutation importance to see if it helps.
**Checkpoint:** Why not use a random train/test split? Why report a recency-only baseline?

## Module 6: RAG
**Learn:** chunking, TF-IDF, retrieval metrics (hit@k, MRR), grounding, abstention.
**Read:** `retailpulse/rag.py`, `retailpulse/evals.py`.
**Do:** add 10 harder paraphrased questions to `RAG_CASES` (don't reuse words from the documents) and see hit@3 fall. Then improve retrieval (synonyms, or embeddings behind `search`). Tune `min_score` and observe the trade-off between abstaining and answering wrongly.
**Checkpoint:** Why is an eval you wrote yourself optimistic? When should the system say "I don't know"?

## Module 7: Agents and guardrails
**Learn:** planner -> tools -> observe loop, allow-lists, step budgets, prompt injection, defence in depth.
**Read:** `retailpulse/agent.py`, `retailpulse/security.py`, `tests/test_ai.py`, `tests/test_security.py`.
**Do:** add a new tool (e.g. `anomalies`) end to end: service method, planner rule, renderer, test. Then try to break the guard: write 5 SQL attacks of your own as test cases. Do they all fail safely? Fix any that don't.
**Checkpoint:** Why is "the agent can only call allow-listed tools" stronger than "the prompt tells it not to"? Which layer stops `SELECT * FROM a, sqlite_schema`?

## Module 8: Computer vision (CNN)
**Learn:** convolution, pooling, batch norm, train/test split, overfitting, safe model serialisation.
**Read:** `retailpulse/vision/`.
**Do:** `pip install torch` (CPU), `python -m retailpulse.cli train-cnn --epochs 10`, compare with the MLP. Add rotation/blur to `synth_images.draw_tile` and watch accuracy drop; add augmentation to recover it.
**Checkpoint:** Why is 98% on synthetic icons not evidence the model works on real photos? Why avoid pickle for model files?

## Module 9: API, Docker, CI
**Learn:** auth, rate limiting, input validation, containers, least privilege, CI.
**Read:** `retailpulse/api.py`, `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml`.
**Do:** run the server locally; call every endpoint with curl; trigger 401, 413, 422, 429 on purpose. Push to GitHub and make CI go green. Break a test and watch CI go red.
**Checkpoint:** Why store only the hash of API keys? What does `read_only: true` + `cap_drop: ALL` buy you?

---
## 4-week plan
| Week | Modules | Outcome |
|---|---|---|
| 1 | 1-3 | You can explain the warehouse and customer analytics and wrote 3 new queries |
| 2 | 4-5 | You improved or honestly explained the forecast bias and churn limits |
| 3 | 6-8 | You extended RAG evals, added an agent tool, trained the CNN |
| 4 | 9 + polish | Repo public, CI green, Power BI dashboard, README screenshots |

## Interview questions you should now be able to answer
1. Walk me through the architecture in 90 seconds.
2. Why a star schema? What is the grain of your fact table?
3. How did you prevent leakage in the forecast and churn models?
4. Your forecast under-forecasts. Why, and how would you fix it?
5. How do you know the model beats a naive approach?
6. How does your agent stay safe against prompt injection? What can it still not defend?
7. Why TF-IDF instead of embeddings? When would you switch?
8. How would you evaluate RAG beyond hit@k?
9. What would you change to run this with real customer data?
10. What are the weaknesses of your own evals?
