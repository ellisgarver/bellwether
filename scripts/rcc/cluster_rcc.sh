#!/bin/bash
# SLURM job script: full-corpus clustering on UChicago RCC (Midway3).
#
# BERTopic/HDBSCAN is CPU-bound after UMAP reduction. Requests a high-memory
# CPU node. UMAP on 500k+ embeddings at 1024 dimensions can peak at ~60 GB RAM.
# Adjust --mem if the corpus is larger or smaller than estimated.
#
# Submit from the repo root on Midway3 AFTER embed_rcc.sh completes:
#   sbatch scripts/rcc/cluster_rcc.sh
#
# Or chain them as a dependency:
#   EMBED_JID=$(sbatch --parsable scripts/rcc/embed_rcc.sh)
#   sbatch --dependency=afterok:$EMBED_JID scripts/rcc/cluster_rcc.sh
#
# Output: data/processed/clusters.parquet + data/processed/topic_info.parquet

#SBATCH --job-name=mnd-cluster
#SBATCH --account=pi-ehgarver          # your own allocation; adjust if under PI account
#SBATCH --partition=bigmem
#SBATCH --cpus-per-task=16
#SBATCH --mem=96G
#SBATCH --time=06:00:00                # 6 h ceiling; UMAP+HDBSCAN ~2-4 h estimated
#SBATCH --output=logs/cluster_rcc_%j.log
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=ehgarver@uchicago.edu

set -euo pipefail

REPO_ROOT="$HOME/Projects/macro-narrative-dynamics"
cd "$REPO_ROOT"

module load python/anaconda-2023.09
conda activate mnd

export USE_TF=0
export KERAS_BACKEND=torch
export MND_EMBEDDING_DEVICE=cpu   # clustering is CPU-only; no GPU needed

echo "Job $SLURM_JOB_ID started: $(date)"
echo "Running on $(hostname), CPUs: $SLURM_CPUS_PER_TASK, RAM: $SLURM_MEM_PER_NODE MB"

python scripts/run_pipeline.py cluster

echo "Clustering complete: $(date)"
echo "Output: $REPO_ROOT/data/processed/clusters.parquet"
ls -lh data/processed/clusters.parquet data/processed/topic_info.parquet
