#!/bin/bash
# SLURM job script: pre-embedding filter (ADR-010/012 archived-source exclusion).
#
# Reads raw JSONL from data/raw/articles/ and writes the canonical
# data/processed/corpus_for_embedding.jsonl that excludes archived journalism
# sources (AP News, MarketWatch, Reuters per ADR-010) and dropped Tier-2
# sources (arXiv, separate Jackson Hole ingestor per ADR-012). The downstream
# filter stage reads this file preferentially.
#
# Chains BETWEEN ingest and filter:
#   INGEST → filter-pre-embed → filter → embed → cluster
#
# Pre-fix bug: the prior pipeline ran ingest → filter directly. filter.py
# logged a WARNING and fell back to inline exclusion against the raw_articles
# directory, but the canonical artifact was never produced. Adding this stage
# enforces ADR-010/012 cleanly at the pipeline level.
#
# Resource spec:
#   Account:   pi-dachxiu
#   Partition: caslake
#   CPUs:      2
#   RAM:       8 GB
#   Time:      30 min  (typical: < 2 min for current corpus volumes)

#SBATCH --job-name=mnd-filter-pre-embed
#SBATCH --account=pi-dachxiu
#SBATCH --partition=caslake
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=logs/filter_pre_embed_rcc_%j.log
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

echo "===== mnd-filter-pre-embed ====="
echo "Job ID:  $SLURM_JOB_ID"
echo "Node:    $(hostname)"
echo "Started: $(date)"
echo "Raw JSONL files: $(ls data/raw/articles/*.jsonl 2>/dev/null | wc -l)"
echo "================================"

python scripts/run_pipeline.py filter-pre-embed

echo "===== Complete: $(date) ====="
OUT="data/processed/corpus_for_embedding.jsonl"
if [[ -f "$OUT" ]]; then
    ls -lh "$OUT"
    echo "Articles kept: $(wc -l < $OUT)"
else
    echo "ERROR: expected output not found at $OUT" >&2
    exit 1
fi
