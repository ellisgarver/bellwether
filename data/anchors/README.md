# Anchor Narratives & Validation Sets

Ground truth for face-validity checking of narrative detection. Anchor recovery
is reported as a diagnostic rate; it is not gated by a pass/fail threshold and
no parameter is tuned toward it. The sets are fixed before analysis.

## Files

### `anchor_narratives.jsonl`
The 10 anchor narratives: documented historical narratives whose recovery within
`tolerance_days` is measured and reported as a face-validity readout.

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
Narratives that emerged but did not crystallize into sustained discourse, used to
check that the system distinguishes survivors from non-survivors. Candidates are
confirmed against actual corpus volumes — a narrative qualifies as fizzled when
the corpus shows it peaking and declining without sustaining, rather than being
assumed to have fizzled. Each entry carries a `_seed_status` field marking
whether it has been confirmed against the corpus.

## Reproducibility

JSONL (one object per line) for line-diffable version control. Corrections are
full-line replacements, never in-place mutation.
