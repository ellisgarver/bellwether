#!/bin/bash
# SLURM job script: corpus embedding on UChicago RCC (Midway3).
#
# Supports two embedding roles (set via ROLE env var):
#
#   ROLE=primary     Qwen3-Embedding-0.6B (1024-dim)
#                    Production embeddings → data/processed/embeddings.npy
#                    Input to BERTopic clustering and dynamics fitting
#
#   ROLE=comparator  all-mpnet-base-v2 (768-dim)
#                    Look-ahead sensitivity check → data/processed/embeddings_comparator.npy
#                    NOT used for clustering; used only to compare cluster quality
#                    across pre-2021 / post-2021 sub-periods (ADR-001)
#
# Both jobs run in parallel in Phase 3. Cluster job depends on primary only.
#
# Submit both simultaneously:
#   EMBED_PRIMARY=$(sbatch --parsable --export=ROLE=primary scripts/rcc/embed_rcc.sh)
#   EMBED_COMPARATOR=$(sbatch --parsable --export=ROLE=comparator scripts/rcc/embed_rcc.sh)
#   sbatch --dependency=afterok:$EMBED_PRIMARY scripts/rcc/cluster_rcc.sh
#   echo "Primary embed:    $EMBED_PRIMARY"
#   echo "Comparator embed: $EMBED_COMPARATOR"
#
# Resource spec (confirmed 2026-05-04):
#   Account:   pi-dachxiu
#   GPU:       1x V100 (constraint=v100; handles Qwen3-0.6B at 32768 tokens and
#              all-mpnet-base-v2 at 384 tokens with ample headroom)
#   CPUs:      8
#   RAM:       16 GB
#   Time:      12 h (conservative; Qwen3 ~5 h / mpnet ~2 h estimated on V100)
#   Cost:      ~300 SUs worst case (allocation balance: 1,532,273 SUs)
#
# Prerequisites (run once interactively on Midway3):
#   git clone https://github.com/ellisgarver/macro-narrative-dynamics.git \
#       /scratch/midway3/ehgarver/macro-narrative-dynamics
#   cd /scratch/midway3/ehgarver/macro-narrative-dynamics
#   module load python/anaconda-2023.09
#   conda create -n mnd python=3.12 -y && conda activate mnd
#   pip install -r requirements.txt
#   pip install torch --index-url https://download.pytorch.org/whl/cu121
#
# All output in /scratch/midway3/ehgarver/ — never in PI project folder.

#SBATCH --job-name=mnd-embed
#SBATCH --account=pi-dachxiu
#SBATCH --partition=gpu
#SBATCH --constraint=v100
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=12:00:00
#SBATCH --output=logs/embed_rcc_%j.log
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=ehgarver@uchicago.edu

set -euo pipefail

REPO_ROOT="/scratch/midway3/ehgarver/macro-narrative-dynamics"
cd "$REPO_ROOT"
mkdir -p logs data/processed

module load python/anaconda-2023.09
conda activate mnd

export USE_TF=0
export KERAS_BACKEND=torch
export MND_EMBEDDING_DEVICE=cuda
# MND_MAX_SEQ_LEN not set → config default (32768) for Qwen3 on CUDA
# all-mpnet-base-v2 uses its own max_seq_len (384) regardless of this variable

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
