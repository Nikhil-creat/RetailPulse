---
title: RetailPulse API
emoji: 📈
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Guarded retail analytics API (SafeSQL, RAG, forecasting, churn, CNN)
---

Live backend for RetailPulse: https://github.com/Nikhil-creat/RetailPulse

Secured API (hashed API keys, roles, rate limits, hash-chained audit ledger). Call `/health`, then
send `Authorization: Bearer <key>` to `/v1/*`. Interactive UI: `/` (needs a key for live data).
