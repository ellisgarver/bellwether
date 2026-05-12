#!/bin/bash
# SLURM job script: corpus embedding on UChicago RCC (Midway3).
#
# Model: all-mpnet-base-v2 (768-dim). Single-model strategy per ADR-010.
# The two-model Qwen3/mpnet strategy from ADR-001 has been superseded.
# Look-ahead sensitivity check uses sub-period NMI comparison with this model.
#
# Input:  data/processed/articles.parquet (after filter stage)
# Output: data/processed/embeddings.npy
#
# Full pipeline submission (run from Midway3 login node):
#   INGEST=$(sbatch --parsable scripts/rcc/ingest_institutional_rcc.sh)
#   FILTER=$(sbatch --parsable --dependency=afterok:$INGEST \
#                scripts/rcc/filter_rcc.sh)
#   EMBED=$(sbatch --parsable --dependency=afterok:$FILTER \
#                scripts/rcc/embed_rcc.sh)
#   sbatch --dependency=afterok:$EMBED scripts/rcc/cluster_rcc.sh
#   echo "Ingest institutional: $INGEST"
#   echo "Filter:               $FILTER"
#   echo "Embed:                $EMBED"
#
# Resource spec (all-mpnet-base-v2 is much smaller than Qwen3):
#   Account:   pi-dachxiu
#   GPU:       1x V100 (constraint=v100; mpnet comfortably fits)
#   CPUs:      8
#   RAM:       16 GB
#   Time:      6 h  (mpnet ~2 h estimated on V100 for full corpus)
#   Cost:      ~150 SUs (allocation balance: 1,532,273 SUs)
#
# All output in /scratch/midway3/ehgarver/ — never in PI project folder.

#SBATCH --job-name=mnd-embed
#SBATCH --account=pi-dachxiu
#SBATCH --partition=gpu
#SBATCH --constraint=v100
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=06:00:00
#SBATCH --output=logs/embed_rcc_%j.log
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
export MND_EMBEDDING_DEVICE=cuda

echo "===== mnd-embed ====="
echo "Job ID:   $SLURM_JOB_ID"
echo "Model:    all-mpnet-base-v2 (ADR-010 single-model)"
echo "Output:   data/processed/embeddings.npy"
echo "Node:     $(hostname)"
echo "GPU:      $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
echo "Started:  $(date)"
echo "====================="

python scripts/run_pipeline.py embed --role primary

EXPECTED_OUTPUT="data/processed/embeddings.npy"
echo "===== Complete: $(date) ====="
if [[ -f "$EXPECTED_OUTPUT" ]]; then
    ls -lh "$EXPECTED_OUTPUT"
    python -c "import numpy as np; a=np.load('$EXPECTED_OUTPUT'); print(f'Shape: {a.shape}, dtype: {a.dtype}')"
else
    echo "ERROR: expected output not found at $EXPECTED_OUTPUT" >&2
    exit 1
fi
