#!/bin/bash
# Macro Narrative Dynamics — integration test battery on Midway3 (SLURM)
#
# RCC login nodes (midway3-login{1..6}) kill long-running CPU processes,
# even with nohup. The integration test battery takes 60-90 min (NBER
# enumeration is the long pole), so it must run as a SLURM job — not on
# a login node.
#
# Usage from the repo root:
#   sbatch scripts/rcc/integration_test_rcc.sh                # full 25-case battery
#   PYTEST_K="cea_erp" sbatch scripts/rcc/integration_test_rcc.sh   # filter cases
#
# Output: logs/integration_test_rcc_<jobid>.log (pytest stdout + ingestor
# INFO logs, streamed live). Email on success/failure.
#
# Resource sizing: 4h walltime is 2.5x the observed full-battery time.
# Single CPU is sufficient — every test is I/O-bound on HTTP fetches.
# 8GB memory matches the institutional ingest box.

#SBATCH --job-name=mnd-integration
#SBATCH --account=pi-dachxiu
#SBATCH --partition=caslake
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=04:00:00
#SBATCH --output=logs/integration_test_rcc_%j.log
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=ehgarver@uchicago.edu

set -euo pipefail

REPO_ROOT="/scratch/midway3/ehgarver/macro-narrative-dynamics"
cd "$REPO_ROOT"

MND_CONDA_ENV="/home/ehgarver/.conda/envs/mnd"
# shellcheck disable=SC1091
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "$MND_CONDA_ENV"

mkdir -p logs

# tests/conftest.py auto-loads .env via python-dotenv; no manual source needed.

# Optional case filter (e.g. PYTEST_K="cea_erp or nber" sbatch ...)
K_FILTER="${PYTEST_K:-}"
K_ARGS=()
if [[ -n "$K_FILTER" ]]; then
    K_ARGS=(-k "$K_FILTER")
fi

echo "=== mnd-integration started $(date -Iseconds) on $(hostname) ==="
echo "REPO_ROOT=$REPO_ROOT"
echo "PYTEST_K=$K_FILTER"
python --version
echo "==="

python -m pytest tests/integration/test_source_coverage.py \
    -m integration -v -s --log-cli-level=INFO \
    "${K_ARGS[@]}"

echo "=== mnd-integration finished $(date -Iseconds) ==="
