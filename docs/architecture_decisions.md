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

- **Status**: Proposed (drafted 2026-05-20; pending implementation)
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

- **Status**: Accepted
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
