# Push RetailPulse to GitHub from your phone (Termux)

Your GitHub: `Nikhil-creat`. Target repo: `https://github.com/Nikhil-creat/RetailPulse`.

## START HERE if you already pushed once (update an existing clone to v3.2.0)

Your GitHub repo already has v2.0.0 plus a v3.0.0 commit (tags `v3.0.0`, `v3.1.0`) that added `src/retailpulse/`.
That folder shadows the real `retailpulse/` package, which is why the CI badge says **failing**. v3.2.0 removes it and keeps
the useful ideas inside the real package. Run these in Termux (they keep your `.git` history and replace everything else):

```bash
cd ~/RetailPulse && test -d .git && echo "in the repo: OK"          # must print OK before continuing
git pull --rebase origin main
rm -rf ~/rp_new && mkdir ~/rp_new && unzip -q ~/storage/downloads/RetailPulse.zip -d ~/rp_new
find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +      # wipes the working tree except .git
cp -a ~/rp_new/RetailPulse/. .
git status --short | head -40                                       # expect: src/ deleted, many modified/added
git ls-files -o -m --exclude-standard | grep -E '(^|/)\.env$|\.db$|\.zip$' || echo "OK: no secrets/DB/zip"
git add -A
git commit -m "feat: v3.2.0 real page URLs and SEO, MCP server, Cloudflare deploy; remove shadow src/ package"
git tag -a v3.2.0 -m "RetailPulse 3.2.0"
git push origin main --follow-tags
```
If the push complains about workflow permission: `gh auth refresh -s workflow` then push again.
Then watch CI: `gh run list --limit 3` (green is expected; if red, send me the failing step's log).

Email privacy: your commits currently carry your real Gmail address (you set it in `git config`), and it is public in the
history. To use GitHub's private address from now on: GitHub -> Settings -> Emails -> copy the `ID+Nikhil-creat@users.noreply.github.com`
address, then `git config --global user.email "<that address>"`. Old commits keep the old address unless you rewrite history
(not needed unless you mind). The token you typed first (the one rejected for `read:org`) is still a live token if it was
created: delete it at GitHub -> Settings -> Developer settings -> Personal access tokens.

Deploy on Cloudflare after that: see **docs/DEPLOY_CLOUDFLARE.md**. The short version for the phone:
```bash
gh variable set SITE_URL --body "https://retailpulse.pages.dev"   # replace with your real address later
```
then Cloudflare dashboard -> Workers & Pages -> Create -> Pages -> Connect to Git -> RetailPulse (build command and output
folder are in that guide).

---

You do **not** need to run the project on your phone to publish it. Pushing is just git. GitHub Actions will run the tests for you.

## 0. Prerequisites
- Install **Termux from F-Droid** (the Play Store build is outdated and `pkg` often breaks).
- A GitHub account with 2FA enabled.

## 1. Set up Termux
```bash
pkg update -y && pkg upgrade -y
pkg install -y git openssh unzip gh
termux-setup-storage          # tap "Allow" so Termux can read Downloads
```

## 2. Get the project onto the phone
Download `RetailPulse.zip` to your phone's Downloads folder, then:
```bash
cd ~
cp ~/storage/downloads/RetailPulse.zip .
unzip RetailPulse.zip
cd RetailPulse
ls
```

## 3. Tell git who you are
Use GitHub's no-reply address so your real email is not published in commits
(GitHub -> Settings -> Emails -> "Keep my email addresses private" shows it, format `ID+username@users.noreply.github.com`).
```bash
git config --global user.name "Nikhil Chary Sriramoju"
git config --global user.email "YOUR_ID+Nikhil-creat@users.noreply.github.com"
git config --global init.defaultBranch main
```

## 4. Authenticate (pick ONE)

### Option A (easiest): GitHub CLI device login
```bash
gh auth login
# GitHub.com -> HTTPS -> "Login with a web browser"
# It prints a one-time code; open the URL on your phone browser, enter the code, approve.
gh auth setup-git
gh auth status
```

### Option B: SSH key
```bash
ssh-keygen -t ed25519 -C "nikhil-termux"        # set a passphrase
cat ~/.ssh/id_ed25519.pub                        # long-press to copy
```
GitHub -> Settings -> SSH and GPG keys -> New SSH key -> paste. Then:
```bash
ssh -T git@github.com                            # expect: "Hi Nikhil-creat!"
```
Use the `git@github.com:Nikhil-creat/RetailPulse.git` remote URL in step 6.

### Option C: Personal access token (fallback)
GitHub -> Settings -> Developer settings -> Fine-grained tokens -> only the `RetailPulse` repo, **Contents: Read and write**, short expiry.
Use it as the password when git asks. **Never paste a token into a chat, a file in the repo, or a screenshot.**

## 5. Safety check BEFORE the first commit
```bash
git init
git add .
git status --short | head -40
git ls-files | grep -E '(^|/)\.env$|\.db$|audit\.jsonl|\.pt$' || echo "OK: no secrets/DB files staged"
```
If a `.env` or database shows up, run `git rm --cached <file>` and check `.gitignore`.

## 6. Commit and push
```bash
git commit -m "feat: RetailPulse analytics + guarded AI platform"
```
Either create the repo from the CLI (Option A users):
```bash
gh repo create RetailPulse --public --source=. --remote=origin --push \
  --description "Retail analytics + forecasting + guarded RAG/agent/CNN over a SQL star schema"
```
or create an **empty** repo on github.com (no README/license), then:
```bash
git remote add origin https://github.com/Nikhil-creat/RetailPulse.git   # or the SSH URL
git push -u origin main
```

## 7. Release, live demo, topics
```bash
git tag -a v3.2.0 -m "RetailPulse 3.2.0"          # skip if you already tagged in the START HERE section
git push origin v3.2.0
gh release create v3.2.0 --title "RetailPulse 3.2.0" --notes-file CHANGELOG.md
```
Turn on the live demo (GitHub Pages built by `.github/workflows/pages.yml`):
```bash
gh api -X POST repos/Nikhil-creat/RetailPulse/pages -f build_type=workflow
# if it says Pages already exists:  gh api -X PUT repos/Nikhil-creat/RetailPulse/pages -f build_type=workflow
gh workflow run pages.yml          # or just push a commit
gh run watch                       # wait for green (~2-4 min)
```
Or in the browser: repo -> Settings -> Pages -> Source: **GitHub Actions**.
Your demo URL: `https://nikhil-creat.github.io/RetailPulse/`. Then add it to the repo **About -> Website**:
```bash
gh repo edit --homepage "https://nikhil-creat.github.io/RetailPulse/" \
  --add-topic data-analytics --add-topic machine-learning --add-topic rag --add-topic sql \
  --add-topic forecasting --add-topic ai-agents --add-topic docker
```
Optional: open it in **Codespaces** (repo -> Code -> Codespaces); `.devcontainer/` installs everything and builds a quick dataset.

Try the demo locally on your laptop before pushing: `python -m retailpulse.cli export-static --out site && python -m http.server -d site 8080`.

## 8. After the push
1. Open the repo -> **Actions** tab: the CI run should go green (tests, quick pipeline, evals, dependency audit, Docker build). If something fails, read the log and fix it. That is normal and a good thing to learn.
2. Repo **About** (gear icon): add topics `data-analytics`, `machine-learning`, `rag`, `sql`, `forecasting`, `fastapi`... and the description.
3. Pin the repo on your profile (Profile -> Customize your pins).
4. The README embeds charts from `artifacts/reports/*.png`; they are committed on purpose. If images don't show, check the paths.
5. Screenshots are already in `docs/assets/` and shown in the README. Add your Power BI screenshots next to them when ready.
6. The first Pages run is the first real test of that workflow. If it fails, open the run log, fix, push again.

## Everyday workflow
```bash
git status
git add -A
git commit -m "fix: describe the change"
git pull --rebase origin main
git push
```

## Troubleshooting
| Symptom | Fix |
|---|---|
| `Permission denied (publickey)` | `ssh-add ~/.ssh/id_ed25519`, confirm the key is on GitHub, re-run `ssh -T git@github.com` |
| `remote: Support for password authentication was removed` | Use `gh auth login` or a token, not your account password |
| `fatal: not a git repository` | You are not inside the `RetailPulse` folder: `cd ~/RetailPulse` |
| `rejected ... fetch first` | `git pull --rebase origin main`, then push again |
| Push is slow/fails on mobile data | Retry on Wi-Fi; the repo is small (no data/DB files) |
| Committed a secret by mistake | **Revoke/rotate it first**, then remove from history (`git filter-repo`) |

## Running the project in Termux (optional, unverified)
Termux can run Python (you can even try `python -m retailpulse.cli serve` and open `http://127.0.0.1:8000` in your phone browser if the installs work), but installing pandas/scikit-learn there can be slow or fail depending on your device and the packages available. This was **not tested** here. If you try: `pkg install python python-numpy matplotlib` and see Termux's package notes for pandas/scikit-learn. A laptop, Google Colab or GitHub Codespaces is far smoother for running everything; use the phone for pushing.
