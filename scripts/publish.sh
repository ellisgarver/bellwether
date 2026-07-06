#!/usr/bin/env bash
# Publish the site from the latest RCC artifacts: pull, resolve any new display
# names (cache-incremental; needs Ollama running locally for misses), build with
# the GitHub Pages paths, and deploy to the gh-pages branch.
#
#   bash scripts/publish.sh                # full: pull data + name + build + deploy
#   bash scripts/publish.sh --site-only    # copy/style edits: build + deploy only
#
# Overridable via env: RCC (ssh target), REMOTE (artifacts dir on RCC),
# SITE / BASE (Pages URL parts).
set -euo pipefail

RCC="${RCC:-ehgarver@midway3.rcc.uchicago.edu}"
REMOTE="${REMOTE:-/scratch/midway3/ehgarver/macro-narrative-dynamics/data/processed/dashboard/}"
SITE="${SITE:-https://ellisgarver.github.io}"
BASE="${BASE:-/bellwether}"
SITE_ONLY=0
[[ "${1:-}" == "--site-only" ]] && SITE_ONLY=1

cd "$(dirname "$0")/.."

if [[ "$SITE_ONLY" == "0" ]]; then
  echo "==> pulling artifacts from RCC"
  rsync -av --delete --exclude='.*' "$RCC:$REMOTE" data/processed/dashboard/

  echo "==> resolving display names (cache hits are free; misses need Ollama)"
  python scripts/run_pipeline.py name

  if ! git diff --quiet -- data/naming_cache; then
    echo "==> committing new narrative names"
    git add data/naming_cache
    git commit -m "data(naming): cache names for the $(date +%Y-%m-%d) refresh"
    git push
  fi
else
  echo "==> --site-only: skipping data pull and naming; deploying current files"
fi

echo "==> building the site"
cd web
SITE="$SITE" BASE="$BASE" npm run build
touch dist/.nojekyll

echo "==> deploying to gh-pages"
npx --yes gh-pages -d dist --dotfiles -m "deploy: $(date +%Y-%m-%d)"

# leave dist as a root-path build so a local preview isn't stuck with the
# deployed /bellwether prefix
echo "==> rebuilding dist for local preview"
npm run build > /dev/null

echo "==> done: $SITE$BASE/"
