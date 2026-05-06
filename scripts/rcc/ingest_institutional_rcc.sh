#!/bin/bash
# SLURM job script: institutional corpus ingestion on UChicago RCC (Midway3).
#
# Covers Tiers 1–3 (ADR-008):
#   Tier 1 — Federal Reserve (FOMC, speeches, Beige Book), IMF, BIS, CEA,
#             CBO, Treasury/OFR
#   Tier 2 — NBER (JEL E/F/G abstracts + intros), SSRN (abstracts),
#             VoxEU full posts
#   Tier 3 — Brookings, PIIE
#
# All via direct fetch / institutional RSS — sequential, network I/O bound.
# No GPU or large RAM needed.
#
# Checkpoint/resume: if the job times out, re-submitting resumes automatically.
# Completed sub-sources are recorded in .institutional_checkpoint.json and
# skipped on restart.
#
# Resource spec:
#   Account:   pi-dachxiu
#   Partition: caslake
#   CPUs:      4  (sequential RSS/HTTP fetches; extra cores unused)
#   RAM:       8 GB
#   Time:      2 h
#
# Submit independently:
#   sbatch scripts/rcc/ingest_institutional_rcc.sh
#
# Submit as part of full pipeline (institutional → journalism → embed → cluster):
#   INGEST_INST=$(sbatch --parsable scripts/rcc/ingest_institutional_rcc.sh)
#   INGEST_JOUR=$(sbatch --parsable --dependency=afterok:$INGEST_INST \
#                    scripts/rcc/ingest_journalism_rcc.sh)
#   EMBED_PRIMARY=$(sbatch --parsable \
#                    --dependency=afterok:$INGEST_JOUR \
#                    --export=ROLE=primary scripts/rcc/embed_rcc.sh)
#   EMBED_COMPARATOR=$(sbatch --parsable \
#                    --dependency=afterok:$INGEST_JOUR \
#                    --export=ROLE=comparator scripts/rcc/embed_rcc.sh)
#   sbatch --dependency=afterok:$EMBED_PRIMARY scripts/rcc/cluster_rcc.sh
#   echo "Ingest institutional: $INGEST_INST"
#   echo "Ingest journalism:    $INGEST_JOUR"
#   echo "Embed primary:        $EMBED_PRIMARY"
#   echo "Embed comparator:     $EMBED_COMPARATOR"
#
# Custom date range:
#   sbatch --export=START=2010-01-01,END=2024-12-31 \
#       scripts/rcc/ingest_institutional_rcc.sh
#
# All data output in /scratch/midway3/ehgarver/ — never in PI project folder.

#SBATCH --job-name=mnd-ingest-inst
#SBATCH --account=pi-dachxiu
#SBATCH --partition=caslake
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=02:00:00
#SBATCH --output=logs/ingest_institutional_rcc_%j.log
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=ehgarver@uchicago.edu

set -euo pipefail

REPO_ROOT="/scratch/midway3/ehgarver/macro-narrative-dynamics"
cd "$REPO_ROOT"

mkdir -p logs data/raw/articles

module load python/anaconda-2023.09
conda activate mnd

export USE_TF=0
export KERAS_BACKEND=torch

START="${START:-2010-01-01}"
END="${END:-$(date +%Y-%m-%d)}"

echo "===== mnd-ingest-inst ====="
echo "Job ID:  $SLURM_JOB_ID"
echo "Node:    $(hostname)"
echo "Window:  $START → $END"
echo "Started: $(date)"
echo "==========================="

python scripts/run_pipeline.py ingest \
    --start "$START" \
    --end "$END" \
    --sources institutional

echo "===== Complete: $(date) ====="
INST_JSONL="data/raw/articles/institutional_${START}_${END}.jsonl"
if [[ -f "$INST_JSONL" ]]; then
    COUNT=$(wc -l < "$INST_JSONL")
    SIZE=$(du -sh "$INST_JSONL" | cut -f1)
    echo "Output: $INST_JSONL ($COUNT articles, $SIZE)"
else
    echo "ERROR: expected output not found at $INST_JSONL" >&2
    exit 1
fi
