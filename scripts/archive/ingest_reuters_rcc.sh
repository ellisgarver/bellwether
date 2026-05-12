#!/bin/bash
# SLURM job script: Reuters corpus ingestion on UChicago RCC (Midway3).
#
# Tier 4 open journalism: Reuters wire coverage via Wayback CDX (2010–2022)
# and RSS feeds (2023–present). Reuters was fully open access until ~2023;
# Wayback CDX coverage is strong for 2010–2022.
#
# CDX patterns: reuters.com/article/, reuters.com/markets/, reuters.com/business/
# ~8 parallel Wayback fetch workers with 0.5 s per-worker delay.
#
# Checkpoint/resume: re-submitting after a timeout resumes from the last
# checkpoint and appends to the existing JSONL.
#
# Resource spec:
#   Account:   pi-dachxiu
#   Partition: caslake (36-hour QOS limit)
#   CPUs:      8   (8 parallel Wayback fetch workers)
#   RAM:       16 GB
#   Time:      36 h  (caslake QOS maximum)
#
# Full pipeline submission block (run from Midway3 login node):
#   INGEST_INST=$(sbatch --parsable scripts/rcc/ingest_institutional_rcc.sh)
#   INGEST_AP=$(sbatch --parsable --dependency=afterok:$INGEST_INST \
#                   scripts/rcc/ingest_apnews_rcc.sh)
#   INGEST_RT=$(sbatch --parsable --dependency=afterok:$INGEST_AP \
#                   scripts/rcc/ingest_reuters_rcc.sh)
#   FILTER=$(sbatch --parsable \
#                --dependency=afterok:$INGEST_RT \
#                scripts/rcc/filter_rcc.sh)
#   EMBED_PRIMARY=$(sbatch --parsable \
#                    --dependency=afterok:$FILTER \
#                    --export=ROLE=primary scripts/rcc/embed_rcc.sh)
#   EMBED_COMPARATOR=$(sbatch --parsable \
#                    --dependency=afterok:$FILTER \
#                    --export=ROLE=comparator scripts/rcc/embed_rcc.sh)
#   sbatch --dependency=afterok:$EMBED_PRIMARY scripts/rcc/cluster_rcc.sh
#   echo "Ingest institutional: $INGEST_INST"
#   echo "Ingest AP News:       $INGEST_AP"
#   echo "Ingest Reuters:       $INGEST_RT"
#   echo "Filter:               $FILTER"
#   echo "Embed primary:        $EMBED_PRIMARY"
#   echo "Embed comparator:     $EMBED_COMPARATOR"
#
# If Reuters times out, resubmit (checkpoint preserved):
#   sbatch --export=START=${START},END=${END} scripts/rcc/ingest_reuters_rcc.sh
#
# Custom date range:
#   sbatch --export=START=2010-01-01,END=2024-12-31 scripts/rcc/ingest_reuters_rcc.sh
#
# All data output in /scratch/midway3/ehgarver/ — never in PI project folder.

#SBATCH --job-name=mnd-ingest-rt
#SBATCH --account=pi-dachxiu
#SBATCH --partition=caslake
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=36:00:00
#SBATCH --output=logs/ingest_reuters_rcc_%j.log
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

echo "===== mnd-ingest-rt ====="
echo "Job ID:  $SLURM_JOB_ID"
echo "Node:    $(hostname)"
echo "Window:  $START → $END"
echo "Started: $(date)"
echo "=========================="

python scripts/run_pipeline.py ingest \
    --start "$START" \
    --end "$END" \
    --sources reuters

echo "===== Complete: $(date) ====="
RT_JSONL="data/raw/articles/reuters_${START}_${END}.jsonl"
if [[ -f "$RT_JSONL" ]]; then
    COUNT=$(wc -l < "$RT_JSONL")
    SIZE=$(du -sh "$RT_JSONL" | cut -f1)
    echo "Output: $RT_JSONL ($COUNT articles, $SIZE)"
else
    echo "ERROR: expected output not found at $RT_JSONL" >&2
    exit 1
fi
