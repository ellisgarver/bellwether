#!/bin/bash
# SLURM job script: corpus embedding (Midway3).
#
# Production role (default):
#   ROLE=primary   Qwen3-Embedding-8B (4096-dim, ADR-036) — 1x A100 40GB, ~6-12 h
#                  Output: data/processed/embeddings.npy
#
# Diagnostic role (opt-in via submit_parallel_ingest.sh COMPARATOR=1):
#   ROLE=comparator   all-mpnet-base-v2 (768-dim); not used for clustering (ADR-019)
#                     Output: data/processed/embeddings_comparator.npy
#
# Canonical chain (use scripts/rcc/submit_parallel_ingest.sh):
#   ingest → filter-pre-embed → filter → embed → cluster

#SBATCH --job-name=mnd-embed
#SBATCH --account=pi-dachxiu
#SBATCH --partition=gpu
#SBATCH --constraint=a100
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=18:00:00
#SBATCH --output=logs/embed_rcc_%j.log
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=ehgarver@uchicago.edu

set -euo pipefail

REPO_ROOT="/scratch/midway3/ehgarver/macro-narrative-dynamics"
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
export MND_EMBEDDING_DEVICE=cuda
# Reduce VRAM fragmentation.
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
# MND_MAX_SEQ_LEN not set → config default (1024 for Qwen3).

ROLE="${ROLE:-primary}"

if [[ "$ROLE" == "primary" ]]; then
    EXPECTED_OUTPUT="data/processed/embeddings.npy"
elif [[ "$ROLE" == "comparator" ]]; then
    EXPECTED_OUTPUT="data/processed/embeddings_comparator.npy"
else
    echo "ERROR: ROLE must be 'primary' or 'comparator', got: $ROLE" >&2
    exit 1
fi

echo "===== mnd-embed ====="
echo "Job ID:   $SLURM_JOB_ID"
echo "Role:     $ROLE"
echo "Output:   $EXPECTED_OUTPUT"
echo "Node:     $(hostname)"
echo "GPU:      $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
echo "Started:  $(date)"
echo "====================="

python scripts/run_pipeline.py embed --role "$ROLE"

echo "===== Complete: $(date) ====="
if [[ -f "$EXPECTED_OUTPUT" ]]; then
    ls -lh "$EXPECTED_OUTPUT"
    python -c "import numpy as np; a=np.load('$EXPECTED_OUTPUT'); print(f'Shape: {a.shape}, dtype: {a.dtype}')"
else
    echo "ERROR: expected output not found at $EXPECTED_OUTPUT" >&2
    exit 1
fi

# chunks.parquet is written by the primary embed run; verify it exists
if [[ "$ROLE" == "primary" ]]; then
    if [[ -f "data/processed/chunks.parquet" ]]; then
        python -c "import pandas as pd; df=pd.read_parquet('data/processed/chunks.parquet'); print(f'Chunks: {len(df)} rows, {df[\"is_chunked\"].sum()} chunked')"
    else
        echo "ERROR: chunks.parquet not found — embed may not have run chunking step" >&2
        exit 1
    fi
fi
