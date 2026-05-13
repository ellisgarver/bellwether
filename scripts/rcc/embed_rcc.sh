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
# Full pipeline submission (run from Midway3 login node):
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
#   echo "Ingest:           $INGEST"
#   echo "Filter:           $FILTER"
#   echo "Embed primary:    $EMBED_PRIMARY"
#   echo "Embed comparator: $EMBED_COMPARATOR"
#
# Resource spec:
#   Account:   pi-dachxiu
#   GPU:       1x V100 (constraint=v100)
#              Qwen3-0.6B at 32,768 tokens: ~16-32 GB per batch — fits V100 (32 GB)
#              all-mpnet-base-v2 at 384 tokens: < 2 GB — trivially fits
#   CPUs:      8
#   RAM:       32 GB  (bumped from 16 for Qwen3 full-context batching)
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

module load python/anaconda-2023.09
source /software/python-anaconda-2023.09-el8-x86_64/etc/profile.d/conda.sh
conda activate mnd
export PYTHONNOUSERSITE=1   # prevent ~/.local site-packages from shadowing conda env

export USE_TF=0
export KERAS_BACKEND=torch
export MND_EMBEDDING_DEVICE=cuda
# MND_MAX_SEQ_LEN not set → config default (32768 for Qwen3 on CUDA)
# mpnet comparator uses its own max_seq_len (384) regardless of this variable

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
