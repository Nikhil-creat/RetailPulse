# Make it fully live: Cloudflare website + Hugging Face API

The Cloudflare site is static (fast, indexable). The *live* parts (SafeSQL console, RAG, guarded agent, CNN upload,
audit ledger) need Python, so they run as a Docker container on a free **Hugging Face Space**. The website detects the
API, shows **"Demo data · sign in for live"** until you enter an API key, then switches every page to **Live backend**.
If the API is asleep or down the site falls back to the pre-exported demo data, never a broken page.

## 1. Create the Space (browser, 1 minute)
huggingface.co -> New Space -> name `retailpulse` -> SDK **Docker** -> **Blank** -> **Public** -> Create.

## 2. Make your API key (Termux)
```bash
cd ~/RetailPulse && python -m retailpulse.cli make-key --name nikhil --role admin
```
It prints the key once (save it in a password manager) and a line `nikhil:<hash>:admin`. Only the hash goes to the server.

## 3. Space settings -> Variables and secrets
| Kind | Name | Value |
|---|---|---|
| Secret | `RP_API_KEYS` | `nikhil:<hash>:admin` (the line from step 2) |
| Variable | `RP_CORS_ORIGINS` | `https://retailpulse.23641a05k6.workers.dev` (your website origin; exact, no slash, no `*`) |
| Secret (optional) | `GROQ_API_KEY` / `GEMINI_API_KEY` | enables hosted LLM routing; offline mode works without them |

## 4. Push the code to the Space (Termux)
```bash
cd ~/RetailPulse && tools/deploy_hf_space.sh <your-hf-username> retailpulse
```
Git asks for a username and password: use your HF username and a **Write** token (HF -> Settings -> Access Tokens), typed at the prompt.
The build takes a few minutes (it trains the models inside the image). Check `https://<user>-retailpulse.hf.space/health`: it must return JSON with `"status":"ok"`.

## 5. Tell the website where the API is
Cloudflare -> Worker `retailpulse` -> Settings -> Builds -> Build variables: add `RP_API_URL` = `https://<user>-retailpulse.hf.space` (origin only).
(GitHub Actions route: `gh variable set API_URL --body "https://<user>-retailpulse.hf.space"`.) Retry/push to rebuild. The build log JSON shows `"api_url"`.

## 6. Use it
Open the website, press **API key**, paste the key from step 2 (stored only in that tab's sessionStorage). The badge turns **Live backend**.

## Resume tip: a public recruiter key
Anyone with a key can use the API, so for a public demo create a **separate** `viewer`-role key, rate-limited, and put it in your README
as "recruiter demo key". Never share the admin key. Rotate by changing `RP_API_KEYS`.

## Honest limits
- Free Spaces sleep after inactivity; the first request wakes them (about a minute). The site waits 12 s, then shows demo data. Refresh after a minute.
- Data is synthetic (seed 42) and rebuilt on each Space rebuild; the audit ledger on the free tier is not persistent across rebuilds.
- Single container, SQLite: a portfolio-grade deployment, not a multi-tenant production service (see `docs/LIMITATIONS.md`).
