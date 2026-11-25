# Deploy RetailPulse to Cloudflare Pages (free), with your own domain

What gets deployed: the **static site** (`export-static`): nine real pages with their own URLs, a custom 404, sitemap,
robots.txt, llms.txt, social images, security headers (`_headers`) and the pre-computed demo data. The live API
(login, free-form SQL, uploads) is a separate Python service and is **not** part of this; the demo says so on screen.

> Not tested against a real Cloudflare account (none was available while building this). The pieces are tested:
> the exported files, the HTML, headers, 404 behaviour and URL handling were verified with a local server that
> behaves like Cloudflare Pages (serves `404.html` on a miss, directory index pages) and with a headless browser,
> both at the domain root and under a sub-path. If a step below differs from what you see, trust Cloudflare's screen.

## 0. What you need
- A free Cloudflare account (https://dash.cloudflare.com/sign-up).
- Your GitHub repo `Nikhil-creat/RetailPulse` (already pushed).
- Optional: a domain you own. **I do not know your domain and cannot register one for you.** Without it you get a free
  `https://<project>.pages.dev` address, which is perfectly fine for a portfolio.

## 1. Choose how to deploy (pick ONE)

### Option A: Cloudflare builds from GitHub (easiest, all in a phone browser)
1. Cloudflare dashboard -> **Workers & Pages** -> **Create** -> **Pages** -> **Connect to Git** -> authorise GitHub -> pick `RetailPulse`.
2. Production branch: `main`. Framework preset: **None**.
3. **Build command** (one line):
   ```
   pip install -r requirements.txt && python -m retailpulse.cli run-all && python -m retailpulse.cli export-static --out site --site-url "$SITE_URL" --base-path ""
   ```
4. **Build output directory:** `site`   |   Root directory: leave empty.
5. **Environment variables** (Production): `PYTHON_VERSION` = `3.12`, `SITE_URL` = the address people will visit,
   e.g. `https://retailpulse.pages.dev` (use the real one Cloudflare shows after the first deploy, then update it and redeploy)
   or `https://your-domain.com`.
6. Save and Deploy. The build takes a few minutes (it generates the dataset and trains the models, seed 42).

### Option B: GitHub Actions uploads to Cloudflare
Uses `.github/workflows/cloudflare.yml` (runs the tests first). Create the project once, then set secrets/variable from Termux:
1. Cloudflare -> My Profile -> API Tokens -> Create Token -> template **Edit Cloudflare Workers** or a custom token with
   *Account -> Cloudflare Pages -> Edit*. Copy it once. Your Account ID is on the Workers & Pages overview page.
2. In Termux (it asks you to paste the value; do **not** put it in a file or in chat):
   ```bash
   cd ~/RetailPulse
   gh secret set CLOUDFLARE_API_TOKEN
   gh secret set CLOUDFLARE_ACCOUNT_ID
   gh variable set SITE_URL --body "https://retailpulse.pages.dev"
   gh workflow run cloudflare.yml && gh run watch
   ```
3. If the project name `retailpulse` is taken on Cloudflare, change `--project-name=retailpulse` in the workflow (and `name` in `wrangler.toml`).

If you use Option A, you can ignore `cloudflare.yml` (it only builds and validates when the secrets are missing).

## 2. Custom domain
1. Pages project -> **Custom domains** -> **Set up a domain** -> enter e.g. `retail.your-domain.com`.
2. If the domain's DNS is on Cloudflare, it creates the record for you. If not, add a `CNAME` at your DNS host pointing to
   `<project>.pages.dev`. (An apex/root domain such as `your-domain.com` needs its nameservers on Cloudflare.)
3. Wait for the certificate (usually minutes). HTTPS is automatic.
4. **Tell the site its real address**, otherwise canonical tags, the sitemap and social images point to the old URL:
   - Option A: change the `SITE_URL` environment variable -> Retry deployment.
   - Option B: `gh variable set SITE_URL --body "https://retail.your-domain.com"` then `gh workflow run cloudflare.yml`.
5. If you also keep the GitHub Pages copy, set the same `SITE_URL` repo variable: that copy then declares your domain as
   canonical, so search engines do not treat the two as duplicates.

## 3. Check it (copy-paste)
```bash
U=https://retail.your-domain.com
curl -sI $U/ | head -5                                   # 200 + security headers
curl -sI $U/definitely-missing/ | head -1                # HTTP/2 404 (custom 404 page body)
curl -s  $U/sitemap.xml | head -5                        # your domain in every <loc>
curl -s  $U/robots.txt
curl -s  $U/llms.txt | head -5
curl -sI $U/demand-forecast/ | grep -i "content-security-policy"
curl -s  $U/demand-forecast/ | grep -E "<title>|rel=\"canonical\"|<h1"
```
Then: Google Search Console -> add the property -> submit `sitemap.xml`; test share cards by pasting a page URL into
WhatsApp/LinkedIn/X; check structured data at https://search.google.com/test/rich-results.
Ranking depends on many things outside this repo and takes time; nothing here guarantees a position.

## 4. Troubleshooting
| Symptom | Fix |
|---|---|
| Unstyled page or missing scripts | You uploaded a build made for a sub-path (GitHub Pages). Cloudflare needs `--base-path ""`. |
| Canonical / sitemap show the wrong domain | `SITE_URL` was not set when it built. Set it, redeploy. |
| Build fails installing packages | Set `PYTHON_VERSION=3.12`; read the build log; the CI run on GitHub uses the same commands. |
| Old files after deploy | Pages -> Caching -> Purge cache. HTML is revalidated; icons/images cache for a day. |
| Want analytics | Cloudflare Web Analytics injects a script that this site's Content-Security-Policy blocks on purpose. Either skip it, or add `https://static.cloudflareinsights.com` to `script-src` and `https://cloudflareinsights.com` to `connect-src` in `retailpulse/seo.py`. |
| Want the live API online | Run the Docker image on a host you control and put it behind HTTPS. See README -> Docker. The static site does not need it. |
