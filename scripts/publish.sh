#!/usr/bin/env bash
# Publish the site from the latest RCC artifacts: pull artifacts + the RCC-
# generated name cache (ADR-073: the mnd-name job does the bulk naming on RCC),
# run the local name pass as a cache-hit no-op / gap-filler (misses need a local
# Ollama), build with the GitHub Pages paths, and deploy to gh-pages.
#
#   bash scripts/publish.sh                # full: pull data + name + build + deploy
#   bash scripts/publish.sh --site-only    # copy/style edits: build + deploy only
#
# Overridable via env: RCC (ssh target), REMOTE (artifacts dir on RCC),
# REMOTE_REPO (repo root on RCC), SITE / BASE (Pages URL parts).
set -euo pipefail

RCC="${RCC:-ehgarver@midway3.rcc.uchicago.edu}"
REMOTE_REPO="${REMOTE_REPO:-/scratch/midway3/ehgarver/macro-narrative-dynamics}"
# ADR-063 persistence: data (dashboard artifacts + name cache) lives on backed-up
# /home, not scratch (purge-eligible). Code/repo stays on scratch.
REMOTE_DATA="${REMOTE_DATA:-/home/ehgarver/bellwether-data}"
REMOTE="${REMOTE:-$REMOTE_DATA/processed/dashboard/}"
SITE="${SITE:-https://ellisgarver.github.io}"
BASE="${BASE:-/bellwether}"
SITE_ONLY=0
[[ "${1:-}" == "--site-only" ]] && SITE_ONLY=1

cd "$(dirname "$0")/.."

if [[ "$SITE_ONLY" == "0" ]]; then
  echo "==> pulling artifacts + name cache from RCC"
  rsync -av --delete --exclude='.*' "$RCC:$REMOTE" data/processed/dashboard/
  # No --delete: the cache is accumulative by design (ADR-056/070).
  rsync -av "$RCC:$REMOTE_DATA/naming_cache/" data/naming_cache/

  echo "==> resolving display names (no-op when the RCC name job covered everything)"
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
