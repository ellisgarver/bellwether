#!/bin/bash
# SLURM job script: full-corpus historical ingestion on UChicago RCC (Midway3).
#
# Runs Wayback CDX ingestion for the full 2010-present window across all
# free/mixed-access outlets in the whitelist. This is network I/O bound —
# no GPU or large RAM needed. Runtime depends on Wayback response times;
# estimate 6-12 h for a full historical run at 200 articles/pattern.
#
# ProQuest ingestion runs separately (see docs/proquest_tdm_setup.md):
#   The JSONL export must already exist in data/raw/articles/ before the
#   filter step. Download from TDM Studio → data/raw/articles/.
#
# Submit from the repo root on Midway3:
#   sbatch scripts/rcc/ingest_rcc.sh
#
# Or with a custom date range:
#   sbatch --export=START=2010-01-01,END=2024-12-31 scripts/rcc/ingest_rcc.sh

#SBATCH --job-name=mnd-ingest
#SBATCH --account=pi-ehgarver
#SBATCH --partition=caslake
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=12:00:00
#SBATCH --output=logs/ingest_rcc_%j.log
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=ehgarver@uchicago.edu

set -euo pipefail

REPO_ROOT="$HOME/Projects/macro-narrative-dynamics"
cd "$REPO_ROOT"

module load python/anaconda-2023.09
conda activate mnd

export USE_TF=0
export KERAS_BACKEND=torch

# Use env-var date range if provided, else default to full historical window
START="${START:-2010-01-01}"
END="${END:-$(date +%Y-%m-%d)}"

echo "Job $SLURM_JOB_ID started: $(date)"
echo "Ingestion window: $START → $END"
echo "Running on $(hostname)"

# Wayback + Fed institutional sources
python scripts/run_pipeline.py ingest \
    --start "$START" \
    --end "$END" \
    --sources wayback,fed

# If ProQuest JSONL already downloaded, run paywalled ingestion too
if [ -n "${PROQUEST_DATASET_ID:-}" ]; then
    echo "PROQUEST_DATASET_ID set — running paywalled ingestion"
    python scripts/run_pipeline.py ingest \
        --start "$START" \
        --end "$END" \
        --sources paywalled
else
    echo "PROQUEST_DATASET_ID not set — skipping paywalled ingestion."
    echo "See docs/proquest_tdm_setup.md to export the TDM Studio dataset."
fi

echo "Ingestion complete: $(date)"
echo "Raw articles:"
ls -lh data/raw/articles/*.jsonl 2>/dev/null || echo "(no JSONL files found)"
