#!/bin/bash
# SLURM job script: topic filter + near-duplicate removal on the full ingested corpus.
#
# Reads all JSONL files from data/raw/articles/ and writes
# data/processed/articles.parquet. embed_rcc.sh depends on this output.
#
# NOTE: Run filter-pre-embed (python run_pipeline.py filter-pre-embed) BEFORE
# this job if any archived journalism sources (AP News, MarketWatch, Reuters)
# are present in data/raw/articles/ from the prior Phase 2 ingestion run.
# filter-pre-embed writes corpus_for_embedding.jsonl excluding those sources.
#
# Resource spec:
#   Account:   pi-dachxiu
#   Partition: caslake
#   CPUs:      4
#   RAM:       16 GB
#   Time:      1 h
#
# Full pipeline submission block (ADR-010; run from Midway3 login node):
#   INGEST=$(sbatch --parsable scripts/rcc/ingest_institutional_rcc.sh)
#   FILTER=$(sbatch --parsable --dependency=afterok:$INGEST \
#                scripts/rcc/filter_rcc.sh)
#   EMBED_PRIMARY=$(sbatch --parsable \
#                    --dependency=afterok:$FILTER \
#                    --export=ROLE=primary scripts/rcc/embed_rcc.sh)
#   EMBED_COMPARATOR=$(sbatch --parsable \
#                    --dependency=afterok:$FILTER \
#                    --export=ROLE=comparator scripts/rcc/embed_rcc.sh)
#   sbatch --dependency=afterok:$EMBED_PRIMARY scripts/rcc/cluster_rcc.sh
#
# All data output in /scratch/midway3/ehgarver/ — never in PI project folder.

#SBATCH --job-name=mnd-filter
#SBATCH --account=pi-dachxiu
#SBATCH --partition=caslake
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=logs/filter_rcc_%j.log
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=ehgarver@uchicago.edu

set -euo pipefail

REPO_ROOT="/scratch/midway3/ehgarver/macro-narrative-dynamics"
cd "$REPO_ROOT"

mkdir -p logs data/processed

module load python/anaconda-2023.09
source /software/python-anaconda-2023.09-el8-x86_64/etc/profile.d/conda.sh
conda activate mnd

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
