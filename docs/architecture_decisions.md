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
