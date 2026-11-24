# Security

## Threat model (what this project defends against, and how)

| Threat | Control | Verified by |
|---|---|---|
| SQL injection / destructive SQL via agent, API or dashboard | Single `SELECT/WITH` only; forbidden keywords; read-only connection (`mode=ro`); SQLite authorizer allow-lists tables + functions | `tests/test_security.py` (DROP, DELETE, stacked statements, comments, PRAGMA, ATTACH, `sqlite_master`, CTE shadowing, unknown functions) |
| Runaway queries (DoS) | Progress-handler timeout (3 s), row cap (200), query length cap | timeout test with a recursive CTE |
| Customer PII leakage | `email`/`phone` read as NULL at the authorizer; output masking; Power BI export drops PII columns; agent refuses contact-detail requests | PII tests (SQL, RAG, agent, API) |
| Prompt injection / jailbreak | Heuristic detector refuses before any tool runs; LLM plans are validated against a tool allow-list + argument schemas; LLM answers must cite retrieved context; context is treated as data | agent + eval tests |
| Unauthorised API use | API keys stored only as SHA-256 hashes, constant-time compare; **roles** viewer < analyst < admin enforced per route (403 on a low role); prod refuses to start without keys | `tests/test_api.py`, `tests/test_v2.py` |
| Brute force / abuse | Token-bucket rate limit per IP and per key; 429 + `Retry-After` | rate-limit test |
| Oversized / malformed input | Body caps (256 KB JSON, 200 KB image), content-type checks, strict field validation, image format + dimension checks | API tests |
| Malicious model files | Weights stored as `.npz` (no pickle); PyTorch loaded with `weights_only=True` | vision tests |
| Tampered logs | Hash-chained audit log; `verify-audit` locates the first altered line | tamper test |
| Information leakage in errors | Generic 500s, no stack traces, security headers (`nosniff`, `DENY`, `no-store`) | API tests |
| XSS / script injection in the web app | Strict CSP (`script-src 'self'`, no inline script or style, `frame-ancestors 'none'`); all server data rendered via `textContent`; CSV export neutralises spreadsheet formulas | `tests/test_export.py` (no `innerHTML`/`eval`, no inline script), CSP header tests |
| Path traversal / file disclosure via static serving | GET only, extension allow-list, dotfiles and `..` blocked, JSON 404 | `tests/test_v2.py` |
| Cached sensitive data | Service worker never caches `/v1/*`, `/health`, `/metrics`; API replies are `no-store`; API key lives in `sessionStorage` only | code review |
| Untraceable requests | `X-Request-ID` on every response, JSON access logs, Prometheus metrics for auth failures and rate limiting | `tests/test_v2.py` |
| Container compromise | Non-root user, read-only root FS, all capabilities dropped, `no-new-privileges`, localhost-only port | config review (**not built or run here**) |

## Known gaps (be honest about these in interviews)

- **Injection detection is heuristic.** A determined attacker can phrase around regexes. The real protection is
  that the agent can only call allow-listed tools that cannot write or read PII, so a successful injection has little to exploit.
- **Audit chain detects edits, not truncation of the tail.** Anchor the latest hash somewhere else (e.g. a separate store) for that.
- **Rate limiter is in-memory and per process.** Use Redis or a gateway for multiple workers. Behind a reverse proxy the client IP will be the proxy's unless you configure forwarded headers.
- **No TLS in the app.** Terminate TLS at a reverse proxy.
- **Roles are coarse and static.** Three fixed roles from an env var; no per-resource scopes, expiry or rotation workflow.
- **API key in `sessionStorage`.** Safer than `localStorage`, but any XSS would expose it. The CSP and `textContent` rule reduce that risk; they do not remove it.
- **The static demo is public and read-only.** It contains only pre-computed synthetic outputs (a test checks there are no keys, databases, audit logs or e-mail addresses).
- **PII is synthetic.** The controls are real; the data is not. Review them against your legal obligations before using real customer data.
- **Dependency audit runs in CI** (`pip-audit`), but results depend on the date it runs.
- **Docker/compose, the Pages workflow and the CI workflow were never executed** in the authoring environment; they run for the first time on your machine/GitHub.

## Secrets

Never commit `.env`. API keys are shown once by `make-key`; only the hash goes in `RP_API_KEYS`.
`ANTHROPIC_API_KEY` (optional) is read from the environment only and never logged or written to disk.
If a key leaks: generate a new one, replace the hash, restart.

## Reporting

Open a private security advisory on the GitHub repository.
