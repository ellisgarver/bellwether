# Architecture Decisions

This document records significant architectural and methodological decisions in
ADR (Architecture Decision Record) format. Each entry has a status, a date,
a context, the decision, and the consequences. Once an ADR is `Accepted`, it
is **not edited**. If the decision is reversed, a new ADR is added that
references and supersedes the old one.

## Status index

ADRs are append-only history. This index is the fast path: it shows which
decisions are still live. The **current methodology lock-in is ADR-019 +
ADR-020**, as amended by ADR-039 (four dynamics lenses), ADR-040 (no held-out
split, no formal pre-registration), and ADR-052 (model-free attention-trajectory
staging — SIR is a lens, not the law). Cite these plus the per-source ADRs they
reference; credibility rests on field-anchored values + no hand-tuning (ADR-040),
not a registered plan. Bodies below are preserved verbatim for that defense.

| ADR | Decision | Status |
|---|---|---|
| 001 | Two-model embedding (Qwen3 primary + mpnet comparator) | Live (as amended by 011) |
| 002 | Logistic growth as MVP fallback for SIR | Live as a lens (039); R₀-staging clause superseded by 052 |
| 003 | Streamlit for the dashboard | Superseded by 043 (static Astro/GH Pages) |
| 004 | GDELT as discovery layer only | Superseded by 005 |
| 005 | Wayback CDX replaces GDELT discovery | Superseded by 010/020 (basis-set ingestors) |
| 006 | `max_seq_len` 512 for local MPS | Live |
| 007 | ProQuest via TDM export | Superseded by 010 (ProQuest removed) |
| 008 | Phase 2 overhaul — AP News + RavenPack dynamics | Superseded by 010/016/020 |
| 009 | MarketWatch reinstatement | Superseded by 010 (removed) |
| 010 | Corpus architecture + embedding model + detection layer | Live (amended by 016/019/020) |
| 011 | Revert primary embedding to Qwen3; formalize look-ahead check | Live |
| 012 | Remove arXiv + separate Jackson Hole; drop Stage-2 topic filter | Live |
| 013 | Post-dry-run ingestor repairs; IMF re-enable; embed OOM fix | Live (IMF portion superseded by 014) |
| 014 | IMF via curl_cffi Chrome impersonation + Coveo | Live |
| 015 | JEL-anchored canonical filter | Superseded by 020 (pre-cluster keyword filter removed) |
| 016 | Single-stage topic filter + Media Cloud Premium as dynamics layer | Live (topic-filter portion superseded by 020) |
| 017 | Coverage-gap closures + Phase 6 scope freeze | Live (CBO Playwright portion superseded by 023) |
| 018 | Remove `named_events` keyword category (anchor circularity) | Live |
| 019 | **Methodology lock-in to field-accepted anchors** | Live |
| 020 | **Basis-set corpus; NBER restored, CFR dropped, CEA added; no pre-cluster filter** | Live |
| 021 | Post-020 upstream patches (VoxEU CF, Atlanta API, Congressional CHRG) | Live (CBO wildcard portion superseded by 023) |
| 022 | Methodology-principle-1 enforcement across ingestors | Live |
| 023 | CBO via bounded publication-ID enumeration; fail-loud hardening | Live (see addendum: latest-real-capture fetch) |
| 024 | Repo cleanse + single-source-of-truth doc governance | Live |
| 025 | NY Fed Staff Reports via RePEc/IDEAS | Live |
| 026 | PIIE via Wayback CDX enumeration | Live |
| 027 | Fed Board testimony as a distinct document stream | Live |
| 028 | Coverage-verification standard (shape + independent inventory) | Live |
| 029 | PIIE two coverage defects (blog tail; 2016 misdating) | Live |
| 030 | **Fail-loud hardening — silent under-capture forbidden at every fetch boundary** | Live |
| 031 | WordPress sources restricted to own-domain content (source-identity rule) | Live |
| 032 | CBO enumeration via the authoritative cbo.gov sitemap (supersedes ADR-023 id-floor estimation) | Live |
| 033 | Atlanta Fed pre-2019 Wayback recovery (macroblog + working papers) | Live |
| 034 | SF Fed `sffed_publications` per-segment labeling + cross-post exclusion | Live |
| 035 | Chicago Fed 2026-redesign date-stamp fix (citation block over OG meta) | Live |
| 036 | **Primary embedder Qwen3-Embedding-0.6B → 8B (4096-dim, A100); BERTopic unchanged** | Live |
| 037 | CBO Wayback: replayed-archived 429 is a dead snapshot to skip, not a live throttle | Live |
| 038 | CBO walk shardable by `pid % N` across independent egress IPs (RCC + laptop) | Live |
| 039 | **Dynamics shown as four complementary lenses (logistic/SIR/Bass/shape-facts), not AICc best-of-N** | Live (amends 019 §E) |
| 040 | **Drop 2010-2019/2020+ held-out split; no formal pre-registration (credibility via anchored values + no tuning)** | Live (supersedes prereg draft) |
| 041 | Markets + bidirectional Granger labeled display overlay (timing-not-cause; drop Bloomberg CPI) | Live (display only) |
| 042 | Media Cloud press volume as display/validation overlay only (never feeds clustering) | Live (relates 016/020) |
| 043 | **Static publishing — Astro on GitHub Pages, precompute everything** | Live (supersedes 003, amends 041) |
| 044 | **Narrative map — hybrid node-link UMAP graph (shape=JEL, color=stage+emerging)** | Live (relates 019/020/039/043) |
| 045 | **Corpus-base-rate volume normalization (fit + display); cross-narrative & lead-lag deferred but unblocked** | Live (supersedes 008 normalizer; relates 016/019/039) |
| 046 | **Analyze every cluster; JEL scope is a display flag, not a dynamics gate (out-of-scope shown with code)** | Live (supersedes 020 "dropped from dynamics"; relates 019/044) |
| 047 | **Markets overlay + Granger for every narrative; VIX canonical (lag tied to it), extra series display-only; `wave_count`→"peaks (≥ ½ max)"** | Live (amends 041; relates 039/043/045) |
| 048 | **Broad-press lead-lag — bidirectional Granger between institutional discourse and Media Cloud press, beside the markets readout** | Live (amends 042; relates 041/047) |
| 049 | **Dashboard artifact contract align-up: producers emit `r0_median` + R₀ interval + threshold in `stage_detail`; `shape_facts` keys renamed to the front-end's; undefined R₀ peak/min row dropped** | Live (relates 039/043/047) |
| 050 | **Incremental embedding cache — `(chunk_id, text_sha1)` sidecar lets `embed` reuse vectors and re-encode only new/changed chunks; full rebuild still re-embeds all** | Live (relates 036/016/030) |
| 051 | **Fit/display floor — only clusters with ≥ `min_articles_to_fit` (42) unique articles are fit, staged, and surfaced; all clusters stay in `clusters.parquet`, total reported on the data page. Map edges are focus-lit on hover, not static.** | Live (amends 046; relates 019/040/044) |
| 052 | **Lifecycle stage is a model-free attention-trajectory classification (Mann–Kendall trend + Mann–Whitney level); growth/stable/decay/dormant + emerging flag; fitted lenses are display-only; reframe — Shiller/SIR is a lens, not the law** | Live (supersedes 002 staging clause + 019 §E; amends 030/039; Level test amended by 058) |
| 053 | **SIR fit on a weekly integration grid + SIR-only reduced inference budget (draws 500 / tune 500 / 2 chains / `target_accept` 0.9) — makes the `O(T)` SIR scan tractable; `R₀` grid-invariant, curve/peak converted back to days; display-only, no-tuning rule intact** | Live (amends 039; relates 019/051/052) |
| 054 | **Cross-document boilerplate strip — sentence-level recurring-passage removal at the filter stage (normalized sentence in ≥ N distinct documents), after MinHash; drops content-free shells; auditable `boilerplate_report.json`** | Live (extends 019; orthogonal to 020; relates 030/046/051) |
| 055 | **Richer JEL cluster representation — c-TF-IDF terms + BERTopic representative documents (terms-first, full AEA taxonomy incl. Y); fixes thin-signal misses (r-star, Basel) and Y over-attraction; JEL stays a display flag** | Live (amends 020/046; relates 019/054) |
| 056 | **Human-readable narrative names — display-layer Claude Haiku titling over c-TF-IDF labels, grounded only in the ADR-055 representation; titles cached under a representation hash and committed for key-free deterministic rebuilds; display-only, degrades to the label** | Live (display-layer; relates 043/046/050/055) |
| 061 | **Three representative-article panels — the narrative's core (most term-aligned + substantial), earliest, and newest, de-duplicated, `n_per_bucket`=3 each; the central panel also grounds the ADR-056 naming layer (replacing the BERTopic rep-doc excerpts). JEL scope keeps its ADR-055 representation unchanged.** | Live (extends 055/056; display + naming layer) |
| 060 | **Fit lenses on the central-mass window + SIR robustness overhaul — nearly every fit-series spans ~14yr from sparse straggler tails, which broke SIR (0/365, γ→0 `HalfNormal` ridge + 855-step Euler scan). Fix: fit all three lenses on the central 95% of cumulative attention mass (α=0.05, keeps multi-wave, no new param; staging/display stay full-span); SIR gets LogNormal β/γ priors, an adaptive grid bounding the scan ≤200 steps, and a `max_treedepth` fail-fast cap so unfittable clusters go non-converged in seconds instead of grinding. Same convergence gate for all three, no outbreak-eligibility filter.** | Live (supersedes 053; amends 039/052; relates 040/058) |
| 062 | **SIR lens via the Schlickeiser–Kröger closed-form solution — retire the `pytensor.scan` Euler ODE (the sole compute pole: ~23 min × 365 clusters ≈ 140 CPU-h) for the near-exact analytic prevalence I(τ), elementary on both branches (rise `η·e^{g−1}`, decay `(k₀/κ)·cosh⁻²ζ`); fit collapses to logistic/Bass cost (1–3 ms). De-risk surfaced R₀ is NOT identifiable from a single curve (true of the current Euler fit too, and it contaminated logistic's R₀=1+k/γ), so DROP R₀ + J∞, RETIRE the Bjørnstad disease β/γ priors + the `N_pop=2·Σy` fudge, and report only curve-identifiable numbers in real units: SIR → rise/decay rates + asymmetry + peak; logistic → doubling time + inflection + plateau; Bass unchanged (field-anchored p/q, total reach m). Display-only + convergence gate + no-tuning intact.** | Live (supersedes SIR numerics + disease priors of 053/060; amends 039/052; relates 040) |
| 063 | **Portable weekly-update orchestration — a single-process `run_pipeline.py update` runs the weekly delta (per-source over-fetch since each source's own `max(published_at)` − buffer → filter → incremental embed → analyze) sequentially, CPU-only, with all paths behind a config `data_root` (env `MND_DATA_ROOT`), so it runs on a laptop / cron VM / GitHub Actions / RCC with no SLURM and no GPU. The parallel SLURM fan-out stays as the full-rebuild path only. Identity-stable institutional re-clustering (`merge_models`) is DEFERRED (ADR-057 §3) — until it lands, `update` refreshes the corpus delta + the Media Cloud press layer (ADR-064) and the narrative set is captioned "as of last full build". Scheduler documented backend-agnostically, not auto-enabled.** | Live (implements 057 §3 partial; relates 016/050; portability for README) |
| 066 | **Weekly incremental re-cluster via BERTopic `merge_models` (design + prereq). Prereq (accepted): the `cluster` stage now persists the fitted BERTopic model (safetensors → `topic_model/`) — it was discarded, and `merge_models` needs the model object, not just `clusters.parquet`. Mechanism (proposed, pending validation): `update` fits a new-week model and `merge_models([base,new], min_similarity=τ)` to keep existing topic ids/URLs/names and append only genuinely-new topics; gated on an anchor-id-stability test (a synthetic weekly merge must not renumber any of the 10 anchors). τ + split/merge back-test + cron cadence deferred until that passes.** | Proposed (implements 057 §3; relates 050/056/063/065) |
| 065 | **Incremental `analyze` re-bake — per-lens fit cache + JEL-encode cache. The fit cache keyed the whole `cfg["dynamics"]` and stored one pickle per cluster (all 3 lenses), so a one-lens prior change refit logistic+Bass identically; now each lens's `FitResult` is cached under a sig hashing only that lens's priors+inference (+series, window, seed). JEL re-encoded all ~365 reps with the 8B model every run even on unchanged clusters (~1h); now each `ClusterJELAssignment` is cached by representation+prototypes+embedder-id, the embedder loads only if a cluster misses, and an unchanged `clusters.parquet` ⇒ zero encodes. Display-mechanics only, results identical (ADR-040).** | Live (relates 050/055/062/063) |
| 064 | **Media Cloud Premium press layer + press-heating emerging signal — add the premium-press outlet collection (ADR-016: WSJ/Bloomberg/FT/Reuters/…) alongside the broad US-National collection, both via the one Media Cloud module. Wire ADR-057 §2: per already-tracked narrative, `detect_anomalies` on the attention-share ratio over a 4-week window vs a 52-week baseline at k=2σ, surfaced as a SEPARATE "heating in the press" signal beside the institutional recency flag in the Emerging view. Recomputes at bake time from live press against the existing narrative set — no re-embed, no re-cluster, never feeds embedding/clustering/scope (ADR-010/020/046). Degrades to absent when unkeyed.** | Live (implements 057 §2; extends 016/042/048; relates 040) |
| 059 | **Emerging flag is recency-only — a narrative is emerging iff its onset falls within the 4-week recency window of the corpus frontier, regardless of stage; drops the earlier `stage == growth` gate so a just-arrived narrative whose short history hasn't yet registered a significant trend is still surfaced as newly arrived** | Live (amends 052 emerging clause; relates 016/057) |
| 058 | **Peak-relative plateau test — `stable` vs `dormant` keyed to the narrative's own high-water window, not its quiet floor; fixes the all-`stable` collapse (342/365) where institutional tails made "above the floor" trivially true. MWU on the zero-heavy daily series was under-powered, so the split is by level: recent-window mean below `dormant_peak_fraction`=0.25 of the peak-window mean → dormant (a definition, not tuned to recovery)** | Live (amends 052 §2/§3 Level test; relates 040) |
| 057 | **Phase-6 live emerging (design) — two display-only signals: institutional onset (existing) + press heating (4wk vs 52wk baseline, k=2, on Media Cloud attention-share); weekly refresh builds onto the model via BERTopic `merge_models` (ids/URLs/names preserved, new topics appended above τ); manual now → cron later; novel press-only clustering scoped out (ADR-010)** | Live design; press-heating + weekly-refresh implementations each need a follow-up ADR (relates 010/016/020/042/046/048/050/056) |

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

## ADR-007: ProQuest ingestion via TDM Studio export script, not REST API

- **Status**: Accepted
- **Date**: 2026-05-01

### Context

The original `proquest.py` (ADR-004) assumed ProQuest TDM Studio exposes a
REST API that can be called with a bearer token (`PROQUEST_API_TOKEN`) from
outside the platform. In practice, TDM Studio is a self-contained Jupyter
notebook environment hosted by ProQuest. There is no externally-callable REST
API; access is through an institutional SSO session that launches a Jupyter
kernel with the `proquest_tdm` Python client pre-installed. The bearer-token
approach would never have worked.

The correct integration pattern is:

1. **Dataset creation** (manual, in TDM Studio web UI): the researcher defines
   search parameters (publication names, date range, keyword filters) and
   ProQuest builds the dataset. The dataset gets a stable ID (a UUID shown in
   the project settings).
2. **Export** (inside TDM Studio Jupyter): a script loads the dataset via
   `proquest_tdm.TDMClient`, iterates documents, and writes JSONL matching our
   `Article` schema to a file the researcher downloads.
3. **Pipeline ingestion** (local machine): `PaywalledSourceIngestor` reads the
   downloaded JSONL file and yields `Article` objects like any other ingestor.

### Decision

Rewrite `src/mnd/ingestion/proquest.py` as a **dual-role file**:

- When run as `__main__` inside TDM Studio: exports the dataset identified by
  `PROQUEST_DATASET_ID` to a JSONL file.
- When imported by the pipeline: `PaywalledSourceIngestor` reads that JSONL
  file from `data/raw/articles/proquest_{PROQUEST_DATASET_ID}.jsonl`.

Replace `PROQUEST_API_TOKEN` (and `PROQUEST_ACCOUNT_ID`, `PROQUEST_PROJECT_ID`)
in `.env.example` with `PROQUEST_DATASET_ID`. Add
`docs/proquest_tdm_setup.md` explaining the manual dataset creation step and
the export-then-download workflow.

### Consequences

**Positive**:
- The ingestion path now matches how TDM Studio actually works.
- No credentials are stored locally (TDM Studio handles auth via SSO).
- The exported JSONL is a stable, versioned artifact that can be re-ingested
  without re-running the export.

**Negative / risks**:
- The export must be run manually inside TDM Studio every time the date range
  or query changes. This is unavoidable given the platform constraints.
- The `proquest_tdm` client API must be verified inside the TDM Studio
  environment; field names and method signatures may differ by version.
  The `_FIELD_MAP` dict in `proquest.py` handles common variants, but should
  be spot-checked on the first export run.
- The pipeline's `--sources paywalled` step requires the JSONL file to already
  exist locally. Running `ingest --sources paywalled` without the file raises
  a `FileNotFoundError` with a clear message pointing to the setup docs.

---

## ADR-008: Phase 2 corpus overhaul — open institutional + AP News + RavenPack dynamics

- **Status**: Accepted
- **Date**: 2026-05-04
- **Supersedes**: ADR-005 (Wayback as discovery layer), ADR-007 (ProQuest TDM pipeline), prior Phase 2 corpus spec (tight corpus, finalized 2026-05-01)

### Context

The "tight corpus" architecture finalized 2026-05-01 relied on ProQuest TDM Studio as
the primary text source for Tier 1 financial press (WSJ, NYT, Economist) plus Wayback
CDX for wires. A subsequent assessment revealed several compounding problems:

1. **Paywalled text pipeline is fragile.** ProQuest TDM Studio requires a per-export
   workflow that is not automatable for Phase 6 live updates. License terms prevent
   any programmatic bulk download outside the Studio environment.
2. **Coverage is uneven over 2010–present.** ProQuest GN has temporal gaps for several
   outlets (hence Barron's, MarketWatch already dropped 2026-05-01). WSJ/NYT/Economist
   are better but cross-year volume comparisons carry systematic risk from index changes.
3. **Financial journalism is downstream of institutional discourse.** The hypothesis
   being tested (narrative lifecycle dynamics) applies most cleanly to the formation and
   diffusion of narratives among policymakers, researchers, and analysts — before the
   financial press picks them up. Institutional + academic + wire discourse is a closer
   proxy to the causal process.
4. **RavenPack via WRDS provides a clean, comprehensive volume signal.** The RPA 1.0
   Global Macro Dow Jones Edition covers WSJ, Barron's, DJN, MarketWatch, PR Newswire,
   and ~800 others with article-level metadata normalized for the WRDS environment.
   This is a better dynamics layer than attempting to count Wayback-retrieved articles.
5. **Anchor set scope creep.** FTX collapse and GameStop short squeeze are not
   macro-financial narratives in the traditional sense; including them risked reward-
   hacking the anchor recovery metric. Taper tantrum (2013) and China devaluation (2015)
   are canonical macro events with clean timestamps in the 2010–present window.

### Decision

**Semantic corpus (text for embedding and clustering):**

| Tier | Sources | Retrieval |
|---|---|---|
| 1 — Institutional policy | Federal Reserve (all: FOMC, speeches, MPR, Beige Book, regional Feds), IMF (WEO/GFSR/WPs/Blog), BIS (QR/WPs), CEA, CBO, Treasury/OFR/FSOC | Direct fetch / institutional RSS |
| 2 — Academic analytical | NBER WPs (abstracts + intros, JEL E/F/G), SSRN macro/finance (abstracts), VoxEU/CEPR (full posts) | Direct fetch / RSS |
| 3 — Policy-journalism bridge | Brookings Institution, PIIE | Direct fetch / RSS |
| 4 — Wire journalism | AP News (full articles, 2010–present) | Wayback CDX (historical); AP RSS (Phase 6 live) |

Cut from pipeline (do not reinstate without new ADR): Reuters, Bloomberg, WSJ, NYT,
Economist, FT, CNBC, FT Alphaville, CFR, Axios, ProQuest TDM, Factiva, NewsAPI.

**Dynamics layer:**

RavenPack RPA 1.0 Global Macro, Dow Jones Edition via WRDS. Weekly article volume counts
per narrative cluster, normalized by total corpus volume that week. Not used for embedding
or clustering — counts only.

**Anchor narratives (10 final, replacing prior 10):**

Removed: FTX collapse (anchor_05), GameStop short squeeze (anchor_02) — out of macro scope.
Added: 2013 taper tantrum (ref: 2013-05-22, Bernanke Senate testimony), 2015 China
devaluation scare (ref: 2015-08-11, PBOC announcement). Renumbered 01–10.

**Key processing decisions:**

- Documents >2,000 words split into 600-token chunks with 100-token overlap before
  embedding. Volume counting uses document count (not chunk count).
- Weekly volume normalization: counts per cluster / total corpus articles that week.
- Two-stage dynamics fitting: parametric models only above 3 articles/week avg over 4
  weeks AND 50 cumulative articles; descriptive stats only below threshold.
- Source-type contamination check: clusters >90% one source type flagged post-hoc.
- FOMC minutes timestamp = release date (not meeting date); NBER papers = posting date.

### Consequences

**Positive:**
- Fully automatable pipeline — no manual ProQuest export step.
- Temporal coverage is uniform across the 2010–present window (institutional sources
  publish continuously; AP News Wayback coverage is consistent).
- Institutional discourse is a cleaner proxy for the causal narrative formation process.
- RavenPack dynamics layer is higher quality and easier to normalize than Wayback counts.
- Anchor set is tighter and more defensible for peer review.

**Negative / risks:**
- Semantic corpus skews toward formal institutional and academic register. If the
  hypothesis is about *public* narrative formation (media → markets), this is a design
  choice that must be disclosed. Mitigation: AP News (Tier 4) provides the popular press
  signal; RavenPack dynamics reflects broader media volume.
- AP News Wayback CDX coverage before ~2016 may be sparse. Monitor in corpus
  composition QA; flag in pre-registration if pre-2016 AP coverage < 50% of later years.
- WRDS access is institutional (UChicago RCC). Reproducibility requires WRDS credentials.
  Mitigation: document WRDS query precisely so others can replicate with own access.

---

## ADR-009: Journalism corpus scope — MarketWatch reinstatement and stated limitations

- **Status**: Accepted
- **Date**: 2026-05-04

### Context

ADR-008 established AP News as the sole Tier 4 (journalism) source in the
semantic corpus. After review, AP News alone was found insufficient: AP is
wire-factual and does not produce the analytical/interpretive framing pieces
where narrative construction happens in financial journalism. The macro-financial
literature distinguishes between event reporting (AP) and narrative formation
(interpretive commentary). The latter is where our clustering signal lives.

Additionally, the prior design left no acknowledged statement about premium
analytical press (WSJ opinion, Bloomberg Opinion, FT) being absent from the text
corpus. This omission could be read as an oversight in peer review; it is better
stated explicitly as a scope constraint with reasoning.

### Decision

**1. MarketWatch reinstated as Tier 4 journalism source.**

MarketWatch fills the interpretive gap AP misses:
- Publishes 15–20 analytical macro pieces per day.
- Fully open access — no paywall, no institutional license required.
- Dow Jones property — consistent editorial standards; also covered by RavenPack
  dynamics layer (rpa_source_id = 'MKW'), enabling cross-validation between text
  corpus and volume signal for the same outlet.
- Historical coverage via Wayback CDX on `www.marketwatch.com/story/`.

Pre-2015 Wayback CDX coverage is thinner. Decision: ingest what is available,
flag records with `sparse_wayback_coverage=True` in raw_metadata, treat corpus
as consistent from 2015-01-01 onward for cross-year comparisons. This asymmetry
is documented explicitly in methodology and pre-registration.

**2. Stated limitation recorded for premium analytical press.**

WSJ opinion, Bloomberg Opinion, and FT are not included in the text corpus
because: WSJ requires ProQuest (pipeline removed in ADR-008); Bloomberg text is
paywalled; FT has Factiva license issues (license prohibits pipeline use).

These outlets' volume signal is partially captured by the RavenPack dynamics
layer (Dow Jones edition covers WSJ, DJN, Barron's, and MarketWatch). This is an
acknowledged scope constraint, not an oversight. It is disclosed in:
- The pre-registration (Appendix A, corpus scope section)
- Methodology section of the technical report
- Dashboard (tooltip on dynamics layer charts)

**3. RavenPack lag and vintage documented.**

RavenPack RPA 1.0 data has approximately a 5-week lag and is delivered as monthly
vintages by design. This is a look-ahead bias protection feature, not a
limitation. All dashboard panels that use RavenPack data are labeled prominently
"as of [last delivered month]". Emergence detection uses own-corpus (Tier 4)
volume counts, which are real-time.

### Consequences

**Positive:**
- Tier 4 now covers both event-factual (AP) and interpretive-analytical
  (MarketWatch) journalism registers, matching the theoretical framing.
- The premium press gap is a stated, documented limitation with a clear rationale
  rather than an implicit omission.
- MarketWatch's dual presence (text corpus + RavenPack dynamics layer) enables a
  cross-validation check: do MarketWatch RavenPack volume counts correlate with
  MarketWatch text-corpus cluster assignments?

**Negative / risks:**
- Pre-2015 MarketWatch coverage asymmetry adds a nuisance covariate to temporal
  analysis. Mitigation: flag in QA output; restrict cross-year comparisons of
  MarketWatch-heavy clusters to 2015+.
- Two Tier 4 sources increase ingestion volume and complexity. Mitigation: both
  use the identical Wayback CDX + RSS architecture via the same module
  (src/mnd/ingestion/apnews.py, class MarketWatchIngestor).

---

## ADR-010: Full project spec overhaul — corpus architecture, embedding model, detection layer

- **Status**: Accepted
- **Date**: 2026-05-11
- **Supersedes**: ADR-001 (two-model embedding), ADR-008 (Phase 2 corpus with AP News), ADR-009 (MarketWatch reinstatement)

### Context

MND_PROJECT_SPEC.md (rev2, 2026-05-11) was written as a comprehensive superseding document after Phase 2 ingestion completed on RCC. Several architectural decisions made during Phase 1 piloting and early Phase 2 planning required consolidation:

1. **Journalism tier (AP News / MarketWatch / Reuters) in semantic corpus**: ADR-008 added AP News as Tier 4; ADR-009 reinstated MarketWatch. Reuters was added 2026-05-07. During Phase 2 review, it became clear that wire journalism adds noise to the semantic clustering — narrative *identity* is determined in institutional and academic discourse, not in wire redistribution. RavenPack (Layer 1B) provides the journalism propagation signal more cleanly and consistently than Wayback CDX retrieval.

2. **Two-model embedding strategy (ADR-001)**: Using Qwen3-Embedding-0.6B as primary with a modern training cutoff increased look-ahead exposure substantially. The spec settles this by reverting to `all-mpnet-base-v2`, whose pre-2021 cutoff is consistent with our historical corpus window. The look-ahead sensitivity check is retained but implemented as a sub-period comparison within the single model run.

3. **CFR added to Tier 2**: ADR-009 dropped CFR ("geopolitical framing dominates"), but the spec reinstates it. CFR's macro-financial coverage of dollar dynamics, sovereign debt, and global monetary policy is distinct from its geopolitical work and is relevant to the corpus.

4. **Media Cloud as Layer 2 detection**: A new detection layer is added — Media Cloud provides daily story count time series by keyword/topic query across thousands of outlets. Its sole role is to detect anomalous narrative volume before institutional sources have characterized it in embeddable text. This does not feed embedding or clustering.

5. **JLN → EPU in validation**: The Jurado-Ludvigson-Ng uncertainty index (accessed via WRDS) is replaced by the Baker-Bloom-Davis Economic Policy Uncertainty index (free direct download). EPU is constructed from the same kind of newspaper text this project analyzes, making it the strongest external benchmark.

6. **NBER and SSRN**: Historical bulk retrieval failed (bot-protected, JavaScript-rendered). Both are retained for Phase 6 live RSS updates only. NBER and SSRN ingestors remain in `src/mnd/ingestion/institutional.py` but are excluded from the institutional RCC ingestion job for the historical corpus.

### Decision

**1. Journalism tier (Tier 4) removed from semantic corpus.** AP News, MarketWatch, and Reuters ingestors are moved to `scripts/archive/`. Raw ingested data remains on RCC (`data/raw/articles/`) but is excluded from embedding by `scripts/filter_corpus_pre_embed.py`. RavenPack provides the journalism volume signal as Layer 1B (dynamics fitting only).

**2. Embedding model: `all-mpnet-base-v2` is the single production model.** The two-model strategy from ADR-001 is superseded. The look-ahead sensitivity check compares pre-2021 and post-2021 sub-period cluster quality using this single model (NMI comparison). The `comparator` config slot is removed.

**3. CFR (Council on Foreign Relations) added as Tier 2 source.** RSS: `cfr.org/rss/all`. `CFRIngestor` added to `institutional.py` and to the `InstitutionalIngestor` composite. The prior exclusion note ("geopolitical framing dominates") is superseded.

**4. Media Cloud detection layer added.** `src/mnd/detection/mediacloud.py` provides daily story count queries. API key: `MEDIACLOUD_API_KEY` in `.env`. Output to `data/detection/mediacloud/`. Does not feed embedding or clustering.

**5. Validation: EPU replaces JLN.** EPU (Baker-Bloom-Davis) is a free download from `policyuncertainty.com`. `WRDS_MFS_*` env vars removed. EPU provides stronger benchmark validity because it is text-based, matching the discourse-measurement methodology.

**6. NBER and SSRN excluded from historical corpus ingestion.** Both ingestors remain in the codebase for Phase 6 live RSS updates. The institutional SLURM job (`ingest_institutional_rcc.sh`) excludes them from the historical run.

**7. FEDS Notes added explicitly to FederalReserveIngestor.** URL pattern: `federalreserve.gov/econres/notes/feds-notes/`. Board economists' fast-response analytical layer, published ~70/yr, was previously not distinguished from FEDS Working Papers.

### Consequences

**Positive:**
- Semantic corpus is now purely institutional and academic register — cleaner clustering signal.
- Single embedding model eliminates the two-model orchestration complexity.
- CFR adds dollar dynamics and global monetary policy coverage absent from other Tier 2 sources.
- Media Cloud detection enables pre-characterization narrative emergence signaling.
- EPU validation is free, text-based, and directly comparable to this system's detection approach.

**Negative / risks:**
- Existing Phase 2 RCC ingestion output (AP News, Reuters, MarketWatch raw JSONL) must be filtered before embedding. `scripts/filter_corpus_pre_embed.py` handles this.
- `all-mpnet-base-v2` is weaker than Qwen3-Embedding-0.6B on MTEB benchmarks. Tradeoff is accepted: the look-ahead bias argument becomes cleaner and the model is sufficient for the institutional corpus register.
- CFR ingestion is RSS-based; historical archive back to 2010 may be incomplete. Corpus composition QA will flag pre-2015 CFR coverage.
- University of Michigan consumer sentiment (`umich_inflation_exp`) remains in `whitelist.yaml` validation supplements for now; user has flagged it for future removal.

---

## ADR-011: Revert primary embedding model to Qwen3-Embedding-0.6B; formalize look-ahead check

- **Status**: Accepted
- **Date**: 2026-05-11
- **Supersedes**: ADR-010 (embedding section only — all other ADR-010 decisions stand)
- **Restores**: ADR-001 (two-model strategy), with enhanced look-ahead check methodology

### Context

ADR-010 replaced the Qwen3-Embedding-0.6B primary model (from ADR-001) with `all-mpnet-base-v2` primarily to minimize look-ahead bias. After review, two problems with that decision:

**1. Context window mismatch with the corpus.** After removing the journalism tier (ADR-010), the semantic corpus is now almost entirely long-form institutional and academic documents:
- FOMC minutes: 10,000–15,000 words
- BIS Quarterly Review articles: 3,000–8,000 words
- Jackson Hole symposium papers: 8,000–15,000 words
- VoxEU full posts: 800–2,500 words
- NBER abstracts (Phase 6): 300–500 words

`all-mpnet-base-v2` has a hard max_seq_len of 384 tokens (~280–300 words). With our headline + body pipeline, this means we embed the headline plus roughly the first 220–250 words of body text. For a 12,000-word FOMC minutes document, that is the first ~2% of the document — systematically missing the staff economic outlook, participants' views on economic conditions, and forward guidance discussion that constitute the majority of the analytical signal. The 600-token article truncation rule in config is irrelevant if the model only attends to 384 tokens.

This context truncation is acceptable for short wire articles (which we've now removed). It is not acceptable for the long-form institutional corpus that is the analytical core of this project.

**2. Look-ahead risk is bounded and measurable, not assumed.** The look-ahead concern with Qwen3 (2025 training cutoff) is real but operates through a specific channel: the model may embed documents with representations influenced by knowledge of how events resolved. Evaluating this risk requires:

- For pre-2015 events (2013 taper tantrum, 2015 China devaluation): Qwen3's knowledge is effectively frozen. These are historicized events with stable interpretive vocabulary; no new outcome information entered the training distribution.
- For 2020–2023 events (COVID crash, SVB, Credit Suisse, soft landing): Qwen3 may embed documents with representations shifted by outcome knowledge. This is the at-risk window.
- The key insight: the risk **can be measured directly** by comparing NMI and silhouette scores on pre-2021 vs post-2021 sub-corpora across Qwen3 and mpnet. If Qwen3 shows dramatically inflated post-2021 cluster quality relative to mpnet, look-ahead is significant. If they track closely, the bias is bounded. This is a better epistemic argument than assuming mpnet is unbiased — mpnet has a 2020-2021 cutoff which means it also has look-ahead exposure on 2020-2021 data.

The honest framing: both models have look-ahead exposure on some of the historical corpus. Qwen3 has more exposure but also far superior context and representational quality. The right response is to measure the exposure, not to assume the weaker model is safe.

### Decision

**1. Restore Qwen3-Embedding-0.6B as the primary production model.** Context window (32,768 tokens) and representational quality are decisive for the long-form institutional corpus. Apache 2.0 license. Run on RCC (CUDA) with full context; local MPS runs use `MND_MAX_SEQ_LEN=512` per ADR-006.

**2. Restore all-mpnet-base-v2 as the comparator model.** Its sole role is the look-ahead sensitivity check — not production embedding. The sensitivity check is now formalized as a quantitative comparison (see below) rather than a qualitative assumption.

**3. Formalize the look-ahead sensitivity check.** The check must:
- Embed a representative sample of all 10 anchor narratives (and their ±3-month surrounding corpus windows) with BOTH Qwen3 and mpnet.
- Compute NMI and mean pairwise silhouette separately for the pre-2021 sub-corpus and post-2021 sub-corpus for each model.
- Report the metric deltas: Δ_NMI(Qwen3) vs Δ_NMI(mpnet) across the temporal split.
- Kill criterion: if Qwen3's post-2021 NMI exceeds pre-2021 NMI by more than 0.15 AND mpnet does not show the same pattern, document as significant look-ahead and add caveat to the pre-registration and methodology section.
- If both models show similar temporal patterns, look-ahead is bounded by corpus vocabulary stability (the expected result for stable institutional register text).

This check is run once after full corpus embedding (Phase 3) and reported in the methodology section. It is not used to change the clustering — it is a diagnostic for the methodology appendix.

**4. Maintain the 600-token article truncation rule in config.** For Qwen3 with 32,768 token context, 600 tokens is well within capacity. For mpnet (384 tokens), the model naturally truncates to 384 tokens regardless of this setting. The config rule still governs the text that is fed to the model; mpnet just truncates further internally.

### Consequences

**Positive:**
- Full analytical content of FOMC minutes, BIS reports, and academic papers is encoded — not just the header text.
- Look-ahead risk is measured, not assumed, which is a stronger methodological argument.
- The temporal sensitivity check produces a reportable finding (even if null) that strengthens the methodology section.

**Negative / risks:**
- Qwen3's 2025 training cutoff means it has seen some of the post-2020 events in this corpus. For SVB (2023), Credit Suisse (2023), and soft landing narrative (2023-2024), the embedding representations may incorporate outcome knowledge. This is disclosed in the pre-registration.
- Instruction-aware prompting prefix required for Qwen3 — adds a small per-document overhead.
- On local MPS runs, MND_MAX_SEQ_LEN=512 is required to avoid OOM (ADR-006). This limits local testing but doesn't affect RCC production runs.

---

## ADR-012: Remove arXiv and Jackson Hole separate ingestor; remove topic filter from Stage 2

- **Status**: Accepted
- **Date**: 2026-05-13

### Context

MND_PROJECT_SPEC rev3 (2026-05-11) identified three issues to fix before running the full corpus pipeline:

1. **arXiv**: Active in `InstitutionalIngestor` but cut from scope in rev3. Reason: arXiv economics coverage was only reliably available from 2017 (the econ category was created in 2017), the macro-relevant volume is low relative to institutional sources, and the preprint abstracts add noise rather than characterizing discourse. arXiv is not in the final spec.

2. **Jackson Hole separate ingestor**: `JacksonHoleIngestor` fetched the Kansas City Fed's proceedings index page (overview text only, not the actual papers). The spec notes that Jackson Hole speeches are delivered by Fed Chair and other governors, published on `federalreserve.gov`, and therefore already captured by `FederalReserveIngestor`. The separate ingestor created duplicates and ingested only low-value overview pages, not the speeches themselves.

3. **Topic filter in Stage 2**: The `filter` pipeline command previously applied keyword-based topic filtering (TopicFilter). This was designed for journalism sources (AP News, MarketWatch) with mixed content. With those sources removed in ADR-010, all remaining Layer 1A sources are macro-relevant by construction — Fed speeches, IMF reports, VoxEU posts, etc. are definitionally in scope. Topic filtering is unnecessary noise that risks incorrectly dropping valid institutional documents.

### Decision

1. **Remove arXiv** from `InstitutionalIngestor._sub_ingestors` and `config/whitelist.yaml`. Archive `src/mnd/ingestion/arxiv.py` → `scripts/archive/arxiv_ingestor.py`.

2. **Remove `JacksonHoleIngestor`** from `InstitutionalIngestor._sub_ingestors` and delete the class from `institutional.py`. Add note to whitelist that Fed Board's speeches ingestor covers Jackson Hole. Jackson Hole speeches are published on federalreserve.gov; they flow through `FederalReserveIngestor` with no gap.

3. **Remove TopicFilter from the `filter` pipeline stage.** Stage 2 now runs: (a) date range filter [2010-01-01, present], (b) MinHash near-duplicate removal. No keyword filter.

### Consequences

**Positive:**
- Corpus ingestion no longer attempts arXiv (which had a 2017 coverage floor) or creates Jackson Hole duplicates.
- Stage 2 filter is simpler and will not incorrectly drop institutional documents that don't contain keyword seeds.
- Ingestion job is cleaner and faster.

**Negative / risks:**
- Any arXiv macro econ abstracts from 2017–present are no longer in the semantic corpus. This is an acknowledged scope constraint (noted in MND_PROJECT_SPEC rev3 §4 removed sources table).
- Jackson Hole speeches are captured only as Fed speeches — they carry `source_id=fed_board` and `document_type=speech`, not a dedicated jackson_hole type. This is correct per the spec.

---

## ADR-013: Post-2024-dry-run fixes — ingestor repairs, IMF re-enable, embed OOM fix, filter-pre-embed in SLURM chain

- **Status**: Accepted
- **Date**: 2026-05-17

### Context

The 2024 dry-run SLURM chain (jobs 49622332–49622335, 2026-05-13/14) surfaced four classes of bugs that must be fixed before the full 2010–present historical submission:

1. **CongressionalIngestor returned 0 articles**: the URL regex `^/news/press-releases/[a-zA-Z]{2}\d+` matched legacy `sb####`/`jy####` slugs only, missing modern `/statements/<slug>`, `/testimonies/<slug>`, `/readouts/<slug>` URL forms. The relevance filter also hardcoded "Economic Fury" as an exclusion, dropping legitimate Bessent-era macro-financial Treasury remarks (it's a policy-branding label, not a topical signal).
2. **CBOIngestor returned 0 articles**: the Drupal listing scraper at `cbo.gov/publications` is now behind DataDome bot protection (HTTP 403 from any non-browser UA). The RSS fallback hits the same bot wall. `cbo.gov/sitemap.xml` is NOT protected and indexes every publication URL with a `<lastmod>` date.
3. **CFRIngestor returned 0 articles**: the RSS feed at `cfr.org/feed` exposes only the most recent ~24 items — zero coverage for any historical window. CFR's sitemap (`/articles/`, `/backgrounders/`, `/reports/`) exposes 24K+ historical URLs but with stamped `lastmod=current-sitemap-build-date`, so lastmod-window filtering is useless and we must filter by URL slug then re-validate dates from each fetched page.
4. **Qwen3 primary embed OOMed on V100 16GB** (job 49622334, allocation 16.07 GiB): SDPA causal mask + KV-cache + activations at `(batch=32, seq=2048, fp16)` exceeded 16 GB. Inference batch size is a perf knob with zero quality impact; same vectors are produced. `max_seq_len` reduction below the chunker's 600-BPE-token output is also lossless. A100 partition switch would also work but adds queue-wait risk.

Additionally, the `filter-pre-embed` stage (canonical ADR-010/012 archived-source exclusion writing `corpus_for_embedding.jsonl`) was not chained between ingest and filter in `submit_full_pipeline.sh`. The filter stage logged a fallback WARNING and applied inline exclusion against the raw_articles directory, but the canonical artifact was never produced.

IMF was set `_HISTORICAL_DISABLED = True` after all hardcoded slug URLs and the `/api/v1/en/publications` JSON API began redirecting to `/en/errors/404`. The contingency in CLAUDE.md anticipated re-enabling once a working retrieval path (Next.js `_next/data/<buildId>` SSG endpoint or `__NEXT_DATA__` payload scrape) was implemented.

### Decision

1. **CongressionalIngestor**: broaden URL regex to `(sb\d+|jy\d+|statements/<slug>|testimonies/<slug>|readouts/<slug>|remarks/<slug>)`. Switch date extraction to prefer `<time datetime=...>` over text regex. Replace the "Economic Fury" hardcoded exclusion with a generic sanctions filter that only excludes when no macro-financial term is present. Add INFO-level per-page diagnostics and a hard-fail when page 0 returns 0 release links (silent-failure prevention).
2. **CBOIngestor**: primary path is `cbo.gov/sitemap.xml` enumeration with a 365-day lastmod slop (CBO does periodic sitemap-wide rebuilds; ~6000 publications got stamped lastmod=2019). Page-date validation in `_fetch_page_full` is the final truth. Legacy archive scrape retained as fallback.
3. **CFRIngestor**: primary path is sitemap enumeration over `/articles/`, `/backgrounders/`, `/reports/` with URL-slug macro pre-filter (~7.6% match rate). Lastmod is ignored. Page-date filtering inside `fetch()` filters into the window. RSS retained as fallback.
4. **Embed OOM**: drop `compute.embedding_batch_size` 32 → 8; drop `embedding.primary.max_seq_len` 2048 → 1024. Both have zero quality impact. Add `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` to `embed_rcc.sh`. Stay on V100 partition.
5. **filter-pre-embed in SLURM chain**: new `scripts/rcc/filter_pre_embed_rcc.sh`, chained between ingest and filter in `submit_full_pipeline.sh`.
6. **IMF**: implement Next.js `__NEXT_DATA__` extraction → recursive walk of pageProps for publication-shaped dicts → `_next/data/<buildId>/<path>.json` SSG endpoint for individual publication bodies. Legacy hardcoded URL tables retained as fallback. Re-enable `IMFIngestor` in the composite list; if both paths return 0 on RCC, the composite handler marks it failed and the chain continues.

### Consequences

**Positive:**
- All four broken ingestors now have functional historical retrieval paths.
- Diagnostic logging is INFO-level, so RCC log files now show per-page item counts, date ranges, and yield counts — silent failures impossible.
- Embed job fits the V100 partition comfortably (~6 GB working set vs 16 GB OOM).
- `filter-pre-embed` is now run automatically; no manual step required.
- IMF coverage MAY return (subject to RCC verification).

**Negative / risks:**
- CFR full historical scrape will fetch ~1800 candidate pages at ~0.5s each (~25 min added to the ingest stage). Acceptable within the SLURM time budget.
- CBO lastmod 365d slop may miss publications that were edited >1 year after publication (a small minority). Acceptable.
- IMF Next.js path is unverified from residential IPs (Cloudflare WAF blocks). Will be confirmed by the next RCC ingest.
- New broader Treasury filter terms (`interest rate`, `recession`, `growth`, `banking`, `credit`, `tariff`, `trade`, `currency`, `dollar`, `tax`) may admit some lower-relevance items. Acceptable; downstream dedup + clustering will absorb.

### Verification

Local smoke tests (residential, 30-day windows):
- Congressional: 3 articles yielded ✓
- CFR: 22,454 + 1,046 + 712 sitemap URLs → 1,843 macro-slug candidates → 3 in-window articles fetched ✓
- CBO: sitemap enumeration yields 500+ in-window-with-slop candidates ✓ (page fetches RCC-only)
- IMF: Next.js + legacy paths execute cleanly with proper 403 handling; 0 yielded from residential (expected)

RCC verification (2026-05-17, Midway3 login node):
- **IMF**: Cloudflare WAF returns HTTP 403 to all `imf.org` URLs from RCC IP space regardless of User-Agent (confirmed with browser UA via both `requests` and `curl`). The Next.js retrieval path is correct but inaccessible from RCC. **`IMFIngestor` re-disabled in the composite list** — re-enable if RCC IP is later unblocked or if a proxy/Wayback retrieval path is implemented. Documented as a corpus limitation in CLAUDE.md.

Other ingestors validated on the next full RCC ingest run.

---

## ADR-014: IMF ingestion via curl_cffi Chrome impersonation + Coveo Search listing

- **Status**: Accepted
- **Date**: 2026-05-17
- **Amends**: ADR-013 (misdiagnosis correction — see "Context")

### Context

ADR-013 disabled `IMFIngestor` in `InstitutionalIngestor._sub_ingestors` after observing HTTP 403 on every `imf.org` URL from RCC's IP space. The diagnosis was "Cloudflare WAF IP block." Both halves of that diagnosis are wrong:

1. **imf.org is fronted by Akamai, not Cloudflare** (`server: AkamaiGHost`). Akamai Bot Manager fingerprints the TLS handshake (JA3/JA4) — stdlib `requests` ships with OpenSSL's cipher list and extension order, which does not match any real browser, and Akamai 403s the request before the HTTP layer is consulted.
2. **The 403 is not IP-based.** Re-running the same stdlib `requests` call from T-Mobile cellular (AS21928, residential) returned 403 with identical headers. Switching the same residential IP to `curl_cffi` with `impersonate='chrome131'` returned 200. The user later confirmed `curl_cffi` returns 200 from RCC as well.

Separately, the Next.js `__NEXT_DATA__` walker that ADR-013 retained as a "fully implemented" retrieval path no longer matches the live site. IMF migrated to Sitecore JSS; `pageProps.componentProps` is now a GUID-keyed map of layout components, and the `AsidePublicationList` in the sidebar only exposes the *latest* issue per series. The actual historical listing on `/publications/<series>` is rendered client-side by a `PublicationIssuesList` React component that calls Sitecore GraphQL (`/api/graphql`) or, more usefully for us, the public Coveo Search endpoint that powers the site-wide search bar (`imfproduction561s308u.org.coveo.com/rest/search/v2`, public Bearer token harvested from the JS bundle).

### Decision

1. **Replace the TLS-layer fix.** `IMFIngestor._imf_get` routes all `imf.org` fetches through `curl_cffi.requests.get` with `impersonate='chrome131'`, falling back to stdlib `requests` only if `curl_cffi` is missing (a loud `ERROR` log makes the failure obvious). Already shipped in commit `ede1de6` (2026-05-17).
2. **Replace the listing-layer fix.** The Sitecore JSS walker (`_walk_publications` + `_NEXT_INDEX_PAGES` + hardcoded `_WEO_PATHS` / `_GFSR_PATHS` / `_FANDD_PATHS` / `_WP_API`) is removed. The new `_coveo_list` queries Coveo with `aq=@uri="<prefix>" @date>=… @date<=…` per series (`weo`, `gfsr`, `fandd`, `wp`, `blog`), paginates to Coveo's 1000-result cap, and recursively bisects the date window when a series exceeds the cap (only the WP series is dense enough to trigger this — ~700 papers/year).
3. **Reuse the existing body-extraction path** with one tweak. `_fetch_publication_body` continues to try `_next/data/<buildId>/<path>.json` first for `/en/publications/*` URLs and falls back to trafilatura on the HTML page. The buildId is now scraped once per `fetch()` from `/en/Publications/WEO` and cached. Blog URLs (`/en/blogs/articles/*`) are not covered by the SSG build (`_next/data` 404s) so they always take the trafilatura path; yields ~800 words/post.
4. **Re-enable `IMFIngestor()` in `InstitutionalIngestor._sub_ingestors`.** RCC composite runs include IMF from this commit forward. The class-level `_HISTORICAL_DISABLED` documentation flag is dropped (no code path consulted it).
5. **Keep `--sources imf` as a debug affordance in `run_pipeline.py`.** Useful for small-window probes of IMF specifically without paying for the full composite cycle; help text and error messages drop the "local-only" framing.
6. **`curl_cffi==0.15.0` is a hard dependency** in `requirements.txt` (MIT-licensed; wraps the curl-impersonate fork of libcurl). Must be installed in the RCC conda env (`mnd`) for IMF retrieval to work.

### Consequences

**Positive:**
- IMF coverage (WEO, GFSR, F&D, WP, Blog) is restored to the semantic corpus with no new infrastructure and no paid dependencies.
- One execution environment, not two. RCC remains the single source-of-truth ingestion host; no local-rsync drift risk.
- The Coveo listing path is more comprehensive than the prior hardcoded URL tables (304 historical WEO entries vs. 30 hardcoded; 16,973 working papers vs. none). Coverage now extends to all WEO/GFSR Updates and F&D individual articles, not just flagship issue landing pages.
- Trafilatura body extraction is well-suited to IMF's HTML — verified ~250 words from WEO Oct 2024 landing page, ~800 words from a representative IMF Blog post.

**Negative / risks:**
- The Coveo Bearer token is harvested from a public JS bundle and may rotate. The token has been stable across the imf.org Next.js rebuilds observed in May 2026, but a future rotation would require re-fetching `/_next/static/chunks/1166-*.js` and updating `IMFIngestor._COVEO_TOKEN`. Failure mode is 401 on the listing call, surfaced via a `WARNING` log; no silent corruption.
- `curl_cffi` is a less common dependency than `requests`. If a future RCC environment rebuild omits it, listing and fetches both fail loudly (the `ImportError` branch in `_imf_get` logs `ERROR`). Mitigated by pinning in `requirements.txt`.
- Akamai Bot Manager could in principle update its fingerprinting heuristics and reject curl-impersonate-chrome131 in the future. If that happens, bump `impersonate='chrome131'` to a newer profile (curl-impersonate ships chrome116 → chrome131 → ...) or pin a specific browser version. Visible as 403s reappearing on every IMF URL.

### Verification

- `from mnd.ingestion.institutional import IMFIngestor; IMFIngestor()` instantiates without error. ✓
- `InstitutionalIngestor()._sub_ingestors` includes `IMFIngestor`. ✓
- Small-window run (`date(2024,9,1)` … `date(2024,10,31)`) yields 80 articles: 1 WEO, 1 GFSR, 24 F&D, 39 WP, 15 Blog, all with body word-count ≥ 50. ✓
- WEO Oct 2024 issue specifically present in output with 254 words of executive-summary text. ✓

### Addendum (2026-06-05): legacy F&D article-level walker for pre-2018 coverage

**Problem.** The 2026-06-04 ADR-028 shape audit (`verify_coverage.py imf`, year × document_type pivot) surfaced a 16x cliff at the `imf_fandd` 2017→2018 boundary (2017=5 vs 2018=81). Probing Coveo for the legacy years showed the `@uri="/en/publications/fandd/issues/"` prefix query returns only whole-*issue* PDFs for pre-2018 F&D — one record per issue in each of en/spa/fre language variants, never the individual *articles*. F&D pre-2018 lived at a different, non-Next.js path that the Coveo prefix never matches, so every legacy F&D article was silently missing from the corpus.

**Why not accept the issue PDFs.** Adding the whole-issue PDFs would trade one cliff for another: the corpus would jump from ~10-15 article-granularity records per issue (2018+) to 1 issue-granularity record per issue (pre-2018), creating a volume discontinuity at the 2017/2018 seam. Per the corpus-correctness principle (no documented limitations), the fix must preserve article-level granularity across the scheme change.

**Decision.** Add `IMFIngestor._fetch_legacy_fandd(start, end)`, wired into `fetch()` after the Coveo series loop. For years in `[max(start.year, 2010), min(end.year, 2017)]` it walks the canonical legacy issue path `https://www.imf.org/external/pubs/ft/fandd/{year}/{mm}/index.htm` (all 12 months tried; non-issue months 404 and self-skip), regex-extracts same-directory `[a-z0-9_-]+\.htm` article slugs (excluding `index.htm`), fetches each article body via `_imf_get` (curl_cffi — verified 2026-06-05 that plain stdlib `requests` 403s at Akamai on the legacy path too), and dates each article from the **issue path** (year/month, first-of-month) — authoritative issue date, never a slug or snapshot guess. The ≥50-word floor applies; nav pages (basics/people/picture) either 404 or fall under the floor and self-drop. Yielded as `document_type="imf_fandd"`, identical to the 2018+ Coveo path, so content-dedup collapses any boundary overlap. 2018+ remains the Coveo `fandd` prefix; the walker is hard-gated to ≤2017 so the two paths do not double-walk.

**Verification.**
- Slug regex against the Wayback copy of `2013/06/index.htm` extracts 19 candidate slugs (real articles + nav pages); nav pages self-drop on 404/word-floor. ✓
- Live legacy article fetch returns 403 to plain `curl` (Akamai), confirming the curl_cffi requirement. ✓
- Post-re-ingest check (pending): `verify_coverage.py imf` must show the `imf_fandd` 2017→2018 cliff gone (legacy years populated to plausible ~40-60 articles/year).

---

## ADR-015: JEL-anchored canonical filter; eliminate inline Stage 1 filters

- **Status**: Accepted (drafted, ratified, and implemented 2026-05-18 during Phase 2 closeout — same day a coverage-bug audit surfaced four ingestor fixes that share the methodology-hardening pre-Phase-4 re-ingest)
- **Date**: 2026-05-18
- **Supersedes**: portions of ADR-012 (which removed a separate Stage 2 topic filter but left inline Stage 1 filters in place)
- **Implemented in**: `config/topic_filter_keywords.yaml` (schema 2.0.0), `src/mnd/ingestion/institutional.py` (`_canonical_topic_keywords()` + `_title_matches_canonical()` helpers; six ingestors refactored), `src/mnd/filtering/topic_filter.py` (backward-compatible `_load_keywords` for both schemas)

### Context

The corpus topic filter currently operates in two stages:

1. **Stage 1 — Per-source inline filter.** Six broad-source ingestors (CBO, NBER, VoxEU, Brookings, CFR, Congressional) each carry a bespoke keyword list inside `src/mnd/ingestion/institutional.py` and apply it to article titles at ingest time. The lists are researcher-derived, ad-hoc per source, and not the same list across sources. Sources without inline filters: IMF, Fed, BIS, Treasury, OFR, fed_regional, PIIE.
2. **Stage 2 — Canonical filter (`src/mnd/filtering/topic_filter.py`).** Loads keywords from `config/topic_filter_keywords.yaml` and applies a two-gate test (≥2 keyword matches AND embedding-similarity vs. seed articles).

The Stage 1 lists are **not a subset of Stage 2** — each source's inline list can drop articles that Stage 2 would have admitted. This means **the corpus is shaped by per-source researcher judgment that is not pre-registered and not audit-traceable.** Pre-registration freeze is coming and this is the kind of methodology softness that requires a defensive "limitations" paragraph.

Separately, the Stage 2 keyword list itself is researcher-derived and not anchored to a field-standard taxonomy. The JEL (Journal of Economic Literature) Classification System maintained by the American Economic Association is the universal classification standard for economics research; anchoring our filter to JEL subcodes makes the operational definition of "macro narrative content" pre-registration-defensible and replication-friendly.

The full audit lives at `docs/filter_audit_jel.md`.

### Decision

1. **Anchor the canonical filter to JEL E/F/G/H scope.** Add a `methodology` block to `config/topic_filter_keywords.yaml` listing in-scope JEL top-level codes (E, F, G) and selected subcodes (F1/F3/F4/F5/F6, G1/G2/G33, H6). Annotate each existing keyword category with the JEL subcode(s) it operationalizes. Bump schema_version to `2.0.0`.
2. **Apply the audit recommendations.** Add ~50 keywords across 11 categories to close JEL subcode gaps (e.g., `r-star`, `inflation breakevens`, `SLOOS`, `BTFP`, `swap lines`, `financial conditions index`, etc.); add a new `named_events` category covering pandemic, Brexit, named legislation (IRA, CHIPS Act) so anchor-relevant content is explicitly captured rather than relying on the embedding gate. Full additions list in `docs/filter_audit_jel.md`.
3. **Eliminate inline Stage 1 filters.** All six broad-source ingestors stop carrying bespoke `_MACRO_TERMS` / `_KEEP_KEYWORDS` lists. The canonical YAML keyword set is loaded at ingest time and applied as a shared Stage 1 filter, identical to Stage 2's keyword set. Same filter at both stages → no asymmetric loss; ingest stays bandwidth-bounded. (Option B in the audit document — strictly faster than option A "no Stage 1 filter at all" with no methodological downside.)
4. **Apply the canonical filter to PIIE as well.** PIIE currently has no Stage 1 filter; after the PIIE undercapture bug is fixed (separately), the article volume will increase substantially and PIIE should be filtered consistently with every other broad source.
5. **NBER's existing JEL-based filter is retained.** NBER papers carry JEL codes natively in metadata; that filter is already JEL-anchored and serves as the canonical reference for sources that don't expose JEL codes.
6. **Document in pre-registration.** Add a "Corpus scope" subsection citing JEL E/F/G/H and pointing at `config/topic_filter_keywords.yaml` as the keyword operationalization, with `docs/filter_audit_jel.md` as the audit record.

### Consequences

**Positive:**

- The operational definition of "macro narrative content" is now citable: JEL E/F/G/H scope, with the keyword list as the audit-traceable operationalization. Pre-registration replaces a half-page "limitations" paragraph with a one-paragraph methodology citation.
- One filter, applied consistently. No per-source researcher judgment shaping the corpus.
- The JEL audit identified ~50 keyword additions (e.g., `inflation breakevens`, `BTFP`, `swap lines`) that close real coverage gaps. Expected to improve anchor recovery for COVID, Brexit, taper tantrum, and China devaluation (the 4 anchors currently failing on the pre-patch corpus per `validate` 2026-05-18 6/10).
- PIIE filter consistency removes an asymmetry that would otherwise need separate justification.

**Negative / risks:**

- Refactor touches six ingestors plus the canonical YAML. Risk of breakage. Mitigated by re-running the `filter` step only (no re-ingest) after the change and re-validating anchor recovery — the loop is cheap (~40 min).
- The `named_events` category contains entity-like terms (pandemic, Brexit, IRA). Risk that the keyword filter drifts toward entity recognition rather than topic operationalization. Mitigated by keeping the `named_events` list small and explicitly cross-referenced to anchor narratives in `data/anchors/anchor_narratives.jsonl`.
- JEL is a 1990-vintage taxonomy and some narrative-economics constructs (e.g., the "soft landing" debate as a self-referential narrative) don't map cleanly to a single subcode. The audit table picks the closest match and accepts that some keywords cross subcode boundaries; this is consistent with how JEL is used in practice (papers typically declare 2-3 JEL codes).

### Implementation steps

1. Author this ADR (this commit).
2. Edit `config/topic_filter_keywords.yaml` per the audit — schema_version 2.0.0, JEL annotations, ~50 additions, `named_events` category.
3. Refactor inline filters: each broad-source ingestor's `_MACRO_TERMS` / `_KEEP_KEYWORDS` constant + `_is_macro_relevant` / `_is_relevant` method is replaced by a shared loader that reads from `topic_filter_keywords.yaml`.
4. Re-run `python scripts/run_pipeline.py filter` (no re-ingest needed; the existing JSONL has more articles than the canonical filter will admit; the filter step's job is to subset it).
5. Re-run `cluster_rcc.sh` and `validate` to confirm the methodology change doesn't regress recovery.
6. Pre-registration update: add Corpus scope subsection.

### Verification

- `from mnd.filtering.topic_filter import TopicFilter; TopicFilter()` loads canonical keywords without error.
- `python scripts/run_pipeline.py corpus-composition` post-refactor shows similar tier-1/tier-2 splits to the current state (gross deviation would indicate a bug).
- `python scripts/run_pipeline.py validate` recovers ≥7/10 anchors post-refactor (validates that methodology hardening doesn't regress signal). Stretch goal: ≥8/10, since the JEL audit added coverage of pandemic/Brexit terminology specifically.

---

## ADR-016: Single-stage topic filtering + Media Cloud Premium as dynamics layer

- **Status**: Accepted (drafted, ratified, and implemented 2026-05-18)
- **Date**: 2026-05-18
- **Supersedes**:
  - ADR-015 partially (the "Option B: canonical Stage-1 mirror of Stage-2" recommendation is rejected here as methodologically asymmetric — see Context (a))
  - ADR-010 partially (the "RavenPack RPA via WRDS = Layer 1B" architecture is replaced by Media Cloud Premium Press — see Context (b))
  - ADR-008 partially (the "AP News + RavenPack" Phase 6 update plan is replaced by Tier 1/2 periodic re-ingest + Media Cloud Premium — see Context (c))

### Context

Three issues surfaced during the 2026-05-18 Phase 2 closeout review.

**(a) ADR-015 Stage-1 inline filter is asymmetric to Stage-2.** ADR-015 replaced six per-source bespoke title-filters with a shared "canonical" title filter using the same keyword list as Stage 2. The audit claimed "no asymmetric loss because Stage 1 and Stage 2 use the same keyword list." This claim is wrong: Stage 1 filters on **title only with ≥1 keyword** while Stage 2 filters on **title + body with ≥2 keywords + embedding similarity**. An article titled "What Happens Next?" with a Fed-policy body fails Stage 1 (no title keyword) and would have passed Stage 2 (body keywords + embedding similarity). The current corpus may already be asymmetrically truncated; pre-registration must defend a corpus shaped by a title-only pre-filter that Stage 2 doesn't apply.

**(b) The RavenPack-via-WRDS dynamics layer was never implemented or used.** ADR-010 declared RavenPack RPA 1.0 the Layer 1B journalism dynamics source. The implementation (`src/mnd/ingestion/ravenpack.py`) requires a WRDS subscription and ~5-week monthly-vintage delivery cadence. The detection layer is sourced from Media Cloud (free academic access, near-realtime). Using two different APIs and access methods for two operationally identical roles (journalism volume aggregation) is unnecessary surface area. Media Cloud supports per-outlet-collection queries — the same API serves both Layer 1B (premium-press collection: WSJ, Bloomberg, FT, Reuters, Barron's, Dow Jones, MarketWatch, etc.) and Layer 2 (broad collection).

**(c) Phase 6 update plan named "AP News RSS + RavenPack live."** AP News was removed from the semantic corpus in ADR-010. The Layer 1B switch in (b) means RavenPack is also out. The Phase 6 update mechanism is unspecified in light of these removals. Periodic re-ingest of Tier 1 + Tier 2 institutional/academic sources captures new analytical text; Media Cloud Premium captures new journalism volume. No third "live RSS" mechanism is needed.

### Decision

1. **No Stage 1 topic filter.** Every per-source inline `_is_macro_relevant` / `_is_relevant` topic check is removed. Topic relevance becomes a single decision made at Stage 2 (`src/mnd/filtering/topic_filter.py`) using `config/topic_filter_keywords.yaml` over title + body with the keyword + embedding two-gate test. The canonical YAML (schema 2.0.0 from ADR-015 with JEL annotations + 234 keywords) is the only topic operationalization.

2. **Preserve structural-only Stage 1 filters.** Filters that drop articles by *type* (not topic) remain:
   - **Congressional `_is_relevant`**: drops sub-Secretary-level releases (under-secretary, assistant secretary, deputy). Tier-1 ingestion is Secretary-level by definition.
   - **CFR `_RELEVANT_SECTIONS`**: limits sitemap walk to `/articles/`, `/backgrounders/`, `/reports/` (skips `/podcasts/`, `/events/`, `/experts/`, `/explainer-videos/`). URL-section structural filter, not topic.
   - **Date-window filters** in every ingestor. Structural.
   - **Word-count minimums** (≥50 words for the body to be considered analytical text). Structural.

   Removed: CBO `_KEEP_KEYWORDS`, VoxEU `_MACRO_TERMS`, Brookings `_MACRO_TERMS`, CFR `_MACRO_TERMS` AND `_URL_MACRO_TOKENS` (the URL-slug topic pre-filter — this also dropped relevant articles asymmetrically), Congressional sanctions-de-dup + canonical title check.

3. **Layer 1B journalism dynamics = Media Cloud Premium Press.** Daily/weekly story counts per canonical-filter keyword across the Media Cloud premium-press outlet collection (WSJ, Bloomberg, FT, Reuters, NYT, Barron's, Dow Jones, MarketWatch, AP Business, etc.). Free academic access, no WRDS subscription, near-realtime indexing.

4. **Single Media Cloud module serves both Layer 1B and Layer 2.** `src/mnd/detection/mediacloud.py` is extended (separate work item) to support per-outlet-collection scoping — premium for 1B dynamics, broad for 2 detection. One API surface.

5. **`src/mnd/ingestion/ravenpack.py` is deprecated.** File retained for reference; module-level docstring is prepended with a DEPRECATED notice. Not imported, not invoked. `WRDS_*` env vars are obsolete.

6. **Phase 6 continuous-update mechanism: re-ingest, not RSS.** Same `run_pipeline.py ingest --sources institutional` job that powers the historical run, scheduled weekly, with checkpoint-based dedup catching new publications since the prior run. SSRN-style RSS-only sources supplement only where institutional sites lack bulk historical access.

7. **CBO accepted as a documented coverage gap.** A Wayback CDX fallback for CBO was prototyped during this commit's drafting and rejected: it would introduce a single-source-specific retrieval path (no other source uses Wayback), snapshot timestamps ≠ publication dates, patchy coverage, and a new methodology limitation to defend in pre-registration. CBO remains zero records until cbo.gov direct retrieval works (would require a headless-browser layer — separate ADR if pursued).

### Consequences

**Positive:**

- The corpus is shaped by exactly one topic decision applied at one well-defined place. Pre-registration sentence: *"Topic relevance is defined operationally by `config/topic_filter_keywords.yaml` v2.0.0 applied with ≥2 keyword matches + embedding similarity threshold at `src/mnd/filtering/topic_filter.py`. No ingest-time topic filter is applied."* No "but some sources also do this at ingest" caveat.
- One API for both journalism-volume roles. No WRDS subscription. No two-API mental model.
- Phase 6 update mechanism reuses the historical-ingest code; no separate live-RSS subsystem to maintain.
- CBO gap is honest and defensible: "DataDome blocks our direct fetcher; we accept it rather than introduce a one-off workaround."

**Negative / risks:**

- **Ingest throughput drops substantially.** Brookings alone: prior canonical-filter pre-fetch kept ingest under an hour; content-neutral ingest of ~48,000 Brookings articles over 2010-2026 at ~1 fetch/s is ~13h. CFR similarly. VoxEU. Total full-corpus ingest moves from ~6-8h to an estimated 20-30h. This is wall-clock, not money. Amortized: ingest happens once per major re-run.
- **More raw JSONL on disk** (rough estimate: 300 MB → 1-1.5 GB before Stage 2 filter dedup). Within scratch budget.
- **The 47/47 unit tests previously asserted that no Stage 1 filter is present is a TODO** — they pass because nothing currently exercises filter behavior; a regression-test sub-task is added.
- **Media Cloud Premium implementation is still TODO.** This ADR ratifies the architecture; the actual extension to `mediacloud.py` for premium-collection queries is a follow-on commit before Phase 4 freeze.

### Implementation steps (this commit)

1. **Code:** `src/mnd/ingestion/institutional.py` — strip topic title-filter call sites from CBO sitemap path, CBO `_fetch_archive`, CBO `_fetch_rss`, VoxEU `_fetch_year`, Brookings `fetch`, CFR sitemap walk + `_fetch_rss`; delete `_URL_MACRO_TOKENS` set from CFR; reduce Congressional `_is_relevant` to the role-guard only (sanctions-de-dup and canonical topic gate are gone — Stage 2 catches them on the body). NBER (inactive in Phase 2) retains its JEL-primary + canonical-fallback logic; flagged for a Phase-6 revisit.
2. **Code:** `src/mnd/ingestion/ravenpack.py` — deprecation docstring at module top.
3. **Docs:** CLAUDE.md, MND_PROJECT_SPEC.md, README.md — replace every "RavenPack/WRDS" mention with "Media Cloud Premium Press"; update Phase 6 plan; remove WRDS env var instructions; mark `ravenpack.py` as deprecated in file-locations table.
4. **Docs:** This ADR.

### Implementation steps (deferred, before Phase 4)

5. Extend `src/mnd/detection/mediacloud.py` with a `query_premium_collection()` function that targets the Media Cloud premium-press outlet IDs. Output: `data/dynamics/mediacloud_premium/` weekly volume series.
6. Update `run_pipeline.py ingest-dynamics` to call the Media Cloud Premium querier instead of (the never-invoked) RavenPack ingestor.
7. Pre-registration update: add "no ingest-time topic filter" disclosure; update Layer 1B source citation to Media Cloud Premium.

### Verification

- `grep -nE "_MACRO_TERMS|_KEEP_KEYWORDS|_URL_MACRO_TOKENS" src/mnd/ingestion/institutional.py` returns no matches.
- `grep -nE "RavenPack|WRDS_" CLAUDE.md MND_PROJECT_SPEC.md README.md` returns only deprecation-marker mentions.
- 47/47 unit tests pass.
- After the full re-ingest (NUKE_RAW=1), `corpus-composition --by-tier` shows substantially higher raw counts on Brookings / CFR / VoxEU and higher filter-stage admission counts when Stage 2 evaluates the now-unfiltered titles' bodies. Anchor recovery target: ≥8/10 (was 6/10 pre-coverage-fix and pre-filter-cleanup).

---

## ADR-017: Coverage-gap closures + Phase 6 scope freeze

- **Status**: Accepted (drafted, ratified, and implemented 2026-05-19)
- **Date**: 2026-05-19
- **Supersedes**:
  - ADR-013 (which characterized CBO as a coverage gap pending headless-browser layer)
  - ADR-010 partially (which kept NBER and SSRN on the books for Phase 6 live RSS — both are now removed entirely)
  - ADR-016 partially (which accepted CBO as a documented gap — now closed via Playwright)

### Context

Three issues surfaced during the 2026-05-19 source-coverage audit:

**(a) CBO is a needed source, not an acceptable gap.** ADR-016 accepted CBO's zero-records state as a documented coverage gap. On review, CBO publications (Budget and Economic Outlook, Long-Term Budget Outlook, Working Papers, scoring reports) are foundational to U.S. fiscal narrative analysis. Anchor coverage for fiscal narratives (debt ceiling, stimulus, deficit framing) is materially weaker without CBO. The "documented gap" position was an unnecessary concession.

**(b) Multiple Tier 1/2 sources are undercaptured in ways the prior re-ingest plan does not fix.** Audit of source counts vs. expected production:
- PIIE: 179 records vs. ~500-800/year expected (~10x undercapture). Cause: title-only listing-fallback logic dropping records when body fetch fails; teaser selector too narrow.
- BIS: 1,057 records — captures Working Papers only. BIS Quarterly Review (~16-24/yr), Bulletins (~10-20/yr since 2020), and curated central-bank speeches (hundreds/yr) are not ingested.
- Treasury: 160 OFR-only is correct for OFR's small output, but the labeling is confusing — Treasury Secretary press releases (the bulk of Treasury content) are captured under `congressional` source_id. Documented rather than restructured (renaming source_id would break existing data alignment).
- ADR-016 removed Stage 1 topic filters so all three will pick up more under content-neutral ingest. But the structural scraper gaps (selectors, missing series) require code fixes, not just filter removal.

**(c) Phase 6 scope drift.** ADR-010 specified NBER and SSRN as Phase-6-only live RSS sources. ADR-016 documented Phase 6 = Tier 1/2 re-ingest + Media Cloud Premium. The continued presence of NBER/SSRN in the live-only list is methodologically untidy — Phase 6 should be a clean scope. User directive (2026-05-18): "nothing new should be added to live except Media Cloud for premium press propagation."

### Decision

1. **CBO via Playwright + curl_cffi hybrid (ADR-013 reopened and closed).** `CBOIngestor._acquire_cookies()` launches a headless Chromium via Playwright once per ingest run to clear DataDome's JS challenge and capture clearance cookies (~3-5s, one-time). `_cbo_get()` then uses curl_cffi with those cookies for the ~25,000-URL sitemap walk (~3.5h at 0.5s/fetch). On a burst of 50 consecutive 403s mid-walk, cookies are invalidated and re-acquired up to 3 times before the run gives up. Requires `playwright==1.48.0` + `python -m playwright install chromium` (one-time per env; ~300 MB). Setup script: `scripts/install_playwright_for_cbo.sh`.

2. **PIIE rewrite.** Replace title-only listing fallback with explicit body-required emission. Broaden teaser selector to `.teaser` (handles `<article>` and `<div>` variants). Add per-page logging of in-window / body-failed / emitted counts. Expectation: PIIE volume jumps from ~179 to ~1,000-2,000.

3. **BIS expansion.** Replace the single working-paper regex with a dispatching list covering Working Papers + Quarterly Review articles + Bulletins + curated central-bank speeches + a catch-all for other `/publ/` HTML. Per-section count logging per year. Expectation: BIS volume jumps from ~1,057 to ~5,000-8,000 (most growth from BIS-republished speeches).

4. **Treasury: clarify, do not restructure.** Document that Treasury Secretary press releases are ingested under `congressional` source_id (and have been since the original design). OFR research stays under `treasury_ofr`. Both will pick up additional content under the ADR-016 content-neutral ingest. No code rename — would invalidate existing data alignment.

5. **NBER and SSRN removed entirely.** Already commented out of `InstitutionalIngestor._sub_ingestors` for historical runs. Now also removed from any Phase 6 plan. The classes survive in code as inactive reference but are NOT in any pipeline path. CLAUDE.md and MND_PROJECT_SPEC.md updated.

6. **Phase 6 scope frozen.** Phase 6 = (i) periodic re-ingest of every Tier 1/2 source already in `InstitutionalIngestor._sub_ingestors`, plus (ii) Media Cloud Premium Press live volume. Nothing else. No "live RSS only" sources. No AP News, no NBER, no SSRN, no separate live ingestors.

### Consequences

**Positive:**

- CBO becomes a first-class source. Fiscal-narrative anchor recovery (debt ceiling, stimulus, IRA, CHIPS Act, deficit framing) gains a major signal.
- PIIE and BIS volume jumps mean fuller coverage of international macro (PIIE) and financial-stability narratives (BIS).
- Phase 6 scope is unambiguously defined: re-ingest + Media Cloud Premium, period. Pre-registration line is clean.

**Negative / risks:**

- Playwright + Chromium adds ~300 MB to each conda env and a one-time setup step on RCC. Documented in `scripts/install_playwright_for_cbo.sh`.
- Playwright sessions are slower to launch than curl_cffi calls; the per-URL average is unchanged because cookies are reused, but if DataDome rotates cookies often mid-walk, we eat 3-5s per re-acquisition. Bounded by the 3-attempt cap.
- DataDome may detect and challenge Playwright too (real-Chrome impersonation is harder to defeat than TLS impersonation, but not impossible). If they do, we revisit — likely with `playwright-stealth` or moving Chromium binary off the well-known path.
- PIIE rewrite drops the title-only fallback. Pages that fail body fetch (residential-IP variants) won't be in the corpus at all, vs. the prior title-only stub. From RCC's university IP, body fetch should succeed; if not, the per-page log surfaces the failure rate.
- BIS speeches via `/review/r\d+.htm` are mostly third-party central bankers (Carney, Lagarde, Powell speaking at non-Fed events). They're curated by BIS but not BIS staff output. Section labeling distinguishes them.

### Implementation steps (this commit)

1. `src/mnd/ingestion/institutional.py`:
   - `CBOIngestor`: add `_cookie_cache` class state, `_acquire_cookies()`, `_invalidate_cookies()`; rewire `_cbo_get()` to use cookies; replace fail-fast 50-403 abort with cookie-reacquire-then-abort (3 attempts max).
   - `BISIngestor`: replace single regex with `_URL_PATTERNS` list (working_paper, quarterly_review, bulletin, speech, other_publication); per-section count logging.
   - `PIIEIngestor`: broaden selector to `.teaser`; remove title-only fallback; require body ≥50 words; per-page logging.
2. `requirements.txt`: add `playwright==1.48.0`; note `playwright install chromium` is required; remove RavenPack/WRDS comment block.
3. `scripts/install_playwright_for_cbo.sh`: new one-time setup script with sanity check.
4. Docs: CLAUDE.md and MND_PROJECT_SPEC.md remove NBER/SSRN Phase 6 mentions; Phase 6 scope clarified.
5. This ADR.

### Verification

- `python scripts/install_playwright_for_cbo.sh` succeeds in the mnd conda env on RCC.
- `python -c "from mnd.ingestion.institutional import CBOIngestor; CBOIngestor._acquire_cookies()"` returns True from RCC and prints the cookie names.
- 47/47 unit tests pass.
- After the next full re-ingest (NUKE_RAW=1):
  - CBO source_id present in the JSONL with >1,000 records.
  - BIS records include `section in (working_paper, quarterly_review, bulletin, speech)`.
  - PIIE records >1,000.
  - No NBER or SSRN records (sources commented out of `_sub_ingestors`).

---

## ADR-018: Remove `named_events` keyword category to eliminate anchor-recovery circularity

- **Status**: Accepted (drafted, ratified, and implemented 2026-05-19)
- **Date**: 2026-05-19
- **Supersedes**: ADR-015 partially (canonical filter keyword list — `named_events` category dropped)

### Context

The `config/topic_filter_keywords.yaml` schema 2.0.0 (ADR-015) included a
`named_events` category of 21 keywords explicitly added to capture anchor-
relevant content. Audit on 2026-05-19 surfaced a circularity:

| Anchor | `named_events` keywords that match anchor `key_terms` |
|---|---|
| 01 SVB collapse | Silicon Valley Bank, SVB |
| 02 COVID market crash | COVID-19, COVID, pandemic, lockdown |
| 03 Brexit aftermath | Brexit, referendum, Article 50 |
| 05 Credit Suisse stress | Credit Suisse |
| 06 Regional banking contagion | First Republic |
| 09 2013 taper tantrum | taper tantrum |

Thirteen of the 21 keywords are entries from the anchor `key_terms` lists
themselves. Anchor-recovery scoring on a corpus filtered using those same
keywords is partially circular: the metric measures whether the system
re-discovers narratives we explicitly selected for in the filter. This
weakens the pre-registration story — reviewers will read it as
researcher-injected confirmation.

The remaining 8 entries are real policy/event entities (Ukraine invasion,
Russian sanctions, Inflation Reduction Act, IRA, CHIPS Act, Build Back
Better, American Rescue Plan, reopening). These are not anchors, but are
still researcher-named choices — and they are redundant with existing
JEL-anchored categories:
- Ukraine invasion / Russian sanctions → already covered by
  `shocks_and_geopolitics_macro` (sanctions, geopolitical risk, energy
  crisis, oil price shock).
- IRA / CHIPS / BBB / ARP → already covered by `policy_fiscal` (fiscal
  policy, stimulus, government spending) when articles discuss these bills
  in macro-policy framing (the framing we want to capture).

Under `filtering.topic.keyword_min_matches: 2`, every genuine
macro-narrative article hits ≥2 JEL-conceptual terms in body text
regardless of whether a single named-entity keyword is in the list. The
recall risk of dropping `named_events` is therefore small in practice,
and removing it cleans up the pre-registration story.

The 2-match threshold is the key design feature making this safe: even
an article that mentions "SVB" only once will, in any realistic financial
journalism or policy text, also contain "bank failure", "deposit run",
"regional banks", "FDIC", "BTFP", etc. — all of which are in
`banking_and_financial_stability` with JEL G21/G28 anchoring.

### Decision

**Drop the entire `named_events` category from
`config/topic_filter_keywords.yaml`.** No replacement — no relocated
keywords, no migration. The JEL-anchored categories already cover the
genuine macro signal in articles about these events.

Companion edits in the same commit:

1. Update the YAML header to remove the stale Stage-1 application claim
   (post-ADR-016 there is no Stage 1 topic filter); call out explicitly
   that no anchor-named entities appear in the canonical list.
2. Update `methodology.stage_policy` to reflect Stage-2-only application
   and reference ADR-016 + ADR-018.
3. Bump `schema_version: "2.0.0"` → `"2.1.0"`.
4. Update `docs/filter_audit_jel.md`: move status from "draft" to
   "ratified by ADR-015 / 016 / 018"; update the architecture description
   to single-stage; preserve the pre-ADR-016 two-stage account as a
   "Historical" section for the record.

No code changes: `src/mnd/filtering/topic_filter.py` iterates `categories`
without referencing any category by name.

### Consequences

**Positive:**

- Pre-registration story is materially cleaner. Anchor recovery becomes a
  clean test of body-text matching against JEL conceptual vocabulary
  rather than partial re-discovery of researcher-named entities.
- Single source of truth for what "in scope" means: JEL E (macroeconomics),
  F (international), G (financial), H6 (fiscal), with the audit document
  enumerating every subcode and what it operationalizes. No special-case
  named entities to defend separately.
- Filter becomes a smaller, simpler artifact (213 keywords vs. 234).
- The methodology-foolproof principle (anchor methodology to field-
  standard taxonomies rather than researcher-derived ad-hoc choices,
  per user directive 2026-05-18) is reinforced.

**Negative / risks:**

- Articles narrowly about IRA/CHIPS/BBB that mention the bill by name
  but contain no other macro vocabulary in body text will be missed by
  the keyword gate. Estimated impact: small for the long-form content
  we ingest (institutional research, policy briefs, academic columns),
  most of which uses domain vocabulary throughout. Worth re-verifying
  during post-re-ingest filter QA.
- A reviewer arguing "the system should find SVB because that's where
  the SVB news lives" can be answered with: yes, and it does — through
  `bank failure`, `deposit run`, `regional banks`, `FDIC`, `BTFP`,
  `unrealized losses`, every one of which appears in any SVB article
  worth clustering. The filter doesn't need "SVB" in its keyword list
  to find SVB articles; it just needs to know what banking-stress
  vocabulary looks like.

### Implementation steps (this commit)

1. `config/topic_filter_keywords.yaml`: delete `named_events:` block;
   update header comment; update `stage_policy`; bump `schema_version`.
2. `docs/filter_audit_jel.md`: status → ratified; new "Current"
   architecture section reflecting single-stage + named-events removal;
   pre-ADR-016 architecture moved into "Historical" section.
3. This ADR.

### Verification

- `pytest tests/test_filtering.py` continues to pass (8/8). The filter
  loader iterates `categories` without referencing `named_events`.
- After the next full re-ingest, post-Stage-2 corpus composition should
  remain within ±10% of the prior post-Stage-2 count. A larger drop
  would indicate the named-entity hit was load-bearing in practice
  rather than redundant.
- Anchor recovery target ≥8/10 on the post-re-ingest corpus. If recovery
  drops noticeably below the pre-removal baseline, that itself is
  evidence the prior filter was performing anchor-name-matching rather
  than genuine narrative recovery — which is the failure mode we wanted
  to surface, not paper over.

---

## ADR-019: Comprehensive methodology lock-in to field-accepted anchors

- **Status**: Accepted — implemented. Embedder choice (0.6B sole embedder) later superseded by ADR-036 (Qwen3-Embedding-8B on RCC, 0.6B local fallback).
- **Date**: 2026-05-20
- **Supersedes**:
  - ADR-001 (partial) — comparator (mpnet) embedder role removed
  - ADR-008 (partial) — chunker 600/100/>2000 superseded by 512/64/no-threshold; `gompertz` and `exponential` dropped from `models_to_fit`
  - ADR-011 (full) — comparator + look-ahead Δ_NMI apparatus removed entirely; the negative finding from the prior look-ahead check is preserved in the project history as evidence, not as a methodology element
  - References to "kill criteria" in any prior ADR — these are removed; quantities are reported, not gated

### Context

A 2026-05-19 audit of `config/config.yaml` and the surrounding pipeline code surfaced ~22 parameters and three architectural pieces that were researcher-chosen without a published anchor, plus a small number of silent BERTopic-default mismatches. The user's stated methodology principle ("everything anchored or removed; no sensitivity sweeps; not a parameter-exploration paper") forces a comprehensive lock-in.

Findings from the audit and parallel field research (see `docs/related_work.md`):

1. **Five BERTopic parameters in `clustering.yaml` silently differ from library defaults** (`umap.min_dist`, `hdbscan.min_cluster_size`, `hdbscan.min_samples`, `ctfidf.reduce_frequent_words`, `ctfidf.bm25_weighting`) — researcher-chosen overrides that were never flagged as such.
2. **The 600/100/>2000 chunker recipe (ADR-008) has no published anchor.** Empirical check: chunker uses `tiktoken.cl100k_base` (GPT-4 BPE) but the embedder uses Qwen3's SentencePiece — 600 cl100k tokens ≈ 660 Qwen3 tokens, which fits within the production `max_seq_len=1024` but the mapping is not cited. Field-standard retrieval chunk size is 512 tokens per Thakur et al. 2021 *BEIR* (NeurIPS).
3. **Three-tier granularity merging** (fine 200 / medium 60 / coarse 15 with silhouette thresholds 0.30/0.45/0.60) has no anchor. Every published BERTopic / LDA narrative study (Bybee et al. 2024 *JF*; Hansen et al. 2018 *QJE*; Larsen & Thorsrud 2019 *JoE*; Bertsch et al. 2021 *Economics Letters*) reports at a single granularity.
4. **The comparator (mpnet) look-ahead sensitivity check (ADR-011)** is exactly the kind of researcher-introduced robustness apparatus the new principle excludes. The negative finding it produced is preserved as evidence; the apparatus itself is removed.
5. **Kill-criterion thresholds** — `required_anchors_recovered: 7/10`, `min_bootstrap_nmi: 0.40`, `min_r_squared: 0.30`, `max_r0_ci_width: 2.0`, plus the `validation.lookahead_check.fail_threshold: 0.15` — are researcher-set binary cutoffs with no literature anchor. Reporting the rate / value is honest; gating on a threshold pre-registers researcher judgment as rigor.
6. **Source-stratified smoothing** (`smooth.py` retains a journalism-tier sentinel + stratifies institutional/academic) has no literature anchor. A 7-day centered MA on combined volume is standard time-series practice (Shumway & Stoffer) and was the implicit underlying claim anyway.
7. **`prepare_text_for_embedding(max_tokens=600)`** has broken whitespace-token math (600 whitespace-words ≈ 1662 Qwen3 tokens — exceeds even the production 1024 cap) and is only called from the filter path. Embed pipeline correctly bypasses it.
8. **Several inactive code paths** continue to exist in the repo: `ravenpack.py` (deprecated by ADR-016), `wayback.py` (retained-for-reference per `__init__.py`), `NBERIngestor` + `SSRNIngestor` (commented out of `_sub_ingestors` in institutional.py per ADR-017). Per the "anchored or removed applies to abandoned pieces too" principle, these get deleted.
9. **Several dynamics models** lack a defensible anchor for this substrate. SIR (Kermack & McKendrick 1927) and logistic (Verhulst 1838) are the classical anchors. Gompertz (1825, biological growth) and bare exponential have no narrative-economics citation that justifies them as primary fits — they're early-stage approximations to SIR/logistic. Drop from `models_to_fit`.
10. **The `embedding_similarity_threshold: 0.55`** in the filter has no literature anchor — Reimers & Gurevych 2019 report task-tuned operating points, not a universal value. Remove the embedding gate from the filter; rely on the JEL keyword gate + downstream clustering.
11. **`bootstrap_replicates: 20`** is far too low for confidence interval estimation. Efron & Tibshirani 1993 recommend ≥500-1000 for CIs. Bump to 1000.
12. **`dedup.window_hours: 48`** has no anchor — full-corpus MinHash LSH is feasible at this scale, so remove the window.

### Decision

Every parameter below is set to either a published library default (cited) or a primary-literature value (cited). Parameters with no defensible anchor are removed.

#### A. Text processing & chunking

| Parameter | New value | Anchor |
|---|---|---|
| Tokenizer used by chunker | Qwen3 SentencePiece (the embedder's own tokenizer) | Eliminates cl100k↔SentencePiece mismatch |
| Chunk size | **512 tokens** | Thakur et al. 2021 *BEIR* (NeurIPS), "first 512 word pieces within all documents" |
| Chunk overlap | **64 tokens** (~12.5%) | LangChain/LlamaIndex library-default band (10-20%); no primary anchor, documented as library convention |
| Chunk-only-if-words>N threshold | **REMOVED** | No primary anchor; chunk uniformly; documents that fit within 512 tokens produce one chunk naturally |
| `prepare_text_for_embedding` helper | **REMOVED** | Broken whitespace-token math; bypassed by embed pipeline; rely on chunker for length-bounding |

#### B. Filtering

| Parameter | New value | Anchor |
|---|---|---|
| `keyword_min_matches` | **Keep at 2** | No primary anchor; documented as "single-keyword false-positive guard" — basic statistical reasoning, not asserted as field-standard |
| `embedding_similarity_threshold` | **REMOVED** (filter Gate 2 dropped) | No literature anchor; task-specific calibration would be researcher-derived. Keyword gate alone + downstream clustering is cleaner |
| `minhash.num_perm` | 128 (no change) | Broder 1997; `datasketch` library default |
| `minhash.threshold` | 0.85 (no change) | Henzinger 2006 mid-band for near-duplicate web pages |
| `dedup.window_hours` | **REMOVED** | No primary anchor; full-corpus MinHash LSH feasible at this scale |

#### C. Embedding

| Parameter | New value | Anchor |
|---|---|---|
| Primary embedding model | `Qwen/Qwen3-Embedding-0.6B` (no change) | Apache 2.0; top of MTEB clustering benchmark; instruction-aware |
| `max_seq_len` | 1024 (RCC) / 512 (local MPS) (no change) | Hardware constraint, not methodology choice |
| Comparator embedder (mpnet) | **REMOVED** | ADR-011's look-ahead sensitivity-check apparatus excluded under "anchored or removed". Negative finding preserved as historical evidence |
| `instruction_prefix` | "Represent this financial policy document for narrative clustering" (no change) | Qwen3 model-card recommended pattern for instruction-aware retrieval |

#### D. Clustering (BERTopic — 5 library-default fixes + 2 removals)

| Parameter | Old | New | Anchor |
|---|---|---|---|
| `umap.n_neighbors` | 15 | **15** (no change) | BERTopic + umap-learn default |
| `umap.min_dist` | 0.1 | **0.0** | BERTopic v0.16.4 default (overrides umap-learn's 0.1 for denser clusters) — Grootendorst 2022 |
| `umap.n_components` | 5 | **5** (no change) | BERTopic default |
| `umap.metric` | cosine | **cosine** (no change) | BERTopic default |
| `hdbscan.min_cluster_size` | 20 | **10** | BERTopic default — Grootendorst 2022 |
| `hdbscan.min_samples` | 5 | **None** (remove key, let library default to None) | BERTopic + hdbscan default |
| `hdbscan.cluster_selection_method` | eom | **eom** (no change) | BERTopic + hdbscan default |
| `hdbscan.metric` | euclidean | **euclidean** (no change) | BERTopic default (operates on UMAP-reduced space) |
| `hdbscan.sweep_min_cluster_size` | [10,20,40] | **REMOVED** | Sensitivity sweep — researcher choice; fixed at library default |
| `ctfidf.reduce_frequent_words` | true | **False** | BERTopic `ClassTfidfTransformer` default |
| `ctfidf.bm25_weighting` | true | **False** | BERTopic `ClassTfidfTransformer` default |
| `granularity` (fine 200 / medium 60 / coarse 15) | — | **REMOVED entirely** | No anchor; published BERTopic/LDA narrative studies all report at single granularity |
| `granularity.silhouette_thresholds` | 0.30/0.45/0.60 | **REMOVED entirely** | Same |

#### E. Dynamics & fitting

| Parameter | New value | Anchor |
|---|---|---|
| `models_to_fit` | **["sir", "logistic"]** (Gompertz + exponential removed) | SIR — Kermack & McKendrick 1927; logistic — Verhulst 1838. Gompertz (biological growth, 1825) and exponential have no narrative-economics anchor; SIR's early phase approximates exponential anyway |
| **Primary volume signal for SIR/logistic fitting** | **Institutional discourse volume** (weekly count of articles in cluster published in institutional + academic corpus) | The project's intellectual claim is that narratives form upstream of journalism in policy/academic discourse — so fitting to institutional volume measures the formation process directly. Premium-press and broad-press volume (Media Cloud) are secondary cross-validation signals, not the fit target. This supersedes the framing in ADR-016 / current CLAUDE.md that listed Media Cloud as the SIR/logistic primary signal (an artifact of the RavenPack→Media Cloud migration). |
| `smoothing_window_days` | 7 (no change) | Shumway & Stoffer — natural weekly cycle for daily count data |
| Source-stratified smoothing | **REMOVED** | No literature anchor; single 7-day MA on combined weekly volume is the standard time-series approach |
| Bayesian priors (β, γ, log L, k) | **Re-elicited per Bjørnstad 2018 + Gelman BDA3 weakly-informative conventions** — specific values deferred to implementation commit; if the elicitation is non-trivial it gets a separate sub-ADR-020 | Bjørnstad 2018 *Epidemics: Models and Data using R*; Gelman et al. *BDA3* |
| `inference.draws` / `tune` / `chains` / `target_accept` | 2000 / 1000 / 4 / 0.95 (no change) | PyMC defaults for HMC convergence; widely cited conventions |
| `min_r_squared` (kill criterion) | **REMOVED** | No anchor; report R² as diagnostic, not gate |
| `max_r0_ci_width` (kill criterion) | **REMOVED** | No anchor; report CI width as diagnostic, not gate |

#### F. Stage classification

| Parameter | New value | Anchor |
|---|---|---|
| Stage scheme | **3 stages: growth, decay, dormant** | R₀ direction keyed to classical SIR threshold |
| `growth_min_r0` | 1.0 (rename from `early_spread_min_r0`) | Classical SIR epidemic threshold — Kermack & McKendrick 1927 |
| `peak_window_days` | **REMOVED** | No anchor |
| `decay_min_pct_below_peak` | **REMOVED** | No anchor; decay = R₀ < 1, simpler and anchored |
| `dormant_max_articles_per_day` | **REMOVED** | No anchor; dormant = R₀ < 1 sustained, low residual volume |
| `pre_emergence_max_articles` | **REMOVED** | Pre-emergence stage dropped entirely (see below) |

**Pre-emergence stage removed.** Every cluster gets a fitted R₀ with credible interval regardless of data thinness — the CI width is the honest signal of fit reliability, not a researcher-set threshold. Clusters with insufficient data simply have wide CIs that straddle 1; the dashboard shows the CI directly.

The "newly emerging narratives" view on the dashboard is a **recency filter on the cluster's first-article date**, not a stage label:

- A narrative is "newly emerging" if its first article (post-deduplication) appeared in the corpus within the last **4 weeks**.
- 4 weeks is anchored to the sharp-emergence anchor windows in `data/anchors/anchor_narratives.jsonl` (SVB 5 days, COVID 14 days at threshold, Brexit 10 days, Credit Suisse 5 days, China devaluation 7 days — all well inside a 4-week window) and to event-study horizons (Brown & Warner 1985 ±5 to ±20 days conventional event windows).
- Operational implication for the clustering pipeline: with `hdbscan.min_cluster_size = 10` (BERTopic default) and Phase 6 running weekly, a narrative with sustained writing (≥ ~1 article/day) forms a cluster within ~10-14 days of its ignition. The 4-week recency window comfortably covers the formation latency plus an additional 2-3 weeks of visibility for the user.

Stages and the recency filter combine in the dashboard:

| Dashboard cell | Filter |
|---|---|
| Newly emerging + growing | first-article ≤ 4 weeks ago AND R₀ posterior median > 1 |
| Established growing | first-article > 4 weeks ago AND R₀ posterior median > 1 |
| Decaying | R₀ posterior median < 1 |
| Dormant | R₀ < 1 sustained for ≥ N weeks (N anchored to fitting context, documented in implementation) |

#### G. Validation

| Parameter | New value | Anchor |
|---|---|---|
| `anchor_tolerance_days` | 14 (no change) | Brown & Warner 1985 event-study window convention |
| `bootstrap_replicates` | **1000** (was 20) | Efron & Tibshirani 1993 — "B ≥500-1000 for confidence intervals" |
| `bootstrap_random_seed` | 42 (no change) | Convention |
| `fdr_alpha` | 0.05 (no change) | Benjamini & Hochberg 1995 |
| `required_anchors_recovered` (kill criterion) | **REMOVED** | No anchor; report recovery rate, no pass/fail threshold |
| `min_bootstrap_nmi` (kill criterion) | **REMOVED** | No anchor; cite Strehl & Ghosh 2002 for NMI as a quality measure, not a threshold |
| `validation.lookahead_check.*` (entire block) | **REMOVED** | Look-ahead apparatus from ADR-011 dropped; cite the negative finding in prereg, not the apparatus |

#### H. Similar-narrative finder (new methodology element)

For each detected narrative, compute the top-5 most-similar past narratives across the full historical narrative set, using three complementary measures reported separately:

| Measure | Method | Anchor |
|---|---|---|
| Semantic | Cosine similarity between cluster embedding centroids | Reimers & Gurevych 2019 (SBERT) — standard retrieval |
| Lexical | Jaccard overlap on top-K c-TF-IDF terms (K=10) | Jaccard 1901; classic in NLP |
| Morphological | Pearson correlation on normalized weekly volume curves | Standard time-series shape comparison |

**Top-K (=5) ranking, not threshold.** Avoids the "where's the cutoff" question. K=5 follows the recall@5 / recall@10 convention from BEIR (Thakur et al. 2021).

#### I. Dashboard structure (canonical specification)

Three pages (replaces the prior two-view spec in §7 of MND_PROJECT_SPEC.md):

1. **Emerging Narratives** (default landing) — narratives with first-article date in the last 4 weeks AND R₀ posterior median > 1 ("newly emerging + growing"), sorted by recent acceleration. Per-narrative card shows three overlaid volume curves (institutional, premium press, broad press), R₀ + credible interval, fitted carrying capacity, calendar event markers, top-5 similar past narratives.
2. **Narrative Landscape** — 2D UMAP scatter of every cluster centroid. Color = stage; size = cumulative volume.
3. **Timeline** — historical view, every narrative on a time axis, brush-to-zoom.

Plus per-narrative drill-down, compare mode (overlay normalized curves of 2-4 narratives), anchor validation page.

#### J. Dead-code cleanup

Per "anchored or removed applies to abandoned pieces too":

- `src/mnd/ingestion/ravenpack.py` — **DELETE** (deprecated by ADR-016)
- `src/mnd/ingestion/wayback.py` — **DELETE** (retained-for-reference; no active code path)
- `NBERIngestor` and `SSRNIngestor` classes in `src/mnd/ingestion/institutional.py` — **DELETE** (commented out of `_sub_ingestors` per ADR-017; `_NBER_JEL_PREFIXES` constant deleted with them)
- `prepare_text_for_embedding` in `src/mnd/embedding/embedder.py` — **DELETE** (broken whitespace-token math; only used in filter path which loses the Gate 2 embedding check under this ADR anyway)
- `Embedder.from_config("comparator")` path + the `embedding.comparator` config block — **DELETE**
- `config.paths.dynamics_ravenpack` — **DELETE**
- `config.validation.lookahead_check` block — **DELETE**
- `data/dynamics/ravenpack/` directory + `whitelist.yaml` ravenpack entry — **DELETE**

### Consequences

**Positive:**

- Every methodology parameter has a citation. The pre-registration story is now defensible without "we found this worked well" language for any choice.
- Surface area shrinks: ~22 parameter removals, 3 architectural pieces removed (comparator embedder, look-ahead apparatus, 3-tier granularity), 4 unused source files / classes deleted.
- BERTopic clustering output should change measurably: `min_cluster_size: 20 → 10` will produce more topics; `ctfidf.bm25_weighting: true → False` will produce different top-term lists per cluster. These are library defaults, not researcher tweaks — outcomes are owned by BERTopic, not by us.
- Bootstrap NMI gets meaningful CI: 20 replicates → 1000 is a 50× increase, well within published standard.
- Reviewers cannot point to a single parameter and ask "why this value?" without the answer being a primary literature citation or a library default.

**Negative / risks:**

- BERTopic library-default changes may produce more / smaller / lower-quality clusters than the researcher-tuned config. This is the price of removing researcher choice. If post-re-ingest cluster quality is meaningfully worse, the ADR remains correct — we report what BERTopic does, not what we tuned it to do.
- The 3-stage R₀-keyed classification is less informative than the prior 5-stage scheme (no "peak" stage, no "pre-emergence" stage). Decision is by design — the peak window threshold has no anchor; pre-emergence as a stage required setting a data-thinness threshold which also has no anchor. The fitted peak day is computed and displayed as a descriptive overlay (not a categorical stage), and the credible interval on R₀ communicates fit reliability honestly (a wide CI = the same information "pre-emergence" used to communicate, but without a binary cutoff).
- Some narratives will fall in the "borderline R₀ ≈ 1" zone where small fluctuations toggle growth/decay. Decision: report R₀ with credible interval, and let users see when the CI straddles 1.
- Removing `prepare_text_for_embedding` and the embedding gate from the filter changes filter behavior. Need to verify filter still produces a reasonable corpus size — possibly the corpus admits more articles. If this causes downstream clustering noise problems, we can revisit, but the principled answer is "the JEL keyword gate is the filter; don't add an unanchored second gate."
- Comparator removal means we lose the look-ahead sensitivity report. We cite the negative finding from the prior ADR-011 run as historical evidence in the prereg, not as a continuing methodology element.

### Implementation steps

This ADR is the spec; the implementation lands in a follow-on commit pair:

1. **Config changes** (`config/config.yaml`, `config/whitelist.yaml`) — all parameter modifications and removals listed in Decision sections A-I.
2. **Code changes**:
   - `src/mnd/processing/chunker.py` — switch to Qwen3 tokenizer; constants 600/100/2000 → 512/64/no-threshold.
   - `src/mnd/embedding/embedder.py` — remove `prepare_text_for_embedding`, remove `comparator` role plumbing.
   - `src/mnd/filtering/topic_filter.py` — remove embedding gate (or make it a no-op pending broader rewrite).
   - `src/mnd/clustering/*.py` — remove granularity merging logic + silhouette threshold logic.
   - `src/mnd/dynamics/smooth.py` — remove source-stratified smoothing (single combined 7-day MA).
   - `src/mnd/dynamics/fitting.py` — remove `gompertz` / `exponential`; update prior recipe per Bjørnstad/Gelman.
   - `src/mnd/stages/*.py` — collapse 5 stages to 4 (R₀-keyed); remove peak/decay/dormant threshold logic.
   - `src/mnd/validation/*.py` — remove pass/fail thresholding; report rates only.
   - `src/mnd/ingestion/__init__.py` — drop ravenpack/wayback references.
   - `src/mnd/clustering/similar_narratives.py` (NEW) — compute 3 similarity measures, return top-5 per measure.
3. **Dead-code deletions** as listed in section J.
4. **Test updates**:
   - `tests/test_filtering.py` — adjust for removed embedding gate.
   - `tests/test_stage_classify.py` — adjust for 4-stage scheme.
   - `tests/test_dynamics_models.py` — adjust for removed gompertz/exponential.
   - Add `tests/test_chunker_tokenizer.py` — assert chunks fit within 512 Qwen3 tokens.
5. **Documentation**:
   - `MND_PROJECT_SPEC.md` — the "Document status" notice already references this ADR; no further changes needed.
   - `CLAUDE.md` — update the "Phase 2 corpus architecture" section's Layer 1B description to clarify that Media Cloud premium-press volume is a cross-validation signal, not the SIR/logistic primary fit target (correcting an ADR-016 framing artifact). Already updated to reference the methodology lock-in elsewhere.
   - `prereg/PREREGISTRATION.md` — update to cite the field-anchored methodology with primary references.

### Verification

After implementation:

- All existing unit tests pass (47/47, possibly with adjustments per step 4).
- New tokenizer-alignment test confirms chunks fit within Qwen3's 512-token window (no silent truncation).
- BERTopic clustering reproducibly produces the library-default output on a small held-out test corpus.
- The full integration test battery on RCC (`pytest tests/integration/test_source_coverage.py -m integration -v`) passes per-source coverage floors with the new methodology in place.
- Anchor recovery rate is reported (not gated) on the post-re-ingest corpus.

---

## ADR-020: Basis-set corpus framing; NBER restored, CFR dropped, CEA added; pre-clustering JEL keyword filter removed

- **Status**: Accepted
- **Date**: 2026-05-20
- **Supersedes (partially)**: ADR-010 (corpus scope), ADR-015 (JEL-anchored canonical filter), ADR-016 (single-stage Stage-2 keyword filter), ADR-017 (NBER/SSRN removal), ADR-018 (named_events keyword category), ADR-019 (NBERIngestor deletion). The methodology lock-in from ADR-019 (chunker, BERTopic, dynamics, validation) remains in force.

### Context

ADR-010 / 012 / 016 / 017 incrementally evolved the Phase 2 corpus by tier (Tier 1 institutional, Tier 2 academic-analytical) and patched coverage failures source-by-source. The set was justifiable in aggregate but lacked a single architectural principle to point at when a reviewer asks "why these sources and not others?" — and prior decisions had accumulated researcher-derived edge cases (per-source title filters, 213-keyword JEL-anchored Stage-2 gate, named-event keyword category) that are hard to defend cleanly in pre-registration.

Re-examining the corpus under a basis-set lens (minimal sources spanning every independent dimension of US macro discourse, no redundancy, no researcher-introduced filters):

1. **Source selection.** The eight independent dimensions of US macro discourse are (1) US monetary authority, (2) US monetary research voice, (3) international macro authority, (4) international central-bank network, (5) US fiscal authority, (6) US financial-stability research, (7) US policy think-tank commentary, (8) academic primary work (with academic-policy column commentary as a sub-axis). Each source in the corpus should map to one or more dimensions; sources whose dimensional coverage is wholly captured by another source are redundancy.

2. **CFR is redundancy.** Council on Foreign Relations output is ~80% foreign-policy non-macro; the macro subset (dollar dynamics, sovereign debt, global monetary policy) is covered by PIIE on the same international-policy dimension (dimension 7). Keeping CFR adds noise without adding a dimension.

3. **CEA is a basis hole.** The Council of Economic Advisers is the executive-branch primary fiscal-and-macro voice (dimension 5), distinct from CBO (legislative-branch fiscal). The annual Economic Report of the President is the US executive analog to IMF WEO. CEA was a notes-only stub in `whitelist.yaml` with no working ingestor.

4. **NBER deletion was premature.** ADR-017/019 deleted `NBERIngestor` because the search API path was bot-protected. A 30-minute 2026-05-20 spike confirmed the `/papers/wNNNNN` paper-detail endpoints are NOT bot-protected — plain Drupal/nginx, `citation_*` meta tags in Google Scholar convention, clean HTTP 200 across years. Direct URL enumeration restores access. NBER is the only open source for academic primary working papers (dimension 8); without it, the basis set has no academic-primary axis.

5. **CBO via govinfo.gov was investigated and rejected.** A spike on 2026-05-20 confirmed govinfo.gov has a CBO corpus accessible via the JSON API (filter on `governmentAuthor:"Congressional Budget Office"`) — 772 publications total, but unevenly distributed by year (41 records 2010 → 6 records 2024). The unevenness reflects GPO's deposit policy, not CBO's publication rate, and would introduce a non-random, time-varying selection filter into the CBO volume time series — exactly the kind of researcher-introduced artifact we're trying to eliminate. The existing Playwright + curl_cffi cbo.gov ingestor (ADR-017) covers the full ~25,000-URL CBO archive directly; its operational complexity is an engineering cost, not a methodological one. Retain.

6. **The pre-clustering JEL keyword filter is double-filtering.** The basis-set source selection is already a coarse macro-content filter (every basis-set source's institutional mandate is in macro scope by construction). Stacking a 213-keyword JEL-anchored Stage-2 gate on top adds researcher choices about which keywords represent each JEL category — exactly the kind of decision reviewers will dig into. In practice `scripts/run_pipeline.py` already does not invoke the topic filter (`filter_cmd` runs date-range + dedup only), and `_title_matches_canonical` in `institutional.py` has had zero call sites since ADR-016 removed the per-source Stage-1 filters. The cleanest move is to remove the apparatus entirely and shift JEL classification to post-clustering.

### Decision

**Source set (the basis set).** Twelve active ingestors in `InstitutionalIngestor._sub_ingestors`:

| Basis dimension | Ingestor(s) |
|---|---|
| 1. US monetary authority | `FederalReserveIngestor` |
| 2. US monetary research voice | `FedRegionalIngestor` (NY, SF, Chicago, Atlanta) |
| 3. International macro authority | `IMFIngestor` |
| 4. International central-bank network | `BISIngestor` |
| 5. US fiscal authority | `CBOIngestor` + `CEAIngestor` (NEW) |
| 6. US financial-stability research | `TreasuryOFRIngestor` |
| 7. US policy think-tank | `BrookingsIngestor` + `PIIEIngestor` |
| 8. Academic primary work / column | `NBERIngestor` (RESTORED) + `VoxEUIngestor` |
| Cross-cutting Q&A register | `CongressionalIngestor` (Treasury Sec testimony) |

**Changes from ADR-019 baseline:**
- **Add `CEAIngestor`** — govinfo.gov ERP collection via `api.govinfo.gov` JSON API. Walks ERP packages and emits one Article per chapter-level granule. PDF text extraction via `pypdf` (added to `requirements.txt`). API key in `GOVINFO_API_KEY` env var; `DEMO_KEY` fallback with warning. 61 historical ERPs (1947-present) with ~3,040 chapter-level granules.
- **Restore `NBERIngestor`** — direct sequential enumeration of `/papers/wNNNNN`. Year-floor paper-number table calibrated 2026-05-20. Extracts metadata from `citation_*` HTML meta tags; body from trafilatura over the abstract block. Polite 0.6s per request; one-time ~8h enumeration for 2010-2026 ≈ 30,000 IDs.
- **Drop `CFRIngestor` from `InstitutionalIngestor._sub_ingestors`** — class file retained in `src/mnd/ingestion/institutional.py` (unwired) so existing pre-ADR-020 data files can still be re-read for QA; not run in any new ingest.

**Filtering.** Pre-clustering JEL keyword filter removed entirely:
- Delete `src/mnd/filtering/topic_filter.py` and its `__init__.py` export.
- Archive `config/topic_filter_keywords.yaml` → `scripts/archive/topic_filter_keywords_archived_adr020.yaml`.
- Remove the `filtering.topic` block from `config/config.yaml`.
- Remove the keyword-coverage check from `scripts/preflight_check.py` and `tests/test_scaffold.py`.
- Remove the `_title_matches_canonical` / `_canonical_topic_keywords` helpers and the `load_yaml` / `functools` imports they required from `src/mnd/ingestion/institutional.py`.

The `filter` stage in `run_pipeline.py` now does date-range filtering and MinHash near-duplicate removal only — nothing else.

**Post-clustering JEL classification.** New module `src/mnd/clustering/jel_classifier.py` (`classify_clusters` function, `ClusterJELAssignment` dataclass). For each BERTopic cluster, embed the c-TF-IDF top terms in the same Qwen3 space used for the clustering itself; embed each top-level JEL code's official AEA description as a prototype; assign the primary JEL code by maximum cosine similarity. Macro-finance scope defaults to {E, F, G, H} per AEA's published taxonomy. Out-of-scope clusters are reported with their JEL label and excluded from SIR/logistic dynamics analysis only — they are NOT dropped from the embedded corpus.

**Symmetry.** No source receives a different pre-clustering filter from any other. Every basis-set source is ingested in full; macro/non-macro determination is made once at the cluster level using a published external taxonomy.

### Consequences

**Positive:**
- One-sentence corpus justification: *"The semantic corpus is the minimum set of sources spanning the eight independent dimensions of US macro discourse, with no redundant or noise-dominated entries."* Answers every "why X / why not Y" reviewer question without invoking researcher judgment over specific sources.
- One-sentence filtering justification: *"No pre-clustering topical filter is applied. The basis-set source selection is the only macro-scope constraint at ingest. Topic relevance is decided post-clustering by assigning each BERTopic cluster a primary JEL code from the AEA's published JEL taxonomy, applied symmetrically across sources."* Reviewer cannot ask "why these 213 keywords?" — we don't use any.
- NBER restored, closing the academic-primary-work basis gap.
- CEA added, closing the executive-fiscal basis gap.
- CFR dropped, removing ~22,000 sitemap candidates of which ~80% are foreign-policy non-macro noise.
- ~600 lines of code (topic_filter.py, topic_filter_keywords.yaml, dead helpers) removed.

**Negative / risks:**
- NBER enumeration is slow (~8h one-time at 0.6s/request × 30k papers). One-time cost on RCC.
- CEA depends on a free GovInfo API key; `DEMO_KEY` fallback only sustains integration tests, not the full ingest.
- Corpus volume grows. NBER alone adds ~24,000 working papers over 2010-2026, ~70% of which are non-macro (J, I, D, L, …). They are embedded and clustered, then excluded from dynamics by the post-clustering JEL classifier. Compute cost on RCC: bounded; user has explicitly accepted compute-cost-for-cleaner-methodology trades.
- Post-clustering JEL classifier accuracy is empirically validated only after the first full ingest. Sensitivity analysis on the runner-up gap (`ClusterJELAssignment.runner_up_gap`) is the planned diagnostic; if median gap is <0.05 across clusters, the classification is ambiguous and we'll need to revisit (likely by expanding the JEL prototype to include sub-code descriptions).

### Verification

After implementation:
- `python -c "from mnd.ingestion import InstitutionalIngestor; ing=InstitutionalIngestor(); print(len(ing._sub_ingestors))"` returns 12.
- `from mnd.filtering.topic_filter import TopicFilter` raises `ImportError`.
- `tests/test_filtering.py`, `tests/test_scaffold.py` pass with the new assertions (CFR absent, CEA present, NBER present, TopicFilter removal asserted).
- Per-source integration battery (`pytest tests/integration/test_source_coverage.py -m integration -v`) passes coverage floors for all 25 cases including the new NBER + CEA cases and the 2010-window historical-edge cases for Brookings / IMF / BIS / Treasury OFR. Run on RCC where curl_cffi, playwright, and pypdf are installed.
- `python scripts/preflight_check.py --skip-embedding` reports 6/6 OK (no keyword-coverage step).
- Post-clustering JEL classifier returns sensible scope labels on a 50-cluster sanity check after the first full re-ingest (≥40% in-scope for E/F/G/H given the basis-set composition).

### Implementation notes

The actual code changes live in:
- `src/mnd/ingestion/institutional.py` — new `NBERIngestor`, new `CEAIngestor`, updated `InstitutionalIngestor._sub_ingestors`, dead helpers removed.
- `src/mnd/filtering/__init__.py` — `TopicFilter` export removed.
- `src/mnd/clustering/jel_classifier.py` — NEW.
- `config/whitelist.yaml` — header rewritten under basis-set framing; CEA entry expanded; CBO entry updated to clarify Playwright path is canonical (govinfo rejected); NBER entry restored to active; CFR entry removed.
- `config/config.yaml` — `filtering.topic` block removed.
- `requirements.txt` — `pypdf==5.0.1` added.
- `tests/test_filtering.py`, `tests/test_scaffold.py` — assertions updated.
- `tests/integration/test_source_coverage.py` — CFR case removed; NBER + CEA cases added; 2010-window historical-edge cases added for Brookings / IMF / BIS / Treasury OFR.
- `scripts/preflight_check.py` — keyword check removed; sub-ingestor count updated to 12.
- `docs/METHODOLOGY.md`, `CLAUDE.md`, `docs/filter_audit_jel.md` — updated to reference ADR-020 as the canonical filtering and source-selection authority.

---

## ADR-021: Post-ADR-020 upstream change patches — VoxEU Cloudflare, CBO Wayback, Atlanta JSON API, Congressional GovInfo CHRG

- **Status**: Accepted
- **Date**: 2026-05-21
- **Refines**: ADR-014 (curl_cffi pattern), ADR-017 (CBO+Atlanta+PIIE coverage closures), ADR-020 (basis-set framing)

### Context

Within 24 hours of the ADR-020 verification (2026-05-20 evening), the per-source integration battery on RCC surfaced four upstream changes / regressions affecting basis-set sources. The user mandate: preserve the basis-set (no source removed, no pivot to alternates already considered and rejected) and document HOW we access each source so we don't forget the configuration if it changes again.

The four issues:

1. **VoxEU silent zero-yield (2012 + 2023 windows).** cepr.org enabled Cloudflare's bot-mitigation JS challenge between 2026-05-19 and 2026-05-20. Every stdlib `requests` call returned HTTP 403 with `cf-mitigated: challenge`, and the ingestor's exception handler silently swallowed it. Basis-set impact: VoxEU is the sole source for the academic-policy column dimension — losing it would have closed a basis hole.

2. **CBO DataDome blocking definitively even with fresh Playwright cookies.** The ADR-017 Playwright + curl_cffi-with-cookies hybrid failed: DataDome now serves the JS challenge interstitial inside Playwright's headless Chromium without ever resolving it (`title='cbo.gov'`, `body_len=0` after 20s+). The "clearance" cookie Playwright captures is a challenge-stub, not real clearance — DataDome rotates its value on every response, and curl_cffi requests carrying these cookies all 403. Re-acquiring 3× doesn't help. govinfo.gov was already considered and rejected (ADR-020) because GPO deposit coverage is uneven over time. Basis-set impact: halving the fiscal-authority dimension (CEA still works).

3. **Atlanta Fed site redesigned, history culled.** atlantafed.org's 2026 redesign retired `/sitemap.xml` (now 404), `/blogs/macroblog/rss` (now 404), and the entire pre-existing publication URL surface. The redesign also actively removed historical content from the live site: working papers pre-2019, macroblog pre-2022, and the original Economy Matters pre-2016 are gone. Basis-set impact: 1 of 4 regional-research-voice sources.

4. **Congressional Treasury Drupal listing caps at ~130 pages (~2.5 years).** Treasury's press-release listing pagination terminates around page 130 because the Drupal "next page" link disappears, leaving only Nov 2023 onward visible from the listing path. Basis-set impact: cross-cutting Q&A dimension reduced to recent material.

### Decision

**VoxEU.** Add `VoxEUIngestor._cepr_get` classmethod using `curl_cffi.requests` with `impersonate='chrome131'` (the ADR-014 pattern for IMF/Akamai). Route both the listing fetch and body fetch through it. Promote the `except: return` to surface a log line on page-0 zero-card results so future regressions are visible. No new dependency — `curl_cffi==0.15.0` is already in `requirements.txt`.

**CBO.** Replace the Playwright + curl_cffi hybrid with the **Wayback Machine CDX API** (`web.archive.org/cdx/search/cdx`) for enumeration plus `web.archive.org/web/{ts}id_/{url}` for snapshot fetches (the `id_` modifier returns raw archived body without Wayback's toolbar rewrite). The canonical `url` field on each emitted Article is still the **cbo.gov publication URL** (not the Wayback wrapper), so downstream dedupe and cluster reporting still attributes content to cbo.gov. Year-sharded CDX queries (one year at a time) keep result sets under the 503 ceiling; 0.5s/shard and 0.3s/snapshot politeness. Playwright is NOT used; `playwright==1.48.0` stays in `requirements.txt` for now but is no longer load-bearing — kept in case DataDome's posture relaxes.

This preserves the basis-set choice: "cbo.gov content," just retrieved via the archive. Wayback has clean snapshots of cbo.gov/publication/* back to 2010+ with no DataDome layer.

**Atlanta Fed.** Switch from sitemap walk to **per-series JSON listing API**: `atlantafed.org/api/feed/getFilteredResults?DataSourceId=…&ContextId=…&PageSize=…&PageNumber=…&StartDateRange=…&EndDateRange=…`. Hit four series — Working Papers, Policy Hub Papers, Policy Hub Macroblog, and What-We-Study : Macroeconomy hub (URL-filtered for Economy-Matters-style paths). Article bodies still fetched via `_atlanta_get` (curl_cffi Chrome131); only the listing surface changed.

Historical content removed by the redesign (working papers pre-2019, macroblog pre-2022, Economy Matters pre-2016) is **not recoverable from atlantafed.org**. Documented as a known upstream limitation. Wayback Machine would be a future option if we decide that historical depth matters more than the operational cost.

**Congressional.** Keep the Treasury Drupal listing as **Path A** (bumped `_MAX_LISTING_PAGES` from 1200 to 2500 to ensure deep historical pagination terminates cleanly; ~21 min wall at 0.5s/page politeness for a full 2010-anchored descent). Add **Path B** — the GovInfo `CHRG` (Congressional Hearings) collection via the same JSON API and `GOVINFO_API_KEY` pattern as `CEAIngestor`. CHRG is GPO's canonical record of formal Congressional hearing transcripts and includes every Treasury Secretary testimony before Senate Banking and House Financial Services back to the 1990s.

Path A produces recent + Drupal-archived Bessent / Yellen / Mnuchin / Geithner press-release-style remarks; Path B fills historical coverage with the long-form verbatim hearing transcript register — exactly the cross-cutting Q&A register that ADR-020 named for this dimension. Both paths feed through one `seen` set so any URL-overlap dedupes automatically.

### Consequences

**Positive:**
- All four basis-set dimensions preserved.
- Three of four sources now run through more durable mechanisms than what ADR-017 set up (JSON APIs and Wayback CDX are less fragile than sitemap scraping and DataDome cookie acquisition).
- Each ingestor's docstring now documents the access path explicitly — including failed approaches and why — so a future regression doesn't cost us another round of forensic debugging.

**Negative / risks:**
- Atlanta Fed historical content (pre-2019/2022/2016 per series) is permanently absent unless we add a Wayback Machine fallback later. Known gap; impact bounded by the basis-set dimension still having 3 other regional Feds.
- CBO via Wayback inherits Wayback's coverage policy. Wayback crawls cbo.gov frequently (the CDX API confirms thousands of unique publication URLs back to 2010), but if Wayback's policy changes (rate-limiting tightens, content removal honored) we'd need a contingency. Mitigation: weekly Phase 6 re-ingest will catch any drop in counts.
- Congressional now requires `GOVINFO_API_KEY` to be set for the historical Path B; without it, Path B falls back to DEMO_KEY (30 req/hr) and silently undercovers. Documented in `.env.example`.
- The integration battery on RCC needs to be re-run to confirm the four fixes work end-to-end. The local probes the agents ran confirmed each fix produces non-zero records, but the floors and date-span asserts need the full battery.

### Verification

Local probes (from agent reports, 2026-05-20→21):
- VoxEU 2023-01 → 4 articles via `_cepr_get`, year-shard endpoint returns 12 article cards as expected.
- CBO 2023-06 → wait for RCC battery; Wayback CDX returns >2000 candidate URLs for the test window.
- Atlanta Fed 2023 → 45 articles across 4 sections (working_paper / policy_hub / macroblog / economy_matters).
- Congressional 2018 H1 → to be verified on RCC; Path B GovInfo CHRG confirmed to list hearings with Treasury Secretary in title.

### Implementation notes

All edits are in `src/mnd/ingestion/institutional.py`:
- VoxEUIngestor: lines ~1668–1885 (class rewritten around `_cepr_get`).
- CBOIngestor: lines ~1318–1588 (entire class replaced with Wayback CDX implementation).
- FedRegionalIngestor `_fetch_atlanta` and supporting constants: lines ~895–1283.
- CongressionalIngestor: lines ~2253–2836 (Path A extended, Path B added).

No changes to `_sub_ingestors`, the composite, or any other ingestor. `tests/integration/test_source_coverage.py` got a minor comment update on the Atlanta case.

Playwright remains in `requirements.txt` for now but is no longer load-bearing (no class currently imports it). Future cleanup may remove it; for now we keep it in case DataDome's posture changes or another source needs JS execution.

---

## ADR-022: Methodology-principle-1 enforcement pass across all 12 ingestors

- **Status**: Accepted
- **Date**: 2026-05-21
- **Refines**: ADR-015, ADR-016, ADR-019, ADR-020, ADR-021

### Context

Post-ADR-021, a senior-engineer audit of all 12 active basis-set ingestors found that several emit records derived from heuristic / fabricated values rather than authoritative source metadata, and several silent zero-yield paths could hide upstream regressions. Methodology principle 1 (`docs/METHODOLOGY.md` §7) says every parameter is anchored or removed; principle 4 says topic-relevance is decided in exactly one place. The audit findings violated principle 1 in seven places — three by fabricating publication dates when source metadata was absent, four by silently degrading to a lower-coverage fallback when an optional dependency or env var was missing.

The defects were:

1. **CBO** (`institutional.py` line 1413): when trafilatura could not extract a page date from a Wayback-archived cbo.gov snapshot, the ingestor fell back to the Wayback snapshot timestamp (the date the page was last crawled, which can be decades after publication). A local probe surfaced a 1993 NAFTA analysis tagged as 2023-07-23.
2. **BIS** (line 845): when the sitemap `<lastmod>` field was missing, the ingestor fabricated `date(year, 1, 1)`.
3. **Chicago Fed** (line 1125): when trafilatura's meta_date disagreed with the URL year, the ingestor fabricated `date(year, 6, 15)`.
4. **Congressional Path B + CEA** (lines 2585-2595, 2969-2978): when `GOVINFO_API_KEY` was unset, the ingestor logged a warning and fell back to GovInfo's public `DEMO_KEY` (30 req/hr), which silently undercovers any full-corpus enumeration.
5. **CEA + Congressional `_extract_pdf_text`** (lines 3022-3033, 2790-2799): when `pypdf` was unimportable, the ingestor logged an error and returned `""`, which the caller treated as a transient parse failure and dropped the granule — silently zeroing both sources for the full ingest if pypdf hadn't been installed.
6. **Atlanta Fed** (line 1299): when the article page body extraction yielded < 50 words, the ingestor substituted the API listing's `Teaser` field (a 1-2 sentence summary) as the body — leaking listing boilerplate into the embedding text.
7. **VoxEU** (line 1805): on any per-shard exception (Cloudflare 403, HTTP timeout), the ingestor logged a warning and `return`ed, silently truncating the year's coverage. The audit found this was how the 2026-05-19 Cloudflare tightening went unnoticed for 24 hours.

A parallel audit of `tests/integration/test_source_coverage.py` found four further defects:

8. `pytest.skip` on ANY exception (line 516) masked code defects as "network/environment errors."
9. `requires_curl_cffi` / `requires_pypdf` / `requires_playwright` helpers (lines 70-92) skipped the test gracefully when those deps were missing — but curl_cffi and pypdf are mandatory for the real ingest per ADR-014 and ADR-020. Skipping their tests would let a developer ship without them.
10. The contracts were three: floor count, section diversity, date span. They did not validate that every emitted record carries a parseable in-window publication date and a real body — i.e. they could pass a corpus full of mis-dated and title-only records.
11. Per-record `min_body_word_count` was not enforced, so a teaser-substitution regression like #6 would not have failed any test.

Two more methodological-cleanup items surfaced from the same audit:

12. **FSOC Annual Reports** (line 1721): `_scrape_fsoc` returned silently with a comment that PDF-only content was "documented as a corpus limitation." This violates the project's mandate to ingest all available content from each basis-set source; FSOC Annual Reports are a major systemic-risk discourse artifact and they are PDF-text-layered (pypdf extracts cleanly).
13. **Atlanta Fed docstring** described the pre-2019 / pre-2022 / pre-2016 cull as a "Hard site-side limitation"; this is a fact about the source's editorial choices, not a methodology limitation of the project, and the framing implied documentation of a flaw rather than a neutral statement about source coverage.

### Decision

All thirteen defects are addressed in one commit. The principles applied:

- **No fabricated dates.** If an ingestor cannot extract a publication date from authoritative source metadata (URL slug, structured page meta, or sitemap `<lastmod>` confirmed by page-side cross-check), it drops the record and logs DEBUG with the candidate URL. We never emit a record with an inferred date — the SIR fit's temporal axis depends on correct dates, and a mis-dated record actively corrupts the analysis.

- **No silent degradation to lower-coverage fallbacks.** `GOVINFO_API_KEY` missing now raises `RuntimeError`. `pypdf` ImportError propagates from `_extract_pdf_text` rather than being swallowed and returning an empty body. `curl_cffi` ImportError already propagated through VoxEU/IMF/Atlanta with a loud error log; we leave that pattern unchanged. The principle: a missing dependency is a configuration error, not a runtime fallback target.

- **No teaser-as-body or title-as-body substitution.** Atlanta Fed's teaser-fallback is removed. PIIE already removed its title-only fallback in ADR-017; we audit-confirmed it.

- **No silent zero-yield paths.** VoxEU now tracks per-shard yield and raises `RuntimeError` if no shard yielded across a multi-year window. Atlanta Fed distinguishes page-1-empty (legitimate "no rows in window," logged INFO) from HTTP error or JSON-parse failure (logged ERROR). The artificial 20-page Atlanta pagination cap is removed; pagination is bounded by the date-range filter alone.

- **Test contracts validate every record, not just aggregate counts.** Every record's `published_at` must parse as an ISO date inside the requested window. Every record's `word_count` must meet a source-specific minimum. Failures specify the URL and value that broke the assertion. The `pytest.skip` for upstream exceptions is narrowed to `(requests.ConnectionError, requests.Timeout, socket.gaierror, ConnectionResetError)` only — every other exception fails loudly. The `requires_*` skip helpers for mandatory deps are removed; if `curl_cffi` or `pypdf` is missing at test time, pytest fails loudly at import time and the developer installs them.

- **FSOC included.** `TreasuryOFRIngestor._scrape_fsoc` is implemented end-to-end. PDF discovery via the `_FSOC_PDF_RE` pattern on the canonical FSOC studies-and-reports index; PDF body via the shared `_extract_pdf_text` helper. FSOC Annual Reports get section `fsoc_annual_report` and document_type `fsoc_annual_report`, dated to December 31 of the reporting year (the report's reporting period closes at year end). This adds ~15 records to the corpus floor across 2010-present — small in count, large in narrative discourse weight.

- **Atlanta Fed docstring reframed.** "Hard site-side limitation" framing replaced with a neutral statement of each series' inaugural date. No `stable_history_gap` marker (it was documented but never implemented). The basis-set composition is symmetric across sources: every source contributes what its publisher emits during the window. Atlanta's pre-2019 / pre-2022 / pre-2016 absence is a fact of the source's editorial choices, not a methodology limitation.

- **NBER dynamic ceiling.** The hardcoded `_ABSOLUTE_CEILING = 38000` was researcher-judgment ("calibrated 2026-05-20, generous through 2026") that would silently undercount once NBER passed w36000. Replaced with `_compute_ceiling(end_year)` that prefers the calibrated next-year floor and otherwise projects forward at 2500 paper-IDs per forecast year. The consecutive-404 stop is the actual termination signal; the ceiling only needs to be `>=` the true head.

### Consequences

**Positive:**

- The corpus is methodologically defensible at the per-record level. Every emitted Article has a real publication date and a real body, sourced from authoritative metadata.
- Pre-registration text simplifies: "All basis-set ingestors emit only records whose publication date is extracted from source-side metadata; records lacking such a date are dropped." No researcher-fabricated dates anywhere.
- Coverage regressions surface as test failures with the broken URL named in the assertion message, not as "skip" lines that scroll past during a CI run.
- Missing dependencies (pypdf, curl_cffi) and missing env vars (GOVINFO_API_KEY) fail at the first call, not after a 48-hour ingest with a silent half-empty corpus.
- FSOC Annual Reports now contribute to the financial-stability dimension; the basis-set framing is more complete.

**Negative / risks:**

- The strict-date enforcement may reduce corpus counts for sources where the upstream surface lacks reliable publication metadata. The empirical question is unresolved for CBO specifically — see calibration probe below.
- A handful of records that previously made it into the corpus on URL-year-only metadata (e.g., Chicago Fed working papers where trafilatura silently picked up the page-modified date instead of the publication date) are now dropped. This is the right trade-off: methodology cleanliness over corpus size.
- NBER's `_compute_ceiling` is calibrated through 2026; running for end-year 2030+ would project 5 × 2500 = +12500 IDs beyond the latest floor. The consecutive-404 stop bounds this in practice but adds a few hundred wasted HTTP calls in the tail.

**Open question — CBO Wayback yield (deferred to RCC empirical check):**

The local probe of the CBO Wayback path (2026-05-21) returned 1 record out of 10036 candidates, mis-dated by ~30 years (a 1993 NAFTA analysis tagged as 2023-07-23). Two interpretations are possible: (a) Wayback's archived snapshots of cbo.gov genuinely lack structured publication metadata on ~99% of pages, in which case the strict-date enforcement above will produce near-zero CBO yield; (b) the probe was time-bounded and most candidates were never actually fetched. We need empirical data before deciding next steps.

`scripts/probe_cbo_wayback_dates.py` samples N candidates uniformly at random, runs each through the same `_fetch_page_full` + page-date extraction the ingestor uses, and reports the empirical `page_date_yield_pct`. Decision tree in the script docstring.

The choices we'll face if Wayback yield is too low:
1. Common Crawl WARC fetch for cbo.gov (free, dense, requires WARC parsing).
2. Residential-IP scraping service for cbo.gov direct (paid).
3. govinfo CBO collection (sparse over time, page-date clean).
4. Drop CBO from the basis set (loses the legislative half of the fiscal-authority dimension).

This ADR does not pre-commit to any of (1-4); the probe result decides.

### Verification

Local:

- `python -m py_compile` clean across all edited files (institutional.py, fed.py, tests).
- Non-integration unit test suite passes (51 tests).
- Smoke-test instantiating each of 13 ingestor classes and verifying `_govinfo_api_key()` raises RuntimeError when the env var is unset.
- Integration test collection identifies 25 cases (was 25 before; the `cbo_2023_datadome` and `fed_atlanta_2023_curl_cffi` cases renamed to `cbo_2023_wayback` and `fed_atlanta_2023_listing_api` to reflect the actual access path).

To verify end-to-end:

- `pytest tests/integration/test_source_coverage.py -m integration -v` on RCC with `GOVINFO_API_KEY` set and `curl_cffi` + `pypdf` installed.
- `python scripts/probe_cbo_wayback_dates.py --sample-size 50` on RCC.

### Implementation notes

All changes are in three files:

- `src/mnd/ingestion/institutional.py` — defects 1-7, 12, 13 above.
- `tests/integration/test_source_coverage.py` — defects 8-11.
- `scripts/probe_cbo_wayback_dates.py` — new file, calibration probe for the open question.

No changes to `_sub_ingestors`, the composite ingestor, the filter / embed / cluster pipeline, the config, or any other module.

---

## ADR-023: CBO via bounded publication-ID enumeration; fail-loud hardening of WP-REST / BIS / CEA-govinfo paths

- **Status**: Accepted; **enumeration layer superseded by ADR-032** (the `_ID_DATE_ANCHORS` / `_estimate_id_range` / `_MIN_PUBLICATION_ID` id-floor estimation is removed — CBO node ids are NOT chronological, so no id floor is sound). The fail-loud hardening of WP-REST / BIS / CEA-govinfo, the per-pid checkpoint-resume, the 12s pacing, and the `_WaybackBanned` pause-and-resume (addendums below) all remain live.
- **Date**: 2026-06-01
- **Refines / resolves**: ADR-021 (CBO Wayback access path), ADR-022 (CBO yield open question)

### Context

ADR-022 left the CBO Wayback path's yield as an explicit open question: a local probe returned 1 in-window record out of 10,036 candidates. The deferred RCC empirical check was run as part of the pre-re-ingest settling pass. The finding is decisive and was misattributed in ADR-022:

**The CBO failure was in the enumeration layer, not the page-date layer.** ADR-021's `CBOIngestor` queried Wayback CDX with `url=cbo.gov/publication/*` and `from`/`to` set to the publication window. This is fundamentally broken because CDX `from`/`to` filter by **crawl date, not publication date**: a 2-month window matches every cbo.gov URL that was *re-crawled* in that period — decades of accumulated back-catalog (~10k URLs), of which a handful are genuinely from the window. Worse, the bulk-wildcard CDX endpoint is non-deterministic under load: the identical query returned 0 / 849 / 6,575 rows across three runs within one hour, and routinely 504s. A full-production run executed during this pass took 77 minutes and yielded 0 records.

Two facts established empirically during the pass, both of which the ADR-022 probe could not see because it never got past the broken enumeration:

1. **Wayback's archival coverage of cbo.gov publications is essentially complete.** A density probe over a contiguous block of 2023 publication IDs (`/publication/59400`–`59460`) found 13/15 archived with clean 200/HTML snapshots and real page bodies; the 2 misses were transient CDX 504s, not archival gaps. The earlier "Wayback doesn't contain all the data points" worry was an artifact of the broken bulk query, not a property of the archive.
2. **Per-URL and narrow-prefix CDX queries are reliable and deterministic.** A 3-digit-prefix CDX query (`cbo.gov/publication/{id//100}`, `matchType=prefix`, `collapse=urlkey`) returns ~90–99 IDs per 100-ID block in 1–8s, with `collapse=urlkey` yielding the earliest snapshot per URL (CDX sorts ascending by timestamp within a urlkey — confirmed empirically). The 847/849-dropped-on-page-date symptom in the ADR-022 probe was Wayback rate-limiting (503 stubs from a rapid burst yield `page_date=None`), not missing page metadata; at a polite per-URL pace the page dates extract correctly.

CBO assigns each publication a monotonically increasing integer node id at `cbo.gov/publication/{id}`. This is the same structure `NBERIngestor` already enumerates for `/papers/wNNNNN` (ADR-020). The user directive for this pass was explicit: fix CBO **without changing the methodology** — CBO stays in the basis set (dimension 5, legislative fiscal authority), retrieval stays on cbo.gov-via-Wayback, the canonical Article.url stays cbo.gov.

### Decision

**1. `CBOIngestor` rewritten to bounded ID enumeration (mirrors `NBERIngestor`).**

- A calibrated `_ID_DATE_ANCHORS` table maps publication-id↔date at six empirically probed points (42000≈2010-01, 44000≈2013-03, 54000≈2018-06, 56000≈2020-01, 58000≈2022-04, 59460≈2023-07). The id rate is non-constant (~625/yr 2010-13, ~1900/yr 2013-18, ~800/yr since 2020), so `_estimate_id` interpolates piecewise-linearly between anchors and extrapolates past the last anchor at the recent slope. `_estimate_id_range` pads ±500 and clamps the floor at `_MIN_PUBLICATION_ID = 40000` (below that is pre-2010 back-catalog, out of corpus scope).
- `fetch` walks the estimated id range one 100-id block at a time (`_cdx_block`), pre-filters each candidate by its earliest-snapshot date ∈ `[start, end + 90d lag]` (a cheap proxy that bounds body fetches to the true in-window set), then fetches the `id_` raw snapshot, extracts the authoritative page date via `_fetch_page_full`, and keeps only records with `page_date ∈ [start, end]` and body ≥ 50 words. The ADR-022 strict-date policy is unchanged — the snapshot timestamp is never used as the publication date.
- The generator yields lazily in id-ascending (≈date-ascending) order, so a bounded consumer (`itertools.islice`) short-circuits without enumerating the whole range.

**2. Fail-loud everywhere a transient upstream failure could silently truncate coverage.** The same audit that produced ADR-022 missed three `except: return` / swallow-to-empty paths that mark a sub-ingestor "completed" in the checkpoint while under-capturing:

- **`_wp_rest_fetch`** (Brookings, Liberty Street, FRBSF) used a single-float timeout and `break` on any exception — silently truncating mid-pagination. Now: tuple timeout, retries 5xx/429/network with backoff, treats 400/404 as genuine end-of-list, raises `RuntimeError` on exhaustion.
- **`BISIngestor._fetch_year`** used a single-float timeout and `return` (dropping the whole year) on any exception. Now: retries transient errors, treats 404 as a legitimate per-year skip (logged WARNING), raises on exhaustion.
- **CEA govinfo path.** The shared `_get` classifies 429 as non-retryable (it's a 4xx), but govinfo throttles bursts with 429 even on a real key, and `_extract_pdf_text` / the listing calls swallowed the resulting `HTTPError` as `""` / silent `return` — dropping ERP chapters or truncating the package enumeration. New `_govinfo_get_json` and `_fetch_pdf_bytes` helpers retry 429/5xx/network with jittered backoff and raise `RuntimeError` on exhaustion. PDF **parse** failure (permanent property of one granule) is distinguished from PDF **fetch** failure (transient): parse failure logs WARNING and skips that granule; fetch failure fails the ingest loudly. API keys are redacted from all log/error messages (`_redact_key`).

The principle is the one ADR-022 established: a sub-ingestor that under-captures but yields > 0 is marked "completed" by the checkpoint, hiding the hole; raising marks it failed-for-retry, and checkpoint-based dedup handles the re-yielded duplicates on the next run.

### Consequences

**Positive:**

- CBO yields cleanly. Battery validation (window 2023-06-01..07-31, floor 5, cap 30) collected the full 30 records, all in-window, all bodies ≥ 50 words, 56-day span — versus 0 from the ADR-021 path. ADR-022's open question is resolved in favor of keeping CBO on cbo.gov-via-Wayback; none of the four fallback options (Common Crawl, paid scraping, govinfo, drop CBO) are needed.
- No methodology change: CBO stays in the basis set, canonical url stays cbo.gov, the strict page-date filter is preserved verbatim.
- Three more silent-truncation paths are now fail-loud, consistent with ADR-022. The corpus cannot be marked "complete" while a transient throttle has quietly halved a source.

**Negative / risks:**

- **Runtime.** The bounded enumeration is one CDX block query per 100 ids plus one body fetch per in-window record. For the full 2010-present window that is ~200 block queries + ~13,000–19,000 body fetches at ~0.3–0.5s politeness ≈ **15–22 wall-clock hours for CBO alone**. Combined with NBER (~5–8h) inside the single institutional SLURM job, the 48h limit in CLAUDE.md is tight. Recommend either bumping the institutional job to 72h or splitting CBO into its own parallel SLURM job (the checkpoint architecture supports this).
- **CEA cannot be validated with DEMO_KEY.** The 30 req/hr public quota is exhausted by a single ERP volume's chapter fetches, so the local battery shows CEA `n=3` (a quota artifact, not a capture bug — the granule structure is intact). CEA must be validated on RCC with a real `GOVINFO_API_KEY`. The hardening above makes a real-key run robust to incidental throttling.
- The `_ID_DATE_ANCHORS` table is calibrated through 2023; windows past it extrapolate at ~800 ids/yr. The ±500 pad and the page-date filter absorb slope error, but a large future drift would need a new anchor.

### Verification

- `python -m pytest -m "not integration"` — 51 pass.
- CBO battery case validated live: 30/30 in-window, real bodies, 56-day span, hardened retry survived a Wayback `ConnectionResetError` burst on block 593 (the first run aborted there with a 5-attempt budget; budget raised to 7 attempts / 5s→320s backoff + jitter, second run completed).
- Beige Book 2014 re-confirmed (8 records, all ≥ 200 words) — the empty battery log was an aborted run, not a defect.
- Remaining 21 battery cases were green in the same pass (Fed main/speeches/FEDS-notes, regional NY/SF/Chicago/Atlanta, Congressional, IMF ×2, BIS ×2, Treasury OFR ×2, Brookings ×2, VoxEU ×2, NBER ×2, PIIE).
- **To verify end-to-end on RCC:** `pytest tests/integration/test_source_coverage.py -m integration -v` with `GOVINFO_API_KEY` set and `curl_cffi` + `pypdf` installed (this is the run that validates CEA).

### Implementation notes

All changes in two files:

- `src/mnd/ingestion/institutional.py` — `CBOIngestor` rewrite (ID enumeration, `_estimate_id_range`, `_cdx_block`, retained `_wayback_get` / `_ts_to_date`); `_wp_rest_fetch` and `BISIngestor._fetch_year` fail-loud retry; CEA `_govinfo_get_json`, `_fetch_pdf_bytes`, `_redact_key`, two-register PDF failure handling. Added `import random`.
- `docs/architecture_decisions.md` — this entry.

No changes to `_sub_ingestors`, the pipeline, the config, or the test contracts (the existing `cbo_2023_wayback` case validates the rewrite unchanged).

### Addendum (2026-06-06): fetch the LATEST snapshot per publication, not the earliest

The ADR-023 body-fetch used `collapse=urlkey` on the CDX query, which returns the **earliest** snapshot per URL, and fetched the body/title/date from that capture. For pre-~2013 publications the earliest capture is a degraded early-migration **stub**: a truncated body, a junk `"CBO"` `<title>`, and a less-accurate page date.

**Trigger.** A 2010 coverage audit showed CBO 2010 at only 28 records, almost all titled `"CBO"`, January-clustered, with bodies of ~60-130 words — implausibly thin against 2011's 127 records. Probing `pub/41813` across its snapshot history isolated the cause:

| snapshot | body words | title | page date |
|---|---|---|---|
| 2012-04-28 (earliest) | 22 | `CBO` | 2010-01-01 |
| 2019-03-04 (later) | 162 | `Policies for Increasing Economic Growth…` | 2010-01-14 |

The earliest capture predates CBO's site re-platforming, so Wayback holds only a thin migration placeholder. The page's own metadata carries the true publication date regardless of snapshot age, so a later capture is **strictly higher-fidelity** for body, title, and date — and some stubs had no extractable date at all and were being dropped entirely (suppressing the count).

**First attempt (rejected) — the `29991231` far-future redirect.** The initial fix fetched the latest snapshot via `web/29991231000000id_/{url}`, on the assumption it 302-redirects to the most recent capture. It does so only *non-deterministically*: a re-ingest still showed 2010 at 23 records, all January cost-estimate scorings, with every analytical report missing. Probing the band exposed why — the far-future redirect frequently resolves to a Wayback **interstitial** page titled `"Wayback Machine"`, ~350 words of chrome, dated *today*. That junk either (a) passed the window filter (today ∈ window) and polluted the latest-year column, or (b) yielded no usable body/date and dropped a real publication. Because it's non-deterministic, the *same* URL returned clean 2010 content on one request and the interstitial on the next, so real publications were silently lost or mis-dated to "today".

**Independent inventory confirmed it's a processing bug, not a discovery gap.** A non-collapsed CDX enumeration of the 2010 ID band (`/publication/418xx-426xx`) returned **695** distinct `/publication/{id}` pages Wayback holds as 200/text-html, against **23** we emitted into 2010 — the pages exist, we were dropping them. The band is also *date-mixed*: CBO's 2012 migration assigned `/publication/` ids to a large pre-2010 back-catalog interleaved among contemporaneous ids, so a single block legitimately spans 2007-2011 page dates (the page-date filter, reading a real capture, sorts this out correctly).

**Fix (adopted).** `CBOIngestor._cdx_block` no longer uses `collapse=urlkey`. It fetches every snapshot row for the block (bumped row limit, fail-loud if truncated) and aggregates `min(ts)`/`max(ts)` per id. `fetch()` pre-filters on the earliest (`min`) timestamp as before, then fetches the **latest real capture** (`max` timestamp) — a concrete archived timestamp, never the `29991231` redirect. Falls back to the earliest capture if the latest is unusable. A defensive guard drops any page whose title is exactly `"Wayback Machine"`. The strict page-date window gate, the ≥50-word floor (ADR-022), and the rule that the snapshot timestamp is never the publication date are all unchanged. Validated on the full 422xx block: every row returned a real archived page with a correctly-extracted date (2010/2011 reports of 399-1588 words, pre-2010 back-catalog correctly dated and dropped, table-only stubs dropped by the floor) and **zero** `"Wayback Machine"` junk.

**Scope.** `CBOIngestor._cdx_block` (no-collapse + min/max aggregation + truncation guard) and `CBOIngestor.fetch` (latest-real-ts fetch + interstitial guard) in `src/mnd/ingestion/institutional.py`, plus this addendum. No config or test-contract change (`cbo_2023_wayback` still validates the path). Verification: re-run `SOURCES="cbo"` ingest, then `scripts/verify_coverage.py cbo` — expect 2010 to rise off 23 and the latest-year column to shed any `"Wayback Machine"`/today-dated junk.

### Addendum (2026-06-08): the earliest-snapshot upper-bound pre-filter dropped the ENTIRE corpus

**Trigger.** A post-cleanse smoke (`CBOIngestor.fetch`, 2010-01-01..2010-06-30) returned **0** publications despite Wayback being reachable (CDX 200). The id band `[41500..42807]` enumerated correctly (14 blocks) but nothing was yielded.

**Cause.** `fetch()` carried a *cheap pre-filter* that skipped any candidate whose earliest snapshot fell outside `[start, end + 90 days]`. The `+90 day` upper bound assumed Wayback crawls a new cbo.gov URL within ~90 days of publication. That assumption is **false for all pre-2018 CBO content**: the `/publication/{id}` URL scheme only came into existence with CBO's 2012 site migration, so the earliest archived capture of a 2010-dated publication is ~2012 — years past the `end + 90d` bound. A CDX probe of the band confirmed it: every id in `415xx–428xx` first appears in Wayback on `2012-04`/`2012-10`, never 2010. The upper-bound filter therefore dropped *every* candidate before any body fetch — a silent total-corpus under-capture, the exact failure mode the project forbids documenting as a limitation.

**Fix (adopted).** Removed the unsound upper bound and the `_WAYBACK_DISCOVERY_LAG_DAYS`/`window_end_with_lag` machinery entirely. The pre-filter now keeps only the **sound lower bound** (`snap_date < start → skip`): a snapshot can never predate publication, so an earliest capture before the window start does prove the publication is pre-window. The authoritative window decision remains the post-fetch `page_date` gate, which reads each capture's own metadata. Cost: candidates in the bottom `_ID_RANGE_PAD` (≈500 ids of late-prior-year publications) are now body-fetched then date-dropped rather than skipped cheaply — negligible over a multi-hour full run, and correctness strictly dominates. Re-smoke (2010 full year) returned real January-2010 cost-estimate publications (e.g. *H.R. 689, Shasta-Trinity National Forest…*, *S. 1369, Molalla River Wild and Scenic Rivers Act*) with correct in-window dates, real titles, and ≥50-word bodies — zero `"Wayback Machine"` interstitials.

**Scope.** `CBOIngestor.fetch` pre-filter + removal of the `_WAYBACK_DISCOVERY_LAG_DAYS` constant in `src/mnd/ingestion/institutional.py`, plus this addendum. No config or test-contract change. Verification before the long re-ingest: `SOURCES="cbo"` smoke shows in-window dates / real titles / ≥50 words, then `scripts/verify_coverage.py cbo` (ADR-028 shape pivot).

### Addendum (2026-06-09): per-pid checkpoint-resume — the Wayback walk can't fit one SLURM job

**Trigger.** Two clean-reingest CBO jobs failed at `HTTP 429` after the `_wayback_get` retry budget (raised 7→10 attempts + honor `Retry-After`, commit `05b1e96`) was exhausted on the same publication. To replace guesswork with measurement, a throwaway probe (`scripts/_probe_wayback_rate.py`, now deleted) hit IA's actual replay endpoint with real CBO snapshot URLs. Findings: IA throttles at **both** the TCP layer (connection-refused, no HTTP) **and** HTTP 429/503; burst tolerance is **~15–31 requests and COUNT-based** (slowing the base request rate barely moves the threshold — you cannot pace under it); cooldown is **~60–180s**; the sustained-safe rate is **~1 request / 9–12s**. A CDX-only census (no replay GETs) counted **13,616 unique CBO pids** in scope. At the safe rate that walk is **~45h**, over the **36h caslake QOS cap** — it cannot complete in a single job.

**Why not the alternatives.** Live `cbo.gov` is DataDome-blocked (defeats headless Chromium; ADR-017/021) and `govinfo.gov` was rejected for uneven GPO deposit coverage (ADR-020), so Wayback remains the mandated source and the only lever is walltime. Splitting CBO into ID-range shards would re-derive the same total work and add bookkeeping; resuming a single logical walk across sequential jobs is simpler and needs no scope change.

**Fix (adopted).** `CBOIngestor` gains an optional `checkpoint_path`. The checkpoint is a flat **one-pid-per-line** file (ext `txt` via `run_pipeline`'s `_make_ingestor`). `fetch()` skips any pid already in the checkpoint (no Wayback GET), and `_mark_done(pid)` appends the pid **only after** the `yield` resumes — i.e. after the caller has written *and flushed* the article to the raw JSONL (or, for a deliberately-dropped pid, immediately, since there's nothing to write). `run_pipeline` now `fh.flush()`es every record and routes `cbo` (alongside the composite `institutional`) through the checkpointed constructor. Ordering guarantee: a pid is never marked done before its record is durable; a kill between write+flush and the mark causes at most a re-fetch + duplicate on resume, which downstream URL/content dedup absorbs. A pid whose fetch **raises** on ban-exhaustion is never marked, so the resume retries it — the ADR-030 fail-loud contract is preserved. A resume run that legitimately yields 0 new records (tail already complete) is no longer treated as under-capture when the output file is already populated.

**Correction (2026-06-09, same day) — pace at the safe rate; the "ride out the bans" assumption was wrong.** The first checkpoint-enabled job (`50614480`) still `FAILED` (exit 1:0) at `pub/41672` after 52 minutes — the *same* pid that killed both pre-checkpoint runs. The retry cushion does **not** absorb the bans: at the old 0.3s/pid pace the walk bursts ~15-30 fast requests, IA blocks, and because the walk resumes hammering immediately after each cooldown the bans **escalate** until one exceeds the 10-attempt `_wayback_get` budget (~170 pids in, deterministically). Resume-and-continue at that pace would only buy ~170 pids per job ⇒ ~80 submissions — not viable. The actual lever is the one first dismissed: the probe's "sustained-safe ~1 req/9-12s" *is* a real sustained pace, and 0.3s was far above it. `CBOIngestor._REQUEST_SPACING_S = 12.0` (replacing the 0.3s inter-pid sleep) keeps the rolling-window request count under IA's threshold so the ban never trips. A job then runs to its 36h walltime (clean `TIMEOUT`, not a mid-walk raise) and the checkpoint carries the ~45h-total walk into a second job. The `_wayback_get` retry cushion is retained only as a safety net for an isolated ban (which, un-escalated, clears within budget); it is no longer the primary defence.

**Scope.** `CBOIngestor.__init__`/`_load_checkpoint`/`_mark_done` + `fetch` skip-and-mark + extracted `_fetch_and_build` helper + `_REQUEST_SPACING_S = 12.0` (replacing the 0.3s inter-pid sleep) in `src/mnd/ingestion/institutional.py`; `_make_ingestor` checkpoint routing + per-record `fh.flush()` + resume-aware 0-count gate in `scripts/run_pipeline.py`; this addendum. The composite `InstitutionalIngestor` path still instantiates `CBOIngestor()` uncheckpointed (its own source-granularity checkpoint is unchanged). No config or test-contract change. The checkpoint file is **co-keyed to the window** (`.{source}_{start}_{end}_checkpoint.{ext}`) so it can never diverge from its date-stamped output file: the submit script defaults the window end to "today", so a multi-day resumable walk gets a new output filename each calendar day, and a date-independent checkpoint would silently skip pids written to the prior day's file. Operation: `NUKE_RAW=1` archives the checkpoint with the raw dir so a fresh build starts clean; **pin `END=<date>`** across re-fires (`END=2026-06-08 SOURCES="cbo" SKIP_DOWNSTREAM=1 SKIP_CLEANUP=1 bash scripts/rcc/submit_parallel_ingest.sh`) so each job resumes the same window rather than starting a fresh file; repeat until the walk completes, then re-fire the downstream chain.

**Second correction (2026-06-09) — pace the CDX *enumeration* sweep too, and cache it; fetch-only pacing left the ban-trip upstream.** With `_REQUEST_SPACING_S = 12.0` applied to the snapshot fetches, the walk *still* `FAILED` (exit 1:0) at `pub/41672` — across **four** consecutive jobs (`50595473`, `50604248`, `50614480`, `50623881`), each dying at the same first-fetched pid with HTTP 429, **zero** real articles fetched, the checkpoint stuck at 172 pids (all the pre-`/publication/`-era ids that skip without a fetch). The 12s fetch pacing never got a chance to act: the traceback dies on the *first* snapshot fetch, and the log timeline (`enumerating…` at 11:23:46 → first 429 at 12:24:19) shows ~1h of **CDX enumeration** ran first. The 218-block CDX sweep was still **unpaced** (a 0.5s inter-block sleep) and is itself enough Wayback traffic to trip IA's count-in-window ban; the sweep established the ban *before* fetching began, so fetch #1 was dead on arrival, and every re-fire repeated the full unpaced sweep, re-escalating the ban. Net: the resume design was defeated because the checkpoint could never advance past pid #1.

Two changes (in `src/mnd/ingestion/institutional.py`):

1. **Pace the enumeration sweep** at the same `_REQUEST_SPACING_S` as the fetches (count-based ban → keep the rolling-window request count under threshold across *both* IA-facing phases, not just the fetch phase). ~44 min for the 218-block sweep.
2. **Cache the CDX map to disk** — `_build_or_load_cdx_map` writes `{pid: (earliest_ts, latest_ts)}` atomically (temp-file + rename) to `.{source}_{start}_{end}_cdxcache.json` (window-keyed, beside the checkpoint) once the full sweep completes; a resume **loads the cache and skips the sweep entirely**. So re-fires neither re-hammer IA with 218 blocks nor re-pay the enumeration — they start fetching immediately from the checkpoint, and the ~45h fetch budget spans ~2 jobs as the resume design intended. `fetch` was restructured to consume the map (sorted-pid walk) rather than interleave enumeration with fetching. Uncheckpointed callers (composite path) get the paced sweep but no cache. No config or test-contract change.

Operational note: IA escalates IP-level bans under repeated abuse, and the four rapid re-fires hammered it; after this fix the first run should **wait several hours for IA to cool** before submitting, or it may still 429 on a residual ban regardless of our pacing. A clean reset before the first fixed run removes the stale partial + checkpoint + any cache: `rm -f data/raw/articles/cbo_*.jsonl data/raw/articles/.cbo_*` then the pinned re-fire above.

**Third correction (2026-06-09) — a ban must PAUSE the walk, not crash it; finishing is an egress-IP problem, not a pacing problem.** The cached, fetch-paced run (`50634074`) confirmed the diagnosis the second correction only half-grasped. Enumeration succeeded (cache wrote 13,616 pids, ~640 KB) and 124 real publications were captured — then the job `FAILED` at `pub/41672` with HTTP 429 after the retry loop's 10 attempts. The fetch death after ~172 checkpoint entries was **identical regardless of pacing** (0.3s and 12s both die there), which is the signature of a *cumulative request-count cap on the egress IP*, not a rate/burst limiter. Pacing cannot beat a count cap; it only changes how long until you hit it. The Midway egress IP was flagged from five CBO jobs in ~19h, so its budget was small.

Two consequences, one code change:

1. **The fix is operational, not algorithmic.** A count-capped, possibly-banned IP cannot complete a ~13.6k-fetch walk no matter how the client behaves. Finishing CBO means running from a **fresh egress IP** (the walk completes in one shot under a clean budget) or after a **long cooldown** that restores the Midway IP's budget. The client's only job is to not *waste* or *escalate* either path.

2. **So the client rides out throttles patiently, and only pauses-and-resumes on a true hard ban — it never crashes on 429.** `_wayback_get` now keeps **two separate budgets**. A 429 is IA's rolling-window throttle: it honors `Retry-After` over up to `ban_cooldowns=20` multi-minute waits and **continues the same request** once the window clears. Patient cooldowns are what IA asks for and do *not* escalate the ban — only the prior *rapid* 10-attempt hammer did. Only after the full patience budget is exhausted (a genuine hard ban needing a human) does it raise a new `_WaybackBanned(RuntimeError)`, which `CBOIngestor.fetch` catches to log where it stopped (`PAUSED at pub/N — … re-fire to resume`) and **`return` from the generator** — a clean exit, not a traceback. The paused pid is *not* marked done, so the checkpoint banks every prior capture and a later run resumes from exactly that pid. 5xx/network stay on the separate `max_attempts=10` escalating-backoff budget and still RAISE on true exhaustion (ADR-030 fail-loud preserved — only a *sustained ban* pauses, never a genuine outage masquerading as empty).

Net effect: at the 12s sustained pace a clean egress IP never trips the throttle, so a **local run from a fresh residential IP completes the full ~13.6k-pid walk in one shot** (~49h wall + ~45min enumeration); a transient IA hiccup is ridden out rather than ending the run; a cooldown-then-resume run on a flagged IP continues without re-paying enumeration or crashing. The reset/re-fire one-liner above is unchanged.

---

## ADR-024: Repo cleanse + single-source-of-truth doc governance + document-and-push-per-task workflow

- **Status**: Accepted
- **Date**: 2026-06-03

### Context

Methodology kept drifting between work sessions: decisions already made (e.g. CBO's retrieval path) were re-litigated because superseded docs and dead code still described the old state as if current. A concrete instance: `institutional.py:14`, `requirements.txt`, and `config/whitelist.yaml` all still described CBO as using the ADR-017 Playwright path (or the even older ADR-013 sitemap path), while the live code uses Wayback bounded-ID enumeration (ADR-023). That stale text caused the project owner to doubt whether we were using a known-unreliable Wayback approach. Scattered one-off scripts, an `scripts/archive/` tree of removed ingestors, and historical docs that contradicted the ADR log all added surface area for confusion.

### Decision

1. **Cleanse.** Removed dead/superseded artifacts (all recoverable from git history):
   - Code: `scripts/smoke_test_checkpoint.py`, `scripts/_battery_case.py`, `scripts/archive/` (entire tree — 12 removed-ingestor files + archived keyword config).
   - Docs: `docs/handoff_to_claude_code.md`, `docs/filter_audit_jel.md`, `docs/deviations_from_plan.md`.
   - Local junk: `__pycache__/`, `.pytest_cache/`, `.DS_Store`.
   - **Retained deliberately:** `scripts/probe_cbo_wayback_dates.py` (CBO `_ID_DATE_ANCHORS` re-calibration tool — CBO full-corpus completeness is still an open question), `playwright` dep + `scripts/install_playwright_for_cbo.sh` (ADR-023 dormant fallback), `docs/*.pdf` (frozen provenance).
2. **Single-source-of-truth doc governance.** A methodology fact lives in exactly ONE place — its ADR. `docs/architecture_decisions.md` is the sole authority for any methodology *change*; `docs/METHODOLOGY.md` describes the *current* method; `CLAUDE.md` is the operational guide and *points to* ADRs rather than re-paraphrasing them; `MND_PROJECT_SPEC.md` holds scope/phases; `prereg/PREREGISTRATION.md` is the freeze. Every other doc references a fact by ADR number rather than restating its value. Fixed the stale CBO restatements in `institutional.py`, `requirements.txt`, and `whitelist.yaml` to point at ADR-023.
3. **Document-and-push-per-task workflow.** Every completed task is documented (what happened, why, what was found) in the timeline — a git commit, plus a new ADR when the task is a methodology decision — and pushed. The project tolerates a timeline-based decision architecture; it does not tolerate scattered files or broken/superseded code.

### Consequences

- The repo now has one authoritative description of each methodology decision; contradictions between docs/code are removed.
- Deleted items are recoverable via git history; nothing is permanently lost.
- Going forward, agents start each session from a consistent base, reducing re-litigation of settled decisions.
- Open item unaffected by this cleanse: CBO full-corpus Wayback completeness remains unvalidated (CBO never ran to completion in the 2026-06-02 ingest) and must be checked against CBO's narrative-prose publication count during the parallel-ingest verification.

---

## ADR-025: NY Fed Staff Reports captured via RePEc/IDEAS; year-only dates imputed by sequence

- **Status**: Accepted
- **Date**: 2026-06-03

### Context

Dimension 2 of the basis set (US monetary research voice, ADR-020) is the NY
Fed. `FedRegionalIngestor._fetch_liberty_street` only captured the Liberty
Street Economics blog, which begins in 2011 and excludes the bank's flagship
*Staff Reports* working-paper series — a large, on-topic body of macro-finance
research that was silently absent from the corpus. This is an under-capture of
an already-decided source, not a corpus change.

newyorkfed.org item pages are JS-rendered and expose no machine-readable
metadata. RePEc/IDEAS indexes the complete series (`fip/fednsr`); verified live
2026-06-03 that each item page (`/p/fip/fednsr/{repec_id}.html`) carries clean
`citation_*` meta tags — identical in shape to the NBER ingestor (ADR-020). The
series listing pages enumerate every report newest-first under `<h3>YYYY</h3>`
headers and provide the internal RePEc id, which is required because for recent
papers the RePEc id differs from the SR number (so SR-number probing of item
pages fails). `citation_publication_date` is full `YYYY/MM/DD` for ~sr659
(late 2013) onward and **year-only** for earlier reports.

### Decision

1. Add `FedRegionalIngestor._fetch_ny_staff_reports`: walk the IDEAS listing
   pages (descending, stop once below the window), then fetch each in-window
   item page and parse `citation_*` meta (title, authors, abstract, date).
   Body = title + abstract (NBER convention). Canonical `Article.url` is the
   newyorkfed.org PDF (`.../staff_reports/sr{number}.pdf`); the RePEc id and
   IDEAS url are kept in `raw_metadata`. Emitted under `source_id="fed_ny"`
   (same bank/dimension as Liberty Street) with `document_type="fed_staff_report"`
   so corpus-composition QA can separate the two streams.
2. **Year-only date imputation.** When only the publication year is available
   (pre-~2014 records), place the report within its year by its rank among
   same-year reports (Staff Reports are numbered monotonically through the
   year): `date = Jan 1 + round((rank + 0.5)/n × 364)`. This avoids piling
   ~40-60 reports/year onto Jan 1, which would fabricate a weekly-volume spike
   in 2010-2013. The imputation is deterministic and anchor-independent — it
   estimates an unavailable field, it is not a tuned parameter (consistent with
   the no-hand-tuning rule). Imputed records are flagged `date_imputed: true`
   in `raw_metadata`. Reports with full dates (~sr659 onward, covering all
   anchor-era years 2015+) use the exact `YYYY/MM/DD`.

### Consequences

- The NY Fed dimension now includes its working-paper series back to 2010, not
  just the 2011+ blog; capture of an already-decided source is completed.
- Pre-2014 NY Staff Reports carry imputed within-year dates; the `date_imputed`
  flag lets downstream analysis identify them. All anchor-relevant years
  (2015+) have exact dates, so no anchor's volume curve depends on the imputation.
- The RePEc `refs.cgi` Python-repr export was evaluated and rejected in favor of
  the item-page `citation_*` meta — same data, valid HTML, no fragile
  literal-eval of a non-JSON payload.

---

## ADR-026: PIIE via Wayback CDX enumeration; sitemap demoted to freshness supplement

- **Status**: Accepted
- **Date**: 2026-06-04

### Context

PIIE is the second ingestor on dimension 7 (US policy think-tank, ADR-020),
paired with Brookings. The 2026-06-03 full re-ingest captured only 857 PIIE
records, and a year histogram exposed the shape as wrong: coverage **starts at
2016**, with no 2010–2015 content, and *declines* into recent years
(2016: 255 → 2024: 38) — backwards for a healthy index. PIIE `COMPLETED` clean
(no timeout), so this is silent under-capture, not a wall-clock failure.

Root cause: PIIE migrated CMS around 2016. Pre-2016 publications live at
flat-slug URLs (`/publications/policy-briefs/2008-oil-price-bubble`, often with
a legacy `?ResearchID=NNNN`); 2016+ items use a `/YYYY/` segment
(`/publications/policy-briefs/2016/...`). The ADR-021 discovery path walks the
Drupal xmlsitemap (`sitemap.xml?page=N`), which lists **only the `/YYYY/` URLs**
plus a thin recent slice of blogs — it structurally cannot reach the legacy
flat-slug corpus, and the `_URL_PATTERNS` regex required a `/YYYY/` segment so
even a discovered flat-slug URL would be rejected. Wayback CDX enumeration of
the publication/blog prefixes (verified live 2026-06-04) shows the true size:

| Type | distinct URLs | `/YYYY/` (in sitemap) | flat-slug (missing) |
|---|---|---|---|
| policy-briefs | 585 | 123 | 462 |
| working-papers | 535 | 135 | 400 |
| piie-briefings | 38 | 11 | 27 |
| blog: realtime-economic-issues-watch | 1,971 | — | — |
| blog: trade-and-investment-policy-watch | 446 | — | — |
| blog: trade-investment-policy-watch (old slug) | 459 | — | — |
| blog: china-economic-watch | 475 | — | — |

So the complete PIIE corpus is ~4,500 URLs vs the 857 captured. Two additional
sitemap-era defects surfaced: the trade blog exists under **two slug eras** (the
`_URL_PATTERNS` regex matched only the no-`and-` form) and `china-economic-watch`
(a macro-relevant blog) was never targeted at all.

### Decision

Replace sitemap-only discovery with **Wayback CDX enumeration ∪ the live sitemap
walk**, deduped into one candidate set (`PIIEIngestor._cdx_enumerate`,
`_cdx_query`, `_cdx_get`):

1. **CDX is the workhorse.** One `collapse=urlkey&filter=statuscode:200&fl=original`
   query per content prefix returns the distinct canonical URL set across both
   URL schemes. Results are cleaned (drop asset extensions, strip query/fragment,
   normalize host to `https://www.piie.com`, drop bare section and `/type/YYYY`
   year-index pages) and deduped. CDX hits archive.org directly — no Cloudflare —
   and `_cdx_get` retries transient 429/5xx/network with jittered backoff and
   **raises on exhaustion** (under-capture must fail loud, per ADR-022/023).
2. **Sitemap walk retained as a freshness supplement** — it catches brand-new
   items Wayback has not yet archived. CDX-listed first so its `doc_type` wins on
   collision; both merge on a canonical (https, no-trailing-slash, lowercased) key.
3. **Bodies fetched from LIVE piie.com via curl_cffi** (`_piie_get`, unchanged) —
   the legacy flat-slug URLs still resolve 200.
4. **Date is page-authoritative.** Flat-slug URLs carry no path year, so every
   CDX URL is fetched-then-date-checked against the window using the page's own
   publication date (Methodology principle 1, ADR-022). The slug year is never
   trusted (e.g. `2008-oil-price-bubble` is a brief *about* the 2008 oil price).
5. Blog coverage expanded to both trade-blog slug eras and `china-economic-watch`;
   `_URL_PATTERNS` (sitemap side) updated to match.

PIIE SLURM budget bumped 3h → 6h to cover ~4,500 live body fetches.

### Consequences

- PIIE publication+blog capture roughly 5×'s and gains the full 2010–2015 history,
  including the taper/China/Brexit anchor-era policy briefs. Dimension 7 is now
  fully captured from both ingestors (Brookings via its full 2010–2026 re-ingest).
- Overlap with the sitemap and with any earlier partial PIIE JSONL is harmless —
  the downstream filter dedups by URL/content (no topical or volume limiting).
- New runtime dependency on Wayback CDX availability for PIIE (already a CBO
  dependency, ADR-023); the fail-loud `_cdx_get` ensures a CDX outage halts the
  job rather than silently truncating.
- `china-economic-watch` adds macro-China blog content not previously in the
  corpus; this is completion of the source, decided here, not a corpus change.

---

## ADR-027: Federal Reserve Board testimony added as a distinct document stream

- **Status**: Accepted
- **Date**: 2026-06-04

### Context

Dimension 1 of the basis set (US monetary authority, ADR-020) is the Federal
Reserve Board. `FederalReserveIngestor` walked seven streams — FOMC statements,
FOMC minutes, Beige Book, speeches, FEDS Notes, Monetary Policy Reports,
Financial Stability Reports — but **not Board testimony**. The Chair's
semiannual Humphrey-Hawkins testimony and governors' appearances before House
and Senate committees are first-order monetary-policy discourse: the Fed
explaining and defending its stance under direct questioning. Their absence is
an under-capture of an already-decided source, parallel to the NY Fed Staff
Reports gap (ADR-025) and directly analogous to `CongressionalIngestor`'s
capture of Treasury-Secretary testimony.

Verified live 2026-06-04: testimony is published on the identical CMS template
as speeches — `/newsevents/testimony/{year}-testimony.htm` (2011+) with the
same no-hyphen legacy filename pre-2011 (`{year}testimony.htm`), the same
`.eventlist > div.row > (time, div.eventlist__event a, p.news__speaker)` markup,
and a parallel RSS feed (`/feeds/testimony.xml`). Volume is ~9–24 items/year.

### Decision

1. Generalize the speech walk into a shared `_walk_eventlist_stream(...)` plus
   `_fetch_eventlist_rss_year(...)`, parameterized by index/legacy URL template,
   RSS url, `section`, and `document_type`. `_fetch_speeches` and the new
   `_fetch_testimony` are thin wrappers; speech behavior is byte-for-byte
   unchanged (same templates, same 200-word index / 50-word RSS thresholds, same
   legacy-fallback and COVERAGE-GAP error logging).
2. Wire `_fetch_testimony` into `fetch()`. Emitted under
   `source_id="federalreserve"` with `section="testimony"` /
   `document_type="testimony"` so corpus-composition QA can separate it from
   speeches. Publication date is the index `time` (MM/DD/YYYY); page date is
   authoritative, consistent with methodology principle 1 (ADR-022).

### Consequences

- The Fed dimension now includes its testimony stream back to 2010 (~200–400
  documents across the window); capture of an already-decided source is
  completed. Requires a federalreserve re-run to materialize.
- The speech and testimony walks now share one code path, so future CMS markup
  changes are fixed once. No new runtime dependency (same federalreserve.gov
  fetch path and `_get` timeout normalization).

---

## ADR-028: Coverage-verification standard (shape + independent inventory); BIS pre-2014 review-speech recovery as the trigger

- **Status**: Accepted
- **Date**: 2026-06-04

### Context

The 2026-06-04 full re-ingest cleared BIS as "fixed" on two signals: the SLURM
job did not fail/timeout, and a year histogram showed all years 2010-2026
present. Both were misleading. BIS was undercapturing the early years by a flat
**~10x** (2010: 96 records captured vs ~1,000 actually published). Root cause:
pre-2014 the BIS sitemap lists each `/review/` speech only as a `…\.pdf` URL
(the `.htm` landing page exists at the same stem but is not in the sitemap), and
`BISIngestor._URL_PATTERNS` required `.htm`. So the `speech` series ran from ~0
in 2010-2012 to 765 in 2014 — invisible in a year-TOTAL view because the other
series filled the gap, and invisible to "did it run" because nothing errored.

This is a general verification failure, not a one-off: "no failure" and "all
years present" do not evidence full capture, and any source whose URL/format
scheme changed mid-window is exposed to the same silent loss.

### Decision

**1. BIS fix (the trigger).** `BISIngestor._fetch_year` rewrites
`/review/rNNN….pdf` → `.htm` before pattern-matching. The existing trafilatura
fetch path parses the HTML landing page; the `seen` set collapses the rewritten
form against any direct `.htm` sibling (2014+). Recovers ~900 review speeches/yr
for 2010-2013 and ~160/yr of PDF-only speeches that persist in later years. No
PDF extraction needed; working papers were already captured as `.htm` pre-2014,
so the rewrite is scoped to `/review/` only.

**2. Verification standard (the go-forward rule).** Before any source is cleared
as fully captured, two checks are mandatory:
   - **Independent ground-truth, by series × year.** Enumerate what the source
     itself exposes — sitemap URLs per series counting *all* format variants
     (`.pdf` and `.htm`), CDX distinct-URL counts, listing-page totals — and diff
     against captured. The gap is the signal; captured counts are never trusted
     in isolation.
   - **Shape, not presence.** Pivot captured records by (year × document_type),
     never year-total alone, and hunt bug signatures: a 5-10x **cliff** between
     adjacent years in one series (format/URL-scheme change), an implausible
     **spike** (dedup bug — see PIIE 2016 dual flat-slug + `/YYYY/` URLs), a
     series at **zero** inside its own active span.
   - Tooling: `scripts/verify_coverage.py <source>` prints the year ×
     document_type pivot, the flat-vs-`/YYYY/` URL split, and auto-flags
     CLIFF/GAP/DUP. It is the standing captured-side check (check #2); a clean
     run is necessary, not sufficient — check #1 (independent inventory) still
     governs whether a source is cleared.

### Consequences

- BIS early-year speech volume rises from ~90/yr to ~1,000/yr, matching the
  2014+ baseline. Requires a BIS re-run to materialize.
- The integration battery (`tests/integration/test_source_coverage.py`) asserts
  per-window floors, which is a weak "lack of failure" check (it would not have
  caught BIS's 10x gap above the floor). Floors should migrate toward
  inventory-relative expectations over time; tracked as follow-up, not blocking.
- The standard adds a verification step per source but is the only defense
  against silent under-capture, which is the project's sole ingest failure mode
  (the corpus is content-neutral by ADR-020; relevance is decided downstream).

---

## ADR-029: PIIE two coverage defects found by the ADR-028 standard (blog tail; 2016-misdated publications)

- **Status**: Accepted
- **Date**: 2026-06-05

### Context

Applying the ADR-028 verification standard to PIIE (year × document_type pivot +
independent Wayback CDX inventory) surfaced two silent under-capture defects that
"no failure + all years present" had hidden:

1. **Blog tail hard-zeros after 2022.** `piie_blog_post` ran 2010→2022 then dropped
   to zero for 2023-2026. The RealTime blog's new posts had migrated from the
   legacy flat-slug path `/blogs/realtime-economic-issues-watch/<slug>` (the only
   realtime prefix we enumerated) to `/blogs/realtime-economics/<YYYY>/<slug>`
   ~2022. CDX confirms ~423 posts that exist *only* under the new path (the missing
   2018-2026 tail) plus ~199 back-catalog posts present under *both* paths.

2. **Pre-2016 publications all misdated to 2016.** `policy_brief` / `working_paper`
   / `piie_briefing` were zero for 2010-2015 then spiked at 2016 (464 / 390 / 35).
   PIIE's 2016 Drupal migration stamped `article:published_time` with the migration
   timestamp (`2016-03-02T20:43:26-05:00`) on the *entire* back-catalog; trafilatura
   reads that OpenGraph field, so every pre-2016 publication collapsed onto 2016.
   The true date survives in the page's `hero-banner-publication__date` <time>
   element (e.g. a 2009 brief shows `datetime="2009-08-01"`). Blog *article*
   pages carry a correct `article:published_time` — but see the 2026-06-05
   addendum below: junk enumeration URLs do not, so blogs need the same
   extract-or-drop treatment. Confirmed by fetching archived raw HTML for a
   policy brief and a working paper; sidebar "related" dates use a distinct
   `teaser__date` class and are explicitly not matched.

### Decision

**1. Blog tail.** Add `blogs/realtime-economics` to `PIIEIngestor._CDX_PREFIXES`
(listed before `realtime-economic-issues-watch`) and a matching
`/blogs/realtime-economics/\d{4}/[^/]+$` entry to `_URL_PATTERNS`. To avoid
double-counting the ~199 posts under both schemes — which a full-path dedup key
would treat as distinct — blog-post candidates dedup on their **trailing slug**
in `fetch()` (publications keep the full-path key). The new `/YYYY/` canonical URL
wins the collision because it is listed first and is more likely to resolve live.
This also collapses the pre-existing trade-blog dual-era duplication
(`trade-and-investment-policy-watch` vs `trade-investment-policy-watch`).

**2. Publication dates.** Add an optional authoritative `date_extractor` hook to
`_extract_from_html` / `_fetch_page_full`. When supplied it *replaces* trafilatura's
metadata date even when it returns `None` (a `None` means "no authoritative date"
→ caller drops the record per methodology principle 1; it must never fall back to
the known-bad migration stamp). `_piie_publication_date_from_html` reads the
`hero-banner-publication__date` <time datetime>, and PIIE passes it for the three
publication doc types only. Blogs continue using the default trafilatura path.
*(Superseded by the 2026-06-05 addendum — blogs now use `_piie_blog_date_from_html`.)*

### Consequences

- The RealTime blog series extends through 2026 (~423 recovered posts), and the
  pre-2016 publication back-catalog redistributes onto its true years instead of a
  spurious 2016 spike. Both require a PIIE re-run to materialize.
- Publication pages lacking a hero-banner date block are now dropped rather than
  dated to 2016. The block is standard PIIE publication chrome, so loss should be
  negligible; the `no_date` counter in the fetch summary surfaces it if not.
- The `date_extractor` hook is generic and available to any future source whose CMS
  poisons `article:published_time`; it is the structured analogue of the Chicago Fed
  citation-block reader.
- Found purely by the ADR-028 standard (shape pivot + independent CDX inventory),
  validating it as the standing pre-clear check.

### Addendum (2026-06-05): blogs also need extract-or-drop dating

Re-verifying the post-fix PIIE corpus surfaced a third defect the original ADR-029
fix did not anticipate: `piie_blog_post` showed a 6.8x CLIFF at 2022 (726 vs ~170
neighbours). Date-clustering proved it artifactual — **581 of the 726 blog records
were stamped to the single date `2022-05-18`** (every other 2022 month had 6-23).
None were unique real articles. They are **junk enumeration URLs**: Wayback CDX had
recorded soft-hyphen-mangled slugs (`case-raising-in-flation-...`,
`debt-stand-stills`), truncations (`arms-and-`), trailing-punctuation fragments
(`...relief-plan[8`, `...europe;`), text-fragment links (`...%23:~:text=`) and JS
placeholder paths (`blur.placeholder`, `beforeunload.placeholder`) harvested from
in-body broken links on archived pages. Fetched live, they all resolve to a
fallback page whose `article:published_time` is the `2022-05-18` RealTime-blog
migration stamp — so trafilatura dated all 581 to that day. This refutes ADR-029's
"blogs' `article:published_time` is correct" assumption: it holds for real article
pages but not for the fallback page junk URLs land on.

**Decision.** Blogs get the same extract-or-drop treatment as publications, via a
new `_piie_blog_date_from_html`. The blog template nests its `<time datetime>` one
wrapper deeper than publications — inside `<div class="field--name-field-blog-date">`
— so `_PIIE_PUB_DATE_RE` (which wants `<time>` immediately after the hero block)
misses it; the blog regex keys on `field--name-field-blog-date` instead. PIIE now
routes `blog_post` → `_piie_blog_date_from_html` and the three publication types →
`_piie_publication_date_from_html`. A junk URL's fallback page has no
`field--name-field-blog-date`, so the extractor returns `None` and the record is
dropped (methodology principle 1); real posts (old- and new-path alike, since
bodies are fetched live in the current uniform Drupal theme) yield their true date.
Verified the regex against archived live-template HTML for a 2020 old-path post
(`2020-04-07`) and a 2022 new-path post (`2022-07-28`).

**Consequence.** No URL-shape allowlist was added — the corrupted slugs are not
reliably distinguishable from valid ones by shape (`case-raising-in-flation-...`
looks valid), and a shape filter risks dropping real articles with unusual slugs,
which violates the under-capture-is-the-only-failure-mode rule. The date-drop is
the robust backstop; the only cost is wasted live fetches on the junk URLs, a
performance nit within PIIE's 6h budget. Requires a PIIE re-run to materialize.

---

## ADR-030: Fail-loud hardening pass — silent under-capture is forbidden at every fetch boundary

- **Status**: Accepted
- **Date**: 2026-06-08

### Context

A 2026-06-07 read-only audit of `src/mnd/ingestion/institutional.py` (recorded
in the `project_ingestor_robustness_gate` memory) found a systemic class of
defect, distinct from any single source's coverage bug: at many fetch/listing
boundaries a transient or partial failure was swallowed (`log.warning/error;
return`/`break`/`continue`) and the sub-ingestor still completed "clean." On the
parallel fan-out (`submit_parallel_ingest.sh`), a sub-ingestor that exits 0
lets the `afterok` `filter→embed→cluster` chain proceed — so a holey corpus
would silently flow downstream and the hole would only surface (if at all) in
post-hoc coverage QA. This violates the locked principle that **under-capture is
the only failure mode that matters** (CLAUDE.md / ADR-022): a silent partial is
worse than a loud abort because it masquerades as success.

Seven findings, all in `institutional.py` unless noted:

1. **Orchestrator + CLI swallow.** `InstitutionalIngestor.fetch` and
   `run_pipeline.py ingest` caught sub-ingestor/source exceptions and continued,
   so one dead source could not fail the composite or the SLURM job.
2. **Empty-vs-failed body conflation.** `_fetch_page_full` / `_extract_body`
   parsed a 5xx error page into a short body and dropped it as if the article
   were genuinely empty.
3-6. **Listing truncation.** Single-fetch or paginated listings that `return`/
   `break` on any error, silently truncating a whole series: IMF Coveo
   (`_coveo_list`/`_coveo_post`), NBER, Fed-regional (NY Staff Reports both
   passes, Chicago Fed sitemap + per-page, Atlanta pagination + body loop),
   Treasury/OFR (`_scrape_ofr_index`, FSOC current/archive/per-year), VoxEU
   (`_fetch_year` shard), Congressional (`_chrg_list_packages` pagination).
7. **Single-float curl_cffi timeouts.** The impersonating getters
   (`_imf_get`, `_atlanta_get`, `_cepr_get`, `_piie_get`) passed scalar
   timeouts, which only bound the inter-byte read gap — a half-open TCP
   connect can stall far past the nominal value (the `c47fb91` lesson, already
   applied in `_get`/`_wayback_get`/`fed.py`).

### Decision

Establish and apply a uniform fail-loud contract at every ingest fetch boundary,
landed in **one** deliberate pre-launch hardening pass (not mid-flight, per the
robustness-gate memory), so the freeze rebuild runs on uniformly hardened code.

**Classification rule.** By the time an exception reaches these handlers, the
fetch layer (tenacity `_get`: 5 attempts, exponential backoff, retries 5xx +
network, not 4xx — and now the curl_cffi getters, see below) has already
absorbed transient blips. So:
- **404 / genuine 4xx** = the resource genuinely does not exist → skip that item
  (or `break` when it marks the true end of a listing).
- **5xx / network / parse failure after retries** = systemic → `raise
  RuntimeError(... refusing to ... silently)`, which propagates to the
  sub-ingestor, fails the composite, exits the CLI non-zero, and halts the
  `afterok` chain.

The contract is only *sound* if a single transient blip cannot trip it. The
tenacity-backed `_get` paths already had that cushion; the impersonating
curl_cffi getters did not (see "Timeouts" below), so this pass gave them one
too — otherwise the new fail-loud raises on curl_cffi paths (IMF/Atlanta/
VoxEU/PIIE) would nuke a multi-hour source on the first flaky response.

**Orchestrator (finding 1).** `InstitutionalIngestor.fetch` collects per-sub
failures (exception *or* zero articles) and raises after the loop; `run_pipeline
ingest` collects per-source failures and `sys.exit(1)`. Zero articles counts as
a failure — a basis-set source is never legitimately empty.

**Body classification (finding 2).** `_fetch_page_full` / `_extract_body`
inspect status before parsing: 4xx → skip, 5xx → raise, never parse an error
page into a droppable short body. The same status-conflation existed on IMF's
*parallel* body path (`_fetch_publication_body`, `_fetch_legacy_fandd[_body]`),
which bypasses `_fetch_page_full` and called `_imf_get` directly with
`if status != 200: return None`; these were given the identical 4xx-skip /
5xx-raise split, and the caller's `except Exception: body=None; continue`
swallow (which would have re-masked the raise) was removed. The legacy F&D
walker keeps 4xx as genuine absence — its nav-page slugs (basics/people/
picture) legitimately 404, and some months have no issue.

**Timeouts + curl_cffi retry (finding 7, extended).** A shared
`_normalize_timeout(kwargs)` coerces a scalar `timeout` into a `(10.0, read)`
connect/read tuple; every curl_cffi getter calls it (the Coveo POST already
used a literal tuple). Additionally, a shared `_cffi_get_retry(do_get, url)`
wraps each impersonating getter (`_imf_get`/`_atlanta_get`/`_cepr_get`/
`_piie_get`): because those getters deliberately do **not** `raise_for_status`
(callers classify status), a 5xx arrives as a normal response that tenacity
can't see, so the wrapper inspects the status itself and retries on
429 / 5xx / network with exponential backoff (5 attempts), returning only once
the result is non-retryable or attempts are exhausted. This gives the curl_cffi
paths the same transient cushion as `_get`. curl_cffi accepts the same tuple
timeout form as `requests`.

The same gap existed on CBO's Wayback **snapshot** getter `_wayback_get`
(added 2026-06-08): the CDX *enumeration* path (`_cdx_block`) already retried
429/5xx + network errors 7× with backoff, but the body-snapshot getter was a
bare `requests.get`, so a single Wayback flap on the thousands-of-snapshots
walk would raise through `_fetch_page_full` and fail the whole CBO source.
Wayback resolves to a single edge IP (no pool, no IPv6) that refuses/resets
connections during recovery and under burst — observed live while clearing
the pre-launch gate. `_wayback_get` now carries the identical 7-attempt
backoff (retry on 429/5xx + raw network errors; genuine 4xx returns for the
caller to skip; exhaustion raises), giving the snapshot path the same
soundness as the CDX path.

**Additional same-class boundaries hardened (found in review).** Beyond the
seven audited findings, the same two defect classes were closed wherever else
they appeared: the Treasury Secretary-remarks paginated listing (404 = end of
pages, page-0 404 / 5xx / network = raise), the FSOC annual-report PDF
fetch+parse (~16 born-digital reports — a fetch/parse failure raises rather
than dropping a whole year), and the CEA package-list safety bail (raises on
contract drift, matching the Congressional 1000-page bound).

**Per-record refinement — cross-domain body fetches (2026-06-08).** The third
integration battery surfaced the contract's one over-aggressive edge: a
WordPress source's `link` is normally same-domain, but a syndicated post can
carry a *canonical link on a third-party domain* (the trigger case: a Brookings
`article` whose link was `www.chinafile.com/...`, presenting a TLS cert invalid
for that host). The finding-2 raise in `_fetch_page_full` then propagated up and
failed the *entire* Brookings source over one unfetchable cross-domain record.
That is genuine absence of a single record on a host we do not control — not a
Brookings outage — so failing the source is wrong. `_wp_post_to_article` now
takes `expected_host` (the WP source's own canonical host); a body-fetch failure
(`RetryError`/`RuntimeError`/`OSError`/`requests` error) on a link whose host
differs is logged and the record kept on its excerpt, while a failure on the
source's **own** host still raises. This preserves the no-silent-truncation
contract: a real source outage hits same-domain pages and still fails loud; only
scattered third-party syndication links degrade to excerpt, which cannot truncate
a source's tail. Threaded to all three WP-REST callers (Brookings, Liberty Street
Economics, FRBSF).

**Wayback sustained-throttle — honor `Retry-After` (2026-06-08).** The clean
re-ingest's CBO job failed after 33 min on `HTTP 429 after 7 attempts` from
`_wayback_get`. Distinct from the earlier connection-flap cushion: this is
Internet Archive's *sustained* rate limiter, tripped by the full
~21.7k-publication walk firing snapshot replay GETs faster than IA tolerates.
The blind exponential backoff (7 attempts, ~10 min cumulative) was both too
short and the wrong shape — IA returns `Retry-After` on those 429s stating its
own cooldown, which we ignored. Fix: `_wayback_get` now honors `Retry-After`
(integer seconds, clamped to [current-backoff, 600s]) and falls back to
exponential backoff only when the header is absent; attempt budget raised 7→10.
This paces us to what IA actually permits rather than guessing. The fail-loud
contract is unchanged — genuine 4xx still returns to skip, and true exhaustion
across the widened budget still RAISES rather than dropping a snapshot silently.
If the full walk still trips a hard IP-level block, the next lever is reducing
the base inter-request rate (currently 0.3s/publication), traded against the
~3h walltime.

**GovInfo collection pagination — follow `nextPage`, do not splice the cursor
(2026-06-08).** The clean re-ingest failed `congressional` after 3h with a
GovInfo `500` on page 2 of the CHRG collection listing. Root cause was a
pagination-construction bug, not an upstream flap: GovInfo's response carries
`nextPage` as a *fully-formed URL* (with the opaque `offsetMark` cursor already
URL-encoded), but `_chrg_list_packages` treated `nextPage` as if it were the
bare cursor token and spliced it back into the base URL via
`re.sub(r"offsetMark=[^&]+", ...)`. That produced a nested URL
(`...&offsetMark=https://api.govinfo.gov/...?offsetMark=AoJw...`) that GovInfo
500s on, which the fail-loud contract then correctly converted into a hard
source failure. The bug only triggers on page 2+, so the single-page
integration window never exercised it. Fix: follow `nextPage` directly,
appending our `api_key` (which GovInfo omits from the link). The identical
pattern in `CEAIngestor._list_packages` (ERP collection) was latently broken too
— it only escaped because ERP is ~61 packages = one page — and was fixed in the
same pass. The non-paginating granule fetch was left as-is: ERP volumes are
structurally <200 granules, so its single-page `pageSize=200` cannot truncate.

### Consequences

- A persistent failure anywhere in the basis set now aborts the run loudly
  instead of shipping a partial corpus downstream. This is acceptable even for
  the long CBO/NBER runs: **correctness > convenience** is the locked tradeoff.
- The `afterok` chain is now a genuine gate — embed/cluster cannot run on a
  corpus that lost a source to a transient blip.
- Operational note: a flaky upstream that survives all 5 retries will now fail
  the whole source's job rather than degrade silently. The fix is to re-run that
  source (`SOURCES="<src>" SKIP_DOWNSTREAM=1 ...`), not to re-soften the handler.
- No config, threshold, or test-contract change; this is purely a control-flow
  hardening of the ingest layer. The pre-existing `_wp_rest_fetch` / `_cdx_block`
  raise-after-retries handlers were the template the rest now match.
- This is the standing contract for any new ingestor: fetch boundaries classify
  404-skip vs systemic-raise, never swallow-and-continue.

---

## ADR-031: WordPress sources restricted to own-domain content (source-identity rule)

- **Status**: Accepted
- **Date**: 2026-06-09

### Context

The clean re-ingest's Brookings job logged a stream of cross-domain warnings —
WP `article` records whose canonical `link` resolved off `brookings.edu`:
`washingtonpost.com`, `t20japan.org`, a `fengshows.com` TV-appearance video,
etc. These fall into two kinds:

1. **Syndicated op-eds** — a Brookings scholar's piece published *in* another
   outlet (e.g. a Washington Post column), surfaced by Brookings' WP because the
   author is affiliated.
2. **Press / media-mentions** — a third-party article or broadcast *about* a
   scholar, catalogued as an appearance.

ADR-030's 2026-06-08 per-record refinement handled these defensively: it kept
the off-domain record on its *excerpt* (so a single unfetchable third-party link
could not fail the whole source), threading `expected_host` into
`_wp_post_to_article`. That solved the fail-loud over-aggression but left the
scope question unanswered — it still *ingested* the third-party records.

The scope question: are these in scope for Brookings? They are written by
Brookings-affiliated authors, but they are **not Brookings-published content**.
Every other basis-set source contributes only what it itself publishes (Fed
speeches from the Fed, IMF working papers from the IMF, CBO reports from CBO).
Ingesting a scholar's Washington Post column under the Brookings source would:

- **Re-import the journalism dimension** that ADR-010 deliberately removed
  (Washington Post, Reuters, AP, etc. are not in the corpus), through a side door.
- **Break basis-set dimensional independence (ADR-020).** The 12 sub-ingestors
  map 1:1 to 8 independent discourse dimensions precisely because each carries
  one source's own voice; folding third-party outlets into Brookings smears that
  mapping.
- Add little signal: meaningful macro content from Brookings scholars is
  overwhelmingly published *on* brookings.edu; the off-domain entries are
  dominated by media-mentions and appearances, and where a genuine op-ed exists
  off-domain it is available only as an excerpt anyway.

### Decision

A WordPress basis-set source contributes **only content hosted on its own
domain family.** `_wp_post_to_article` now drops any record whose `link` host is
outside `expected_host`'s family **before any body fetch** (host-family test:
strip a leading `www.` from `expected_host`; keep iff `link_host == base` or
`link_host` ends with `"." + base`). This supersedes ADR-030's keep-on-excerpt
refinement for off-domain records: we now drop them outright rather than retain
the excerpt.

This is a **provenance filter on source identity, not a topical filter** — it
asks "did this source publish this?", never "is this about macro?". It is
therefore fully consistent with ADR-020's no-pre-cluster-topic-gate: scope is
still decided post-clustering by the JEL classifier; this only enforces that each
source dimension carries that source's own output.

Checking *before* fetch (not after) is load-bearing for two reasons: (1) it
prevents silently keeping the full body of a *reachable* third-party page (the
keep-on-excerpt logic only degraded gracefully when the off-domain fetch
*failed* — a reachable one would have kept the external body); (2) it removes the
cross-domain fetch-timeout drag (paywalled third-party links that stall the
crawler), which also shortens the Brookings long-pole walltime.

The rule lives in the **shared** `_wp_post_to_article` helper, so it applies
uniformly to all three WP-REST callers — Brookings, Liberty Street Economics
(`fed_ny`), FRBSF (`fed_sf`). The two Fed blogs are expected to carry ~no
off-domain records (their WP only publishes own-host posts), so the rule is a
no-op there and simply makes the invariant explicit and enforced.

On-domain body-fetch failures still **raise** (ADR-030 fail-loud is preserved):
once the off-domain records are dropped up front, every remaining fetch is on the
source's own host, so a failure there is a real outage and must fail the source.

### Consequences

- Brookings (and any WP source) is now strictly own-domain. Off-domain syndicated
  op-eds and media-mentions are excluded — closing the ADR-010 journalism re-import
  side door and preserving ADR-020 dimensional independence.
- **Reversal of an ADR-030 sub-decision:** off-domain WP records are no longer
  kept on excerpt; they are dropped. The `expected_host` parameter is retained but
  its semantics change from "keep-on-excerpt if off-domain fetch fails" to
  "drop if off-domain."
- The current Brookings raw file (already on disk from the in-flight run) can be
  corrected **post-hoc** by filtering off-domain lines with the *identical*
  host-family predicate, avoiding a ~15h re-run. If that run instead TIMEOUTs with
  no usable output, the re-run picks up the new rule (and runs faster for skipping
  the paywall stalls).
- No config/threshold/seed change; control-flow + scope only. Standing contract
  for any future WordPress ingestor: own-domain only, enforced in the shared helper.

---

## ADR-032: CBO enumeration via the authoritative cbo.gov sitemap (supersedes ADR-023 id-floor estimation)

- **Status**: Accepted
- **Date**: 2026-06-10
- **Supersedes**: the enumeration layer of ADR-023 (id↔date anchor table + `_estimate_id_range` + `_MIN_PUBLICATION_ID` floor). Everything else in ADR-023 and its addendums (fail-loud hardening, per-pid checkpoint-resume, 12s pacing, `_WaybackBanned` pause-and-resume, CDX min/max-ts capture) is unchanged.

### Context

ADR-023 enumerated CBO's publication universe by *guessing* a publication-id range from a six-point id↔date anchor table (`_ID_DATE_ANCHORS`), padding ±500, and clamping the floor at `_MIN_PUBLICATION_ID = 40000` on the premise that "below that is pre-2010 back-catalog, out of corpus scope." That premise rests on CBO node ids being roughly chronological. **They are not.**

The CBO full-corpus completeness audit (2026-06-10) probed dates directly across the id space and found old back-catalog reports interleaved with 2011 republications across the *entire* range:

| pid | page date | pid | page date |
|---|---|---|---|
| 21000 | 1981 | 41138 | 2009 |
| 20000 | 1992 | 41479 | 2011 |
| 22000 | 2011 | 41441 | 1983 |
| 25157–25164 | 2011 | 41448 | 2011 |

A 94-of-361 sample of the contested boundary band `41138–41499` (the band just below the Wayback floor of 41500 that ADR-023's machinery would discard) was **19/94 dated 2010+** — real in-window publications the floor was silently dropping. There is **no id value that separates 2010+ from pre-2010 content**: any floor drops scattered in-window publications, and any ceiling keeps scattered out-of-window ones. The page-date gate already sorts window membership correctly *for whatever it is handed* — the only failure was the enumerator never handing it those ids. Dropping scattered 2010+ publications is precisely the under-capture failure the basis-set framing (CLAUDE.md, ADR-020) forbids documenting as a limitation.

CBO publishes an authoritative, complete index of itself: **`cbo.gov/sitemap.xml`**. Crucially, the sitemap path returns **HTTP 200 even though cbo.gov *publication pages* are DataDome-blocked** (403, even via curl_cffi chrome impersonation — verified 2026-06-10) — the sitemap sits outside the bot wall. So we can enumerate the true publication universe directly from CBO, without Wayback and without guessing, then use the archive only for the bodies (the pages we cannot fetch live).

### Decision

**1. The publication universe is the cbo.gov sitemap, not an estimated id range.** `_fetch_sitemap_pids()` fetches `cbo.gov/sitemap.xml` (a `<sitemapindex>` of 14 sub-sitemaps at `sitemap.xml?page=N`), walks every sub-sitemap, and extracts every `/publication/{id}` id via `_PUBLICATION_RE`. Live result 2026-06-10: **25,423 unique publication ids spanning 10329–62515.** Fetched with curl_cffi chrome131 impersonation (`_cbo_get`), which **fails loud** (raises) on any non-200 — there is no guessed-range fallback, because a silent fallback to the old broken estimator is exactly the under-capture trap ADR-030 forbids.

**2. The sitemap `lastmod` is NOT used for dating.** It is CMS-migration noise (13,631 docs stamped "modified" 2019; earliest 2014; publications go back to 1996). Window membership remains the post-fetch page-date gate reading each Wayback capture's own `datePublished`/`article:published_time`/`datetime` metadata — the ADR-022 strict-date policy, unchanged.

**3. CDX still supplies snapshot timestamps; the sweep is driven by the sitemap.** `_build_or_load_cdx_map` now derives the CDX block range from `min/max` of the sitemap ids (≈523 100-id prefix blocks for the full universe), paced at `_REQUEST_SPACING_S` per the ADR-023 third-correction addendum. Each block's `(earliest_ts, latest_ts)` rows are kept **only for ids the sitemap declares real publications** (a prefix query also returns redirects / non-publication nodes). The window-keyed CDX cache (ADR-023 second correction) is unchanged.

**4. Sitemap ids with no Wayback snapshot are logged as a measurable gap, not silently lost.** After the sweep, `missing = sitemap_pids - cdx_map.keys()` is WARN-logged with a count and sample. This converts "publications the archive doesn't hold" from an invisible hole into a counted, auditable quantity — consistent with ADR-028's independent-inventory standard.

**Removed:** `_ID_DATE_ANCHORS`, `_ID_RANGE_PAD`, `_MIN_PUBLICATION_ID`, `_estimate_id_range`, `_estimate_id`. Added: `_SITEMAP_INDEX`, `_fetch_sitemap_pids`, `_cbo_get`. `_PUBLICATION_RE` is retained (now shared by `_cdx_block` and `_fetch_sitemap_pids`).

### Consequences

- **CBO is now enumerated completely and correctly.** Every publication CBO lists is a candidate; the page-date gate decides window membership from real metadata; no id heuristic can silently drop in-window content. The audit's 19%-of-band 2010+ leakage is closed.
- **Enumeration works from any IP** (sitemap + CDX are not the throttled replay endpoint). Only the body fetches hit IA's replay throttle, so the ADR-023 third-correction conclusion stands: finishing CBO is an egress-IP problem. A fresh residential/cloud IP body-fetches the full snapshotted sitemap (~25k pids — see next bullet) at the 12s safe pace: **~83h of active fetching (~3.5 days-equivalent), plus a one-time ~1.7h enumeration.** The checkpoint + CDX cache + `_WaybackBanned` pause-resume carry it across IPs / cooldowns / manual sessions otherwise.
- **Larger candidate set AND a larger body-fetch count (≈2× ADR-023).** 25,423 sitemap ids vs ADR-023's ~13.6k floored census. The lower-bound CDX pre-filter (`earliest snapshot < window start → skip`) is a **near-no-op** here: CBO's `/publication/{id}` URLs were all minted in the 2012 site migration, so almost every pid's earliest snapshot is ~2012 ≥ the 2010 window start. So essentially **all ~25k snapshotted pids are body-fetched**, then the post-fetch page-date gate drops the pre-2010 back-catalog. The *kept* (in-window) set is the original ~13.6k **plus** the scattered 2010+ publications the old id-floor silently dropped — recovering those is the whole point — but the *fetched* set, which is what costs IA budget and wall time, roughly doubles. This is the unavoidable price of correctness: non-chronological ids + migration-flattened snapshot dates leave no pre-fetch date signal, so completeness requires fetching broadly and letting page-date decide. The CDX sweep grows to ~523 blocks (~1.7h paced) but is cached, so a resume pays it once.
- **No methodology change beyond enumeration:** CBO stays in the basis set (dimension 5, legislative fiscal authority), canonical url stays cbo.gov, retrieval stays cbo.gov-via-Wayback for bodies, strict page-date filter and ≥50-word floor preserved. No config/threshold/seed change.
- **New dependency surface:** correctness now relies on cbo.gov keeping its sitemap reachable and outside the bot wall. If CBO ever DataDome-gates the sitemap too, `_cbo_get` fails loud (the run stops) rather than silently under-capturing — the correct failure mode.

### Verification

- `python -c "import ast; ast.parse(open('src/mnd/ingestion/institutional.py').read())"` — syntax OK; module imports clean; no dangling references to the removed symbols.
- Live smoke of `_fetch_sitemap_pids()` against cbo.gov: **25,423 pids (10329–62515), 523 prefix blocks**, with all scattered 2010+ ids found in the audit (22000, 25157, 41150, 41479) plus the RCC death-point pid 41672 present in the set.
- End-to-end remains the fresh-IP body walk (calibration probe of ~300 paced fetches first, then the full checkpointed run), per the ADR-023 third-correction operational note — not yet executed.

### Correction (2026-06-11): the authoritative date extractor was never wired in

The 2026-06-11 source audit found the all-`2011` dating symptom (an early partial run stamped every record `2011`) traced to a real bug, not stale data. ADR-023's class docstring promised CBO dates came from the page's structured `dcterms.created` metadata, but `_fetch_and_build` called `_fetch_page_full` with **no `date_extractor`**, so the date fell to trafilatura's generic picker. trafilatura 1.12.2's picker is **order-sensitive** (verified offline): when the Open Graph `article:published_time` meta appears earlier in `<head>` than the Dublin Core block — the normal Drupal layout — it returns the OG value. On CBO that OG timestamp is the 2011-12 site-migration stamp, which collapsed the pre-migration back-catalogue onto a single `2011` date. This is the same migration-stamp failure class as PIIE (ADR-029), and the strict in-window gate then *kept* the mis-stamped records because `2011` is in-window.

**Fix:** added module-level `_cbo_publication_date_from_html`, an explicit reader of the genuine structured date fields (`dcterms.created → dcterms.issued → dcterms.date → dc.date.created → dc.date.issued → dc.date`, first present wins, tolerant of either meta-attribute order), and passed it as the `date_extractor` on both the latest- and earliest-capture `_fetch_page_full` calls. Reading dcterms explicitly is authoritative regardless of tag order and never falls through to the OG stamp; a `None` result (no structured date present) drops the record per methodology principle 1, surfacing as visible under-capture on re-ingest QA rather than silent mis-dating. No methodology change — this brings the code in line with the date policy ADR-023 already documented and the ADR-029 anti-migration-stamp principle.

**Residual to verify on re-ingest:** the fix assumes CBO's archived Drupal pages actually carry a `dcterms.*`/`dc.date.*` tag. This could not be confirmed offline (no cached CBO HTML; IA + the DataDome-walled live site both unavailable at fix time). The first calibration batch of the fresh-IP body walk must confirm real dates (not zeros) before committing the full run.

---

## ADR-033: Atlanta Fed pre-2019 Wayback recovery (macroblog + working papers)

- **Status**: Accepted
- **Date**: 2026-06-11
- **Lineage**: same deleted-from-live-but-archived recovery pattern as ADR-032 (CBO), ADR-026 (PIIE), and the Brookings off-domain backfill — CDX enumeration + Wayback body fetch for in-scope content the live site no longer serves.

### Context

The full-corpus composition QA (2026-06-11) found `fed_atlanta` is a **hard zero across all of 2010–2018** — a clean zero-band at the window open that abruptly turns on in 2019. This is the classic under-capture signature, not a real absence: the Atlanta Fed published continuously through that period.

The cause is the 2026 atlantafed.org redesign, which retired the old discovery surface entirely (documented in `_fetch_atlanta`: old `/blogs/macroblog`, RSS, and `/research/publications/*` listings all 404). The current ingestor hits the new Sitecore JSS listing API, whose four series only exist from their inaugural dates on the *new* surface (Working Papers 2019-02, Policy Hub Papers 2020-01, Policy Hub Macroblog 2022-10, Macroeconomy hub feed 2016-09). The old article URLs 404 on the live site, so even the hub-feed rows that *list* 2016–2018 items drop on `_fetch_page_full`'s ≥50-word body gate — which is exactly why the band is a hard zero rather than thin.

Dimension 2 (US monetary research voice, ADR-020) stays covered for 2010–2018 by NY/SF/Chicago, all of which span the full window — so no *dimension* goes uncovered, and this gap was previously documented (not silent). But under per-source full-scope (user decision, 2026-06-11), Atlanta's distinctive **macroblog** is a voice worth recovering rather than conceding.

A Wayback CDX audit (2026-06-11) sized the recoverable, in-window, in-scope surface honestly:

| Surface | Archived URL pattern | 2010–2018 | Disposition |
|---|---|---|---|
| Macroblog | `macroblog.typepad.com/macroblog/YYYY/MM/slug.html` | 392 | **Recover** — narrative macro discourse |
| Working Papers | `frbatlanta.org/research/publications/wp/YYYY/NN.aspx` (pre-2016) or `/wp/YYYY/NN-slug` (2016+) | 177 | **Recover** — abstract/landing pages, clean dated surface |
| Economic Review | `/research/publications/economic-review/YYYY/…` | 3 (2010 only) | Skip — journal wound down ~2010 |
| CQER tools | `/cqer/research/*` (GDPNow, Wu-Xia, etc.) | — | **Exclude** — persistent data products, not narrative documents |

Total recovery ≈ **569 documents** (392 macroblog + 177 WP). Two prior estimates were wrong and are corrected here: an off-the-cuff 900–1,500, then a ~340 figure derived from enumerating `frbatlanta.org/blogs/macroblog/` — which turned out to be the wrong host (see Decision §1). Enumerating the macroblog's real home (typepad) yields 392 in-window posts.

**Source-of-truth correction (load-bearing):** the macroblog lived on `macroblog.typepad.com` for its entire pre-2020 life. The `frbatlanta.org/blogs/macroblog/YYYY/MM/DD/slug` URLs are **post-deletion 404 stubs** — Wayback has *no contemporaneous captures* of them (earliest snapshots are 2023–2024, all post-redesign error pages). Recovery therefore enumerates and fetches the **typepad** host, not frbatlanta.

### Decision

Add `_fetch_atlanta_wayback(start, end, seen)` to `FedRegionalIngestor`, yielded from `fetch()` alongside the live-API `_fetch_atlanta`. Two recovery surfaces:

1. **Macroblog** — CDX-enumerate `macroblog.typepad.com/macroblog`, keep posts matching `/macroblog/\d{4}/\d{2}/slug.html` (the monthly `index.html` archive pages are excluded by a negative lookahead). The typepad path carries **year/month but no day**, so the URL gives only a coarse `YYYY-MM-01` provisional date; the authoritative `pub_date` comes from the page metadata after the body fetch. The post `<title>` is the site masthead ("macroblog"), so the title falls back to a title-cased URL slug. **Capped at `pub_date < 2019-01-01`** to match WP — the live fetch already covers 2019+, and the cap prevents double-capture across the typepad→frbatlanta migration. `document_type=fed_regional_research`.
2. **Working Papers** — CDX-enumerate `frbatlanta.org/research/publications/wp` (+ the `atlantafed.org` alias), keep `/wp/\d{4}/\d+` optionally followed by `.aspx` (pre-2016) or a `-slug` (2016+); `.aspx` is stripped for the dedup key. These resolve to the WP **abstract/landing page** (the full text lives in a separate PDF), which clears the ≥50-word floor (~300–400 words). **Capped at `pub_date < 2019-01-01`** because the live listing API already covers WP from 2019-02. `document_type=fed_staff_report`. `pub_date` prefers the page metadata, falling back to the URL year (`YYYY-07-01`).

Mechanics (reusing established patterns, not the CBO checkpoint/ban apparatus — ~570 fetches on a clean IP is a single sub-hour session):
- CDX query with `filter=statuscode:200`, `filter=mimetype:text/html`, `fl=original,timestamp`; keep the **earliest real** snapshot per distinct URL. This is the opposite of CBO/ADR-023 (which keeps the latest): this content was *deleted* in the 2026 redesign, so a late snapshot of an frbatlanta URL captures the post-deletion 404 stub — the earliest capture is when the page was live and complete. (The `29991231` far-future redirect stub is skipped outright.) The **exact archived original URL** — including its `:80` port or `.aspx` variant — is retained and used as the snapshot-fetch target (a reconstructed URL would not resolve).
- Bodies fetched from the raw `web.archive.org/web/{ts}id_/{url}` snapshot (the `id_` modifier strips Wayback chrome so trafilatura extracts the original article), via a compact `_atlanta_wayback_get`: tuple timeout, escalating backoff on 5xx / connection-reset, patient `Retry-After` cooldown on 429, **fail-loud** (raises) on true exhaustion (ADR-030).
- Extraction reuses `_fetch_page_full` with the ≥50-word floor; the exact archived URL is stored for provenance and dedup against the shared `seen` set (no collision with the live pass — typepad/`.aspx` URLs differ from the live-API URLs, and the 2019 cap separates the date ranges).
- Strict page-date / window gate and ADR-022 dating policy preserved.

### Consequences

- **The fed_atlanta 2010–2018 zero-band fills** (~569 docs); Atlanta's macroblog voice is recovered rather than conceded. The previously-documented gap is closed under the user's full-scope-per-source standard.
- **Cheap recovery:** ~570 paced fetches ≈ 30 min, one session, clean IP — no checkpoint/resume machinery needed. CDX enumeration runs from any IP. **But it is ~570 Internet-Archive fetches**, so it cannot run concurrently with another large IA walk (e.g. the CBO ingest) on the same egress IP without compounding IA's per-IP throttle — schedule them apart.
- **Deliberate exclusions, recorded:** CQER pages (ongoing data tools, not documents) and the pre-2010 Economic Review (out-of-window) are intentionally not recovered — exclusion rationale lives here so it isn't re-litigated as a coverage hole.
- **No methodology change beyond capture:** Atlanta stays in the basis set (dimension 2), strict page-date filter and ≥50-word floor preserved. No config/threshold/seed change. Provenance URLs are the archived typepad/`.aspx` URLs (the live frbatlanta paths are dead), which is acceptable for a recovered-from-archive source.
- **New dependency:** correctness relies on Wayback holding the old-surface snapshots (audit confirmed it does). A CDX outage fails loud (ADR-030) rather than silently under-capturing.

### Verification

- Wayback CDX audit (2026-06-11): macroblog enumerates 1,668 typepad posts total, 392 in-window/under-cap (2010–2018, by url-year: 57/45/58/52/47/36/46/25/26); WP enumerates 555 total, 177 in-window/under-cap. Economic Review 3 (skipped).
- Local end-to-end smoke (2026-06-11): both surfaces fetch clean bodies from `{ts}id_/` snapshots — macroblog 944–2066 words with accurate metadata dates (e.g. 2010-01-07/13/21); WP 323–399-word abstract pages with real titles ("Do Credit Constraints Amplify Macroeconomic Fluctuations?"). Earliest-snapshot selection confirmed (latest-snapshot returns 404 stubs).
- Post-change (deferred until IA throttle clears): re-ingest `fed_atlanta` only, then `verify_coverage.py fed_regional` + `corpus-composition` must show the 2010–2018 fed_atlanta band populated with no 2019+ regression.

---

## ADR-034: SF Fed `sffed_publications` per-segment labeling + cross-post exclusion

- **Status**: Accepted
- **Date**: 2026-06-11

### Context

The SF Fed WordPress REST endpoint exposes a single custom post type,
`sffed_publications`, that is a **catch-all bucket** holding 16+ distinct series
(Economic Letter, Working Papers, FedViews, the Twelfth-District Beige Book,
Community Development articles/research briefs, and more). The prior
`_fetch_frbsf` pulled every post from this type and emitted them under one flat
`section`, which (a) erased the series distinction the rest of the pipeline
relies on and (b) silently violated the ADR-031 source-identity rule: the bucket
includes **cross-posts of other institutions' research** whose slugs begin with
`system-research-` (Federal Reserve System working-paper series) and
`board-of-governors` (Board content republished on frbsf.org). Because those
cross-posts carry canonical `link`s on `www.frbsf.org`, URL-dedup against the
native Fed Board / FEDS ingestors cannot catch them — they would enter the
corpus twice and inflate the SF dimension with content that belongs to other
ADR-020 dimensions.

### Decision

`_fetch_frbsf` now classifies each post by its URL path segment
(`/publications/<segment>/`) before emitting:

- A `_FRBSF_SECTION_BY_SEGMENT` map assigns each known series its own
  `(section, document_type)` — Economic Letter, Working Papers (→
  `fed_staff_report`), FedViews, Beige Book, and Community Development
  articles/briefs. Unknown segments fall back to a generic
  `(frbsf_publication, fed_regional_research)` so a new SF series is still
  captured (under-capture is the failure mode that matters), just not
  mislabeled.
- Posts whose segment begins with `system-research-` or `board-of-governors`
  (`_FRBSF_EXCLUDED_PREFIXES`) are **dropped** — they are other institutions'
  content and belong to those institutions' dimensions, not SF's.

This keeps the SF ingestor mapped 1:1 to the SF dimension (ADR-020) and honors
the source-identity rule (ADR-031). No content filter beyond the standing
window + dedup is introduced; the exclusion is an *identity* gate (whose
research is this), not a *topical* one.

### Consequences

- The SF dimension now carries correctly-labeled per-series sections instead of
  one undifferentiated bucket; downstream composition QA can see each series.
- Cross-posted System/Board research no longer double-enters via SF, so the
  1:1 ingestor↔dimension invariant holds.
- Verified offline against a live 100-record `sffed_publications` sample: kept
  Economic Letter / Working Papers / FedViews / Beige Book / Community
  Development; skipped 9 `board-of-governors` + the `system-research-*` posts.
- Residual to confirm on re-ingest: the segment map is keyed to current SF URL
  shapes; a renamed segment would degrade to the generic fallback (still
  captured), surfacing as a label drift in composition QA rather than as silent
  loss.

---

## ADR-035: Chicago Fed 2026-redesign date-stamp fix (citation block over OG meta)

- **Status**: Accepted
- **Date**: 2026-06-11

### Context

While extending Chicago Fed capture to the business/economic-conditions survey
series (CFSBC 2016–2022 and its successor CFSEC 2023–present — the Beige Book
genre already in the corpus via the Board + SF, so an in-scope series extension,
not a new methodology), live verification surfaced a dating defect: the 2026
chicagofed.org site redesign (the same redesign that retired Atlanta's old
discovery surface, ADR-033) overwrote the OG `article:published_time` on the
survey page templates with a **2026-01-01 migration stamp**. Other templates
(e.g. Chicago Fed Letter) kept a genuine day-precise OG date.

The prior date logic was meta_date-first: `if meta_date.year == url_year: use
meta_date`. trafilatura returns the stamp as `meta_date`, so for every
**in-window 2026** page the stamp's year (2026) matched the URL year and the
stamp won — silently collapsing all 2026 Chicago content onto Jan 1. Pre-2026
years were unaffected only by luck (stamp-year 2026 ≠ their URL year, so the
existing citation-block fallback already ran). Same defect *class* as ADR-029
(PIIE 2016 migration stamp) and the ADR-032 CBO correction (order-dependent
trafilatura date picker).

### Decision

Anchor Chicago dating on the **citation block** (`_chicago_fed_date_from_html`)
— Chicago's own structured publication date, month-granular and authoritative —
and keep the OG `meta_date`'s day-precision **only when it corroborates the
citation block's month and year**. When they disagree (the stamp's January vs.
the citation block's real month) the citation block wins; the stamp can never
win. `meta_date` survives solely as a fallback for a page with no citation block
and no in-body "MONTH YYYY". No fabricated dates: a page resolving to none is
still dropped (methodology principle 1).

### Consequences

- All in-window 2026 Chicago records (every series, not just surveys) now date
  to their true month instead of Jan 1; pre-2026 day-precise dates are preserved
  unchanged (verified: 2021 Fed Letter keeps 2021-04-27; 2026 CFSEC April resolves
  2026-04-15, was 2026-01-01; 2019 CFSBC September → 2019-09-15).
- Survey series enumerated from the live sitemap: CFSBC 59 + CFSEC 49 records.
  Sections `survey_business_conditions` / `survey_economic_conditions`,
  `document_type=fed_regional_research` (Beige Book genre).
- Day-precision on the survey pages themselves is mid-month (day 15) because the
  citation block is month-granular — immaterial to volume-curve / lifecycle
  dynamics, which bin well above day resolution.

---

## ADR-036: Primary embedder Qwen3-Embedding-0.6B → 8B (4096-dim, A100); BERTopic unchanged

- **Status**: Accepted
- **Date**: 2026-06-11

### Context

The production embedder (ADR-001/011/019) was Qwen3-Embedding-0.6B (1024-dim),
chosen when the only RCC GPU we'd provisioned was V100-16GB. Embedding quality is
the upstream determinant of cluster separation — sharper vectors give HDBSCAN
denser, better-separated regions, which is the lever most likely to improve anchor
recovery (6/10 on the pre-fix corpus). The Qwen3-Embedding family (all Apache-2.0,
instruction-aware, 32k context, identical interface) offers 0.6B (1024-dim),
4B (2560-dim), and 8B (4096-dim); 8B is top-tier on MTEB. config.yaml already
named 4B as an `upgrade_path` "if RCC capacity allows."

The constraint was GPU memory: 8B is ~16 GB of fp16 weights, which will not fit a
V100-16GB alongside activations. A 2026-06-11 `sinfo` audit showed the standard
Midway3 `gpu` partition carries **a100** feature nodes (`gold-6248r,384g,a100`,
40 GB/GPU) in addition to v100/rtx6000, and the account already submits embedding
jobs to that partition. So A100-40GB is reachable via `--constraint=a100` with no
new allocation — putting 8B comfortably in budget (16 GB weights, 24 GB headroom).

### Decision

1. **Primary embedder → `Qwen/Qwen3-Embedding-8B`, `dimensions: 4096`** (config
   `embedding.primary`). 8B over 4B because the corpus embed is a one-time cost
   and we want maximum cluster separation; the marginal MTEB gain is worth the
   extra A100-hours here. `max_seq_len` stays 1024 (the ADR-019 chunker emits
   512-token chunks); `instruction_prefix` unchanged. No `upgrade_path` — 8B tops
   the family.

2. **Embed SLURM job moves to A100**: `embed_rcc.sh` `--constraint=v100` →
   `a100`, `--mem` 32G→64G, `--time` 12h→18h. Partition stays `gpu`.

3. **BERTopic is NOT retuned.** This is the load-bearing methodological point.
   BERTopic's pipeline is `embeddings → UMAP(n_components=5) → HDBSCAN →
   c-TF-IDF`. UMAP maps *any* input dimensionality to a fixed 5-dim manifold, so
   the embedding dim (1024 → 4096) never reaches HDBSCAN, which clusters on the
   5-dim output. `n_neighbors=15`, `min_dist=0.0`, `cosine`, `min_cluster_size=10`,
   `eom`, and c-TF-IDF (text-only) are all unchanged. Scaling UMAP `n_components`
   "because the embeddings are richer" would be unanchored researcher-tuning —
   precisely what methodology principles 1, 2, and 7 (ADR-019) forbid. The
   model-agnostic library-default clusterer is *why* an embedder swap is a clean,
   isolated change.

### Consequences

- **Intended**: sharper semantic separation → tighter, better-separated clusters
  and a plausibly higher anchor-recovery rate. Reported as-is, not tuned toward.
- The clustering *result* will shift — outlier rate (was 25.4%) and cluster count
  will differ under the new embeddings. Expected; we report whatever emerges.
- `embeddings.npy` grows ~4× (4096 vs 1024 dim); a few GB at corpus scale. Fine.
- `embedding_batch_size: 8` is retained but is now a pure throughput knob with
  ~24 GB of A100 headroom — raisable later with zero effect on the vectors.
- **Invalidates the prior Phase-3 numbers** (Qwen3-0.6B NMI=0.880±0.003, anchor
  6/10). Re-validation was already pending the post-fix re-ingest, so the timing
  cost is zero.
- Hard dependency: 8B requires an A100 — the embed job must land on a
  `--constraint=a100` node. A V100-only fallback would force 0.6B (or 4B at tiny
  batch); not in scope while A100 is reachable.
- The comparator path (mpnet, ADR-011) is untouched here; it remains removed from
  active methodology by ADR-019 and is not part of this decision.

---

## ADR-037: CBO Wayback — a replayed-archived 429 is a dead snapshot to skip, not a live throttle

- **Status**: Accepted
- **Date**: 2026-06-11

### Context

CBO bodies come from the Wayback Machine (`id_/` raw replay) because live cbo.gov
is DataDome-walled (ADR-032). The 2026-06-11 re-ingest (job 50722066) ran ~90 min
and wrote **zero** articles: it stalled on the very first publication with
snapshots (pid 41672), looping `HTTP 429` cooldowns. The surface reading was an IA
replay-throttle ban on the RCC egress IP.

Direct probing disproved that. The `id_/` request 302-redirects to the nearest
capture; following it returned `429` — but the response carried `x-archive-orig-*`
headers (`x-archive-orig-content-length: 444`, `x-archive-orig-date: 2025-09-04`).
Those headers are the *origin's* response as IA stored it: when IA crawled the page
on 2025-09-04, CBO's DataDome wall returned a 429 block stub, and IA archived it.
The `id_/` endpoint replays that captured 429 verbatim — **it is frozen; no amount
of waiting changes it.** The CDX index for pid 41672 holds 44 captures, 43 of them
`200` with real 5–27 KB bodies (2013–2025-05); only the single most-recent capture
is the 429 block page.

Two faults compounded:

1. **Stale CDX cache.** The current `_cdx_block` query already filters
   `statuscode:200` (it would have selected the 2025-05 real capture). But the run
   reused a `cdxcache.json` carried forward from a pre-filter build, which stored
   the 2025-09-04 non-200 timestamp. The cache short-circuits enumeration, so the
   corrected query never ran.
2. **Misclassification in `_wayback_get`.** A replayed-archived 429 is
   indistinguishable, by status code alone, from a live IA throttle — and the
   fetcher treated every 429 as a live throttle, spending its full multi-minute
   cooldown budget on a snapshot that can only ever return 429, then raising
   `_WaybackBanned` and pausing the whole walk.

### Decision

1. **`_wayback_get` distinguishes the two 429s by the `x-archive-orig-*` marker.**
   A 429 bearing any `x-archive-orig-*` header is a replayed archived block page:
   return it immediately so `_fetch_page_full` classifies it as a 4xx genuine
   absence (skip → earliest-ts fallback → drop the pid as unfetchable). A 429
   *without* those headers is a live IA throttle and keeps the existing patient
   cooldown/`_WaybackBanned` budget. The discriminator is safe-by-default: the
   archived-origin headers are added only on replay, so a live throttle never
   trips the skip path.

2. **A CDX cache built by superseded selection logic must be rebuilt, not carried
   forward.** Operationally: when the snapshot-selection query changes, discard
   `.cbo_*_cdxcache.json` and let the current code rebuild it. Rebuilding is cheap
   — it hits the CDX *index* API, not the throttled `id_/` content endpoint.

### Consequences

- One dead capture can no longer halt the CBO walk; it costs a single skipped pid,
  and the earliest-ts fallback still recovers a real body when an older capture is
  `200`. Upholds the ADR-030 fail-loud rule without letting a frozen 429 masquerade
  as a live outage.
- A pid whose every capture is a block page is dropped as genuine absence — correct:
  there is no archived CBO body to recover. This is real source-side absence, not
  under-capture from our enumeration.
- The IA-egress-ban theory is retired for this incident: the RCC IP was never
  banned; the 429s were archived content. (A genuine live throttle remains possible
  and is still handled by the cooldown path.)
- No methodology-surface change to the corpus definition or selection criteria —
  this is fetch-layer correctness. The `statuscode:200` CDX filter (ADR-032) is the
  primary selector; this ADR hardens the fetch against the residual case where a
  selected/redirected capture still replays an archived error.

---

## ADR-038: CBO Wayback walk is shardable by `pid % N` across independent egress IPs

- **Status**: Accepted
- **Date**: 2026-06-11

### Context

The CBO ingestor walks the full cbo.gov sitemap pid universe (~25k publications,
ADR-032) fetching each body from the Wayback Machine. Internet Archive throttles
`id_/` content replay by **egress IP** on a rolling window; the measured
sustained-safe single-IP rate is ~1 request / 9–12 s. At ~18 s/pid observed
(fetch + earliest-ts fallback), the recoverable ~25k-pid walk is ≈130 h — roughly
four sequential 36 h caslake jobs (the QOS cap, ADR-023). That is the dominant
long pole in the corpus build.

The only lever on wall time is parallelism across **distinct egress IPs** — a
single IP cannot safely go faster. An `srun` two-node probe (2026-06-11) showed
both Midway3 compute nodes egress through the **same** NAT IP (`128.135.34.94`),
so sharding *within RCC buys nothing*: N RCC streams share one per-IP throttle.
The user's laptop is an independent IP (`136.56.213.171`). So the realistic
parallelism ceiling is the number of genuinely independent IPs available
(RCC NAT + laptop = 2), not the number of nodes/cores.

### Decision

Make the CBO walk shardable by a residue partition and deploy it across whatever
independent IPs exist:

1. **`CBOIngestor(shard_index=k, shard_count=N)`** — `fetch()` processes only pids
   where `pid % N == k`. The partition is on the raw pid (not a contiguous id
   range): sitemap ids are interleaved across eras (ADR-032), so `pid % N` gives
   every shard a balanced old/new mix and roughly equal work. `N=1` is the
   unsharded default and is a no-op.
2. **Shared, pre-built CDX cache.** The `{pid: (earliest, latest)}` enumeration is
   the full pid universe — identical for every shard. It is built **once** by an
   unsharded warm-up run and read-only thereafter; `_cdx_cache_path()` strips the
   `_shard{k}of{N}` token so all shards resolve to the same `cdxcache.json`. A
   sharded run with **no** cache present **raises** (`_build_or_load_cdx_map`):
   N shards must never race to rebuild it (they would collide on one IP and
   re-establish the ADR-037 ban, and waste N × the ~44 min enumeration).
3. **Disjoint per-shard output + checkpoint.** Each shard writes
   `cbo_<win>_shard{k}of{N}.jsonl` with its own `_shard{k}of{N}_checkpoint.txt`,
   so independent runs never touch shared resume state and each resumes its own
   slice across 36 h job cycles.
4. **`cbo-merge-shards` reassembles the canonical file.** After all shards finish,
   `run_pipeline.py cbo-merge-shards --start --end` concatenates the shard files,
   dedups on `article_id` (shards are disjoint by construction; dedup is defensive
   against a window-roll re-crawl), writes the canonical `cbo_<win>.jsonl`, and
   renames the shard files `.merged` so the filter-pre-embed glob sees exactly one
   CBO file and a stale shard can never double-count.

### Consequences

- Wall time scales with the count of independent egress IPs, not RCC parallelism.
  With RCC + laptop (2 IPs) the ~130 h walk halves to ~65 h. More IPs would help
  linearly, but RCC's shared NAT means extra RCC nodes do not count.
- Operational sequence is fixed: (a) one unsharded warm-up run builds the cache;
  (b) launch shard `k/N` per independent IP, each pinned to the **same** window so
  they share the cache and merge cleanly; (c) `cbo-merge-shards` once all complete.
- `--shard` is gated to `--sources cbo` only — no other ingestor has the per-IP
  throttle problem or the pid partition, and sharding them would just fragment
  output for no gain.
- No corpus-definition or selection change: identical pids fetched, identical
  bodies, identical dedup — only the *order and host* of the walk differ. This is
  throughput plumbing, not methodology.

---

## ADR-039: Dynamics shown as four complementary lenses, not an AICc best-of-N pick

- **Status**: Accepted
- **Date**: 2026-06-12
- **Amends**: ADR-019 §E (which fit `["sir", "logistic"]` and selected one by AICc)

### Context

ADR-019 locked the dynamics layer to two ODE models (logistic = Verhulst 1838,
SIR = Kermack & McKendrick 1927) and selected the better fit per cluster by AICc.
That made sense when the deliverable was framed as a paper with one reported model
per narrative. The project's primary deliverable is now an **educational tool/web
page** (see `project_goal_intent` in working memory): people explore how macro
narratives form and develop. For that audience a single AICc winner throws away
the most interesting part — *each model answers a different question about the same
volume curve*. AICc best-of-N is a model-selection ritual that serves a paper, not
a reader who wants to understand the shape of a narrative.

### Decision

Fit and display **four lenses side by side** for every in-scope cluster. Each lens
is framed on the dashboard as the plain-language question it answers (front-end
clarity is first-class, see `feedback_frontend_clarity`):

1. **Logistic** (Verhulst 1838) — "how fast did it take off, and where did it level
   off?" Reports growth rate *k* and carrying capacity *L*.
2. **SIR** (Kermack & McKendrick 1927) — "was it contagious, and did it burn out?"
   Reports R₀ (with 94% credible interval) and peak time.
3. **Bass diffusion** (Bass 1969) — "was this driven by an external shock or by
   word-of-mouth?" Reports the coefficient of innovation *p* (external) vs.
   imitation *q* (internal). Bass is the field-standard diffusion model in
   marketing/innovation and has a primary-literature anchor, satisfying the
   ADR-019 "anchored or removed" rule.
4. **Shape-facts** — model-free descriptive statistics straight off the smoothed
   weekly curve: total volume, peak height, time-to-peak, duration above
   half-peak, and **wave count** (number of distinct re-emergence humps). Answers
   "how big, how fast, how long, and how many comebacks?" No fitting, no
   assumptions — the honest baseline a reader can always trust.

All four are reported together; **no AICc selection gate**. Per-model fit
diagnostics (R², CI width) are shown as honesty signals next to each lens, never as
a pass/fail filter (consistent with ADR-019's removal of kill criteria).

Stage classification (growth/decay/dormant, ADR-019 §F) continues to key off the
**SIR R₀ posterior**, unchanged — the four-lens display does not alter staging.

### Consequences

- `config.dynamics.models_to_fit` grows to include `bass`; `models/models.py` gains
  a Bass parameterization + a model-free `shape_facts` extractor. AICc is retained
  only as a displayed diagnostic, not a selector.
- The dashboard life-cycle viewer shows four small framed panels per narrative
  instead of one "winning" curve. Each panel carries its one-line question and a
  plain-language reading of its headline parameter.
- This is a display + fitting change, not a corpus or clustering change. The volume
  signal fit by all four lenses remains institutional discourse volume (ADR-019
  §E), with press volume as a secondary overlay (ADR-042).
- More compute per cluster (four fits vs. an AICc race over two), but cluster count
  is ~70–120 and the fits are cheap relative to embedding.

---

## ADR-040: Drop the 2010-2019/2020+ held-out split; no formal pre-registration

- **Status**: Accepted
- **Date**: 2026-06-12
- **Amends**: ADR-019 (look-ahead apparatus already removed there); supersedes the
  `prereg/PREREGISTRATION.md` draft and the `train_test_split` config key

### Context

The pipeline carried a walk-forward train/test boundary (`train_test_split:
"2020-01-01"`, CLAUDE.md invariant "never load held-out 2020+ data before Phase 4")
and a draft `prereg/PREREGISTRATION.md` with kill criteria, FDR control, and 5-stage
/ 4-model language. Both are vestiges of a falsification-style paper framing. The
held-out split exists to detect **overfitting from tuning** — but ADR-019 already
established the project's core discipline: *every threshold is a field-accepted
library default or primary-literature value, and nothing is hand-tuned* (esp. never
tuned to improve anchor recovery). With zero tuning, there is no fitted-on-train
quantity that a held-out test could catch overfitting on. The split guards against a
risk the no-tuning rule already eliminates, while complicating the pipeline and the
narrative-formation analysis (which wants the full 2010-present series, not a
truncated training window). The user confirmed (2026-06-12): "since we don't tune at
all, we don't need the split."

The pre-registration likewise served reviewers, not the tool. The user is "not
pursuing a formal pre-registration" (no OSF, no locked timestamp). Credibility rests
on the hard rules, not a registered analysis plan.

### Decision

1. **Remove the held-out split.** Delete `train_test_split` from `config/config.yaml`
   and the "never load held-out 2020+ data" invariant from CLAUDE.md. Clustering,
   dynamics, and validation all run over the full 2010-present corpus. Anchor
   narratives remain **validation diagnostics** (does the pipeline recover known
   episodes?), reported, never gated — and never tuned toward.
2. **No formal pre-registration.** Delete `prereg/PREREGISTRATION.md`. The useful,
   non-stale content — the field-anchored value list and the no-tuning honesty
   statement — folds into `docs/METHODOLOGY.md` as a short "methodological
   commitments" section. Credibility is sourced from: (a) every parameter anchored
   to a published default or primary-literature value (ADR-019), and (b) the
   standing no-hand-tuning rule, especially against anchor recovery.

### Consequences

- The "held-out discipline" survives in spirit as the **no-retro-tuning rule**: we
  still do not adjust parameters after seeing anchor results — that honesty is what
  keeps the tool credible about what it can actually detect, and is itself
  educational. What changes is that we no longer *withhold* post-2020 data from the
  pipeline to enforce it.
- CLAUDE.md Phase 4 line ("Pre-registration finalized; full anchor + fizzled
  validation") is rewritten to drop the pre-registration gate; Phase 4 becomes the
  full-corpus anchor + fizzled validation pass, reported not gated.
- `MND_PROJECT_SPEC.md` and `docs/METHODOLOGY.md` references to a train/test split or
  pre-registration are corrected. The project stays "paper-writeable" (anchored to
  respected methods) without a registered plan.
- One less invariant to honor at ingest/cluster time; simpler reproduction story.

---

## ADR-041: Markets + bidirectional Granger as a labeled display overlay

- **Status**: Accepted
- **Date**: 2026-06-12
- **Amended**: 2026-06-13 by ADR-043 — Granger is **precomputed** into the
  per-narrative artifact for a fixed market-series menu, not run live on click
  (static hosting has no Python server). The "on demand (on click)" wording in the
  Consequences below is superseded; the user still picks a series via a toggle, but
  the readout is baked, not computed in-browser.

### Context

A recurring question a reader brings to a macro narrative is "did the discourse move
before or after the market did?" The pipeline already has FRED access
(`FRED_API_KEY`, validation only). A prior framing (ADR-016-era) considered a
Bloomberg CPI-surprise control series; Bloomberg is a removed paid source (ADR-010)
and the surprise series is not reproducible for free. The lead-lag question is
genuinely insightful for the tool and was explicitly kept (not cut) as a labeled
feature, so it needs its own ADR rather than living as scattered intent.

### Decision

Add a **markets overlay** on the per-narrative life-cycle view, plus an on-demand
**bidirectional Granger** readout:

- Overlay a relevant free FRED market series (e.g., VIX, 10y yield, equity index)
  against the narrative's weekly discourse volume on the same time axis.
- On click, run **bidirectional Granger causality** (VAR on the first-differenced
  series, both directions tested) and report which direction, if any, shows
  statistically significant precedence, at what lag.
- Every markets/lead-lag element carries the caption **"this shows timing, not
  cause"** (per `feedback_frontend_clarity`) — Granger precedence is temporal
  ordering, not causation, and the UI must say so to avoid mis-educating.
- **Drop the Bloomberg CPI-surprise control** entirely; it is paid + removed-source.

### Consequences

- This is a display/diagnostic feature only. Market series **never feed clustering,
  embedding, or dynamics fitting** — they are an overlay computed after the corpus
  is built, so the no-paid-dep core invariant and ADR-020 (no external signal into
  clustering) are untouched. FRED is free.
- Granger is run per-narrative on demand (on click), not precomputed for all
  clusters, keeping it cheap and clearly user-initiated.
- Lives in the detection/display layer, not the core pipeline; first-differencing
  handles the non-stationarity Granger requires.

---

## ADR-042: Media Cloud press volume as a display/validation overlay only

- **Status**: Accepted
- **Date**: 2026-06-12
- **Relates to**: ADR-016 (Media Cloud as dynamics layer), ADR-020 (no external
  signal into clustering)

### Context

The corpus is locked to the ADR-020 institutional/academic basis set; premium press
(NYT, WSJ, Bloomberg) is excluded because it is paid and not reproducibly fetchable
(ADR-010). But premium and broad press are obviously where macro narratives become
*public*, and the central intellectual claim of the project is that narratives form
upstream in institutional/academic discourse and surface later in the press. Showing
both side by side makes that dynamic visible and is pedagogically valuable. Media
Cloud provides free aggregate **story counts over time** (not full text) for large
news collections — exactly a volume overlay, with no text to embed. The legacy
integration (`src/mnd/detection/mediacloud.py`) targets the dead
`api.mediacloud.org/api/v2` (retired Dec 2023); the live interface is the
`mediacloud` PyPI package (`SearchApi.story_count_over_time(query, start, end,
collection_ids=[34412234])`, US National collection). Historical depth thins before
~2017.

### Decision

Use Media Cloud as a **press-volume overlay** on the life-cycle view, and as a
secondary cross-validation signal for dynamics — **display/validation only**:

- For a given narrative, overlay Media Cloud weekly story counts (broad/premium
  press proxy) against the institutional discourse volume, captioned to make the
  institutional-vs-press timing contrast explicit ("this shows timing, not cause").
- Migrate `mediacloud.py` from the dead v2 REST API to the `mediacloud` PyPI
  package; query the US National collection (`34412234`).
- Press counts may be reported as a **secondary** signal that cross-checks the
  institutional fit; they are **never the SIR/logistic fit target** (institutional
  volume is, per ADR-019 §E).

### Consequences

- **Media Cloud must never feed clustering, embedding, or dynamics fitting** — it is
  not in the embedded corpus (ADR-020) and remains a post-hoc overlay. This keeps the
  basis-set corpus definition and the no-external-signal-into-clustering rule intact.
- Media Cloud is free; story-count-over-time needs only `MEDIACLOUD_API_KEY` (free
  signup at search.mediacloud.org). It is currently absent from `.env` — the press
  overlay is blocked until a key is added and a historical-depth probe confirms
  usable coverage back to the narrative's window (reliable ~2017+).
- Pre-2017 narratives may have thin or absent press counts; the overlay must degrade
  gracefully (show "press coverage data unavailable before ~2017" rather than a
  misleading flat line).
- A forward-looking Media Cloud early-detector (press as a leading signal) is a
  deferred add-on, not part of this ADR.

---

## ADR-043: Static publishing — Astro on GitHub Pages, precompute everything

- **Status**: Accepted
- **Date**: 2026-06-13
- **Supersedes**: ADR-003 (Streamlit for the dashboard)
- **Amends**: ADR-041 (Granger precomputed, not on-click-live)

### Context

Phase 5 is the public face of the project: a "cool, educational tool/page" (not a
paper) showing how macro narratives form upstream in institutional discourse and
surface later in the press. ADR-003 picked Streamlit. Two constraints have since
hardened:

1. **Cost must be zero and hosting reproducible** — the no-paid-dependency spirit
   extends to hosting. The user wants something "entirely free" with no server bill.
2. **Streamlit is a Python *server* app.** It cannot run on GitHub Pages (static
   file host, no Python runtime). Keeping Streamlit would force a paid/managed host
   (Streamlit Community Cloud sleeps; HF Spaces is a container that still runs a
   server) and couples the front end to the heavy analysis stack (pymc/bertopic/torch)
   we deliberately quarantined behind the artifact contract (ADR-039 companion,
   `src/mnd/dashboard/artifacts.py`).

The artifact contract already bakes everything the screen needs into small plain
JSON ("curves not parameters"). If the JSON is complete, the front end needs **no
server at all** — every view can render client-side.

### Decision

Publish a **fully static site built with [Astro](https://astro.build), deployed to
GitHub Pages** via the repo's CI. Take **Clarity-Template** (lorenmt/clarity-template,
CC BY-SA 4.0) as *visual inspiration only* — clean, paper-like, research-y, modular —
not as a code dependency (it is single-page; we are multi-page).

- **Astro** renders static HTML at build time with "islands" of client-side
  interactivity (Plotly.js charts, the map, lens tabs, overlay toggles). No runtime
  server, no Python on the host. Deploys as plain files to `gh-pages`.
- **Precompute everything** into the ADR-039 artifact JSON. Specifically, this ADR
  resolves the one live-compute hole in ADR-041: **bidirectional Granger is
  precomputed** for a *fixed, small menu of the most-popular market series* (e.g.
  VIX, 10y yield, yield spread — not the full FRED catalogue) and baked into each
  `narrative_<id>.json`. The user toggles a series; the readout is already there. No
  in-browser statistics, no API calls at view time.
- The front end **only ever reads the baked JSON** — it never imports the analysis
  stack and makes no network calls to FRED / Media Cloud / any API at view time.
- Supersede ADR-003: Streamlit is dropped as the dashboard technology.

### Consequences

- **All interactivity survives static hosting** because it is data-driven (Plotly.js
  over baked arrays) rather than compute-driven. Lens tabs, overlay checkboxes
  (ADR-041/042), the narrative map, and the Granger readout all work client-side.
- The artifact builder (task 41) becomes the single integration seam and must emit
  the fixed-menu Granger results and the map's coordinates/edges (see ADR-044). The
  build is reproducible and re-runs only when the corpus changes.
- Cost is zero; hosting is a public GitHub Pages site. No secrets ship to the client
  (all API keys are used only at build/precompute time, server-side in CI or locally).
- Trade-off accepted: no live/user-typed queries (e.g. arbitrary FRED series, live
  Media Cloud search). This is fine — the tool is a curated educational artifact, not
  a query console, and the fixed menu keeps results deterministic and no-tuning-clean.

---

## ADR-044: Narrative map — hybrid node-link UMAP graph (shape=JEL, color=stage)

- **Status**: Accepted
- **Date**: 2026-06-13
- **Relates to**: ADR-039 (lenses), ADR-019 §H (similar-narratives edges), ADR-020
  (JEL scope), ADR-043 (static front end)

### Context

The landing page needs an interactive overview that conveys the *shape of the corpus*
— which narratives exist, how they relate, what lifecycle stage they are in, and
which are newly emerging — and lets a reader click through to any narrative. A flat
2-D UMAP scatter shows *position* (semantic neighborhood) and can encode *size*
(volume), but it does not show *similarity structure* (which clusters are kin) and
gets visually muddy at the cluster counts we expect ("a fair amount"). We already
compute pairwise similarity (`similar_narratives.py`, ADR-019 §H: semantic / lexical /
morphological top-k), so the relationship edges exist for free.

### Decision

Render the overview as a **hybrid node-link graph seeded by 2-D UMAP positions** —
nodes placed at their UMAP coordinates, with explicit **edges drawn from the semantic
top-k** similarity already computed. Visual encoding:

- **Shape = JEL primary code** (ADR-020 scope: E / F / G / H families) — a small,
  fixed shape vocabulary.
- **Color = lifecycle stage + emerging**, a **four-color** scheme: growth, decay,
  dormant, plus *newly-emerging* as its own color (the ADR-019 recency flag), with an
  added ring/glow on emerging nodes so the status reads even for color-blind users.
- **Size = discourse volume** (article count).
- **Click a node → navigate to that narrative's page** (or the emerging feed for
  emerging nodes). The map is the primary navigation surface, not just a picture.
- **No literal 3-D.** A z-axis hurts legibility and click-accuracy more than it helps;
  similarity is conveyed by edges and proximity, not depth.

### Clutter mitigation (explicit, since cluster count is unknown but likely non-trivial)

A naive all-nodes-all-edges plot becomes a hairball. The map must stay legible by:

- **Edge thresholding / top-k only** — draw at most the top-k semantic edges per node
  (k small, e.g. 3), above a similarity floor; never the full pairwise matrix.
- **Degree-aware edge fading** — edges rendered low-opacity so dense regions read as
  texture, not noise; hover/selection highlights a node's own edges at full opacity.
- **Label-on-demand** — only top-volume nodes label by default; the rest reveal labels
  on hover, avoiding overlapping text.
- **Optional stage/JEL filter toggles** — the reader can isolate one stage or one JEL
  family to declutter (client-side, over the baked index).
- **Deterministic layout seeded from the global seed** (UMAP coords are precomputed and
  baked, so the map is stable across loads and reproducible — no per-load jitter).

### Consequences

- The artifact contract must carry, per narrative, the **UMAP 2-D coordinates** (the
  `umap_xy` field already reserved in `IndexEntry`) **and the semantic top-k edges**
  (`IndexEntry.similar_edges` — list of `(neighbor_cluster_id, weight)`). The *map*
  uses the semantic edges only, to keep one clear meaning per visual.
- **All three** ADR-019 §H measures (semantic / lexical / morphological) stay
  available on the **narrative page**, carried in a separate
  `NarrativeArtifact.similar` field (a `SimilarNarratives` record of three ranked
  neighbor-id lists). This is the per-narrative "related narratives" panel — distinct
  from the map's semantic-only edges: the panel is for reading ("what resembles this,
  by meaning vs. wording vs. shape"), the edges are for drawing the graph. The front
  end resolves neighbor ids → labels via the index, so the panel stores ids only.
- Rendering is client-side over baked data (ADR-043) — Plotly.js or a lightweight
  force/graph layer reading the index JSON; no server.
- All encodings are derived from existing pipeline outputs (JEL, stage, emerging flag,
  volume, UMAP, similar-narratives); the map introduces **no new analysis and no
  tuning**, only display.

---

## ADR-045: Corpus-base-rate volume normalization (and what it means for cross-narrative + lead-lag analysis)

- **Status**: Accepted
- **Date**: 2026-06-15
- **Relates to / amends**: ADR-008 (original RavenPack denominator — now dead),
  ADR-016 (RavenPack/WRDS dropped; Media Cloud Premium replaced it), ADR-019
  (report-don't-gate; staging off SIR R₀), ADR-039 (four lenses, "curves not
  parameters"), ADR-042 (Media Cloud overlay), ADR-043 (precompute → static site)

### Context

A pre-downstream audit (2026-06-15) found that every volume curve the dashboard
plots — and every series the SIR/logistic/Bass lenses are fit to — is a **raw
weekly article count**. The embedded corpus is not stationary: more basis-set
sources are active in 2024 than in 2013, and per-source publishing cadence
drifts. So a narrative's apparent rise is confounded with **corpus growth**: a
2024 narrative sits on a larger denominator of total discourse than a 2013 one,
inflating its raw count and its fitted growth. This is a validity hole, not a
cosmetic one — it changes the meaning of every curve and biases cross-narrative
comparison toward recent narratives.

The original normalizer (`dynamics/normalize.py`, ADR-008) already anticipated
this — it expressed weekly cluster counts as a fraction of a total-corpus
denominator — but that denominator was the **RavenPack** weekly volume, and
RavenPack/WRDS was removed in ADR-016. The module has been dead code coupled to
a removed dependency ever since.

Three audited gaps are entangled here: (#1) base-rate normalization is absent;
(#2) cross-narrative dynamics (seeding/competition/transition) is absent; (#3)
source-provenance / lead-lag ("forms upstream in institutions, surfaces later in
press") is unquantified. All three recompute from the persisted
`clusters.parquet` / `embeddings.npy` — only embed+cluster is irreversible — so
this ADR is a scope decision taken **before** the one-shot downstream run, not a
re-embed.

### Decision

**1. Normalize by a single, global, whole-corpus base rate — expressed back in
count units.** For each day *d*:

- `N(d)` = unique articles published that day across the **entire embedded
  corpus** (all clusters, including the BERTopic outlier bucket and out-of-scope
  clusters — it is the denominator of *all* discourse, not just in-scope).
- Smooth the denominator with a centered 7-day mean → `N̄(d)` (kills weekend
  zero-division and the institutional Mon–Fri sawtooth; same window as the
  dynamics smoother, `dynamics.smoothing_window_days`).
- `N̄_mean` = mean of `N̄` over the corpus span (a single scalar for the run).
- Adjusted volume for cluster *c*: **`adj_c(d) = c(d) / N̄(d) × N̄_mean`** —
  the count cluster *c* *would* have if the corpus were always at its average
  daily size. Where `N̄(d) = 0`, `adj_c(d) = 0`.

Indexing the share back to `N̄_mean` (rather than fitting on the bare fraction
`c(d)/N̄(d)`) is deliberate: it removes the corpus-growth trend **while keeping
the series in article-count units**, so the existing PyMC priors (logistic `L`,
SIR `N_pop`/`I0` heuristics — all in count units, anchored in ADR-019/config)
and the AICc diagnostics stay valid **unchanged**. No prior re-anchoring, no
schema bump to the dynamics block.

**2. The adjusted series is what both the fit AND the display use.** The
dynamics fitter is trained on `adj_c`, and the dashboard plots `adj_c` as the
observed volume (the fitted `curve` is already on the same daily grid, ADR-039).
There is no second "raw" curve on the headline chart — a corpus-confounded curve
is exactly what this ADR removes, so it must not remain the thing a reader sees.
The y-axis is labeled as **corpus-size-adjusted discourse volume** (front-end
caption), not "articles/week", so the normalization is self-explanatory per the
front-end clarity rule. (True raw counts remain trivially recoverable from
`clusters.parquet` for any audit; they are not a dashboard series.)

**3. The base rate is global and singular — one `N̄(d)`, one `N̄_mean` for all
narratives.** This is the specific change that makes gap #2 (cross-narrative
dynamics) *valid when it is built*: every narrative's adjusted curve is on the
same yardstick, so seeding/competition/transition between narratives can be
measured directly later without re-deriving comparability. Building the
cross-narrative model itself is **deferred** — it is a new analysis that
recomputes from persisted artifacts (no re-embed), and shipping it is not
required for the one-shot run. This ADR's obligation to #2 is to not foreclose
it; a per-narrative denominator *would* have foreclosed it, so we don't use one.

**4. Source provenance / lead-lag (#3) is deferred, with one binding
constraint.** When built, any institutional-vs-press lead-lag (cross-correlation
against the ADR-042 Media Cloud series) and any "which source moved first"
first-appearance statistic must consume the **adjusted** institutional series,
not raw counts — otherwise corpus growth re-enters as a fake lead. Per-source
first-appearance recomputes from `clusters.parquet`'s `source_id`. No code now;
the constraint is recorded so the future implementation is correct by default.

**5. Rewrite `normalize.py` to the live contract.** Drop the RavenPack
denominator (ADR-016) and the `above_threshold` count gate (3/wk over 4wk AND 50
cumulative) — the gate predates and conflicts with ADR-019's report-don't-gate
stance (low-volume clusters get a fit with a wide credible interval, which is the
honest signal, not a hard cutoff). Keep `compute_source_contamination` as a
diagnostic. The module's new surface is the base-rate computation + per-cluster
adjustment.

### Consequences

- **Closes #1 everywhere** — both the fitted series and the displayed series are
  corpus-growth-adjusted; R₀ and stage no longer inherit the confound.
- **#2 and #3 stay out of the one-shot** but are unblocked: the global single
  denominator is the enabling invariant, recorded so a later pass is comparable
  and lag-honest by construction. The memory note `project_analysis_gaps.md`
  tracks #4 (stage-confidence) and #5 (anchor-recovery surfacing) — untouched
  here.
- **Priors / config unchanged** — units are preserved, so no `dynamics` schema
  bump and no re-tuning (the no-tuning rule, ADR-040, is respected: the
  adjustment is a fixed deterministic transform, not a fitted knob).
- **One denominator choice is a judgment call**: counting the outlier bucket and
  out-of-scope clusters in `N(d)` treats "total written discourse" as the base
  of spread (a narrative competes for attention against *everything* published,
  not only against in-scope macro). The alternative (in-scope-only denominator)
  would measure share-of-macro-discourse instead; we choose total-corpus because
  the SIR contagion framing is about penetration of the whole stream. Revisiting
  this is a new ADR.
- **The fix lands via the new analysis driver** (the CLI-gap subcommand, separate
  task) — normalization is computed there and fed to the fitter, so the one-shot
  downstream run produces adjusted curves with no further wiring.

---

## ADR-046: JEL scope is a display flag, not a dynamics gate

- **Status**: Accepted
- **Date**: 2026-06-15
- **Supersedes**: ADR-020's "out-of-scope clusters are dropped from *dynamics
  only*" rule (the no-pre-clustering-filter stance of ADR-020 still stands).
- **Relates to**: ADR-019 (report-don't-gate), ADR-044 (narrative map shape=JEL),
  ADR-045 (the analysis driver this lands in)

### Context

ADR-020 decided scope post-clustering via the JEL classifier and dropped
out-of-scope clusters (JEL ∉ {E,F,G,H}) from dynamics — they were embedded and
clustered but never fit, staged, or shown. The downstream analysis recomputes
cheaply from persisted `clusters.parquet` / `embeddings.npy` (no re-embed), so
fitting an out-of-scope cluster costs one extra PyMC run and nothing irreversible.
The artifact contract already carries `in_scope` and `jel_code` per narrative, and
the front-end already renders an "out of scope" badge + the JEL field name
(`StageBadge`, `NarrativeCard`). Dropping these clusters therefore discards
information the reader could see, for no methodological gain.

### Decision

Analyze **every** non-noise cluster with the full four-lens dynamics + stage,
regardless of JEL field. The JEL classification still runs, but its output is a
**per-narrative label/flag**, not a gate: out-of-scope narratives are shown with
their JEL code and an "out of scope" badge rather than omitted. The only hard
exclusion remains the BERTopic noise/outlier bucket (`topic == -1`), which is not
a narrative. Consistent with ADR-019's report-don't-gate stance — surface the
reading with its caveat, don't silently drop it.

### Consequences

- `run_analysis` (ADR-045 driver) sets `fit_ids` to all non-noise clusters; JEL
  no longer filters. One extra fit per out-of-scope cluster.
- No artifact-schema or front-end change — `in_scope`/`jel_code` and the oos badge
  already exist; they now appear on real out-of-scope narratives instead of only
  in sample data.
- A future in-scope-only filter is a display toggle, not a pipeline gate — all
  narratives remain present in the artifacts.
- The CLAUDE.md scope invariant is updated to match (out-of-scope flagged, not
  dropped).

---

## ADR-047: Markets overlay + Granger everywhere; VIX canonical; peak-count relabel

- **Status**: Accepted
- **Date**: 2026-06-16
- **Amends**: ADR-041 (markets overlay was "on-click, per-narrative on demand,
  relevant series"; this fixes the canonical series, makes it universal, and ties
  the lag test to one series)
- **Relates to**: ADR-039 (shape-facts lens, where `wave_count` lives), ADR-043
  (precompute everything into the static artifact), ADR-045 (adjusted volume is the
  series the overlay aligns against)

### Context

Three loose ends surfaced while finishing the per-narrative life-cycle view:

1. **Inconsistent market series.** Narratives showed different FRED overlays
   (VIX / 10y yield / 10y–2y spread) with no principled reason — in fact the
   variety was a sample-data artifact (`scripts/_sample_dashboard_artifacts.py`
   rotated series by `hash(label) % 3`). ADR-041 said "a relevant free FRED
   series" without fixing one, so there was no canonical default to fall back to.
2. **`wave_count` label.** The shape-facts lens reports `wave_count` =
   `len(find_peaks(y, height=½·peak))` (half-maximum convention, ADR-019/039, no
   tuned param). "wave count" reads as a modeled quantity; it is a plain count of
   prominent peaks.
3. **Coverage of the overlay + lag test.** ADR-041 framed Granger as on-click and
   per-narrative-on-demand; ADR-043 then made it precomputed. Production never
   wired it (`run.py` step 5 builds artifacts with `markets` absent). The question
   was whether to compute overlays + a lag readout for *every* narrative, and if so
   what caveats that universality brings (chiefly multiple comparisons across
   ~hundreds of narratives × directions × candidate series).

### Decision

1. **VIX is the canonical market series.** `VIXCLS` is the default overlay for
   every narrative and the **only** series the Granger/lag readout is computed
   against. It is the broadest single risk-sentiment gauge, free on FRED, and
   defined across the whole 2010-present window. Other series (10y yield, 2y, 10y–2y
   spread, HY/IG spreads) remain available as **display-only** overlay toggles with
   **no lag test** attached — so the precedence claim is made once per narrative,
   against one series, in one place.

2. **Compute the overlay + bidirectional Granger for every narrative**, baked into
   the artifact (ADR-043), against the adjusted weekly volume (ADR-045). Where a
   narrative has fewer than `_MIN_OBS_PER_LAG·max_lag` (5·4 = 20) weekly
   observations, the readout is **"insufficient data"** rather than a fitted number.
   The lag test stays at weekly resolution and first-differenced (ADR-041) — we do
   **not** chase daily resolution or per-series tuning.

3. **Framing is strictly descriptive, with a multiple-comparison caveat.** Running
   one bidirectional test per narrative is a large family of tests; some "significant
   precedence" verdicts will be false positives at α=0.05. We do **not** apply a
   formal family-wise/FDR correction (consistent with ADR-040: this is a descriptive
   educational tool, not a registered inferential claim). Instead the UI carries the
   existing **"this shows timing, not cause"** caption *plus* a caveat that the
   readout is one of many such tests and individual verdicts should be read as
   suggestive, not confirmatory. Honesty via labeling, per `feedback_frontend_clarity`.

4. **Relabel `wave_count` → "peaks (≥ ½ max)"** in the front-end shape-facts list.
   The artifact key and the computation are unchanged (ADR-019/039); only the human
   label changes, so the number is read as what it is — a count of peaks at least
   half the maximum height.

### Consequences

- `scripts/_sample_dashboard_artifacts.py` stops rotating series by hash and always
  emits VIX; sample artifacts now match the production contract.
- `src/mnd/dashboard/run.py` step 5 builds a VIX overlay per fitted narrative via
  `MarketsOverlay.from_env()` and passes the `markets` dict into
  `build_dashboard_artifacts`. FRED is free and validation-tier (no new paid dep,
  core invariant intact); the overlay is post-corpus, so ADR-020 (no external signal
  into clustering) is untouched.
- The lag claim is single-series and single-test-per-narrative, which bounds the
  multiple-comparison surface to one family of `n_narratives` tests rather than
  `n_narratives × n_series` — the most defensible universal design without a formal
  correction.
- No artifact-schema change: `markets` is an already-defined optional block on the
  narrative artifact; this just populates it for real narratives instead of only in
  sample data.
- Narratives shorter than 20 usable weeks (short-lived spikes) will show
  "insufficient data" for the lag readout but still get the VIX overlay drawn — the
  overlay is descriptive even where the test can't run.

---

## ADR-048: Broad-press lead-lag — bidirectional Granger vs. Media Cloud press

- **Status**: Accepted
- **Date**: 2026-06-16
- **Amends**: ADR-042 (the Media Cloud press overlay was display/validation only;
  this adds a lead-lag readout on top of it)
- **Relates to**: ADR-041 (the Granger machinery this reuses), ADR-047 (the
  markets lead-lag this mirrors), ADR-045 (adjusted weekly volume is the discourse
  series both tests consume)

### Context

The central claim of the project is that macro narratives **form upstream** in
institutional/academic discourse and **surface later** in the broad/premium press.
ADR-042 added a Media Cloud press-volume overlay so the two curves can be eyeballed
side by side, but stopped at the overlay — it never tested the timing directly. The
markets overlay already carries a bidirectional Granger readout (ADR-041/047); the
same test applied to press-vs-discourse is the most direct quantitative statement of
the project's thesis, and the data to run it (adjusted weekly discourse volume,
ADR-045; Media Cloud weekly story counts, ADR-042) already exists wherever the press
overlay does.

### Decision

Add a **broad-press lead-lag** readout to the per-narrative view, sitting beside the
markets readout (two-column, mirroring the stage / shape-facts pair):

- Run the **same** bidirectional Granger as markets (ADR-041): weekly resolution,
  first-differenced for stationarity, `max_lag=4`, `alpha=0.05`, minimum
  `_MIN_OBS_PER_LAG·max_lag = 20` weekly observations or the verdict is
  "insufficient data". The two series are the **adjusted institutional discourse
  volume** (ADR-045) and the **Media Cloud press story count** (ADR-042).
- Reuse `MarketsOverlay.granger_bidirectional`; the only generalization is a verdict
  wording parameter (`other_label`, default `"market"`) so the press readout reads
  "press precedes discourse" / "discourse precedes press" rather than market wording.
  The dict shape (`volume_leads_market` / `market_leads_volume` / `verdict` / per-lag
  `min_p`+`best_lag`+`significant`) is identical — "market" is the generic
  second-series slot, relabeled in the UI.
- Same **descriptive-only** framing as ADR-047: no family-wise/FDR correction
  (ADR-040), and the "this shows timing, not cause" + multiple-comparison caveat
  live on the **guide** page (explaining both the markets and press readouts), not
  repeated on each narrative.

### Consequences

- `MediaCloudArtifact` gains an optional `granger` field (same shape as
  `MarketsArtifact.granger`); no other schema change.
- The press readout exists **only where the Media Cloud series does** — key-gated
  (`MEDIACLOUD_API_KEY`) and reliable only from ~2017 (ADR-042), so pre-2017
  narratives show neither the press overlay nor its lead-lag. Markets (VIX) remains
  universal (ADR-047); the two readouts are independently present/absent.
- Production computation rides along with the Media Cloud overlay, which is still
  the ADR-042 follow-on (no key in `.env` yet); when that overlay is wired, the
  press Granger is the same `granger_bidirectional(..., other_label="press")` call on
  the weekly discourse/press pair. Sample data fabricates it for ≥2017 narratives so
  the front end is exercised now.
- This is the thesis test made visible: a "press precedes discourse" verdict is a
  point **against** the upstream-first story for that narrative, and the tool shows
  it honestly rather than hiding disconfirming cases.

---

## ADR-049: Dashboard artifact contract align-up (stage_detail + shape_facts)

- **Status**: Accepted
- **Date**: 2026-06-18
- **Relates to**: ADR-043 (the artifact contract this tightens), ADR-039 (the
  fits whose R₀ this surfaces), ADR-047 (the `shape_facts` relabel this completes)

### Context

The artifact builder (`build_artifacts.py`) passes `shape_facts` and
`stage_detail` through to the front end as opaque dicts — no key remap — so the
Astro narrative view reads producer keys verbatim. The hand-built sample artifact
set masked a drift between the two sides:

- The stage table read `sd.r0_median`, `sd.r0_ci_low/high`, and `sd.threshold`,
  but `classify_stage` only emitted `r0_mean`, `peak_time_mean`, `converged`,
  `total_articles`, `elapsed_days` — so on real pipeline output those cells would
  render "—".
- The stage table also read `sd.r0_peak` / `sd.r0_min`, which **no producer ever
  computed**. Under the constant-β/γ SIR fit (ADR-039) R₀=β/γ is a single
  posterior quantity; there is no time-varying R₀, so "peak" and "min" R₀ have no
  definition. (The sample's `r0_mean=0.55` with `r0_peak=2.6` was an impossible
  placeholder — even an effective R_t = R₀·S(t)/N is bounded above by R₀.)
- `shape_facts` keys (`peak_height`, `time_to_peak`, `duration_above_half_peak`)
  did not match the front-end's (`peak_volume`, `time_to_peak_days`,
  `active_days`); the sample data had already been written in the new names, so
  only real output would have surfaced the mismatch.

The choice was to dumb the front end down to current producer output, or to
**align up** — make the producers emit the richer set the front end was built
for. These are features we want to keep, so we align up.

### Decision

- `FitResult` gains `r0_median`. `_fit_sir` computes it as the per-draw median
  `median(β_draws/γ_draws)` (a ratio, so it does **not** equal the ratio of the
  marginal medians); `_fit_logistic` computes `logistic_r0(median(k_draws), γ)`
  (monotonic in k, so the median commutes through). `r0_mean` and the staging
  logic are untouched — this is display enrichment, not a staging change.
- `classify_stage`'s `detail` dict gains `r0_median`, `r0_ci_low`, `r0_ci_high`,
  and `threshold` (= `config.stages.growth_min_r0`), read via `getattr` so a
  minimal FitResult stand-in stays valid.
- `shape_facts` keys are renamed to the front-end contract: `peak_height` →
  `peak_volume`, `time_to_peak` → `time_to_peak_days`, `duration_above_half_peak`
  → `active_days` (`total_volume`, `wave_count` unchanged).
- The front-end "R₀ (peak / min)" row is **dropped** (no coherent definition under
  a constant-R₀ fit), and the interval label is corrected "95%" → "94%" to match
  the `hdi_prob=0.94` the fits actually report.

### Consequences

- Real pipeline output now populates the R₀ mean/median/interval/threshold cells
  the stage table was already built to show; no front-end logic changed beyond the
  row drop and label fix.
- The artifact schema is additive — `stage_detail` gains keys, `shape_facts` keys
  are renamed; `SCHEMA_VERSION` is unchanged because no consumer keyed off the old
  `shape_facts` names (the front end already used the new ones).
- A genuine "how hot did it peak" statistic (effective R_t over the fitted
  trajectory) is deferred to a future ADR if wanted; it is intentionally **not**
  faked here.
- Safe to deploy mid-run: the change is producer-additive and only the `analyze`
  stage emits these fields, so an RCC `git pull` while jobs are queued lets the
  downstream analyze step write the enriched artifacts.

---

## ADR-050: Incremental embedding cache (embed only new/changed chunks)

- **Status**: Accepted
- **Date**: 2026-06-18
- **Relates to**: ADR-036 (the 8B embedder whose ~7h full pass this avoids
  re-running), ADR-016 (the Phase-6 weekly re-ingest cadence this serves),
  ADR-030 (fail-loud — the alignment guard is preserved, not relaxed)

### Context

`embed` is batch full-recompute: it reads all of `chunks.parquet`, encodes every
row, and saves `embeddings.npy` as a positional matrix row-aligned to that
parquet, behind a hard downstream guard (`cluster`/`analyze` refuse to run if
`npy.rows != chunks.rows`). Any mutation of `chunks.parquet` therefore forces a
re-embed of the **entire** corpus — ~429k chunks, ~7h on an A100 — even when only
a handful of chunks are new. That is acceptable for a one-shot full build but not
for the Phase-6 weekly re-ingest (ADR-016), and it makes backfilling an ingest
discrepancy (a late coverage fix) disproportionately expensive.

Incremental embedding is well-posed because chunk identity is stable and
content-addressable upstream: `chunk_id = article_id + _cNNN` and
`article_id = sha256(source_id|url)`. The only blocker was that `embeddings.npy`
is stored positionally, with no key to merge against.

A subtlety rules out keying on `chunk_id` alone: `chunk_id` derives from the URL,
not the body, so a corrected / more-complete re-capture of an existing URL keeps
its `chunk_id` while its text changes. Reusing a vector on a `chunk_id` match
alone would silently serve a stale embedding.

### Decision

Persist a sidecar index next to the matrix and reuse vectors keyed on
`(chunk_id, text_sha1)`:

- `embeddings.npy` — `(N, D)` float32, **unchanged** positional contract.
- `embeddings_index.parquet` — `[chunk_id, text_sha1]`, row-aligned to the matrix.
  `text_sha1` hashes the exact title/body string fed to the embedder (one
  definition, `mnd.embedding.cache.build_chunk_text`).

`embed` now loads the cache iff present, reuses the cached vector for every row
whose `(chunk_id, text_sha1)` matches, encodes only the remainder, reassembles the
matrix **in current `chunks.parquet` order**, and rewrites both files. The
positional row-count guard is retained verbatim.

Cache presence — not a new flag — selects the mode, and it falls out of the
existing run topology:
- A full rebuild archives/NUKEs `data/processed` (`submit_parallel_ingest.sh`),
  removing matrix + sidecar → no cache → full re-embed.
- A delta run (`SKIP_CLEANUP=1`, the weekly cadence) preserves them → incremental.

Escape hatches: `embed --full` / `MND_EMBED_FULL=1` force a full re-encode (use
when the embedder/model changes); a dim mismatch between fresh and cached vectors
raises rather than concatenating; an index/matrix row-count disagreement discards
the cache and re-embeds in full. `embed-index` backfills the sidecar for an
existing matrix with no re-embedding — run once for embeddings that predate this
ADR, before the first delta re-ingest.

### Consequences

- Weekly re-ingest embeds only genuinely new/changed chunks (minutes on the delta)
  instead of the whole corpus (~7h). Clustering still re-runs globally by design —
  topic structure shifts as documents are added — so "futureproof" means
  *incremental embed + full re-cluster*, not incremental clustering.
- Correctness holds by construction: identical `(chunk_id, text)` ⇒ identical
  embedder input ⇒ identical vector from a deterministic model; any text change
  re-embeds. Re-captures/corrections are handled, not masked.
- `cluster`/`analyze` are untouched — they read `embeddings.npy` positionally and
  never open the sidecar — so this is safe to deploy mid-run; the in-flight
  recovery (cluster→analyze on the banked matrix) is unaffected.
- The current banked matrix has no sidecar; `embed-index` seeds it from the live
  `chunks.parquet` so the first Phase-6 delta can reuse all ~429k vectors.
- New pure module `src/mnd/embedding/cache.py` (unit-tested without ML deps);
  `embed` gains `--full`; new `embed-index` command.

---

## ADR-051: Fit/display volume floor — fit and surface only clusters above an article threshold

- **Status**: Accepted
- **Date**: 2026-06-19
- **Amends**: ADR-046 ("analyze every non-noise cluster"). The noise bucket
  (`topic == -1`) is still the only *hard* clustering exclusion, and ADR-046's
  rule that JEL is a display flag (not a gate) is unchanged — it now applies to
  the surfaced set.
- **Relates to**: ADR-019 (BERTopic library-default `min_cluster_size`, untouched),
  ADR-040 (credibility via no hand-tuning), ADR-044 (the narrative map this thins),
  ADR-045 (corpus base rate, still computed over the whole corpus)
- **Revised 2026-06-19** (same day, pre-`analyze`): floor 50 → 42 (pinned to the
  global random seed; identifiability is the binding bound, see Decision) and the
  ADR-044 map switched to focus-lit (hover-only) edges, which removed the
  static-hairball pressure that had argued for a larger floor.

### Context

The first full-corpus cluster run produced 7,242 non-noise BERTopic topics from
~429k chunks at the locked, library-default `min_cluster_size=10` (ADR-019). The
article-per-topic distribution is sharply power-law: median 7 articles, p90 27,
max 492; only 268 topics have ≥50 articles, 79 have ≥100.

Two independent problems follow, with one shared cause (too many tiny topics):

1. **Identifiability.** The four lenses fit 3-parameter curves (logistic L/k/t₀,
   Bass p/q/m, SIR β/γ/I₀) to each topic's daily volume series over its own active
   span (ADR-045). A ~7-article topic is a near-flat series with no identifiable
   rise/peak/decline; the standard ~10-observations-per-parameter heuristic for
   nonlinear models implies ~30+ informative points before a fit means anything.
   Fitting the long tail emits noise dressed as dynamics.
2. **Presentability.** `analyze` fits PyMC for *every* topic with no floor, so the
   long tail blows the 12 h analyze budget (3 NUTS fits × 7,242), and 7,242 nodes
   is unnavigable on the UMAP map / narratives / emerging / search.

Lowering granularity (raising `min_cluster_size`) would "fix" the count but is
exactly the hand-tuning ADR-040 forbids — it would alter the clustering whose
stability/anchor-recovery metrics are the credibility basis.

### Decision

Add a post-clustering **fit/display floor**, `dynamics.min_articles_to_fit`
(default **42**). Only non-noise clusters with at least that many *unique articles*
are fit, staged, and surfaced on the front end (map, narratives, emerging, search).
Sub-threshold clusters are retained verbatim in `clusters.parquet` and counted, but
get no dynamics, stage, map point, story card, or search entry.

The floor is set by the **identifiability bound**, not navigability: the
~10-observations-per-parameter heuristic for the 3-parameter lenses implies ~30+
informative points before a fit means anything, so any defensible floor sits at
~30 or above. Within that band the value is fixed by convention to the project's
`reproducibility.global_random_seed` (**42**) — a single, non-arbitrary anchor that
clears the bound with margin, rather than a round number chosen to hit a target
narrative count. This keeps the choice auditable: it is pinned to an existing
constant, not reverse-engineered from the output.

- Clustering is **untouched** — `min_cluster_size` and every other BERTopic/UMAP
  parameter stay at the ADR-019 defaults; stability and anchor-recovery metrics are
  still computed on the full clustering. The floor is a selection applied *after*
  clustering — a property of what we can fit and usefully show, not a tuned
  hyperparameter. It is fixed a priori on the two grounds above and is **never**
  adjusted to improve anchor recovery (ADR-040 holds).
- The driver (`run_analysis`) sets `fit_ids` to the ≥floor set; because
  `build_dashboard_artifacts` emits one artifact per cluster in `dynamics`, and
  centroids/UMAP/JEL/similar all key off `fit_ids`, restricting `fit_ids` thins the
  entire front-end surface in one place.
- Transparency: the index artifact carries `n_clusters_total` (all non-noise
  clusters detected) and `min_articles_to_fit`, so the data page reports
  "N detected, M surfaced (≥ floor articles)".

### Consequences

- 42 surfaces a few hundred narratives (between the measured ≥30 → 641 and
  ≥50 → 268; the exact count is logged by `analyze` and reported on the data page) —
  a navigable map and a fast `analyze` (well within 12 h) — while keeping every
  cluster in the corpus artifact for the reported total.
- Map edges no longer render statically. The ADR-044 narrative map draws each
  node's incident `similar_edges` only while that node is hovered (focus-lit,
  `mountMap3d` in `web/src/lib/chart.ts`), so node count no longer trades off
  against edge-hairball density. This is why the floor is now governed purely by
  identifiability (~30) rather than being pushed higher to keep the static graph
  legible — the earlier rationale for a larger floor no longer binds.
- The floor is a single config value (no hardcoding; honors the config invariant).
  Changing it is a presentation/identifiability call recorded here, not a model tune.
- A genuinely new narrative below 42 articles will not appear in the dashboard's
  emerging lens until it crosses the floor. That is a deliberate static-corpus
  tradeoff; Phase-6 live emerging detection runs off Media Cloud press counts
  (ADR-016), a separate layer this floor does not gate.
- No artifact-schema break for consumers: existing fields are unchanged; two
  optional index fields are added.

---

## ADR-052: Lifecycle stage is a model-free attention-trajectory classification

- **Status**: Accepted
- **Date**: 2026-06-19

### Context

The first full-corpus `analyze` run staged 365 narratives as **253 growth /
112 dormant / 0 decay**. Zero converging decay states is not a finding — it is a
compound failure, and unpicking it exposed a methodology error that would survive
the bug fix.

**Proximate cause (a crash, not a result).** All 365 SIR fits raised
`AttributeError: module 'pytensor.tensor' has no attribute 'scan'` —
`fitting.py` calls `pt.scan(...)` where `pt = pytensor.tensor`; `scan` lives at
`pytensor.scan`. The broad `except Exception` in `_fit_model` caught it and
recorded each as ordinary `converged=False` (the ADR-030 fail-loud gap: a code
error that killed *every* cluster was logged 365× as benign per-cluster
non-convergence). Staging then fell back to logistic, whose implied
`R_0 = 1 + k/gamma` has `k >= 0` (HalfNormal) and is therefore **structurally
>= 1** — decay was mathematically unreachable on the fallback path. The 253
clusters where logistic converged → growth; the 112 where it also failed →
dormant. Zero decay was over-determined.

**Deeper cause (R_0 is the wrong quantity).** Even with the crash fixed,
keying stage to R_0 is wrong. R_0 = beta/gamma is the *basic* reproduction
number — whether a narrative ever spread. In SIR, `R_0 > 1` is exactly what
*produces* a rise-and-fall hump; `R_0 < 1` means the contagion never caught.
So a risen-and-fallen narrative — the normal "faded" case — has `R_0 > 1` and
gets mislabeled "growth." Decay is a *current-phase* statement (the effective
`R_t` crossing below 1 at the peak), not a basic-`R_0` statement. The corpus is
full of decline the `R_0` mapping cannot express: 357/365 rose-then-fell, the
median narrative is 55% of its span past peak, 31% are declining over their last
quarter.

**Framing has diverged.** The project is now an educational/analysis tool
spanning narrative identification (clustering) + trajectory dynamics +
statistics. Shiller's narrative-economics and the SIR contagion analogy were the
catalyst and remain a *lens*, not the organizing law.

### Decision

1. **Stage is model-free.** Lifecycle stage = the narrative's recent attention
   trajectory, decided by robust non-parametric tests on the smoothed daily
   volume series over a recent window `W`, **independent of any fitted model**.
   "Now" = the corpus end date; `W` = the existing 4-week emerging horizon,
   clamped to the series span.

2. **Two rank-based tests over `W`:**
   - **Trend** — modified Mann–Kendall with the Hamed–Rao (1998)
     autocorrelation correction (the 7-day smoothing induces serial correlation
     that would otherwise inflate the false-positive rate). Theil–Sen slope on
     `log(1+y)` gives the robust growth-rate magnitude for display.
   - **Level** — Mann–Whitney U comparing the recent window to the narrative's
     own lowest-activity baseline window ("is current attention significantly
     elevated above this narrative's floor?").

3. **Four mutually-exclusive trajectory states:**
   - **growth** — significant upward trend.
   - **decay** — significant downward trend.
   - **stable** — no significant trend, level elevated above the narrative's own
     floor (sustained attention — perennial topics like debt-ceiling / Fed
     policy that sit at steady volume).
   - **dormant** — no significant trend, level at the floor (faded and settled,
     or never rose).

   `emerging` stays an **orthogonal recency flag** (significant upward trend
   AND first article within `W`), layered on growth — not a fifth state. It is
   not a distinct shape, would double a "rising" bucket, and is near-empty in a
   static run; live emerging detection is Phase-6's Media Cloud job (ADR-016).
   The existing `is_emerging` field already carries it.

4. **Significance, not magnitude.** Both splits use a field-standard `alpha`
   (0.05); there are **no tuned volume thresholds**, and the only horizon (`W`)
   is reused from the emerging window. ADR-040's no-hand-tuning basis is
   preserved and, if anything, strengthened (the old `growth_min_r0` threshold
   no longer gates staging).

5. **Fitted models are display-only lenses.** logistic / SIR / Bass (ADR-039)
   no longer touch the stage label. `R_0` is shown as the SIR lens's headline
   ("was it contagious?"), not the stage driver. The four-lens panel is
   unchanged.

6. **Reframe.** Stages are described as *attention trajectory*, not epidemic
   compartments. Shiller (2017/2019) + SIR is the marquee interpretive lens, not
   the foundation; the growth-rate ↔ `R_t` link (Wallinga & Lipsitch 2007,
   `sign(R_t − 1) = sign(r)` regardless of the generation interval) is offered as
   an optional connection for the curious, not the justification.

7. **Fail-loud hardening (ADR-030).** A model lens that fails on *every* cluster
   must raise, not be silently recorded as per-cluster non-convergence. Staging
   no longer depends on a fit converging, but the lens *display* does, and a
   100%-failure mode must never again masquerade as a result.

### Consequences

- **Decay becomes expressible and abundant**, matching what is plainly in the
  data. The dormant/decay boundary is now a clean significance call —
  significantly falling = decay; not moving + at floor = dormant — so the two
  cannot collide.
- **Dormant stops being polluted by fit-failure.** All 112 prior "dormant"
  clusters were dormant *only* because logistic did not converge; under the new
  rule dormant means "the series is quiet," a real property.
- **Robustness dividend.** Staging no longer breaks when a sampler fails — the
  exact failure mode that produced the zero-decay artifact would now yield a
  broken SIR *display* but **correct stages**.
- **New `stable` state** needs a fourth colour/label in the front end
  (`Stage` union + `STAGE_COLOR`/`STAGE_LABEL` in `web/src/lib/data.ts` and
  `chart.ts`), plus a methodology/UI copy pass for the reframe and an "as of
  <generated_at>" date line for honesty.
- **Left-censoring caveat.** A narrative already high before 2010 that stayed
  high has no in-window floor and may read dormant — rare, accepted, and
  consistent with "analysis is as-of the latest ingest" (the static-corpus
  tradeoff already acknowledged in ADR-051).
- **Dependency.** Modified Mann–Kendall is not in scipy; either add the free,
  open `pymannkendall` (BSD — allowed under the core-pipeline free/reproducible
  rule) or implement the Hamed–Rao correction in-repo on top of
  `scipy.stats.kendalltau`/`theilslopes`/`mannwhitneyu`. Implementation-time
  choice.
- **Supersession.** Supersedes ADR-002's staging-selection clause
  (logistic-as-SIR-fallback driving `R_0` staging) and ADR-019 §E's
  `R_0`-threshold staging. The four-lens display (ADR-039), the corpus base-rate
  normalization (ADR-045), and the fit/display floor (ADR-051) are unchanged.
  Amends `src/mnd/stages/classify.py`.

---

## ADR-053: SIR fit on a weekly integration grid + SIR-only reduced inference budget

- **Status**: Accepted
- **Date**: 2026-06-22

### Context

ADR-052 made the lifecycle stage model-free and demoted SIR `R_0` to a
display-only lens headline ("was it contagious?") — it no longer gates the stage,
and it never touched anchor recovery. ADR-052 also fixed the `pt.scan` crash
(commit `09bda0f`) that had silently turned every SIR fit into a no-op, so the
next run will *actually* sample SIR for the first time.

That exposed a compute wall. SIR is integrated for NUTS by a `pytensor.scan`
discrete-time Euler loop with `n_steps = T − 1` (`fitting.py`), so its gradient
cost is `O(series length)`. Logistic and Bass are vectorized / closed-form and
cost the same regardless of length — the cost is entirely SIR's.

The Jun-19 `dashboard_full` produced 365 fittable clusters whose series span
their full active range: median ~5077 days (mean 4693, max 6000). Macro topics
recur, so a narrative's "own active span" is ≈ the whole 16-year corpus for
nearly all of them. At the production NUTS budget (draws 2000 + tune 1000, 4
chains, `target_accept` 0.95) a single ~180-day fit did not finish in 13 min
locally; a ~5000-day fit is ~28× that scan length → hours per cluster × 365 →
hundreds–thousands of A100-hours. That exceeds a 12 h SLURM wall, and a single
fit overrunning the wall cannot be rescued by the per-cluster checkpoint/resume
(commit `b1bc1b2`), which has no mid-fit checkpoint. The Jun-19 run only
"completed" because SIR was a no-op.

### Decision

1. **Weekly integration grid for SIR only.** Bin each cluster's
   already-7-day-smoothed daily series to a weekly grid (mean over
   `dynamics.sir_fit_grid_days = 7` days) before the SIR scan, cutting `n_steps`
   ~7×. The displayed volume curve and the model-free stage stay daily — only
   SIR's internal integration resolution changes.

2. **`R_0` is grid-invariant; time-unit outputs are converted back to days.**
   The weekly Euler step makes the fitted `beta`, `gamma` per-week rates.
   `R_0 = beta/gamma` is dimensionless, so it is reported unchanged. For the
   displayed SIR curve and peak time the fitted rates are divided by the grid
   (per-week → per-day) and integrated on the daily grid via the existing
   `sir_prevalence` / `sir_peak_time`, so the curve keeps its ADR-039 daily-grid
   contract and the peak is in days, consistent with the logistic and Bass lenses.

3. **Population scale is held fixed.** `N_pop` is computed from the daily total
   as before, not the binned series, so the fit's amplitude and identifiability
   are identical to the daily version; only the integration resolution changes.

4. **SIR-only reduced inference budget.** SIR samples under a separate
   `dynamics.sir_inference` block (draws 500, tune 500, chains 2,
   `target_accept` 0.9); logistic and Bass keep the production
   `dynamics.inference` budget (2000 / 1000 / 4 / 0.95). This is a ~4–6×
   multiplier applied only to the expensive, display-only lens.

5. **The no-tuning rule (ADR-040) is untouched.** ADR-040 binds parameters
   adjusted to improve *anchor recovery*. Anchor recovery is a clustering metric,
   independent of the display-only SIR fit; neither the grid nor the budget can
   change it. A sampler budget is a Monte-Carlo-precision setting, not a model
   parameter or threshold. This is therefore a fit-mechanics decision (like
   ADR-051), not a methodology lock-in amendment.

### Consequences

- **Tractability.** Each SIR fit becomes short enough to finish well within a
  12 h wall, so checkpoint/resume completes the whole run across resubmissions
  regardless of total hours. The absolute per-fit time on A100 is unmeasured; the
  guarantee is sub-wall-per-fit, not a specific minutes figure.
- **Cache invalidation is automatic.** The fit-cache key hashes
  `repr(cfg["dynamics"])` (`run.py` `_fit_signature`); adding both keys under
  `dynamics:` invalidates every stale Jun-19 SIR entry, so the next run refits
  SIR rather than reloading the no-op result.
- **Accuracy caveat (accepted).** Euler-`Δt=1` on a weekly step is a coarser ODE
  approximation than on a daily step; for a decorative lens whose headline is the
  dimensionless `R_0`, this is acceptable, and the daily-resolution display curve
  is re-integrated continuously from the converted per-day rates. Fewer draws plus
  a lower `target_accept` can push a few borderline fits below the convergence
  gate (`ess_bulk > 400`, `R-hat < 1.05`) — i.e. more `R_0` "n/a"; the front end
  already renders a missing lens, and logistic remains the fallback `R_0` headline.
- **Convergence is now observable.** Because Jun-19 SIR was a no-op, the real SIR
  convergence rate on this corpus is unknown; the first weekly-grid run is also
  the first measurement. If SIR converges on almost nothing, dropping it (its own
  ADR) becomes the obvious follow-up.
- **Scope.** Amends the SIR fit mechanics of ADR-039 and the SIR portion of the
  ADR-019 inference settings; relates to ADR-052 (SIR is display-only), ADR-051 (a
  comparable fit-mechanics decision), and the `b1bc1b2` checkpoint/resume.
  Amends `src/mnd/dynamics/fitting.py` and `config/config.yaml`.

---

## ADR-054: Cross-document boilerplate stripping at the filter stage (sub-document recurring-passage removal)

- **Status**: Accepted
- **Date**: 2026-06-25

### Context

Whole-document near-duplicate removal (ADR-019, MinHash LSH at Jaccard 0.85)
catches articles that are duplicates *in their entirety*. It cannot catch a
disclaimer, donation disclosure, media-contact block, or speech caveat repeated
verbatim *inside* otherwise-distinct documents. These recurring passages survive
into the embedded text, and because they are lexically identical across hundreds
of documents they dominate the c-TF-IDF signal, producing artifact clusters keyed
on the boilerplate rather than the macro content. Observed in the Jun-19 bake: a
458-article Brookings cluster whose representative text is the donation-influence
disclosure ("...the conclusions and recommendations of any Brookings publication
are solely those of its author(s)..."), and a BIS cluster keyed on the speaker
disclaimer ("The views expressed are those of the author and do not necessarily
reflect those of the BIS"). The same passages impoverish the JEL representation
(ADR-046) and inflate single-source share.

The fix must remove the *repetition*, not the *topic*: ADR-020 forbids any
pre-cluster topical filter, and that prohibition stands. The only question is
mechanical — text repeated across many documents carries no per-document signal.

### Decision

Add a sub-document recurring-passage strip at the filter stage, immediately after
MinHash dedup and before the filtered corpus is persisted
(`scripts/run_pipeline.py` `cmd_filter`). New module
`src/mnd/filtering/boilerplate.py`.

1. **Granularity: normalized sentences.** Each article body is split into
   sentences; each is normalized (lowercase, whitespace-collapsed, surrounding
   punctuation stripped) to a match key. Only sentences with ≥ `min_sentence_words`
   (6) tokens are eligible — short phrases collide legitimately and are never
   stripped.

2. **Criterion: cross-document frequency.** Document frequency of a normalized
   sentence is the number of *distinct documents* containing it (counted once per
   document). A sentence with DF ≥ `min_doc_frequency` (25) is template and is
   removed from every document. This is the template-detection criterion of
   Bar-Yossef & Rajagopalan 2002 and the boilerplate-removal lineage of
   Kohlschütter et al. 2010 at corpus scale; it is the sub-document analogue of
   the Broder 1997 / Henzinger 2006 whole-document dedup locked in by ADR-019, and
   is consistent with Lee et al. 2022 (removing verbatim spans repeated across a
   corpus improves downstream models).

3. **Document count, not topical content, is the only input.** The strip never
   inspects what a sentence is about. A content sentence stays below the threshold
   because real macro prose carries document-specific numbers, dates, and
   entities, so its exact normalized form rarely recurs across ≥25 documents; only
   invariant template text crosses the line. ADR-020's no-topic-filter invariant
   is intact — ADR-054 extends the ADR-019 dedup family, it does not reintroduce a
   scope gate.

4. **Pure-boilerplate articles are dropped, but only if actually stripped.** An
   article whose stripped body falls below `min_content_words` (50) *and* from
   which at least one sentence was removed is dropped as a content-free shell. A
   naturally short article from which nothing was stripped is always kept —
   under-capture is the failure mode that matters (corpus-correctness invariant).

5. **Auditable removal (ADR-030 fail-loud).** The strip logs the count of
   boilerplate sentence-types, instances removed, articles modified, and articles
   dropped, and persists `boilerplate_report.json` beside the filtered parquet
   listing every stripped sentence with its document frequency and every dropped
   `article_id`, so the removal can be reviewed after a remote RCC run rather than
   inferred from scrolled logs.

6. **Config-driven, no tuning.** All knobs live under `filtering.boilerplate`
   (`enabled`, `min_doc_frequency`, `min_sentence_words`, `min_content_words`).
   These are corpus-hygiene parameters; ADR-040 binds only parameters tuned to
   improve anchor recovery, and none is set against the anchor metric. Thresholds
   are absolute document counts: template DF grows with the corpus while
   coincidental content repetition does not, so the floor stays valid as the
   corpus grows (Phase 6).

### Consequences

- **Artifact clusters dissolve at the root.** With the recurring passage gone, the
  Brookings-disclaimer and BIS-disclaimer members re-cluster by their actual
  content or fall below the ADR-051 fit floor; neither is surfaced as a narrative.
- **JEL and source-mix improve for free.** The c-TF-IDF terms that feed the JEL
  representation (ADR-046) and the single-source share stop being dominated by
  template text.
- **Recompute required; lands on the next embed.** The strip rewrites article
  bodies and `word_count`, so it takes effect when the pending catch-up re-ingest
  + re-embed runs; existing artifacts are unaffected until then.
- **Bounded false-positive risk, fully logged.** Stripping an invariant template
  sentence that is technically "content" (e.g. a standing FOMC caveat) is possible
  but low-cost (such sentences are non-discriminating) and is enumerated in the
  report for review.
- **Scope.** Extends ADR-019 (whole-document dedup) to sub-document repetition;
  orthogonal to and does not weaken ADR-020 (no topical pre-cluster filter);
  relates ADR-030 (fail-loud), ADR-046 (JEL representation), ADR-051 (fit floor).
  Adds `src/mnd/filtering/boilerplate.py`, a `filtering.boilerplate` config block,
  and wires one call into `cmd_filter`.

---

## ADR-055: Richer JEL cluster representation — c-TF-IDF terms + BERTopic representative documents

- **Status**: Accepted
- **Date**: 2026-06-25

### Context

JEL scope (ADR-020/046) is assigned per cluster by nearest-prototype: the
cluster's representation is embedded and matched to the closest AEA JEL code
description. The representation was the cluster's c-TF-IDF terms alone — a handful
of stemmed keywords. Two failure modes followed:

1. **Thin signal misses real macro clusters.** Bare terms under-determine the
   match. With the terms-only representation the natural-rate / r-star cluster and
   the Basel cluster both fell to the "Y" (miscellaneous) catch-all instead of E
   and G — core macro narratives flagged out of scope.
2. **Catch-all asymmetry.** "Y — Miscellaneous Categories" is a two-word prototype
   against ~60-word real-code descriptions; an impoverished bare-term
   representation is drawn to it, so Y over-attracts.

(The earlier all-Y collapse was a separate parquet round-trip bug fixed in
93ddaa4; this ADR is about representation quality, not that bug.)

JEL is a display flag, not a gate (ADR-046), so the bar is "more accurate flag,"
not "perfect classifier." But sending r-star and Basel out of scope is a visible
error worth fixing at the representation level rather than by tuning prototypes
(which the no-tuning rule discourages).

### Decision

Enrich the cluster representation passed to `classify_clusters` with BERTopic's
representative documents. For each surfaced cluster the representation becomes the
c-TF-IDF terms followed by the text of its top
`clustering.jel.n_representative_docs` (3) `Representative_Docs`, each a bounded
leading excerpt. Terms are placed first so they always survive the embedder's
sequence cap; representative-document text fills the remaining budget.

1. **Source: BERTopic's own representative docs.** `Representative_Docs` is
   BERTopic's canonical per-topic representative selection (already in
   `topic_info`), so the JEL representation is consistent with the model's notion
   of what each cluster is about — no ad-hoc re-ranking, no clustering→display
   dependency.
2. **Terms-first ordering.** The terms anchor the representation and are never
   truncated away; the document text is supplementary context.
3. **Taxonomy unchanged; Y kept.** The full AEA top-level taxonomy including Y is
   retained. Dropping Y was tested and rejected: without a miscellaneous home,
   genuinely off-topic clusters (Syria, pollution, drug trafficking) leak into
   E/F/G/H. The richer representation makes Y stop over-attracting on its own — Y
   shrinks because real clusters now match their true code, while off-topic
   clusters still land on Y.
4. **Config-driven, no tuning.** `clustering.jel.n_representative_docs` is the only
   new knob; it is a representation-construction choice, not tuned against anchor
   recovery (ADR-040 holds).

### Consequences

- **Macro recall improves; Y normalizes.** On the Jun-19 narratives (0.6B proxy,
  representative title+excerpt as a stand-in for `Representative_Docs`), all nine
  macro probes land in scope (r-star → E and Basel → G both recovered from Y),
  pollution stops leaking, and Y falls from a 75-cluster bucket to 43 with no
  taxonomy change. Production uses the larger 8B embedder and the fuller
  `Representative_Docs` text, expected at least as discriminating.
- **Residual imperfection is acceptable and non-gating.** One off-topic leak
  remains in the proxy (drug-trafficking → F, a genuine JEL ambiguity); the other
  apparent leak is the BIS-disclaimer cluster, which ADR-054 boilerplate removal
  eliminates upstream. Because JEL is a display flag (ADR-046), a residual
  mislabel is shown with its code, never dropped.
- **Recompute required.** The representation is built at analyze time from
  `topic_info`; it takes effect on the next bake/re-embed, where the
  representative-doc text is itself already boilerplate-cleaned (ADR-054).
- **Scope.** Amends the representation step of ADR-020/046; keeps the AEA taxonomy
  and the {E,F,G,H} scope unchanged; relates ADR-054 (boilerplate) and ADR-019
  (embedding space). Adds `clustering.jel.n_representative_docs`, a
  `_representative_docs_from_topic_info` helper, and one changed call in
  `dashboard/run.py`; corrects the stale `jel_classifier` docstring that still
  described JEL as a dynamics gate (superseded by ADR-046).

---

## ADR-056: Human-readable narrative names — display-layer LLM titling over c-TF-IDF labels

- **Status**: Accepted
- **Date**: 2026-06-30

### Context

Every surfaced narrative is labelled with BERTopic's default: the cluster id
joined to its top c-TF-IDF terms, e.g. `23_nps_lands_acres_park` or
`27_expressed speech_bank speech_speaker necessarily_reflect bis`. For the
internal pipeline this is fine — the terms *are* the cluster representation. But
the stated product goal is an educational tool that "identifies macroeconomic
stories/narratives" for a non-expert reader (project_goal_intent), and a wall of
underscore-joined stems is not a story name. The front-end clarity principle
(every element self-explanatory to a non-expert) is violated at the most basic
level: the title.

Constraints that shape the fix:

1. **No-paid-dependency rule binds data fetching + analysis only** (CLAUDE.md,
   ADR governance). The display/presentation layer is explicitly exempt — paid-LLM
   story prose is already sanctioned there. A readable title is display-layer.
2. **Reproducibility.** The core pipeline (curves, stages, JEL scope, dynamics)
   must stay free and deterministic. An LLM titling step introduces non-determinism
   and an external dependency, so it must not sit on the analysis path and the
   published artifact must be reproducible without re-calling the model.
3. **No hand-tuning toward anchor recovery (ADR-040).** Titles are cosmetic and do
   not touch clustering, scope, fits, or recovery — but the naming prompt must not
   smuggle in anchor names or otherwise become a tuning surface.
4. **Grounding.** A title must describe the cluster's actual content, not invent a
   plausible macro story. Hallucinated names would mislabel exactly the out-of-scope
   clusters the JEL flag is meant to mark honestly (ADR-046).
5. **Graceful degradation.** Like the markets (ADR-047) and Media Cloud (ADR-048)
   overlays, the feature must degrade to absent — no key, no titles, fall back to the
   c-TF-IDF label — never block a bake.

### Decision

Add a display-layer **narrative naming** step that turns each surfaced cluster's
existing representation into a short human title plus a one-line description, via a
paid LLM, cached and committed so the published site is reproducible without the
key.

1. **Model + transport.** Claude Haiku 4.5 (`claude-haiku-4-5`) — the cheapest
   current tier, ample for short titling. One **synchronous** Messages call per
   cache miss, `temperature=0` with a JSON-schema structured output
   (`{title, description}`) for stable, parseable results. The committed cache
   (point 3) makes each bake incremental, so the Batches API's throughput buys
   nothing here while its polling lifecycle adds complexity; at Haiku rates the
   50% batch discount is a fraction of a cent. Batches remains a drop-in option
   if a cold full-corpus naming pass ever needs it. A first-call failure (missing
   key, SDK, rate ceiling) aborts the pass rather than firing ~N failing calls;
   later one-off failures are skipped per cluster.
2. **Input is the same representation already built for JEL (ADR-055).** The prompt
   carries the cluster's c-TF-IDF terms, its top representative-document excerpts,
   date range, and source mix — nothing else. The system prompt instructs: name the
   cluster **only** from the supplied material, no outside knowledge, ≤6-word title,
   one factual sentence; if the material is not about economics, name it plainly
   anyway (do not force a macro framing). No anchor names appear in the prompt.
3. **Cache keyed on a representation hash; commit the cache.** Each title is stored
   under a content hash of its representation (mirroring the embedding cache ADR-050
   and the per-cluster fit cache). A bake reuses any unchanged cluster's title and
   calls the model only for new/changed clusters; the cache is committed to the repo
   so the static site rebuilds deterministically with no key present. Re-titling
   happens only when a cluster's representation actually changes.
4. **Additive artifact contract; front-end falls back.** `label_human` and
   `description` are added to the index/narrative artifacts (schema_version bump).
   The front end shows `label_human` when present and falls back to the raw
   c-TF-IDF `label` otherwise, so a key-less build and the current data both render
   unchanged. The c-TF-IDF `label` and `top_terms` remain in the artifact — the
   readable name is layered over them, not a replacement, so the provenance of the
   cluster stays inspectable.
5. **Display-only, never upstream.** The title never feeds embedding, clustering,
   JEL scope, fitting, staging, or anchor recovery. It is generated after clusters
   are fixed, from their frozen representation, exactly like the overlays.

### Consequences

- **The catalog reads as stories, not term-dumps**, satisfying the educational goal
  and the front-end clarity principle, while the macro-first relevance default
  (build_artifacts ordering + the scope facet) decides *which* stories lead.
- **Reproducibility preserved.** The published artifact is deterministic: the
  committed title cache means a rebuild needs no API key and produces identical
  output. The free, no-paid-dep core (curves/stages/scope/fits) is untouched; only a
  cosmetic label is paid, consistent with feedback_paid_dep_scope and the CLAUDE.md
  display-layer exemption.
- **Honest about residual error.** A title is grounded in real cluster material but
  is still model output; a mislabel is a cosmetic display error shown alongside the
  unchanged terms and JEL code, never a gate (ADR-046 holds). Out-of-scope clusters
  get a plain descriptive name, not a forced macro one.
- **New knobs / surfaces.** Adds a `display.naming` config block
  (`model`, `enabled`, `max_title_words`, cache path), a naming module in the
  display layer, two artifact fields, and a schema_version bump. No change to any
  ADR-019/020/039/045/046/051/052 analysis decision.
- **Cost + dependency.** Introduces `anthropic` as a display-layer dependency and an
  `ANTHROPIC_API_KEY`, both gated behind `display.naming.enabled` and absent-tolerant.
  Per-bake cost is negligible (Haiku via Batches, cache-incremental).
- **Scope.** Display-layer only; relates ADR-055 (shares the representation),
  ADR-046 (flag-not-gate), ADR-043 (static-site contract), ADR-050 (cache pattern),
  and the no-paid-dep governance in CLAUDE.md. Supersedes nothing.

---

## ADR-057: Phase-6 live emerging — press-heating detection + weekly institutional refresh (design)

- **Status**: Accepted
- **Date**: 2026-06-30 (parameters + `merge_models` mechanism settled 2026-07-01)

### Context

The pivoted mission includes surfacing narratives "for current news," but the
tool's live surface is thin. The Emerging view ranks narratives by
`is_emerging` — a within-corpus recency flag (growth stage + last-active within
the four-week window of the corpus frontier). It has two limits:

1. **Corpus staleness.** The frontier is the last ingest date, so "emerging"
   only means "recent *as of the last build*," not "emerging now." Between builds
   the feed goes stale.
2. **No press-led signal.** Institutional writing is the formation layer, but it
   lags the press for already-forming stories. The tool has a per-narrative Media
   Cloud press overlay (ADR-042) and a bidirectional lead-lag readout (ADR-048),
   yet nothing flags a tracked narrative that is *spiking in the press right now*.

Detection scaffolding already exists but is unwired into the feed:
`MediaCloudDetector.fetch_story_counts` (story counts + attention-share ratio over
time) and `detect_anomalies` (z-score: count above baseline mean + k·σ) in
`src/mnd/detection/mediacloud.py`.

Hard constraints from prior decisions:
- **Press is a signal, not substrate (ADR-010).** Press *text* is never embedded
  or clustered; ingesting it would bias the corpus toward post-formation stories.
- **Display/validation only, never a gate (ADR-020/042/046).** No emerging signal
  may feed embedding, clustering, or JEL scope — that would reintroduce the
  pre-cluster topic gate ADR-020 removed.
- **Under-capture is the failure mode that matters.** A weekly refresh must not
  leave per-source gaps (weekly-reingest note: staggered per-source end dates).

### Decision (design; no pipeline code in this ADR)

Treat "emerging" as **two distinct display-only signals**, and scope out a third.

1. **Institutional onset (existing `is_emerging`), kept — refreshed by a weekly
   pipeline run (§2).** Unchanged in meaning; it just needs a current frontier.

2. **Press heating (new, near-term, low-risk).** For each *already-tracked*
   narrative, run `detect_anomalies` on the trailing Media Cloud window using the
   same ADR-042 per-narrative query, on the **attention-share ratio** (not raw
   counts, so it is robust to overall press-volume drift). Flag a narrative as
   "heating in the press" when its most-recent **4-week window** (matching the
   institutional emerging horizon) sits ≥ **k·σ, k = 2**, above its own **trailing
   52-week baseline** (a year, so the baseline carries seasonality). Surface it in
   the Emerging view as a **separate signal beside** the institutional recency flag
   — never merged, so the reader can tell "our sources just started on this" from
   "the press is spiking on a story we already track." Recomputes entirely from the
   press series at bake time: **no re-embed, no re-cluster, and it never touches
   embedding/clustering/scope** (ADR-020/046 invariant intact), exactly like the
   ADR-042/048 overlays. The window, baseline, and k are fixed config values, not
   tuned against anchor recovery (ADR-040); k = 2 is the deliberately sensitive
   starting point (≈ upper 2.3% tail) — captioned literally as "press attention
   more than 2σ above its yearly baseline" so the reader knows the bar.

3. **Weekly institutional refresh — build onto the existing model, don't
   re-cluster from scratch.** Per-source **over-fetch** delta (start each source's
   window before its own `max(published_at)` in the corpus; dedup absorbs the
   overlap) → incremental embed of only the new chunks (ADR-050). The new week is
   folded into the existing narrative set with BERTopic's own incremental primitive
   rather than a fresh fit that would renumber every topic: fit a model on the
   new-week docs and `merge_models([base, new], min_similarity=τ)`. `merge_models`
   **keeps every existing topic's id** — so its narrative-page URL and its ADR-056
   human name are stable *by construction* — and **appends only genuinely-new
   topics**, those whose similarity to every existing topic is below τ, as new ids.
   `analyze` then re-runs on the merged clusters: existing narratives' volume curves
   simply extend with the new articles, new narratives are fit and staged, and the
   ADR-056 name cache reuses every unchanged representation's title while paying the
   model only for the new clusters. Existing articles keep their assignments; a new
   article either extends an existing narrative or seeds a new one. **The tracking
   invariant holds: ids, URLs, names, and histories persist, and new narratives can
   still form.** A full from-scratch re-fit — reconciled back to the prior id set by
   Hungarian centroid-matching above a cosine floor — is kept only as an occasional
   rebuild path (when drift warrants a clean slate), never the weekly mechanism.
   This still warrants its own implementation ADR (choosing τ; handling a topic that
   splits or merges across a weekly `merge_models`; validating that the anchors keep
   their ids across a merge), but the math stays inside BERTopic's built-in merge
   rather than a bespoke assignment layer.

4. **Scoped out: novel press-only narratives.** Detecting narratives that exist
   *only* in the press and not yet in the institutional corpus would require
   clustering press text — which ADR-010/020 forbid. Press stays a volume signal
   over the institutional narrative set; the tool does not claim to discover
   stories the institutions have not written about.

### Consequences

- **Sequence.** §2 (press heating) is the near-term win: display-only, buildable
  now from the persisted clusters + live Media Cloud, no re-embed, gated by a new
  config flag and degrading to absent when unkeyed (like every Media Cloud
  coupling). §3 (weekly refresh) is deferred until the identity-stability approach
  is validated — until then the feed is refreshed by manual re-runs, and "emerging"
  is honestly captioned as "as of the last build."
- **Honesty.** Keeping the two signals separate avoids implying the institutions
  are writing about something when only the press is; the caption states which
  signal fired. Press coverage thins before ~2017 (ADR-042 `reliable_since_year`),
  so heating is only computed on the reliable window.
- **Invariants preserved.** Nothing here feeds embedding, clustering, or scope
  (ADR-020/046); press text is never embedded (ADR-010); values are fixed a priori
  (ADR-040). Relates ADR-016 (Media Cloud Premium live), ADR-042/048 (press
  overlays), ADR-050 (incremental embed), and the corpus-correctness invariant.
- **Settled here.** Press-heating recent window = 4 weeks, baseline = 52 weeks,
  k = 2 (sensitive start); narrative identity via BERTopic `merge_models` (existing
  ids/URLs/names preserved, new topics appended above τ), Hungarian centroid-match
  kept only for an occasional full rebuild; cadence starts **manual** and moves to a
  **cron on RCC** once identity stability is validated.
- **Deferred to the weekly-refresh implementation ADR.** The `merge_models`
  similarity floor τ; how to handle a topic that splits or merges across a weekly
  merge; and the cron schedule itself. Press heating (§2) needs no such follow-up —
  it is buildable now as its own small implementation ADR.

---

## ADR-058: Peak-relative plateau test — `stable` vs `dormant` keyed to the narrative's own high-water level

- **Status**: Accepted
- **Date**: 2026-07-02

### Context

The first clean `analyze` run under ADR-052 (job 51323109, 365 narratives, all
ADR-052/053/054/055 fixes in place, JEL scope validated — 185 in-scope, no all-Y
collapse) staged **342 stable / 23 growth / 0 decay / 0 dormant**. Zero dormant
and zero decay across a 2010–2026 corpus of overwhelmingly transient event
narratives is not a finding — it is the ADR-052 `Level` test failing on real data.

**Empirical diagnosis.** Of the 342 `stable` narratives, **100% sit below 20% of
their own peak volume**; the median recent-window activity is **1.7% of peak**
(p25 = 1.3%). Concretely: a cluster peaking Sept-2010 at 406 articles, now at 0.3%
of that, is labelled `stable`; a cluster peaking 2015, ten-plus years past, at 0.5%
of peak, is `stable`. These are dead narratives called stable.

**Root cause — a spec/implementation divergence inside ADR-052.** ADR-052 §2/§3
defines the `Level` test as Mann–Whitney U comparing the recent window to the
narrative's **lowest**-activity baseline window ("is current attention elevated
above this narrative's *floor*?"), and describes `stable` as a "high plateau." On
this corpus the two are incompatible: institutional sources (Fed, BIS, NBER, IMF)
never fully drop a topic, so every narrative keeps a low nonzero tail to the corpus
edge. That tail is trivially "above the quiet floor," so the floor test returns
*elevated* for essentially every no-trend narrative → `stable`. The test never
checks that the plateau is actually **high**, which was the stated intent.
`dormant` (recent *at* the floor) is therefore nearly unreachable, and `decay`
(a significant *downward* Mann–Kendall trend over the 4-week window) does not fire
either because a long-faded narrative is already low-*flat* there, not falling.
ADR-052's own prediction ("decay becomes expressible and abundant; dormant means
the series is quiet") was falsified by the data it had not yet seen.

### Decision

Amend ADR-052 §2 (`Level` test) and §3 (`stable`/`dormant` definitions). The
trend test (Mann–Kendall → `growth`/`decay`) and the four-state vocabulary are
unchanged; only the no-trend split is corrected.

1. **The reference flips from the quietest window to the narrative's own
   high-water window.** Mirroring the existing baseline construction (the
   minimum-sum width-`W` window), take the **maximum-sum** width-`W` window as the
   peak reference. Both are the narrative judged against its own dynamic range — no
   absolute magnitude threshold, no new tuned constant.

2. **`stable` vs `dormant` becomes a peak-relative *level* comparison, not a rank
   test.** A Mann–Whitney U comparing the recent 4-week window to the peak 4-week
   window was implemented first and **empirically rejected**: the smoothed daily
   series is zero-heavy, so two 28-point windows both dominated by ties give no
   power — narratives sitting at a *tenth* of their peak returned `p ≈ 0.15–0.72`
   and stayed `stable` (265/365 on the first pass, all still well below peak). The
   split is therefore by level:
   - **stable** — no significant trend **and** the recent-window mean is **≥
     `dormant_peak_fraction` × the peak-window mean**: still near its own high-water
     mark (perennial topics at sustained volume).
   - **dormant** — no significant trend **and** the recent-window mean is **below
     `dormant_peak_fraction` × the peak-window mean**: fallen well off its own
     peak — faded.

3. **`growth` / `decay` / `emerging` unchanged.** Still the modified Mann–Kendall
   trend over `W`; `emerging` stays the orthogonal recency flag layered on growth.

4. **One new parameter: `stages.dormant_peak_fraction = 0.25`.** The recent window
   must fall below a quarter of the narrative's own peak level to read `dormant`.
   This is a **definition** (where "faded" begins on the narrative's own scale),
   **not** a hyperparameter tuned to improve anchor recovery — ADR-040's no-hand-
   tuning basis binds tuning-for-recovery, and this line is never touched by the
   anchor/fizzled set. The dormant share moves smoothly with it (≈8% at 0.10, ≈45%
   at 0.25, ≈85% at 0.50), so it is stated transparently and surfaced in the UI
   ("N% of its own peak") rather than hidden behind a p-value. The 4-week window
   `W` is still reused, and the `max`-sum peak-window selection mirrors the prior
   `min`-sum floor construction (whole-life-inside-`W` and `W < n < 2W` prefix
   guards carry over).

### Consequences

- **Dormant becomes the honest majority.** Most narratives peaked and faded, so
  most classify `dormant` — the correct lifecycle picture. `stable` is reserved
  for narratives genuinely holding near their own peak. `growth` (23) is
  unaffected. `decay` stays rare by construction — "currently mid-decline over a
  4-week window" is a narrow transient state; a fully-faded narrative is `dormant`,
  not `decay`. This is expected, not a defect; if a future run shows *exactly* zero
  decay it is worth revisiting the trend-window length, tracked separately.
- **Matches ADR-052's stated "high plateau" intent** — this is a correction to
  make the code do what ADR-052 already claimed, not a new methodology.
- **Front-end copy.** The stage glossary (`web/src/pages/guide.astro`) and the
  per-narrative stage-detail row (`web/src/pages/narratives/[id].astro`, the
  "above own floor" line) are reworded from *floor*-relative to *peak*-relative and
  now show "N% of peak level". `stage_detail` keys change: `recent_elevated` →
  `recent_near_peak`, `level_p` → `recent_peak_ratio`, `baseline_level` →
  `peak_level`, and a new `dormant_peak_fraction` records the line used.
- **Left-censoring caveat (from ADR-052) is unchanged and slightly relaxed:** a
  narrative already high before 2010 that stays high now reads `stable` (recent not
  below its in-window peak), which is more correct than the prior `dormant` misread.
- **Scope.** Analysis-layer only. No re-embed, no re-cluster, no change to JEL,
  fitting, or anchor recovery. Amends `src/mnd/stages/classify.py` and the two
  front-end copy sites. Supersedes ADR-052 §2/§3's floor-relative `Level` clause;
  the rest of ADR-052 stands.

---

## ADR-059: Emerging flag is recency-only (drop the growth gate)

- **Status**: Accepted
- **Date**: 2026-07-02

### Context

ADR-052 defined "newly emerging" as an orthogonal recency flag layered on the
stage: a narrative was emerging iff `stage == "growth"` **and** its onset fell
within the 4-week recency window of the corpus frontier. The growth gate was
meant to keep a "just-arrived but already-flat" cluster off the emerging feed.

In practice the gate suppresses exactly the narratives the feed exists to surface.
A narrative that first appears in the trailing four weeks has, by construction, at
most four weeks of history — too short for the modified Mann–Kendall trend test to
reach significance in most cases, so it reads `stable`/`dormant` rather than
`growth` and is dropped from the emerging feed despite being the freshest thing in
the corpus. The recency signal (onset at the frontier) is the point; the trend
signal is redundant with it for a brand-new series and actively filters out true
new arrivals.

### Decision

The emerging flag is **recency-only**: a narrative is emerging iff its onset date
falls within `stages.newly_emerging_recency_weeks` (4) of the corpus frontier
(the latest last-active date across surfaced narratives), independent of its
lifecycle stage. Drop the `stage == "growth"` conjunct in
`build_artifacts.py`. Stage and emerging become fully orthogonal: a fresh
narrative can be emerging **and** any of growth/stable/dormant.

### Consequences

- **The emerging feed surfaces genuine new arrivals**, including those whose
  four-week history is too short to register a significant trend — the common case
  for a just-onset narrative.
- **No new parameter**; reuses the existing recency window. Frontier reference is
  unchanged (corpus frontier, not wall-clock), so a corpus built weeks ago still
  flags its own freshest narratives.
- **Orthogonality restored** as ADR-052 originally framed it ("a separate recency
  flag ... orthogonal to the four states") — the growth conjunct had quietly made
  it non-orthogonal.
- **Phase-6 relevance.** The live press-heating and institutional-onset signals
  (ADR-057) layer on top of this recency flag; keeping emerging stage-independent
  keeps those signals from inheriting the trend-significance filter.
- Amends ADR-052's emerging clause. Analysis/display-layer only; no re-embed, no
  re-cluster, no change to the four-state staging. Amends
  `src/mnd/dashboard/build_artifacts.py` and METHODOLOGY §8.

---

## ADR-060: Fit lenses on the central-mass window + SIR robustness overhaul

- **Status**: Accepted
- **Date**: 2026-07-02

### Context

The first clean run under ADR-052/058 fit logistic and Bass acceptably (69% / 79%
converged) but **SIR converged on 0 of 365 clusters** — every SIR fit hit the
sampler's exception path (empty `failure_reason`, no `R_0`, no AICc). Two causes,
uncovered by local reproduction:

1. **The γ→0 ridge.** The SIR priors were `HalfNormal`, which puts mass at γ→0.
   Since `R_0 = β/γ`, γ near zero sends `R_0` and the infected compartment to
   infinity, so the discrete Euler scan overflows to NaN and the fit throws.
2. **The 14-year scan.** Measuring fit-series lengths across the corpus was the
   surprise: **the median fit-series is 13.9 years (99% span > 3 years, 88% > 8).**
   A BERTopic topic almost always has a stray related article near 2010 and near
   2026, so its first-to-last active span covers most of the corpus. The real
   signal — an outbreak, if any — is a concentrated hump inside a long, near-empty
   series. So the SIR Euler scan runs ~855 weekly steps over mostly zeros; error
   compounds and the sampler either NaNs or grinds at maximum leapfrog depth for
   tens of minutes. (This is the same sparse-tail pathology that broke staging in
   ADR-058.)

Logistic and Bass are closed-form (a direct formula for any `t`), so series length
is irrelevant to them; only SIR's step-by-step ODE integration is length-sensitive.

An "only fit SIR on outbreak-shaped clusters" filter was considered and **rejected**
as a researcher-tuned distinction that would make SIR inconsistent with the other
two lenses (which are fit on every cluster, convergence-gated uniformly).

### Decision

Two changes; the first is uniform across all three lenses, the second is SIR-only
and confined to numerics.

1. **Fit window = the central `1 − α` of cumulative attention mass** (`dynamics
   .fit_window_mass_alpha = 0.05`), for **all three lenses**. Drop the sparse
   leading/trailing stragglers; keep the whole active lifecycle. Every wave that
   carries real attention lies inside the central band, so **multi-wave narratives
   keep all their humps** (a two-spike narrative fits both, and the single-wave
   models correctly fail the gate on it while shape-facts reports `wave_count = 2`).
   "Central 95%" is a standard convention and **reuses the project α = 0.05** (the
   trend-test threshold) — no new tuned parameter. Each fitted curve is reprojected
   onto the full daily grid (padded with nulls outside the window; peak-time shifted
   by the offset), so it aligns with the displayed volume. **Staging (ADR-058) and
   the displayed volume series stay on the full span** — only the fitted lens curves
   are windowed.

2. **SIR numerical robustness** (SIR-only; logistic/Bass are closed-form and need
   none of it):
   - **LogNormal β, γ priors** centered on the field-anchored config means
     (β 0.3, γ 0.1; Bjørnstad 2018), replacing `HalfNormal`. Strictly positive,
     no mass at γ→0. Mirrors the Bass lens, which already uses LogNormal rates.
   - **Adaptive integration grid**: `grid = max(sir_fit_grid_days, ⌈window /
     sir_max_grid_steps⌉)`, bounding the Euler scan at `sir_max_grid_steps = 200`
     steps regardless of window length. A numerical ODE-solver step-count bound,
     applied uniformly — **not** a data-dependent applicability filter.
   - **`max_treedepth = 8` fail-fast cap** on the SIR NUTS sampler. A cluster SIR
     cannot fit hits the cap and is marked non-converged in **seconds** instead of
     grinding at max leapfrog depth on every draw. This matters because LogNormal
     removed the NaN crash that used to make bad fits fail *fast*; the cap restores
     fast failure without the crash.
   - **Fuller budget** (draws 1000 / tune 1000 / chains 4 / target_accept 0.95),
     affordable now that the window + adaptive grid make each fit short, so
     fittable clusters clear the ESS > 400 bar (a sharp cluster reached R-hat 1.010
     / ESS 247 at *half* this budget).

3. **The convergence gate is unchanged and uniform** — R-hat < 1.05 **and** ESS >
   400 (Vehtari et al. 2021) for all three lenses. SIR now converges on genuinely
   outbreak-shaped narratives and fails the gate elsewhere, by the identical
   mechanism that makes logistic converge on logistic-shaped curves and fail on
   others. No eligibility threshold anywhere.

### Consequences

- **SIR becomes an honest, consistent lens.** It converges where the data supports
  a single outbreak and grays out ("sir (no fit)") elsewhere — exactly how logistic
  and Bass already behave on shapes they can't fit. The front end already handles
  per-lens non-convergence (`[id].astro`), so no UI change is needed.
- **The displayed lens curves span the active lifecycle**, not 14 years of flat
  line with a tiny bump — a display improvement for all three lenses.
- **No new tuned parameter that touches methodology.** The window α reuses the
  existing 0.05; the SIR grid/tree-depth are numerical ODE-solver + Monte-Carlo
  settings that cannot affect anchor recovery (a clustering metric), so ADR-040
  holds.
- **Fit cache invalidated.** `cfg["dynamics"]` changed (window α, SIR priors, grid,
  budget), so `run.py`'s `_fit_signature` re-fits all lenses on the next analyze.
- **Validation is on RCC, not local.** Local Mac PyMC sampling of the SIR scan
  hangs (20+ min/cluster: NUTS grind + per-chain scan recompilation +
  oversubscription); the fix's *direction* was validated on a sharp cluster
  locally (R-hat 1.010), and full convergence rates are read from the RCC re-fit.
- **α tail sensitivity, tracked.** α = 0.05 trims the outer 2.5% of mass each side,
  which clips the extreme rise/decay tips SIR uses for γ. If the RCC re-fit shows
  the decay tails over-clipped, α = 0.02 (central 98%) is the fallback. One-line
  config change, no code change.
- **Supersession.** Supersedes ADR-053 (fixed weekly grid + reduced SIR budget).
  Amends ADR-039 (the lenses are now windowed) and ADR-052/058 (staging unchanged,
  but the shared sparse-tail root cause is now noted). Amends `config/config.yaml`,
  `src/mnd/dynamics/fitting.py`, and METHODOLOGY §7.

---

## ADR-061: Three representative-article panels; central panel grounds naming

- **Status**: Accepted
- **Date**: 2026-07-02

### Context

The story card surfaced a single "representative articles" list (top-5 by c-TF-IDF
term overlap) for display, and the naming layer (ADR-056) grounded titles on
BERTopic's `Representative_Docs` excerpts. Neither conveys a narrative's *arc*, and
the two used different document sets.

### Decision

`build_story_card` surfaces **three de-duplicated panels**, `n_per_bucket = 3` each:

- **central** — most aligned with the narrative's own c-TF-IDF terms (term-overlap),
  then most substantial (text length), then newest. The narrative's core.
- **earliest** / **newest** — by publication day; how the narrative entered and
  where it stands now.

De-duplication is central-first: a document in the central panel is excluded from
earliest/newest, which backfill to the next candidate, so no article appears twice.

The **central panel grounds the naming layer** (ADR-056) — titles are generated
from the most-aligned, most-substantial pieces (extractive article text), replacing
the BERTopic rep-doc excerpts. **JEL scope is unchanged** — it keeps its ADR-055
representation (terms + BERTopic rep docs), so scope assignments are untouched and
this needs no re-embed.

The naming **output and backend** are refined at the same time (amending ADR-056):
the title is a short phrase with a soft length target (no hard word cap, never a
sentence) and the description grows from one sentence to **3–4 plain sentences**,
both at **temperature 0** (deterministic → the committed cache stays meaningful).
The prompt is rewritten for strict grounding and an explicit anti-slop rule (no
"This narrative…"/"Explores…" openers, vary sentence structure). Naming is now
**backend-selectable** (`display.naming.backend`): the paid `AnthropicNamer`
(Claude Haiku) **or** an open, key-free `LocalHFNamer` (Qwen2.5-7B-Instruct,
Apache-2.0, greedy decoding) — both exposed so the open vs paid choice can be A/B'd
(`scripts/naming_ab.py`) before the final bake. The committed cache means whichever
wins, replication stays free and key-free.

### Consequences

- The narrative page can tell the story (entry → core → present). `StoryCard` gains
  `earliest_articles` / `newest_articles` / `central_articles`;
  `representative_articles` aliases `central_articles` for back-compat.
- Naming and display now draw from the same central set — titles reflect what the
  reader sees. The naming-cache signature already keys on the excerpts, so the new
  grounding text invalidates stale titles automatically (ADR-056).
- Display/naming-layer only: no re-embed, no re-cluster, no change to JEL, fits, or
  staging. Ships in the cheap follow-up naming/rebuild pass, not the dynamics
  re-fit. Amends `story_card.py`; front-end + naming-input wiring follow.

---

## ADR-062: SIR lens via the Schlickeiser–Kröger closed-form solution (retire the ODE scan)

- **Status**: Accepted
- **Date**: 2026-07-03

> **Course-correction during design (2026-07-03, same day).** An earlier draft
> claimed the closed form "recovers R₀ to ~1%." That came from a **circular test**
> (fitting the KSSIR curve to KSSIR-generated data). Fitting it to a *numerically
> integrated* SIR shows R₀ is **not identifiable** from a single attention bump:
> free amplitude drives the profile likelihood monotonically to R₀→1; a fixed
> population flattens it above R₀≈2. This is intrinsic — recovering R₀ needs an
> independent removal rate γ / generation interval, which one curve's shape does
> not pin. **The current Euler-scan fit shares this**; its R₀ = β/γ is pinned by
> the LogNormal priors (mean ≈ 3), not measured. A follow-on audit found the same
> disease priors contaminate the **logistic** lens too (its R₀ = 1 + k/γ borrows
> the SIR γ). The resolution adopted below: **drop R₀ entirely** (and J∞, which is
> bijective with R₀ and needs the unobservable population N), **retire the disease
> priors**, and report only quantities identifiable from the observed curve in real
> units. The speed and curve-fidelity findings stand.

### Context

SIR is the entire compute pole of the analysis layer. ADR-060 tamed its
numerics (LogNormal β/γ priors, an adaptive grid capping the Euler scan at ≤200
steps, a `max_treedepth` fail-fast) but left the fundamental cost in place: the
SIR mean function is a `pytensor.scan` Euler integration of the ODE, re-run on
**every leapfrog step of every NUTS draw**. Measured on the live re-analysis
(job 51390331): **~23 min per cluster × 365 fit-eligible clusters ≈ 140 CPU-h**,
which overruns the 18 h caslake wall (≈13% done at timeout) and recurs on every
Phase-6 weekly re-fit. Logistic (Verhulst 1838) and Bass (1969) are closed-form
— a direct formula for any `t` — and cost seconds; the difference is entirely
SIR's step-by-step integration. There is no elementary closed form for the SIR
ODE, which is why it was integrated numerically.

Recent applied-mathematics work has closed that gap. Schlickeiser & Kröger
(*J. Phys. A* **53** 505601, 2020; *Appl. Math. Stat.* 2026, "near-exact
solution") derive an accurate analytic solution of the constant-reproduction-factor
SIR model. In their reduced time τ = γt with `k₀ = 1/R₀` and η the initial
infected fraction, the **prevalence** I(τ) — the quantity our `_fit_sir`
already fits to the smoothed daily counts — is *elementary on both branches*:

- rise (τ ≤ τ_U):  `I = η·exp(g(τ)−1)`                    (their eq 88)
- decay (τ ≥ τ_U): `I = (k₀/κ)·cosh⁻²(ζ(τ))`             (their eq 76)

where κ, ζ, Φ, U_max are elementary functions of the two scalars (k₀, η). The
curve is **asymmetric** (different rise/decay widths), so it stays visually
distinct from the logistic — unlike the symmetric Kermack–McKendrick 1927 `sech²`
approximation, whose shape collapses onto the logistic's own derivative.

A local de-risk prototype (no PyMC; `scipy` only) fit the closed form to a
numerically integrated SIR across R₀ ∈ {1.25 … 5}. Findings:

- **Speed: decisive.** A least-squares fit costs **1–3 ms/cluster** vs ~23 min for
  the Euler-scan NUTS fit — the 140 CPU-h pole disappears.
- **Curve fidelity: good for real epidemics.** For R₀ ≳ 2 the closed form tracks
  the numerical SIR prevalence at **1–4% nRMSE**; it degrades for weak epidemics
  (R₀ < 1.5), which the central-mass window + convergence gate already handle.
- **R₀: not identifiable** (see course-correction). The profile likelihood in R₀
  has no interior minimum — the shape is consistent with a wide R₀ range once
  timescale and amplitude absorb the difference. Scale-free shape statistics
  (skewness, rise/decay asymmetry) *are* monotonic in R₀ in the noiseless curve,
  but under realistic noise + 7-day smoothing only the rise/decay asymmetry
  survives, and then only **ordinally** (correct ranking, downward-biased, wide
  band) — not to a defensible point value.
- **J∞ is not an independent quantity.** `J∞ = 1 + k₀·W₀(α)` is a monotonic
  function of `k₀ = 1/R₀`, so it is exactly as unidentified as R₀; as a *fraction*
  it also needs the unobservable population N. Its only honest, observable form is
  the plain cumulative article count, already reported as Bass's `m`. Dropped.

### Decision

Replace the numerically integrated SIR prevalence with the Schlickeiser–Kröger
closed-form prevalence I(τ); **drop R₀ and J∞**; **retire the disease priors**
from both SIR and logistic; and report per lens only quantities identifiable from
the observed curve in real units. SIR stays a **display-only lens** (ADR-039/052),
fit under the **same convergence gate** as logistic/Bass and the no-tuning rule
(ADR-040). The three lenses are kept — two lenses is too thin, and SIR carries the
asymmetric-contagion view the other two do not.

1. **`_fit_sir` fits the analytic I(τ)** — elementary rise/decay branches above —
   instead of the `pytensor.scan` Euler loop. No ODE, no scan, no custom PyTensor
   Op; the log-likelihood is elementary, so NUTS runs at logistic/Bass cost. The
   fit is **reparametrized to identifiable quantities**: peak height, peak time,
   and the early-**rise rate** and late-**decay rate** (per day). The SIR shape
   ties rise and decay through one shape scalar, but both rates are read off the
   observed limbs in real time units — no β/γ, no N, no R₀.
2. **Retire the disease priors.** Delete `priors.sir.{beta_mean, beta_log_sd,
   gamma_mean, gamma_log_sd}` (Bjørnstad 2018 epidemiological values, R₀-prior ≈ 3)
   and the `N_pop = 2·Σy` population fudge. Priors on the new SIR parameters are
   **data-scaled and weakly informative** (peak height ≈ observed peak, peak time
   ≈ data centre, rates wide/data-scaled), following the logistic lens's existing
   `t0 ~ Normal(data mean, data sd)` pattern — no borrowed epidemiology.
3. **SIR reports:** rise rate (→ doubling time up), decay rate (→ half-life down),
   peak date, peak height, and the **asymmetry** = rise ÷ decay. All in observable
   units. `R₀`, `J∞`, `β`, `γ` are removed from the SIR `FitResult`.
4. **De-contaminate the logistic lens.** Delete the `r0 = 1 + k/γ` derivation
   (`fitting.py:263–266`), which borrowed the SIR disease γ. Logistic reports
   **doubling time = ln2/k**, **inflection date** `t0`, and **plateau level** `L`.
   Remove the dead `priors.logistic.k_mean` config key (the fit uses `HalfNormal`
   and never reads it).
5. **Bass is unchanged** — its `p, q` priors are field-anchored to the
   Sultan–Farley–Lehmann 1990 meta-analysis of 213 real diffusion studies (the same
   model on real data), and `m` (total reach) is data-anchored and observable. It
   reports total reach `m`, innovation `p`, imitation `q` (+ ratio), and peak date.
6. **Retire the scan-era numerics** — `dynamics.sir_fit_grid_days` and
   `sir_max_grid_steps` are removed; the `sir_inference` budget and `max_treedepth`
   fail-fast carry over but now bound a cheap elementary model. A monotone /
   non-epidemic-shaped curve (no interior peak) fails the convergence gate in
   seconds — the ADR-060 fail-fast, now the norm.

**Removing R₀ across the stack.** `FitResult.r0_*` fields and
`StageClassification.r0_*` become obsolete; staging already does not key off them
(ADR-052), so removing the R₀ display values touches only the artifact builder and
front-end wiring, not the model-free stage rule. `models.py` loses `sir_r0`,
`logistic_r0`, `sir_prevalence`/`sir_peak_time` (ODE helpers); gains the KSSIR
closed-form curve + rate helpers.

**Rejected alternatives.** (a) The symmetric Kermack–McKendrick 1927 `sech²` form
— indistinguishable from the logistic's derivative. (b) Keeping the Euler scan —
the pole. (c) Keeping R₀ as a prior-regularized readout, or (c′) fixing γ to a
news-generation-interval constant to make R₀ identifiable — both keep a
false-precision number resting on a handcrafted constant; rejected for the honesty
posture (numbers must stand on their own). (d) Reporting J∞ — bijective with the
unidentified R₀ and needs the unobservable N. (e) Cluster-level parallelism of the
fit loop — orthogonal infra (no ADR), pursued separately.

### Consequences

- **Compute.** The 140 CPU-h SIR pole collapses to the logistic/Bass scale
  (seconds/cluster); the whole `analyze` step fits comfortably inside one caslake
  job, and every Phase-6 weekly re-fit is cheap. The `.fit_cache` signature keys
  on `cfg["dynamics"]`, so this change invalidates all existing SIR `.pkl`s and
  forces a clean re-fit — expected and now affordable.
- **Honesty.** Every displayed dynamics number is now either a direct measurement
  off the observed curve (rise/decay rate, peak, plateau, total reach) or a
  field-anchored diffusion parameter (Bass p/q). No number rests on the
  unobservable population N or on borrowed epidemiological constants. This matches
  the project stance that analytics/graphs/numbers must stand on their own without
  an interpretive readout layer.
- **Fidelity.** SIR remains a display lens; its curve tracks the data at a few-%
  nRMSE for epidemic-shaped clusters, with no γ→0 ridge and no scan overflow. Peak
  time is the fitted curve's argmax (the eq-90 integral is not needed once the fit
  is anchored at a free peak-time parameter).
- **Validity domain.** The solution assumes a single epidemic-shaped hump with
  constant reproduction factor; multi-wave or monotone series are handled exactly
  as today — the central-mass window (ADR-060) isolates the main hump, and
  non-epidemic shapes fail the convergence gate rather than being force-fit.
- **Citations.** The lens is now backed by a named field-standard analytic result
  (Schlickeiser–Kröger) rather than a bespoke Euler discretization, which
  strengthens the "field-accepted citation behind each choice" posture.
- **Supersession.** Supersedes the SIR *numerical-integration mechanics* of
  ADR-053 and ADR-060 (weekly/adaptive grid, scan-step caps, disease β/γ priors);
  the fail-fast/uniform-convergence-gate philosophy of ADR-060 carries over.
  Amends ADR-039 (the SIR lens curve is now analytic and reports rates, not R₀) and
  the ADR-052 R₀-display clause (R₀ is dropped; staging was already model-free and
  is untouched). Bass, JEL scope, the displayed volume series, and staging are
  unchanged; logistic loses only its R₀ derivation.
- **Future (not in scope).** For the Bass lens's "external shock vs word-of-mouth"
  question, the modern field standard for news/attention is the Hawkes
  self-exciting point process (Crane & Sornette 2008, endogenous/exogenous
  classes), which uses the article timestamps directly. Noted as a candidate for
  a later ADR; Bass stays as-is for now.

---

## ADR-063: Portable weekly-update orchestration (`update` command)

- **Status**: Accepted
- **Date**: 2026-07-04

### Context

Phase 6 needs the corpus to refresh on a cadence, and the mission pivot (a public
educational tool, reproducible by others per the README) makes **portability** a
first-class requirement: someone should be able to check the data or fork a
spin-off without a UChicago RCC account. Two problems block that today.

1. **Orchestration is RCC-coupled.** The only runner is
   `scripts/rcc/submit_parallel_ingest.sh` — hardcoded `/scratch/midway3/ehgarver`
   paths, a SLURM fan-out (one `sbatch` per source), and `afterok` chaining. The
   `run_pipeline.py` CLI itself is portable, but the *orchestration* around it is
   not; there is no way to run "ingest the new week, then the rest" off RCC.
2. **Ingest has no delta mode.** `ingest` takes one global `--start/--end`. A
   weekly refresh with a single global start leaves per-source gaps (sources have
   staggered last-captured dates), and re-fetching 2010–present every week is
   absurd. Checkpoint dedup exists but nothing computes a per-source delta window.

Two pieces already support an efficient delta: incremental embedding reuses
vectors keyed on `(chunk_id, text_sha1)` and encodes only new/changed chunks
(ADR-050), and a weekly delta is *small* — a few hundred articles — so it needs
neither the parallel fan-out nor an A100.

Settled by the Phase-6 scoping discussion (2026-07-04): the default weekly path is
a **portable single-process command**, `merge_models` re-clustering is **deferred**
(ADR-057 §3, still needs its identity-stability validation), and the schedule is
**documented backend-agnostically, not auto-enabled**.

### Decision

1. **A single-process `run_pipeline.py update` command** runs the weekly delta
   sequentially, in one process, CPU-only: per-source over-fetch ingest → filter →
   incremental embed (ADR-050, only new chunks) → analyze (which now also refreshes
   the Media Cloud press layer, ADR-064). No SLURM, no GPU, no parallel fan-out. It
   runs unchanged on a laptop, a cron VM, GitHub Actions, or an RCC login/compute
   node. Because the embed step is incremental and the delta is small, the whole
   run is minutes on CPU.

2. **Per-source over-fetch delta.** For each source, `update` reads the corpus's
   own `max(published_at)` for that source and ingests from `(that − buffer_days)`
   to today, so every source advances from its *own* frontier (fixing the
   staggered-end-date gap) and the buffer overlap is absorbed by URL/content dedup
   — the only legitimate ingest filters (corpus-correctness invariant). `buffer_days`
   is a config value.

3. **Paths behind a config `data_root`.** All data locations derive from
   `paths.data_root` (env override `MND_DATA_ROOT`), defaulting to the repo's
   `data/`. The `/scratch/midway3/ehgarver` locations move from hardcoded strings
   into the RCC environment's `MND_DATA_ROOT`, so nothing in the Python or the
   `update` path names a cluster-specific directory. The RCC SLURM scripts become
   thin adapters that set `MND_DATA_ROOT` and call the same CLI.

4. **The parallel SLURM fan-out is the full-rebuild path only.**
   `submit_parallel_ingest.sh` stays for the `NUKE_RAW` historical rebuild (12
   sources, long poles, A100 embed). `update` never fans out.

5. **Institutional re-clustering is deferred (ADR-057 §3).** Until `merge_models`
   (its own ADR) lands with the anchor-id-stability check, `update` does **not**
   re-cluster: it keeps the corpus delta warm (ingested + embedded, ready to fold
   in) and refreshes the parts that need no re-cluster — the Media Cloud press layer
   and press-heating (ADR-064), recomputed against the existing narrative set. The
   institutional narrative set is captioned **"as of the last full build"** until
   the merge path is validated. This is the honest near-term state ADR-057 named.

6. **Scheduling documented, not auto-enabled.** The README gets a backend-agnostic
   "run it weekly" section with example `cron`, `systemd` timer, GitHub Actions, and
   RCC-`cron` snippets — all invoking the one `update` command. No scheduler is
   committed live; the operator turns it on.

### Consequences

- **Reproducibility.** A forker runs `pip install -e .` then
  `python scripts/run_pipeline.py update` (or a full build) with no RCC, no SLURM,
  no GPU — the README can honestly claim portability. Right-sizing is automatic:
  weekly deltas are CPU-minutes; only a full rebuild wants the GPU fan-out.
- **Efficiency.** Incremental embed + per-source delta means the weekly cost scales
  with *new* articles, not corpus size. No re-fetch, no re-embed of unchanged text.
- **Honesty.** Deferring `merge_models` is stated, not hidden: the narrative set is
  "as of last build" until validated, while press-heating gives the live signal.
- **Relates.** ADR-050 (incremental embed), ADR-016 (weekly cadence), ADR-057
  (Phase-6 design; this implements §3's portable-refresh half), ADR-064 (the press
  layer `update` refreshes). The `merge_models` identity-stable re-cluster remains a
  separate, gated ADR.

---

## ADR-064: Media Cloud Premium press layer + press-heating emerging signal

- **Status**: Accepted
- **Date**: 2026-07-04

### Context

ADR-016 defined the Layer-1B journalism-dynamics source as **Media Cloud Premium
Press** — daily story counts across a premium-press outlet collection (WSJ,
Bloomberg, FT, Reuters, NYT, Barron's, Dow Jones, MarketWatch, AP Business, …) via
the same Media Cloud API that serves the broad Layer-2 collection. ADR-057 §2 then
specified a **press-heating** emerging signal on top of it. Neither is wired yet:

- `src/mnd/detection/mediacloud.py` queries only the **broad US-National
  collection** (`34412234`); no premium collection is defined, and the per-narrative
  overlay in `analyze` uses the broad one.
- `detect_anomalies` (z-score over a baseline) exists but is **unwired** — nothing
  flags a tracked narrative spiking in the press, and the Emerging view carries only
  the within-corpus recency flag (`is_emerging`), which goes stale between builds.

Hard invariants (ADR-010/020/042/046/057): press *text* is never embedded or
clustered; the press layer is display/validation only and never feeds embedding,
clustering, or JEL scope; values are fixed a priori (ADR-040); press counts thin
before ~2017 (`RELIABLE_SINCE_YEAR`).

### Decision

1. **Add the premium-press collection alongside the broad one.** A
   `PREMIUM_PRESS_COLLECTION` id (config-overridable) joins `US_NATIONAL_COLLECTION`
   in the one Media Cloud module. The per-narrative overlay can be built for both
   scopes — broad for the Layer-2 attention-share baseline, premium for the
   Layer-1B "what the financial press is saying" volume — selected by config; the
   fetch/normalize/anomaly code is shared, only the collection id differs.

2. **Wire press-heating (ADR-057 §2) as a separate Emerging signal.** For each
   already-tracked narrative, at bake time, run the anomaly test on the **attention-
   share ratio** (`story_count / total_count`, robust to overall press-volume drift)
   over the trailing window: flag "heating in the press" when the most-recent
   **4-week** mean sits **≥ k·σ (k = 2)** above the narrative's own **52-week**
   baseline. It is surfaced **beside**, never merged with, the institutional
   recency flag, so the reader can tell "our sources just started on this" from "the
   press is spiking on a story we already track". Captioned literally: "press
   attention more than 2σ above its yearly baseline". Window/baseline/k are fixed
   config, not tuned to anchor recovery (ADR-040).

3. **Recompute at bake time, never in the substrate.** The signal is computed in
   `analyze` from the live Media Cloud series against the *existing* clusters — no
   re-embed, no re-cluster, no touch to embedding/clustering/scope (ADR-010/020/046
   intact), exactly like the ADR-042/048 overlays. This is what lets the weekly
   `update` (ADR-063) refresh the live feel without the deferred re-cluster.

4. **Degrade gracefully.** Absent `MEDIACLOUD_API_KEY`, the whole layer is omitted
   (as the existing overlay already does); pre-2017 narratives get no heating
   signal (below `RELIABLE_SINCE_YEAR`) and are captioned as such rather than shown
   a misleading flat line.

### Consequences

- **A live surface.** The Emerging view gains a press-led signal that refreshes
  every `update` without re-clustering — the near-term Phase-6 win ADR-057 named,
  and the reason the deferred `merge_models` is not blocking.
- **Honesty.** The two signals stay separate and literally captioned; the tool
  never implies the institutions are writing about something when only the press
  is (ADR-057 §4 scoped out press-only narratives entirely).
- **Invariants preserved.** Nothing here feeds embedding, clustering, or scope;
  press text is never embedded; k/window/baseline are fixed a priori.
- **Relates.** ADR-016 (Premium press definition), ADR-042/048 (press overlay +
  lead-lag), ADR-057 §2 (this implements it), ADR-063 (the `update` that refreshes
  it), ADR-040 (no-tuning).

---

## ADR-065: Incremental `analyze` re-bake — per-lens fit cache + JEL-encode cache

- **Status**: Accepted
- **Date**: 2026-07-04

### Context

Phase 6's whole point is that a re-run should cost only what actually changed
(ADR-050 did this for embedding; ADR-063 for ingest). The `analyze` re-bake broke
that promise in two places, both surfaced when the ADR-062 SIR-prior change forced
a full re-run:

1. **The fit cache is all-or-nothing.** `_fit_signature` hashes the *entire*
   `cfg["dynamics"]` dict, and the cache stores one pickle per *cluster* (all three
   lenses together). So changing one lens's prior (e.g. the SIR reparametrization)
   invalidates every cluster's cache and refits logistic and Bass too — byte-for-byte
   identical work, ~2/3 of the fit cost wasted.

2. **JEL re-encodes on every run.** `analyze` loads the 8B embedder (~1 min) and
   encodes all ~365 cluster representations (~tens of minutes on CPU) to assign JEL
   scope, *even when `clusters.parquet` is unchanged*. On a re-analyze — and on
   every weekly `update`, which re-bakes against the same clusters — that ~1 h is
   pure waste. JEL assignment is deterministic in (representation text, prototype
   descriptions, embedder), so it is cacheable exactly like the fits.

### Decision

Cache at the granularity of the thing that changes; both are content-addressed so
a genuine change still invalidates cleanly, and both are display-mechanics only
(identical results, no methodology change — ADR-040 intact).

1. **Per-lens fit cache.** `fit_cluster` caches each lens's `FitResult` separately
   under `fit_{cid}_{model}_{sig}.pkl`, where `sig` hashes the (windowed) series,
   the **global** fit config (smoothing, fit window, seed), and **only that lens's**
   priors + inference block (`priors.sir` + `sir_inference` for SIR; `priors.{model}`
   + `inference` for logistic/Bass). A one-lens config edit re-fits only that lens;
   the resume granularity becomes per-(cluster, lens), so a wall-clock timeout loses
   at most one lens of one cluster. Staging and shape-facts stay recomputed (cheap,
   model-free).

2. **JEL-encode cache.** Each cluster's `ClusterJELAssignment` is cached under a
   `sig` hashing its JEL representation text, the macro scope, the prototype
   descriptions, and the embedder model id + revision. On re-run, cached assignments
   load directly; the 8B embedder is built **only if at least one cluster misses**,
   and then encodes only the misses (plus the ~20 prototypes). An unchanged
   `clusters.parquet` ⇒ zero encodes, no model load — the ~1 h step becomes seconds.

### Consequences

- **Cheap re-runs, the Phase-6 promise kept.** A lens-only change re-fits one lens;
  a pure re-bake (unchanged clusters — the weekly `update` case) skips the JEL
  encode and the two unchanged lenses entirely. The immediate ADR-062 SIR re-run
  refits SIR only.
- **Correctness preserved.** Content-addressed keys mean any real change to inputs
  (corpus, config, embedder revision) still invalidates; a fixed seed keeps a cache
  hit identical to a refit. Unreadable/partial entries are discarded and recomputed,
  as before.
- **Cache location.** Both live under the dashboard `out_dir` (`.fit_cache`,
  `.jel_cache`), git-ignored, safe to delete to force a clean rebuild.
- **Relates.** ADR-050 (incremental embed — same content-addressed philosophy),
  ADR-063 (the weekly `update` this makes cheap), ADR-055/046 (JEL representation +
  display-flag semantics unchanged), ADR-062 (the change that exposed #1).

---

## ADR-066: Weekly incremental re-cluster via BERTopic `merge_models` (design + model-persistence prereq)

- **Status**: Proposed (prereq accepted + shipped; mechanism validated synthetically,
  pending real-corpus anchor-id validation + `update` wiring)
- **Date**: 2026-07-04

> **Validation note (2026-07-04).** `merge_models` was probed on BERTopic 0.16.4:
> with realistic (angularly-separated) topic embeddings it **preserves base topic
> ids**, appends genuinely-new topics, and `merged.transform` routes new-week docs
> to the kept id (continuing story) or the appended id (new story). An initial
> "scrambled assignment" observation was a degenerate-toy-data artifact (collinear
> blobs from the origin, on which cosine cannot separate topics), not a merge fault.
> `src/mnd/clustering/incremental.py` implements `merge_new_week` + the
> `anchors_keep_ids` gate; the synthetic anchor-id-stability test passes. Still
> gated on running the gate against the **real** anchors + wiring into `update`.

### Context

ADR-057 §3 chose BERTopic's `merge_models` as the weekly-refresh mechanism: fold
the new week into the existing narrative set so **every existing topic keeps its
id** (its narrative-page URL and ADR-056 name are stable *by construction*) and
only genuinely-new topics (similarity to every existing topic below τ) are
appended. ADR-063's `update` currently defers this — new institutional articles are
parked, the narrative set is "as of last build" — precisely because this piece is
unbuilt and needs validation.

A blocker surfaced on inspection: **the fitted BERTopic model is never persisted.**
The `cluster` stage runs `BertopicPipeline.fit_transform` and saves only
`clusters.parquet` (topic assignments) + `topic_info.parquet` + `embeddings.npy`;
the model object (`pipeline._model`) is discarded. `merge_models([base, new])`
operates on *model objects*, so without a saved base model there is nothing to
merge the new week into. Persisting the model is a hard prerequisite for the whole
weekly-refresh path, independent of the merge details.

### Decision

**Part A — model-persistence prereq (accepted, buildable now).** The `cluster`
stage persists the fitted BERTopic model with safetensors serialization to
`topic_model/` alongside `clusters.parquet`. The embedding model is referenced by
id (not re-serialized), matching how `embed` and JEL already pin it. A saved model
plus the existing `clusters.parquet` is enough to (a) merge a new week and (b)
reproduce assignments. This is a self-contained addition with no effect on current
outputs.

**Part B — weekly merge mechanism (proposed; pending validation).**

1. `update` (once merged in): per-source delta ingest → filter → incremental embed
   of only the new chunks (ADR-050) → **fit a BERTopic model on the new-week docs**
   → `merge_models([base_model, new_model], min_similarity=τ)` → persist the merged
   model + refreshed `clusters.parquet` → `analyze` (which now, via ADR-065, refits
   only new/changed clusters and re-encodes JEL only for them).
2. **τ (the similarity floor).** A new-week topic within τ of an existing topic is
   absorbed into it (existing id kept); below τ it is appended as a new id. Higher τ
   fragments continuing stories into new topics; lower τ over-absorbs distinct new
   stories. A starting value is proposed and **reported, not tuned to anchor
   recovery** (ADR-040); the validation below, not anchor performance, sizes it.
3. **Topic drift (split/merge).** A narrative that splits across a weekly boundary,
   or two that converge, is handled by `merge_models`' similarity step; the ADR
   documents the observed behavior on a back-test rather than a bespoke assignment
   layer.
4. **Anchor-id-stability gate (the credibility check ADR-057 required).** A test
   that runs a synthetic weekly merge and **fails loudly if any of the 10 anchor
   narratives changes topic id across the merge.** The weekly path does not ship
   until this passes: id stability is the whole point.
5. **Occasional full rebuild** stays the clean-slate path (the SLURM fan-out), with
   Hungarian centroid-matching to map fresh ids back to the prior set when a rebuild
   is warranted — never the weekly mechanism.

### Consequences

- **Unblocks true weekly narrative-set updates:** existing narratives extend with
  the week's articles, new ones appear, and ids/URLs/names persist — the tracking
  invariant ADR-057 named. Combined with ADR-065, the weekly re-bake refits only
  what changed.
- **Prereq is low-risk and immediately useful** (also lets anyone reload the model
  to inspect or reproduce clustering). Part B is gated on the anchor-id test.
- **Deferred until validated:** τ's final value, the split/merge back-test, and the
  cron cadence (ADR-057 said "manual → cron once identity stability is validated").
- **Relates.** ADR-057 §3 (the design this implements), ADR-050 (incremental embed),
  ADR-063 (the `update` this completes), ADR-065 (per-cluster refit/JEL reuse that
  makes the merged re-bake cheap), ADR-056 (names keyed on representation, stable
  across a merge), the anchor set (the id-stability gate).

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
