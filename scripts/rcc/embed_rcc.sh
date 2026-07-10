#!/bin/bash
# SLURM job script: corpus embedding on UChicago RCC (Midway3).
#
# Two-model strategy (ADR-001, restored by ADR-011):
#
#   ROLE=primary     Qwen3-Embedding-8B (4096-dim)
#                    Long context (32,768 tokens) — essential for FOMC minutes,
#                    BIS QR articles, Jackson Hole papers. Production embeddings.
#                    Output: data/processed/embeddings.npy
#
#   ROLE=comparator  all-mpnet-base-v2 (768-dim, 384-token context)
#                    Look-ahead sensitivity check ONLY (ADR-011).
#                    Compares Δ_NMI(post-2021 − pre-2021) across both models on
#                    anchor narrative sub-corpora. Not used for production clustering.
#                    Output: data/processed/embeddings_comparator.npy
#
# Canonical chain (use scripts/rcc/submit_parallel_ingest.sh):
#   ingest → filter-pre-embed → filter → embed (primary) → cluster
#   The fan-out also submits embed --role comparator in parallel
#   with the primary embed when COMPARATOR=1.
#
# Resource spec:
#   Account:   pi-dachxiu
#   GPU:       1x A100 40GB (constraint=a100)  — ADR-036
#              Qwen3-8B at max_seq_len=1024, batch=8, fp16: ~16 GB weights +
#              activations — comfortable on 40 GB (was V100 16GB for 0.6B, which
#              cannot hold 8B). The gpu partition has a100 nodes (gold-6248r,384g).
#              all-mpnet-base-v2 comparator at 384 tokens: < 2 GB — trivially fits.
#              config uses batch=8 + seq=1024 (see config/config.yaml).
#   CPUs:      8
#   RAM:       64 GB
#   Time:      18 h   (Qwen3-8B primary on A100 ~6-12 h; mpnet comparator ~2 h)
#
# All output goes under the user scratch space, never in the PI project folder.

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
