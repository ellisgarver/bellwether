#!/bin/bash
# SLURM job script: MarketWatch corpus ingestion on UChicago RCC (Midway3).
#
# Tier 4 open journalism: MarketWatch analytical coverage via Wayback CDX
# (2010–present; consistent from 2015 onward — ADR-009).
# ~50 K article URLs for full 2010–present window; 8 parallel Wayback fetch
# workers with 0.5 s per-worker delay.
#
# Checkpoint/resume: re-submitting after a timeout resumes from the last
# checkpoint (.marketwatch_checkpoint.txt) and appends to the existing JSONL.
#
# Resource spec:
#   Account:   pi-dachxiu
#   Partition: caslake (36-hour QOS limit — max wall time for this partition)
#   CPUs:      8   (8 parallel Wayback fetch workers)
#   RAM:       16 GB
#   Time:      36 h  (caslake QOS maximum; resume via resubmit if needed)
#
# Submit after AP News completes (part of the sequential journalism chain):
#   INGEST_MW=$(sbatch --parsable --dependency=afterok:$INGEST_AP \
#                   scripts/rcc/ingest_marketwatch_rcc.sh)
#
# See ingest_apnews_rcc.sh for the full pipeline submission block.
#
# Custom date range:
#   sbatch --export=START=2010-01-01,END=2024-12-31 scripts/rcc/ingest_marketwatch_rcc.sh
#
# All data output in /scratch/midway3/ehgarver/ — never in PI project folder.

#SBATCH --job-name=mnd-ingest-mw
#SBATCH --account=pi-dachxiu
#SBATCH --partition=caslake
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=36:00:00
#SBATCH --output=logs/ingest_marketwatch_rcc_%j.log
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=ehgarver@uchicago.edu

set -euo pipefail

REPO_ROOT="/scratch/midway3/ehgarver/macro-narrative-dynamics"
cd "$REPO_ROOT"

mkdir -p logs data/raw/articles

module load python/anaconda-2023.09
source /software/python-anaconda-2023.09-el8-x86_64/etc/profile.d/conda.sh
conda activate mnd

export USE_TF=0
export KERAS_BACKEND=torch

START="${START:-2010-01-01}"
END="${END:-$(date +%Y-%m-%d)}"

echo "===== mnd-ingest-mw ====="
echo "Job ID:  $SLURM_JOB_ID"
echo "Node:    $(hostname)"
echo "Window:  $START → $END"
echo "Started: $(date)"
echo "=========================="

python scripts/run_pipeline.py ingest \
    --start "$START" \
    --end "$END" \
    --sources marketwatch

echo "===== Complete: $(date) ====="
MW_JSONL="data/raw/articles/marketwatch_${START}_${END}.jsonl"
if [[ -f "$MW_JSONL" ]]; then
    COUNT=$(wc -l < "$MW_JSONL")
    SIZE=$(du -sh "$MW_JSONL" | cut -f1)
    echo "Output: $MW_JSONL ($COUNT articles, $SIZE)"
else
    echo "ERROR: expected output not found at $MW_JSONL" >&2
    exit 1
fi
