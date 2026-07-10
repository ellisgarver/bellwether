#!/bin/bash
# One-time (idempotent) persistence setup on RCC (ADR-063).
#
# Points the repo's data/ dir at the backed-up, non-purge-eligible /home store,
# so every pipeline read/write — Python (data_root defaults to the repo) AND the
# RCC scripts' repo-relative `data/...` verification paths — lands on /home,
# with zero changes to the pipeline scripts. Code, HF cache, and Ollama stay on
# scratch (regenerable). /project is over quota; /home holds the ~3 GB corpus +
# base model. See memory: weekly-cron-end-state.
#
#   bash scripts/rcc/link_data_home.sh
#
# Safe to re-run: if data/ is already the symlink it just reports and exits.

set -euo pipefail

REPO_ROOT="/scratch/midway3/ehgarver/macro-narrative-dynamics"
HOME_DATA="/home/ehgarver/bellwether-data"

cd "$REPO_ROOT"
mkdir -p "$HOME_DATA"

if [[ -L data ]]; then
    echo "data/ already links to: $(readlink data)"
elif [[ -d data ]]; then
    # The scratch data/ has already been copied to /home; move it aside (not
    # delete) before replacing with the symlink.
    bak="data.scratch.$(date -u +%Y%m%dT%H%M%SZ).bak"
    echo "Moving existing scratch data/ -> $bak (safe to delete once /home is verified)"
    mv data "$bak"
    ln -s "$HOME_DATA" data
    echo "Linked data/ -> $HOME_DATA"
else
    ln -s "$HOME_DATA" data
    echo "Linked data/ -> $HOME_DATA"
fi

# Silence git-status noise from the tracked .gitkeep placeholders now behind the
# symlink (the RCC checkout never commits to main, but keeps `git pull` clean).
git update-index --skip-worktree \
    data/raw/.gitkeep data/processed/.gitkeep data/snapshots/.gitkeep 2>/dev/null || true

echo
echo "Verify — the corpus should be visible through the symlink:"
ls -la data/raw/articles/ 2>/dev/null | grep -E 'cbo|\.jsonl' | head
echo
echo "Then: python scripts/run_pipeline.py corpus-composition"
