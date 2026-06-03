#!/bin/bash
# =============================================================================
# Macro Narrative Dynamics — PARALLEL ingest submission (Midway3)
# =============================================================================
# Fans the basis-set corpus ingest (ADR-020, 12 sources) out into one SLURM
# job per source, then chains the downstream stages on afterok of ALL ingest
# jobs:
#
#   [ federalreserve | fed_regional | congressional | imf | bis | treasury_ofr
#     | cea | voxeu | brookings | piie | cbo | nber ]  (all parallel)
#                              │  (afterok: every ingest job)
#                              ▼
#         filter-pre-embed → filter → embed (primary) → cluster
#
# Why parallel instead of the single chained composite (submit_full_pipeline.sh):
# the composite runs all 12 sources sequentially in one job, so a long pole
# (CBO Wayback enumeration, NBER ID walk, Brookings ~44k articles) can starve
# the rest and risk the wall-clock limit. Here each source gets its own job and
# its own --time budget, sized below. A single source can fail/rerun without
# re-running the others. Per-source runs don't touch the composite checkpoint,
# so reruns overwrite that source's JSONL cleanly (no stale-checkpoint pitfall).
#
# Usage from a Midway3 login node:
#   cd /scratch/midway3/ehgarver/macro-narrative-dynamics
#   bash scripts/rcc/submit_parallel_ingest.sh
#
#   # Custom window:
#   START=2010-01-01 END=2025-12-31 bash scripts/rcc/submit_parallel_ingest.sh
#
#   # Re-run only specific sources (e.g. ones that failed), no downstream:
#   SOURCES="cbo nber" SKIP_DOWNSTREAM=1 bash scripts/rcc/submit_parallel_ingest.sh
#
#   # Hard-delete prior data instead of archiving (DESTRUCTIVE):
#   NUKE_PRIOR=1 bash scripts/rcc/submit_parallel_ingest.sh
#
# All data under /scratch/midway3/ehgarver/ — never PI project storage.
# =============================================================================

set -euo pipefail

REPO_ROOT="/scratch/midway3/ehgarver/macro-narrative-dynamics"
SCRATCH_DATA="/scratch/midway3/ehgarver/data"

START="${START:-2010-01-01}"
END="${END:-$(date +%Y-%m-%d)}"
SKIP_CLEANUP="${SKIP_CLEANUP:-0}"
NUKE_PRIOR="${NUKE_PRIOR:-0}"
NUKE_RAW="${NUKE_RAW:-0}"
SKIP_DOWNSTREAM="${SKIP_DOWNSTREAM:-0}"
COMPARATOR="${COMPARATOR:-0}"

# All 12 basis-set sources, ordered longest-pole-first so they enter the queue
# early. Override with SOURCES="..." to run a subset.
SOURCES="${SOURCES:-cbo nber brookings voxeu imf congressional bis fed_regional federalreserve piie treasury_ofr cea}"

# Per-source wall-clock budget (hours). Long poles get generous limits; quick
# direct-fetch sources get short ones. CBO Wayback enumeration is the extreme
# (ADR-023: ~15-22h for the full 2010-present walk).
declare -A HOURS=(
    [cbo]=36
    [nber]=14
    [brookings]=10
    [voxeu]=10
    [imf]=6
    [congressional]=5
    [bis]=4
    [fed_regional]=4
    [federalreserve]=4
    [piie]=3
    [treasury_ofr]=2
    [cea]=2
)

cd "$REPO_ROOT"

echo "=========================================="
echo "MND — PARALLEL ingest submit"
echo "Window:   $START → $END"
echo "Sources:  $SOURCES"
echo "Downstream: $([[ $SKIP_DOWNSTREAM == 1 ]] && echo skip || echo "filter→embed→cluster")"
echo "Cleanup:  $([[ $SKIP_CLEANUP == 1 ]] && echo skip || ([[ $NUKE_PRIOR == 1 ]] && echo nuke || echo archive))$([[ $NUKE_RAW == 1 ]] && echo " +raw" || true)"
echo "Started:  $(date)"
echo "=========================================="

# ---------------------------------------------------------------------------
# 1. Clear / archive prior output (mirrors submit_full_pipeline.sh)
# ---------------------------------------------------------------------------
if [[ "$SKIP_CLEANUP" == "1" ]]; then
    echo ">> SKIP_CLEANUP=1 — leaving prior data in place"
else
    TS="$(date -u +%Y%m%dT%H%M%SZ)"
    ARCHIVE_DIR="${SCRATCH_DATA}/_archived_${TS}"
    declare -a TARGETS=(
        "${SCRATCH_DATA}/processed"
        "${REPO_ROOT}/data/processed"
        "${REPO_ROOT}/logs"
    )
    if [[ "$NUKE_RAW" == "1" ]]; then
        TARGETS+=( "${SCRATCH_DATA}/raw" "${REPO_ROOT}/data/raw" )
    fi
    if [[ "$NUKE_PRIOR" == "1" ]]; then
        echo ">> NUKE_PRIOR=1 — deleting prior output (DESTRUCTIVE)"
        for t in "${TARGETS[@]}"; do
            [[ -e "$t" ]] && { echo "   rm -rf $t"; rm -rf "$t"; }
        done
    else
        echo ">> archiving prior output to ${ARCHIVE_DIR}"
        mkdir -p "$ARCHIVE_DIR"
        for t in "${TARGETS[@]}"; do
            if [[ -e "$t" ]]; then
                rel="${t#${REPO_ROOT}/}"; rel="${rel#${SCRATCH_DATA}/}"
                dest="${ARCHIVE_DIR}/${rel}"
                mkdir -p "$(dirname "$dest")"
                echo "   mv $t -> $dest"; mv "$t" "$dest"
            fi
        done
    fi
fi

mkdir -p "${REPO_ROOT}/logs" "${REPO_ROOT}/data/raw/articles" "${REPO_ROOT}/data/processed"

# ---------------------------------------------------------------------------
# 2. Submit one ingest job per source (all parallel, no inter-dependency)
# ---------------------------------------------------------------------------
echo ""
echo ">> Submitting per-source ingest jobs ..."
ING_IDS=()
for s in $SOURCES; do
    h="${HOURS[$s]:-12}"
    jid=$(sbatch --parsable \
        --job-name="mnd-ing-$s" \
        --time="${h}:00:00" \
        --export=ALL,SOURCE="$s",START="$START",END="$END" \
        scripts/rcc/ingest_source_rcc.sh)
    printf "   %-15s -> job %s (%sh)\n" "$s" "$jid" "$h"
    ING_IDS+=("$jid")
done

if [[ "$SKIP_DOWNSTREAM" == "1" ]]; then
    echo ""
    echo ">> SKIP_DOWNSTREAM=1 — not chaining filter/embed/cluster."
    echo "   Ingest jobs: ${ING_IDS[*]}"
    exit 0
fi

# ---------------------------------------------------------------------------
# 3. Chain downstream stages on afterok of EVERY ingest job
# ---------------------------------------------------------------------------
DEP="$(IFS=:; echo "${ING_IDS[*]}")"

echo ""
echo ">> Submitting filter-pre-embed (afterok:all ingest) ..."
FILTER_PRE=$(sbatch --parsable --dependency=afterok:$DEP scripts/rcc/filter_pre_embed_rcc.sh)
echo "   filter-pre-embed: $FILTER_PRE"

FILTER=$(sbatch --parsable --dependency=afterok:$FILTER_PRE scripts/rcc/filter_rcc.sh)
echo "   filter:           $FILTER"

EMBED_PRIMARY=$(sbatch --parsable --dependency=afterok:$FILTER --export=ALL,ROLE=primary scripts/rcc/embed_rcc.sh)
echo "   embed primary:    $EMBED_PRIMARY"

if [[ "$COMPARATOR" == "1" ]]; then
    EMBED_COMPARATOR=$(sbatch --parsable --dependency=afterok:$FILTER --export=ALL,ROLE=comparator scripts/rcc/embed_rcc.sh)
    echo "   embed comparator: $EMBED_COMPARATOR"
fi

CLUSTER=$(sbatch --parsable --dependency=afterok:$EMBED_PRIMARY scripts/rcc/cluster_rcc.sh)
echo "   cluster:          $CLUSTER"

cat <<EOF

==========================================
Submission complete (monitor: squeue -u \$USER).

Ingest jobs (parallel):
$(for i in "${!ING_IDS[@]}"; do printf "  %-15s %s\n" "$(echo $SOURCES | cut -d' ' -f$((i+1)))" "${ING_IDS[$i]}"; done)

Downstream (afterok-chained):
  filter-pre-embed: $FILTER_PRE
  filter:           $FILTER
  embed primary:    $EMBED_PRIMARY
$( [[ "$COMPARATOR" == "1" ]] && echo "  embed comparator: $EMBED_COMPARATOR" )
  cluster:          $CLUSTER

If any single source fails (0 articles → job exits 1), the afterok chain holds.
Re-run just that source, then re-launch downstream:
  SOURCES="<failed_source>" SKIP_DOWNSTREAM=1 SKIP_CLEANUP=1 bash scripts/rcc/submit_parallel_ingest.sh
  # then submit filter_pre_embed_rcc.sh ... cluster_rcc.sh with the new dependency
==========================================
EOF
