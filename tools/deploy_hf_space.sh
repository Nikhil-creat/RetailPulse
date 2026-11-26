#!/usr/bin/env bash
# Publish the live API to a Hugging Face Space (Docker). Usage: tools/deploy_hf_space.sh <hf-username> [space-name]
# Create the Space first in the browser (New Space -> SDK: Docker -> Blank -> Public). When git asks for a password,
# paste a Hugging Face WRITE token (typed at the prompt, never into chat).
set -euo pipefail
USER_NAME="${1:?usage: $0 <hf-username> [space-name]}"
SPACE="${2:-retailpulse}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cp -r "$ROOT/retailpulse" "$ROOT/sql" "$ROOT/web" "$ROOT/requirements.txt" "$TMP/"
cp "$ROOT/deploy/huggingface/Dockerfile" "$ROOT/deploy/huggingface/README.md" "$TMP/"
find "$TMP" -name __pycache__ -type d -prune -exec rm -rf {} +
cd "$TMP"
git init -q -b main
git add -A
git -c user.name="RetailPulse deploy" -c user.email="deploy@users.noreply.huggingface.co" commit -q -m "Deploy RetailPulse API"
git push -f "https://huggingface.co/spaces/${USER_NAME}/${SPACE}" main
echo "Pushed. Build logs: https://huggingface.co/spaces/${USER_NAME}/${SPACE}"
