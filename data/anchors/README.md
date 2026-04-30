# Anchor Narratives & Validation Sets

This directory contains the **ground truth** against which the system's narrative
detection is validated. These files are part of the project's pre-commitment —
they should be **finalized before any predictive analysis** and not modified
post-hoc to fit results.

## Files

### `anchor_narratives.jsonl`
The 10 anchor narratives from §10.1 of the project plan. Each is a documented
historical narrative the system **must** recover within `tolerance_days` to be
considered functioning. Below the kill-criterion threshold (7 of 10 recovered),
the project pivots methodology or scope.

**Status: LOCKED** — do not modify entries after Phase 1 pilot completes. Any
changes require a documented architectural decision.

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
Narratives that emerged but did **not** crystallize into significant sustained
discourse. Used to validate that the system distinguishes survivors from non-survivors
(see §8.5 — survivorship bias mitigation).

**Status: DRAFT (seed entries marked `_seed_status: DRAFT`)** — these are
plausible candidates from background research, but **must be confirmed by
inspecting actual corpus volumes** during Phase 1 pilot before being locked.

The reason for the DRAFT marking is methodological honesty: a fizzled narrative
should be one the corpus shows as fizzled, not one we *think* fizzled. After
Phase 1 ingestion, run the confirmation protocol below.

### `topic_seed_articles.jsonl` *(to be created in Phase 1)*
A small set (~30) of paradigmatically macro-financial articles used as positive
examples for the embedding-similarity arm of the topic filter. Built in Phase 1
from a hand-curated selection of WSJ/FT/Economist/FOMC pieces spanning categories.

## Confirmation Protocol for Fizzled Narratives

After Phase 1 ingestion completes:

1. For each `_seed_status: DRAFT` fizzled candidate, query the ingested corpus
   for articles matching the `key_terms` within the `reference_window`.
2. Verify that volume genuinely peaks and declines without sustaining (the
   "fizzle" claim).
3. Update `_seed_status` to `CONFIRMED` and remove the field, OR
   replace the entry with a different fizzled candidate that the corpus supports.
4. Commit the update before any predictive analysis runs.

This protocol prevents post-hoc tuning of the fizzled set to support results.

## Reproducibility

All entries are JSONL (one JSON object per line) for easy diffing in version
control. No mutation in place — corrections are full-line replacements.
