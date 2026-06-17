# Anchor Narratives & Validation Sets

Locked ground truth for face-validity checking of narrative detection. Anchor
recovery is **reported as a diagnostic, not gated**: there is no pass/fail
threshold and no kill criteria (ADR-040). The sets are fixed before analysis and
not modified post-hoc, so the no-tuning rule (ADR-040) holds — recovery is never
optimized toward.

## Files

### `anchor_narratives.jsonl`
The 10 anchor narratives (§10.1 of the project plan): documented historical
narratives whose recovery within `tolerance_days` is measured and reported. The
recovery rate is a face-validity readout, not a gate.

**Status: LOCKED** — entries are not modified after the Phase 1 pilot. Changes
require an ADR.

Each entry contains:
- `id`, `name`, `category` — identification
- `reference_date`, `reference_window_start`, `reference_window_end` — temporal anchor
- `tolerance_days` — max deviation between system-detected emergence and reference date
- `key_terms` — for sanity-checking that the recovered cluster is the right one
- `expected_emergence_speed` — `sharp` (<7d to peak), `moderate` (7-30d), `gradual` (>30d)
- `expected_significance_threshold` — articles/day for X consecutive days that
  defines "significant emergence"
- `why_anchor` — narrative rationale
- `references` — primary-source citations supporting the timing

### `fizzled_counterparts_seed.jsonl`
Narratives that emerged but did not crystallize into sustained discourse. Used to
check that the system distinguishes survivors from non-survivors (survivorship-bias
mitigation, §8.5).

**Status: DRAFT (entries marked `_seed_status: DRAFT`)** — plausible candidates
from background research that must be confirmed against actual corpus volumes
before being locked. The DRAFT marking enforces that a fizzled narrative is one
the corpus shows as fizzled, not one assumed to have fizzled.

## Confirmation Protocol for Fizzled Narratives

After ingestion completes:

1. For each `_seed_status: DRAFT` candidate, query the corpus for articles
   matching `key_terms` within the `reference_window`.
2. Verify volume peaks and declines without sustaining (the "fizzle" claim).
3. Set `_seed_status` to `CONFIRMED` and remove the field, OR replace the entry
   with a different fizzled candidate the corpus supports.
4. Commit before analysis runs.

This prevents post-hoc tuning of the fizzled set toward results.

## Reproducibility

JSONL (one object per line) for line-diffable version control. Corrections are
full-line replacements, never in-place mutation.
