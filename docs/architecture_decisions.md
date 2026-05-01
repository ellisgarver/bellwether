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

## ADR-005: Wayback Machine CDX replaces GDELT as historical discovery layer

- **Status**: Accepted
- **Date**: 2026-04-30

### Context

ADR-004 designated GDELT 2.0 as the discovery layer for free-outlet URLs.
During Phase 1 piloting, GDELT's free API applied IP-level rate throttling
that rejected the majority of requests regardless of per-request delay.
With 26 weekly batches over a 6-month pilot window (September 2023 – February
2024), 18 of 26 batches failed with the documented error "Please limit
requests to one every 5 seconds." Increasing the inter-request delay from
1 s (original) to 6 s had no effect, confirming the limit is not per-request
timing but a broader IP-level quota. The result was 0 GDELT-discovered articles.

GDELT's full-text search endpoint (`api.gdeltproject.org/api/v2/doc`) is a
separate API with potentially different limits, but its reliability for bulk
historical queries from a single academic IP is untested and not documented.

The Internet Archive Wayback Machine CDX API offers an alternative with
different properties:
- No authentication required, no hard documented rate limit on CDX search.
- Coverage of all major outlets back to mid-2000s.
- One CDX search call per domain yields many article URLs, so the
  request count scales with the number of outlets (~20), not with
  calendar weeks (~26–182).
- The `if_` endpoint modifier returns raw archived HTML without the
  Wayback toolbar, which trafilatura can extract cleanly.

### Decision

For **historical bulk ingestion** (date ranges > 7 days), replace GDELT with
the Wayback Machine CDX as the free-outlet discovery layer. The new
`WaybackIngestor` class (`src/mnd/ingestion/wayback.py`):

1. Loads all free/mixed-access outlets from `config/whitelist.yaml`.
2. For each domain, issues one CDX API request covering the full date window.
3. Filters CDX results to article-like URLs (rejects tag/category/search pages).
4. Fetches each archived page via `https://web.archive.org/web/{ts}if_/{url}`.
5. Extracts text + metadata with trafilatura; drops documents < 200 words.

The default pilot command is now `--sources wayback,fed`.

GDELT (`src/mnd/ingestion/gdelt.py`) is **retained** for two use cases:
- Near-real-time discovery (last 7 days), where request volume is low
  enough that rate limits are unlikely to trigger.
- Potential future integration with GDELT's GFT (full-text) endpoint if
  that API proves reliable.

### Consequences

**Positive**:
- Bulk historical ingestion is now reliable and reproducible regardless of
  network conditions or IP reputation.
- Coverage extends to the full whitelist of ~20 free outlets per run.
- No new API keys or paid dependencies.

**Negative / risks**:
- Wayback coverage is retrospective: articles must have been crawled by the
  Internet Archive. Very recent content (< 24–48 h) may not be archived yet.
  This does not affect Phase 1 pilot (6-month historical window) but will
  matter for Phase 6 (weekly live updates), which should use GDELT for
  recent discovery.
- The `if_` endpoint has been stable for years but is not formally part of
  the CDX API contract. Monitor for breakage on future runs.
- Wayback page fetches are slower than GDELT URL discovery (~1.5 s/page);
  a 150-article-per-domain cap is in place to bound total runtime.

---

## ADR-006: Reduce `max_seq_len` from 32768 to 512 for local MPS runs

- **Status**: Accepted
- **Date**: 2026-04-30

### Context

`Qwen/Qwen3-Embedding-0.6B` (ADR-001) supports sequences up to 32768 tokens.
When `sentence-transformers` batches documents for encoding, it pads each batch
to the model's `max_seq_length` before the forward pass. On Apple Silicon (MPS),
the SDPA attention kernel materialises the full causal mask of shape
`[batch_size × num_heads × seq_len × seq_len]`. With the model's default
`max_seq_length = 32768` and `embedding_batch_size = 32`, this allocates
approximately 29 GB per batch — well beyond the unified memory available on a
MacBook Air M-series. Reducing to `max_seq_len = 2048` still required 8 GB per
batch (also too large). At 512 tokens the allocation is ≈ 536 MB, which fits
comfortably alongside model weights (~2.4 GB fp32 / ~1.2 GB fp16).

The article-preprocessing function `prepare_text_for_embedding` already caps
body text to 600 whitespace-words (≈780 BPE tokens at 1.3 tokens/word), so the
effective content loss from truncating at 512 BPE tokens is the final ≈270 tokens
of longer articles. Headline and lead paragraph — the highest-signal text — are
preserved.

A second fix was required: `embedder.py` was not calling
`model.max_seq_length = self.max_seq_len` after loading the `SentenceTransformer`,
so the model always used its built-in default (32768) regardless of the config
value. This is corrected in the same commit.

### Decision

Set `embedding.primary.max_seq_len: 512` in `config.yaml` for Phase 1 local
runs (Apple Silicon). This value must be restored to `32768` before Phase 2 full
corpus embedding on UChicago RCC (CUDA), where memory is not a constraint.
A comment in `config.yaml` flags the restore point.

Separately, always invoke the pipeline with `USE_TF=0` (set in `.env` or shell)
to prevent `sentence-transformers` from loading TensorFlow's ≈691 MB dylibs on
import, which caused the process to stall for 15+ minutes during local testing.
`USE_TF=0` is added to `.env.example` as a recommended variable.

### Consequences

**Positive**:
- Phase 1 pilot runs on MacBook Air without out-of-memory crashes.
- No loss of headline or lead-paragraph content; truncation affects only the
  tail of longer articles.

**Negative / risks**:
- Articles longer than ≈400 words of body text are silently truncated at 512
  tokens. This is acceptable for the pilot corpus (148 articles) but would
  affect information density on longer Fed minutes and academic papers in the
  full corpus. **Must restore to 32768 before Phase 2.**
- The `USE_TF=0` workaround is environment-level, not enforced by the code.
  If a developer forgets to set it, the first run will stall on TF import.
  The comment in `.env.example` is the only guard.

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
