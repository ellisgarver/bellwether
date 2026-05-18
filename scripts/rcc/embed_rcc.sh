#!/bin/bash
# SLURM job script: corpus embedding on UChicago RCC (Midway3).
#
# Two-model strategy (ADR-001, restored by ADR-011):
#
#   ROLE=primary     Qwen3-Embedding-0.6B (1024-dim)
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
# Canonical chain (use scripts/rcc/submit_full_pipeline.sh):
#   ingest → filter-pre-embed → filter → embed (primary) → cluster
#   submit_full_pipeline.sh also submits embed --role comparator in parallel
#   with the primary embed when COMPARATOR=1 (default).
#
# Resource spec:
#   Account:   pi-dachxiu
#   GPU:       1x V100 16GB (constraint=v100)
#              Qwen3-0.6B at max_seq_len=1024, batch=8, fp16: < 6 GB working set
#              all-mpnet-base-v2 at 384 tokens: < 2 GB — trivially fits
#              (Job 49622334 OOMed on 2026-05-13 at the prior config of seq=2048 +
#              batch=32: caused 16 GB causal-mask + KV-cache allocation. Config is
#              now batch=8 + seq=1024; see config/config.yaml comments.)
#   CPUs:      8
#   RAM:       32 GB
#   Time:      12 h   (Qwen3 primary ~5-8 h; mpnet comparator ~2 h on V100)
#
# All output in /scratch/midway3/ehgarver/ — never in PI project folder.

#SBATCH --job-name=mnd-embed
#SBATCH --account=pi-dachxiu
#SBATCH --partition=gpu
#SBATCH --constraint=v100
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=12:00:00
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
# Reduce VRAM fragmentation. The torch hint from the prior OOM error.
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
# MND_MAX_SEQ_LEN not set → config default (1024 for Qwen3, lowered from 2048
# after 2026-05-13 OOM). mpnet comparator uses its own max_seq_len (384).

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
