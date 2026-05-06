#!/bin/bash
# SLURM job script: Tier 4 journalism corpus ingestion on UChicago RCC (Midway3).
#
# Covers Tier 4 open journalism (ADR-008, ADR-009):
#   AP News       — wire journalism via Wayback CDX (2010–present)
#   MarketWatch   — analytical journalism via Wayback CDX (2010–present;
#                   consistent coverage from 2015)
#
# Both sources use 8 parallel Wayback fetch workers (0.5s delay per worker).
# AP News: ~50 K URLs for 2010–present. MarketWatch: similar volume.
# Checkpoint/resume: re-submitting the same job after a timeout or failure will
# skip already-fetched URLs (stored in .apnews_checkpoint.txt /
# .marketwatch_checkpoint.txt) and append to the existing JSONL files.
#
# Failure isolation: both sources are always attempted even if one fails.
# The job exits non-zero if either source fails or is killed by the time limit,
# which correctly prevents the embed dependency from firing on incomplete data.
# Resubmit this job to resume from checkpoint.
#
# Resource spec:
#   Account:   pi-dachxiu
#   Partition: caslake
#   CPUs:      8  (8 parallel Wayback fetch workers)
#   RAM:       16 GB
#   Time:      48 h
#
# Typical chain (submit after ingest_institutional_rcc.sh with afterok):
#   INGEST_JOUR=$(sbatch --parsable \
#                    --dependency=afterok:$INGEST_INST \
#                    scripts/rcc/ingest_journalism_rcc.sh)
#
# See ingest_institutional_rcc.sh for the full pipeline submission block.
#
# Custom date range:
#   sbatch --export=START=2010-01-01,END=2024-12-31 \
#       scripts/rcc/ingest_journalism_rcc.sh
#
# All data output in /scratch/midway3/ehgarver/ — never in PI project folder.

#SBATCH --job-name=mnd-ingest-jour
#SBATCH --account=pi-dachxiu
#SBATCH --partition=caslake
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=48:00:00
#SBATCH --output=logs/ingest_journalism_rcc_%j.log
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=ehgarver@uchicago.edu

# No -e: both sources are always attempted even if one fails.
# -u and -o pipefail remain to catch unset variables and pipe errors.
set -uo pipefail

REPO_ROOT="/scratch/midway3/ehgarver/macro-narrative-dynamics"
cd "$REPO_ROOT"

mkdir -p logs data/raw/articles

module load python/anaconda-2023.09
conda activate mnd

export USE_TF=0
export KERAS_BACKEND=torch

START="${START:-2010-01-01}"
END="${END:-$(date +%Y-%m-%d)}"

echo "===== mnd-ingest-jour ====="
echo "Job ID:  $SLURM_JOB_ID"
echo "Node:    $(hostname)"
echo "Window:  $START → $END"
echo "Started: $(date)"
echo "==========================="

FAILURES=0

# AP News (Wayback CDX, checkpoint/resume via .apnews_checkpoint.txt)
echo "----- AP News: $(date) -----"
if python scripts/run_pipeline.py ingest \
        --start "$START" \
        --end "$END" \
        --sources apnews; then
    echo "AP News: completed successfully"
else
    echo "WARNING: apnews ingest failed or was killed — checkpoint preserved for resume on resubmission"
    FAILURES=$((FAILURES + 1))
fi

# MarketWatch (Wayback CDX, checkpoint/resume via .marketwatch_checkpoint.txt)
echo "----- MarketWatch: $(date) -----"
if python scripts/run_pipeline.py ingest \
        --start "$START" \
        --end "$END" \
        --sources marketwatch; then
    echo "MarketWatch: completed successfully"
else
    echo "WARNING: marketwatch ingest failed or was killed — checkpoint preserved for resume on resubmission"
    FAILURES=$((FAILURES + 1))
fi

echo "===== Summary: $(date) ====="
ls -lh data/raw/articles/apnews_*.jsonl data/raw/articles/marketwatch_*.jsonl 2>/dev/null || \
    echo "(no journalism JSONL files found)"

if [[ $FAILURES -gt 0 ]]; then
    echo "ERROR: $FAILURES source(s) did not complete — resubmit this job to resume from checkpoint" >&2
    echo "Re-submit command:"
    echo "  sbatch --export=START=${START},END=${END} scripts/rcc/ingest_journalism_rcc.sh"
    exit 1
fi

echo "Journalism ingest: all sources completed"
exit 0
