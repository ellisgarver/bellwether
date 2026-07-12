#!/usr/bin/env bash
# Manual site deploy. The PRODUCTION path is the RCC weekly chain pushing the
# `site-data` branch + the GitHub Action building and deploying to gh-pages
# (.github/workflows/deploy.yml); this script is the manual fallback.
#
#   bash scripts/publish.sh --site-only    # copy/style edits: build + deploy only
#
# Full mode (pull RCC artifacts + name + commit naming_cache to main) is
# RETIRED: committing data/naming_cache to main can make the RCC checkout —
# which reaches those paths through the data/ -> /home symlink — refuse to
# pull. It remains available behind FORCE_FULL=1 for emergencies only.
#
# Overridable via env: RCC (ssh target), REMOTE (artifacts dir on RCC),
# REMOTE_REPO (repo root on RCC), SITE / BASE (Pages URL parts).
set -euo pipefail

RCC="${RCC:-ehgarver@midway3.rcc.uchicago.edu}"
REMOTE_REPO="${REMOTE_REPO:-/scratch/midway3/ehgarver/macro-narrative-dynamics}"
REMOTE="${REMOTE:-$REMOTE_REPO/data/processed/dashboard/}"
SITE="${SITE:-https://ellisgarver.github.io}"
BASE="${BASE:-/bellwether}"
SITE_ONLY=0
[[ "${1:-}" == "--site-only" ]] && SITE_ONLY=1

cd "$(dirname "$0")/.."

if [[ "$SITE_ONLY" == "0" && "${FORCE_FULL:-0}" != "1" ]]; then
  echo "publish.sh full mode is retired — the weekly RCC chain + GitHub Action deploy the site." >&2
  echo "Use 'bash scripts/publish.sh --site-only' for a manual build+deploy, or FORCE_FULL=1 to override." >&2
  exit 1
fi

if [[ "$SITE_ONLY" == "0" ]]; then
  echo "==> pulling artifacts + name cache from RCC"
  rsync -av --delete --exclude='.*' "$RCC:$REMOTE" data/processed/dashboard/
  # No --delete: the cache is accumulative by design (ADR-056/070).
  rsync -av "$RCC:$REMOTE_REPO/data/naming_cache/" data/naming_cache/

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
