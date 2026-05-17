#!/bin/bash
# =============================================================================
# Macro Narrative Dynamics — full Midway3 pipeline submission
# =============================================================================
# Submits the full Phase 2/3 chain as six chained SLURM jobs:
#
#   ingest_institutional → filter-pre-embed → filter → embed (primary) → cluster
#                                                    └→ embed (comparator) (parallel, optional)
#
# filter-pre-embed added 2026-05-17 — applies ADR-010/012 archived-source
# exclusion at the pipeline level (writes corpus_for_embedding.jsonl).
# Prior runs skipped this and the filter stage logged a fallback WARNING.
#
# Each job is `afterok:` chained, so a failure halts the chain cleanly.
#
# Before submitting, this script ARCHIVES any prior pipeline output under
# /scratch/midway3/ehgarver/data/{raw,processed} into a timestamped folder.
# Set NUKE_PRIOR=1 to *delete* instead of archive. Set SKIP_CLEANUP=1 to keep
# everything as-is (e.g. for ingestion-resume runs that use the checkpoint).
#
# Usage from Midway3 login node:
#   cd /scratch/midway3/ehgarver/macro-narrative-dynamics
#   bash scripts/rcc/submit_full_pipeline.sh
#
#   # Custom date window:
#   START=2010-01-01 END=2025-12-31 bash scripts/rcc/submit_full_pipeline.sh
#
#   # Skip comparator embedding (faster; primary only):
#   COMPARATOR=0 bash scripts/rcc/submit_full_pipeline.sh
#
#   # Hard-delete prior data instead of archiving (DESTRUCTIVE):
#   NUKE_PRIOR=1 bash scripts/rcc/submit_full_pipeline.sh
#
# All data lives under /scratch/midway3/ehgarver/ — never PI project storage.
# =============================================================================

set -euo pipefail

REPO_ROOT="/scratch/midway3/ehgarver/macro-narrative-dynamics"
SCRATCH_DATA="/scratch/midway3/ehgarver/data"   # symlinked from repo data/ on RCC

START="${START:-2010-01-01}"
END="${END:-$(date +%Y-%m-%d)}"
COMPARATOR="${COMPARATOR:-1}"        # set to 0 to skip mpnet comparator
SKIP_CLEANUP="${SKIP_CLEANUP:-0}"    # set to 1 to preserve prior outputs
NUKE_PRIOR="${NUKE_PRIOR:-0}"        # set to 1 to delete (not archive) prior outputs

cd "$REPO_ROOT"

echo "=========================================="
echo "Macro Narrative Dynamics — Phase 2/3 submit"
echo "Window:     $START → $END"
echo "Comparator: $([[ $COMPARATOR == 1 ]] && echo yes || echo no)"
echo "Cleanup:    $([[ $SKIP_CLEANUP == 1 ]] && echo skip || ([[ $NUKE_PRIOR == 1 ]] && echo nuke || echo archive))"
echo "Repo:       $REPO_ROOT"
echo "Started:    $(date)"
echo "=========================================="

# ---------------------------------------------------------------------------
# 1. Clear / archive prior pipeline output
# ---------------------------------------------------------------------------

if [[ "$SKIP_CLEANUP" == "1" ]]; then
    echo ">> SKIP_CLEANUP=1 — leaving prior data in place"
else
    TS="$(date -u +%Y%m%dT%H%M%SZ)"
    ARCHIVE_DIR="${SCRATCH_DATA}/_archived_${TS}"

    # Targets to wipe between full runs. Raw articles are kept by default
    # (they're expensive to re-ingest); set NUKE_RAW=1 to clear them too.
    NUKE_RAW="${NUKE_RAW:-0}"
    declare -a TARGETS=(
        "${SCRATCH_DATA}/processed"
        "${REPO_ROOT}/data/processed"
        "${REPO_ROOT}/logs"
    )
    if [[ "$NUKE_RAW" == "1" ]]; then
        TARGETS+=( "${SCRATCH_DATA}/raw" "${REPO_ROOT}/data/raw" )
        # Also kill the institutional checkpoint so ingestion starts clean
        TARGETS+=( "${REPO_ROOT}/data/raw/articles/.institutional_checkpoint.json" )
    fi

    if [[ "$NUKE_PRIOR" == "1" ]]; then
        echo ">> NUKE_PRIOR=1 — deleting prior output (DESTRUCTIVE)"
        for t in "${TARGETS[@]}"; do
            if [[ -e "$t" ]]; then
                echo "   rm -rf $t"
                rm -rf "$t"
            fi
        done
    else
        echo ">> archiving prior output to ${ARCHIVE_DIR}"
        mkdir -p "$ARCHIVE_DIR"
        for t in "${TARGETS[@]}"; do
            if [[ -e "$t" ]]; then
                # Preserve directory layout under archive
                rel="${t#${REPO_ROOT}/}"
                rel="${rel#${SCRATCH_DATA}/}"
                dest="${ARCHIVE_DIR}/${rel}"
                mkdir -p "$(dirname "$dest")"
                echo "   mv $t -> $dest"
                mv "$t" "$dest"
            fi
        done
    fi
fi

# Ensure required directories exist before submission
mkdir -p "${REPO_ROOT}/logs" \
         "${REPO_ROOT}/data/raw/articles" \
         "${REPO_ROOT}/data/processed"

# ---------------------------------------------------------------------------
# 2. Submit chained SLURM jobs
# ---------------------------------------------------------------------------

echo ""
echo ">> Submitting ingest_institutional ..."
INGEST=$(sbatch --parsable \
    --export=ALL,START="$START",END="$END" \
    scripts/rcc/ingest_institutional_rcc.sh)
echo "   ingest job:           $INGEST"

echo ">> Submitting filter-pre-embed (afterok:$INGEST) ..."
FILTER_PRE=$(sbatch --parsable \
    --dependency=afterok:$INGEST \
    scripts/rcc/filter_pre_embed_rcc.sh)
echo "   filter-pre-embed job: $FILTER_PRE"

echo ">> Submitting filter (afterok:$FILTER_PRE) ..."
FILTER=$(sbatch --parsable \
    --dependency=afterok:$FILTER_PRE \
    scripts/rcc/filter_rcc.sh)
echo "   filter job:           $FILTER"

echo ">> Submitting embed --role primary (afterok:$FILTER) ..."
EMBED_PRIMARY=$(sbatch --parsable \
    --dependency=afterok:$FILTER \
    --export=ALL,ROLE=primary \
    scripts/rcc/embed_rcc.sh)
echo "   embed primary job:    $EMBED_PRIMARY"

if [[ "$COMPARATOR" == "1" ]]; then
    echo ">> Submitting embed --role comparator (afterok:$FILTER) ..."
    EMBED_COMPARATOR=$(sbatch --parsable \
        --dependency=afterok:$FILTER \
        --export=ALL,ROLE=comparator \
        scripts/rcc/embed_rcc.sh)
    echo "   embed comparator job: $EMBED_COMPARATOR"
fi

echo ">> Submitting cluster (afterok:$EMBED_PRIMARY) ..."
CLUSTER=$(sbatch --parsable \
    --dependency=afterok:$EMBED_PRIMARY \
    scripts/rcc/cluster_rcc.sh)
echo "   cluster job:          $CLUSTER"

# ---------------------------------------------------------------------------
# 3. Summary
# ---------------------------------------------------------------------------

cat <<EOF

==========================================
Submission complete.

Job IDs (use squeue -u \$USER to monitor):
  ingest:           $INGEST
  filter-pre-embed: $FILTER_PRE
  filter:           $FILTER
  embed prim:       $EMBED_PRIMARY
$( [[ "$COMPARATOR" == "1" ]] && echo "  embed comp:       $EMBED_COMPARATOR" )
  cluster:          $CLUSTER

Logs:        logs/{ingest_institutional,filter_pre_embed,filter,embed,cluster}_rcc_<jobid>.log
Outputs:     data/raw/articles/, data/processed/

After cluster completes, run interactively on a login node (NMI/ARI is fast):
  python scripts/run_pipeline.py stability
  python scripts/run_pipeline.py validate --anchors all
==========================================
EOF
