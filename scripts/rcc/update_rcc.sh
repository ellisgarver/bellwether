#!/bin/bash
# SLURM job — weekly autonomous refresh (ADR-063/066/070). One self-contained
# job that runs the FULL pipeline delta and pushes artifacts so the deploy
# GitHub Action rebuilds the site. Designed to run unattended under scrontab.
#
# Persistence: the repo's data/ dir is a symlink to the backed-up /home store
# (see scripts/rcc/link_data_home.sh) — so all repo-relative data/ paths below
# resolve to /home, not purge-eligible scratch. Code + HF cache stay on scratch.
#
# What it does, in order:
#   1. update --sources all --merge : per-source delta ingest -> filter ->
#      incremental embed onto the base model -> merge-week (identity-stable
#      re-cluster; existing ids/names preserved, new topics appended, gated) ->
#      analyze (re-bake artifacts + Media Cloud press layer).
#   2. name : title newly-appended clusters via a user-space Ollama (CPU — a
#      weekly delta is a handful of new clusters; cache-incremental, resumable).
#   3. Force-push dashboard + naming_cache to the orphan `site-data` branch
#      (single snapshot, no history growth), which fires deploy.yml to rebuild.
#
# Scheduling: scrontab is DISABLED on Midway3 (verified 2026-07-10), so this
# job is a SELF-RESUBMITTING chain — the first thing a run does is queue next
# week's run with `sbatch --begin=now+7days`, guarded so only one successor is
# ever pending, and done before any work so a failure later in the run never
# breaks the cadence. The first sbatch IS the enrollment; there is no separate
# installation step.
#
#   Validate once, no successor:  MND_NO_RESUBMIT=1 sbatch scripts/rcc/update_rcc.sh
#   Enroll the weekly chain:      sbatch scripts/rcc/update_rcc.sh
#     (anchor to a weekday/hour:  sbatch --begin=2026-07-13T06:00 scripts/rcc/update_rcc.sh)
#   Inspect the chain:            squeue -u $USER -n mnd-update
#   Stop the chain:               scancel -n mnd-update
#
# Silence is a signal: the job mails on END and FAIL, so a Monday with no
# email means the pending successor vanished (e.g. cancelled in a maintenance
# window) — re-enroll with a fresh sbatch.
#
# One-time prerequisites: base model exists (a full rebuild has run cluster),
# `data` symlinked to /home (link_data_home.sh), git push creds for origin on
# RCC, and .env at the repo root with GOVINFO_API_KEY (CEA) + Media Cloud token.

#SBATCH --job-name=mnd-update
#SBATCH --account=pi-dachxiu
#SBATCH --partition=caslake
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=18:00:00
#SBATCH --output=logs/update_rcc_%j.log
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=ehgarver@uchicago.edu

set -euo pipefail

REPO_ROOT="/scratch/midway3/ehgarver/macro-narrative-dynamics"
cd "$REPO_ROOT"
mkdir -p logs

# Perpetuate the weekly chain FIRST — before any work — so a failure later in
# this run cannot break the cadence (scrontab is disabled on Midway3; the job
# re-enrolls itself instead). The guard keeps exactly one successor pending.
if [[ "${MND_NO_RESUBMIT:-0}" != "1" ]]; then
    if squeue -h -u "$USER" -n mnd-update -t PENDING 2>/dev/null | grep -q .; then
        echo "Weekly successor already pending — not resubmitting."
    else
        NEXT_ID=$(sbatch --parsable --begin=now+7days "$REPO_ROOT/scripts/rcc/update_rcc.sh")
        echo "Scheduled next weekly run: job $NEXT_ID (begins in 7 days)"
    fi
fi

# Guard: data/ must be the /home symlink, or this would write to scratch.
if [[ ! -L data ]]; then
    echo "ERROR: $REPO_ROOT/data is not the /home symlink — run scripts/rcc/link_data_home.sh first." >&2
    exit 1
fi

MND_CONDA_ENV="/home/ehgarver/.conda/envs/mnd"
export PATH="${MND_CONDA_ENV}/bin:$PATH"
export PYTHONNOUSERSITE=1
PYTHON_USED="$(which python)"
if [[ "$PYTHON_USED" != "${MND_CONDA_ENV}/bin/python" ]]; then
    echo "ERROR: expected ${MND_CONDA_ENV}/bin/python but got $PYTHON_USED" >&2
    exit 1
fi
echo "Python: $PYTHON_USED"

export USE_TF=0
export KERAS_BACKEND=torch
export MND_EMBEDDING_DEVICE=cpu
# Keep the ~16 GB Qwen3-8B HF cache on scratch, not the 30 GB home quota.
export HF_HOME="/scratch/midway3/ehgarver/huggingface"
export HF_HUB_OFFLINE=0
export OMP_NUM_THREADS=2
export MKL_NUM_THREADS=2

# API keys (GOVINFO_API_KEY for CEA, Media Cloud token, etc.) live in the repo
# .env (scratch). The /home backup copy survives a scratch purge — keep it in
# sync when keys change: cp .env /home/ehgarver/bellwether-data/.env.backup
set -a
if [[ -f .env ]]; then
    source .env
elif [[ -f /home/ehgarver/bellwether-data/.env.backup ]]; then
    echo "WARNING: repo .env missing (scratch purge?) — using /home backup"
    source /home/ehgarver/bellwether-data/.env.backup
fi
set +a

echo "===== mnd-update (weekly refresh) ====="
echo "Job ID:   ${SLURM_JOB_ID:-manual}"
echo "Node:     $(hostname)"
echo "Data:     $(readlink -f data)"
echo "Started:  $(date)"
echo "======================================="

# 1) Full delta: all sources + identity-stable merge + re-bake artifacts.
#    MND_ANALYZE_ONLY=1 skips ingest+merge and re-bakes artifacts only (e.g.
#    to land front-end-baked features without pulling new articles).
if [[ "${MND_ANALYZE_ONLY:-0}" == "1" ]]; then
    python scripts/run_pipeline.py update --skip-ingest --no-merge
else
    python scripts/run_pipeline.py update --sources "${MND_SOURCES:-all}" --merge
fi

# 2) Title newly-appended clusters (user-space Ollama on CPU; cache-incremental).
OLLAMA_ROOT="/scratch/midway3/ehgarver/ollama"
export OLLAMA_MODELS="$OLLAMA_ROOT/models"
export OLLAMA_HOST="127.0.0.1:11434"
mkdir -p "$OLLAMA_ROOT" "$OLLAMA_MODELS"
if [[ ! -x "$OLLAMA_ROOT/bin/ollama" ]]; then
    echo "Installing Ollama to $OLLAMA_ROOT"
    curl -fsSL https://ollama.com/download/ollama-linux-amd64.tgz | tar -xz -C "$OLLAMA_ROOT"
fi
export PATH="$OLLAMA_ROOT/bin:$PATH"
ollama serve >> "logs/ollama_serve_${SLURM_JOB_ID:-manual}.log" 2>&1 &
OLLAMA_PID=$!
trap 'kill "$OLLAMA_PID" 2>/dev/null || true' EXIT
for _ in $(seq 1 60); do
    curl -sf "http://${OLLAMA_HOST}/api/tags" > /dev/null && break
    sleep 2
done
curl -sf "http://${OLLAMA_HOST}/api/tags" > /dev/null || {
    echo "ERROR: Ollama did not come up (see logs/ollama_serve_${SLURM_JOB_ID:-manual}.log)" >&2
    exit 1
}
# Pull the model the `name` command actually requests (config display.naming.model
# = qwen2.5:7b, ADR-067/naming v4); must match name_rcc.sh or new clusters fail to
# title. MND_NAMING_MODEL overrides both in lockstep.
ollama pull "${MND_NAMING_MODEL:-qwen2.5:7b}"
python scripts/run_pipeline.py name

# 3) Publish the site artifacts to the orphan `site-data` branch — a single
#    force-pushed snapshot, so main's history stays code-only and the repo never
#    bloats (the dashboard re-bakes whole each week, ~380 MB). The deploy Action
#    builds from main (code) + site-data (artifacts). Built in a throwaway
#    worktree so the deployed code checkout is never disturbed. Artifacts are
#    read through the data/ symlink (-> /home). The workflow file is copied
#    INTO the snapshot because push-triggered Actions only run when the
#    workflow exists on the pushed ref — an orphan branch without it would
#    trigger no deploy at all.
ART_BRANCH="site-data"
git worktree prune
# The local branch survives from last week's run; delete it so --orphan can
# recreate it fresh (the remote copy is force-pushed anyway, nothing is lost).
git branch -D "$ART_BRANCH" 2>/dev/null || true
WT="$(mktemp -d)/wt"
git worktree add --detach "$WT" HEAD
(
    cd "$WT"
    git checkout --orphan "$ART_BRANCH"
    # Empty the inherited index + worktree. NOT `git reset` — HEAD is unborn
    # on a fresh orphan branch and reset dies resolving it.
    git rm -rfq . 2>/dev/null || true
    git clean -qfdx
    mkdir -p data/processed/dashboard data/naming_cache .github/workflows
    rsync -a --delete --exclude='.fit_cache' "$REPO_ROOT/data/processed/dashboard/" data/processed/dashboard/
    rsync -a --delete "$REPO_ROOT/data/naming_cache/" data/naming_cache/
    cp "$REPO_ROOT/.github/workflows/deploy.yml" .github/workflows/deploy.yml
    git add -f data/processed/dashboard data/naming_cache .github/workflows
    git -c user.name='mnd-bot' -c user.email='mnd-bot@rcc.local' \
        commit -q -m "site-data snapshot $(date +%F)"
    git push -f origin "$ART_BRANCH"   # fail-loud (job emails FAIL) if creds/branch wrong
)
git worktree remove --force "$WT"
rmdir "$(dirname "$WT")" 2>/dev/null || true
echo "Pushed site-data snapshot — deploy workflow will rebuild the site."

echo "===== Complete: $(date) ====="
