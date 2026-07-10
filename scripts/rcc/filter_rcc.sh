#!/bin/bash
# SLURM job script: date-range filter + near-duplicate removal on the ingested corpus.
#
# Per MND_PROJECT_SPEC rev3 Stage 2: NO topic filter — Layer 1A sources are
# macro-relevant by construction (ADR-012). Two operations only:
#   1. Date range filter: keep documents in [2010-01-01, today]
#   2. MinHash near-duplicate removal within rolling 48h windows
#
# Input precedence (auto-detected in run_pipeline.py filter_cmd):
#   1. data/processed/corpus_for_embedding.jsonl  (canonical, written by
#      filter_pre_embed_rcc.sh — ADR-010/012 archived-source exclusion)
#   2. data/raw/articles/*.jsonl                  (fallback, with inline exclusion)
# Output: data/processed/articles.parquet — embed_rcc.sh depends on this.
#
# Resource spec:
#   Account:   pi-dachxiu
#   Partition: caslake
#   CPUs:      4
#   RAM:       16 GB
#   Time:      1 h
#
# Canonical chain (use scripts/rcc/submit_parallel_ingest.sh):
#   ingest → filter-pre-embed → filter → embed (primary) → cluster
#
# All data output in /scratch/midway3/ehgarver/ — never in PI project folder.

#SBATCH --job-name=mnd-filter
#SBATCH --account=pi-dachxiu
#SBATCH --partition=caslake
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=04:00:00
#SBATCH --output=logs/filter_rcc_%j.log
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=ehgarver@uchicago.edu

set -euo pipefail

REPO_ROOT="/scratch/midway3/ehgarver/macro-narrative-dynamics"
# ADR-063 persistence: data on backed-up /home (never scratch/purge); HF cache stays on scratch
export MND_DATA_ROOT="/home/ehgarver/bellwether-data"
cd "$REPO_ROOT"

mkdir -p logs data/processed

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

echo "===== mnd-filter ====="
echo "Job ID:  $SLURM_JOB_ID"
echo "Node:    $(hostname)"
echo "Started: $(date)"
echo "Raw JSONL files: $(ls data/raw/articles/*.jsonl 2>/dev/null | wc -l)"
echo "======================"

python scripts/run_pipeline.py filter

echo "===== Complete: $(date) ====="
if [[ -f "data/processed/articles.parquet" ]]; then
    ls -lh data/processed/articles.parquet
    python -c "import pandas as pd; df=pd.read_parquet('data/processed/articles.parquet'); print(f'Filtered articles: {len(df)}')"
else
    echo "ERROR: expected output not found at data/processed/articles.parquet" >&2
    exit 1
fi
