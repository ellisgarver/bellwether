# Architecture Decisions

This document records significant architectural and methodological decisions in
ADR (Architecture Decision Record) format. Each entry has a status, a date,
a context, the decision, and the consequences. Once an ADR is `Accepted`, it
is **not edited**. If the decision is reversed, a new ADR is added that
references and supersedes the old one.

---

## ADR-001: Two-model embedding strategy (primary + comparator)

- **Status**: Accepted
- **Date**: 2026-04-30

### Context

The project requires embedding model selection. The original project plan
(§7.2) specified `all-mpnet-base-v2` (cutoff ~2020–2021) as the sole choice
to mitigate look-ahead bias on historical articles. Since the plan was
drafted, embedding model quality has advanced significantly. Top
self-hostable models in April 2026 include the Qwen3-Embedding family
(0.6B / 4B / 8B), Voyage / Cohere / OpenAI proprietary, and several BAAI
and Alibaba models. MTEB leaderboard shows multi-point quality jumps over
mpnet-base.

The look-ahead concern is real but bounded: it can be **measured** by
comparing cluster quality and stability on pre-2021 vs post-2021 sub-periods.

### Decision

Adopt a **two-model strategy**:

1. **Primary**: `Qwen/Qwen3-Embedding-0.6B`. Apache 2.0, runs on consumer
   GPU, top-tier MTEB. Used for all production work.
2. **Comparator**: `sentence-transformers/all-mpnet-base-v2`. Older cutoff,
   used ONLY for the look-ahead sensitivity check on early anchor narratives.

The comparator is run on a sub-sample (early anchor narratives only); if
its results materially diverge from primary on pre-2021 data, look-ahead
bias is significant and we caveat. If they agree, look-ahead is bounded.

### Consequences

**Positive**:
- Stronger primary clustering quality.
- The look-ahead argument becomes *formal* (contaminated-but-strong vs.
  clean-but-weaker explicit comparison) rather than an *implicit*
  trust-the-cleanest-model claim.
- Future-proof: when better models are released, the framework swaps the
  primary; the comparator stays as the look-ahead anchor.

**Negative / risks**:
- Qwen3 has a 2025 training cutoff, so look-ahead exposure is HIGHER than
  mpnet on 2010–2024 articles. This is precisely what the comparator
  measures.
- Qwen3 0.6B is ~600MB to download; first run is slow.
- Instruction-aware prompting requires a small prefix in our pipeline
  (handled in `Embedder` class).

**Optional upgrade path**: Qwen3-Embedding-4B if RCC capacity allows.
Switch by editing `embedding.primary.model` in `config.yaml` and
documenting the change as ADR-N.

---

## ADR-002: Logistic growth as MVP fallback in lieu of SIR

- **Status**: Accepted
- **Date**: 2026-04-30

### Context

The project plan specifies multi-model dynamics fitting (SIR, logistic,
Gompertz, exponential). SIR is the epidemiologically-motivated model and
the project's intellectual centerpiece. However, SIR has 3–4 parameters
on noisy data; if posterior CIs are too wide or fits are poor, kill
criterion 3 triggers a fallback to logistic.

### Decision

Implement **logistic-first, SIR-second** in code:

- Logistic fitting is in the MVP path. It is the most stable two-parameter
  model and produces meaningful $R_0$-equivalent characterizations
  (carrying capacity $L$ and growth rate $k$).
- SIR / Gompertz / exponential are implemented in parallel but tagged as
  "compress-able" in the build plan.
- Stage classification consumes whichever model has best fit per cluster
  (selected by AICc, with logistic preferred at ties).

### Consequences

If SIR fits poorly across the validation set, the project still produces
a credible artifact. The "epidemiological dynamics" framing remains valid
because logistic is the deterministic limit of SIR under standard
assumptions. The project plan's narrative-dynamics contribution is
preserved.

---

## ADR-003: Streamlit for dashboard (vs. Gradio / FastAPI)

- **Status**: Accepted
- **Date**: 2026-04-30

### Context

Dashboard deployment options for the public artifact include Streamlit,
Gradio, and full FastAPI + React. Hosting target is Hugging Face Spaces
or Vercel free tier.

### Decision

Streamlit for MVP. Reasons:

- Tightest path from cluster artifacts → user-visible chart.
- HF Spaces has first-class Streamlit support.
- Built-in caching for static-artifact reads.
- Single-developer codebase; React would more than double frontend work.

If the project needs richer interactivity later (e.g., 2D narrative-map
zoom-and-click), a Gradio or custom-frontend version becomes a Phase 6
stretch goal.

### Consequences

Some interactive limits — Streamlit rerenders the whole page on
interactions, which can be slow with large datasets. Mitigation: pre-compute
artifacts heavily; the dashboard reads cached JSON, never recomputes.

---

## ADR-004: GDELT as discovery layer only, not text source

- **Status**: Accepted
- **Date**: 2026-04-30

### Context

GDELT 2.0 is the primary candidate for free, comprehensive article
discovery, but it has documented quality issues (~55% accuracy on key
fields, ~20% redundancy, Western/U.S. media overrepresentation). It
provides URL + headline + source domain, not full text.

### Decision

Use GDELT **only** to discover URLs published by outlets on the
whitelist. Full text is fetched downstream:
- Free outlets: HTTP fetch + Trafilatura extraction.
- Paywalled outlets: library database (Factiva or ProQuest).

GDELT's discovery role is robust to its known issues — false-positive
URLs are filtered when full-text retrieval fails or returns content
that fails the topic filter.

### Consequences

The pipeline is gated on UChicago library access for paywalled-outlet
text, but discovery itself is robust and free. If library access fails,
the project falls back to free outlets only (CNBC, MarketWatch, FT
Alphaville, etc.) plus institutional sources, with explicit
acknowledgment that the analytical-source layer is reduced.

---

## ADR template (copy for new entries)

```
## ADR-NNN: <short title>

- **Status**: Proposed | Accepted | Deprecated | Superseded by ADR-MMM
- **Date**: YYYY-MM-DD

### Context
<What problem are we solving? What constraints apply?>

### Decision
<What did we decide?>

### Consequences
<What follows from the decision — both intended and unintended?>
```
