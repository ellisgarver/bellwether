# Macro Narrative Dynamics — Claude Code Guide

## Project overview

Quantitative study of narrative lifecycle dynamics in U.S. macro-financial media
discourse. Methodology: embed articles → cluster with BERTopic → fit SIR/logistic
ODE to cluster volume time series → classify lifecycle stage.

**Canonical methodology reference:** `docs/METHODOLOGY.md` — plain-English
walkthrough of every pipeline stage and the field-accepted citation behind each
methodological choice. Read this first.

Supporting docs:
- `MND_PROJECT_SPEC.md` — full project specification (scope, source list, phases).
- `docs/architecture_decisions.md` — every methodological change is gated on an ADR here.

## Critical rules (do not violate without an ADR)

- Every threshold and hyperparameter lives in `config/config.yaml`. Never hardcode.
- Every random seed flows from `config.reproducibility.global_random_seed` (42).
- Do not hand-tune any parameter to improve anchor recovery.
- Do not load held-out (2020+) data into clustering or hyperparameter search before Phase 4.
- Do not add closed-source or paid-API dependencies to the core pipeline.
- ProQuest, Factiva, Bloomberg, AP News, Reuters, MarketWatch are NOT semantic corpus sources — do not reinstate without a new ADR. (AP News and Reuters were removed in ADR-010, 2026-05-11.)
- arXiv and Jackson Hole (separate ingestor) are NOT active sources — removed in ADR-012, 2026-05-13. arXiv had 2017-only coverage; Jackson Hole speeches are captured by FederalReserveIngestor.
- **IMF runs on RCC via curl_cffi + Coveo (ADR-014, 2026-05-17)** — imf.org is fronted by Akamai (not Cloudflare); the 403 ADR-013 attributed to an IP block was actually a TLS fingerprint (JA3) reject of stdlib `requests`. `IMFIngestor._imf_get` uses `curl_cffi.requests` with `impersonate='chrome131'` (verified 200 from RCC, T-Mobile cellular, and eduroam). Listing comes from the public Coveo Search endpoint (`imfproduction561s308u.org.coveo.com/rest/search/v2`); the old Sitecore JSS `_walk_publications` was replaced by series-keyed URL-prefix queries (`weo`, `gfsr`, `fandd`, `wp`, `blog`). `IMFIngestor()` is back in `InstitutionalIngestor._sub_ingestors`; no local-rsync needed. `curl_cffi==0.15.0` is in `requirements.txt` and must be installed in the RCC conda env (`mnd`).
- **After any dry-run, window change, or schema change, re-submit `submit_full_pipeline.sh` with `NUKE_RAW=1`.** Default archive mode does NOT touch `data/raw/` — including `.institutional_checkpoint.json`. A stale checkpoint from a smaller-window prior run will silently SKIP sub-ingestors marked "completed" in that prior context, producing an incomplete corpus. This bit us on 2026-05-17/18: job 49737806 was submitted with default args, loaded the May-13 2024-dry-run checkpoint, and skipped Fed/FedRegional/BIS/Treasury/OFR/VoxEU/Brookings/PIIE with 2024-only counts. Cancelled and re-submitted as job 49740251 with `NUKE_RAW=1`. The script ARCHIVES (not deletes) under archive mode, so prior data is recoverable.
- **CBO via Wayback bounded publication-ID enumeration (ADR-023, 2026-06-01).** Supersedes ADR-021's year-sharded CDX wildcard, which was broken: CDX `from`/`to` filter by crawl date (not publication date), so a window query matched ~10k re-crawled back-catalog URLs; the bulk-wildcard endpoint is non-deterministic under load (0/849/6575 rows across three runs in one hour) and 504s; a full run yielded 0 records in 77 min. `CBOIngestor` now mirrors `NBERIngestor`: a calibrated `_ID_DATE_ANCHORS` table estimates the `/publication/{id}` range for the window, then issues one CDX query per 100-id block (`matchType=prefix`, `collapse=urlkey` → earliest snapshot per URL), pre-filters by snapshot date, and fetches bodies via `web.archive.org/web/{ts}id_/{url}` (`id_` = raw archive, no toolbar). The strict page-date filter (ADR-022) is preserved — the snapshot ts is never used as the publication date. Canonical Article.url is still cbo.gov. Playwright/curl_cffi are NOT used by CBO (kept in `requirements.txt` only in case DataDome relaxes). **Runtime: ~15-22h for the full 2010-present CBO walk** — bump the institutional SLURM job to 72h, or split CBO into its own parallel job.
- **VoxEU via curl_cffi chrome131 (ADR-021, 2026-05-21).** cepr.org enabled Cloudflare bot mitigation 2026-05-19→20. `VoxEUIngestor._cepr_get` now uses the same ADR-014 IMF/Akamai pattern; year-sharded listing fetches and body fetches both routed through it.
- **Atlanta Fed via JSON listing API (ADR-021, 2026-05-21).** atlantafed.org's 2026 redesign retired `/sitemap.xml`, `/blogs/macroblog/rss`, and culled historical content (pre-2019 working papers, pre-2022 macroblog, pre-2016 Economy Matters). New strategy: hit `atlantafed.org/api/feed/getFilteredResults` per series (Working Papers, Policy Hub Papers, Policy Hub Macroblog, What-We-Study macro hub). Bodies still go through `_atlanta_get` (curl_cffi). Historical content removed by Atlanta Fed is not recoverable from atlantafed.org — Wayback would be a future fallback if needed.
- **Congressional Treasury via dual-path (ADR-021, 2026-05-21).** Treasury Drupal listing caps at ~130 pages of date-DESC pagination (~Nov 2023 onward visible from a fresh walk). Path A retained for recent + Drupal-archived legacy (slugs `jl/sm/mnu/tg` for Lew/Yellen/Mnuchin/Geithner); `_MAX_LISTING_PAGES` bumped 1200→2500 so a full descent surfaces 2010-vintage content. Path B added — GovInfo `CHRG` (Congressional Hearings) collection via `GOVINFO_API_KEY`, filtered to packages with "Secretary of the Treasury" in title. Both paths feed one `seen` set.
- **HTTP timeouts must be tuples, not single floats.** stdlib `requests` single-value timeouts only enforce inter-byte gaps as the read timeout; a server dripping bytes never trips a 30s timeout. The 2026-05-18 patch ingest hung 2+ hours on a single Fed speech URL in exactly that state. Both `_get` helpers (`fed.py`, `institutional.py`) now normalize float timeouts to `(connect=10, read=30)` tuples. Don't bypass this normalization in new ingestor code.
- **No pre-clustering topical filter (ADR-020, 2026-05-20).** ADR-020 removed the JEL keyword filter apparatus entirely. The basis-set source selection is now the only macro-scope constraint at ingest. Topic relevance is decided post-clustering by `src/mnd/clustering/jel_classifier.py` — each BERTopic cluster gets a primary JEL code from the AEA's published taxonomy via nearest-prototype matching in Qwen3 embedding space; non-macro clusters (primary JEL ∉ {E, F, G, H}) are excluded from dynamics analysis only, not from the embedded corpus. Do NOT reintroduce per-source title filters, `_MACRO_TERMS`, `_title_matches_canonical()`, `TopicFilter`, or any pre-clustering keyword gate. The JEL keyword config and filter-audit doc were removed in the ADR-024 cleanse (recoverable from git history); see ADR-020 for the rationale.
- **Corpus is the basis set, not a tier hierarchy (ADR-020).** Twelve active sub-ingestors map 1:1 to the eight independent dimensions of US macro discourse — see `docs/architecture_decisions.md` ADR-020 for the dimension table. CFR was dropped by ADR-020 (basis redundancy with PIIE on the international-policy dimension); `CFRIngestor` is retained in `institutional.py` unwired, do NOT re-add to `_sub_ingestors` without a new ADR. CEA added (ADR-020) via the govinfo.gov ERP collection — `GOVINFO_API_KEY` env var, free signup at https://api.govinfo.gov/signup/, DEMO_KEY fallback for integration tests only. NBER restored (ADR-020) via direct `/papers/wNNNNN` enumeration — paper detail pages are not bot-protected, citation_* meta tags give clean metadata. CBO uses Wayback bounded publication-ID enumeration (ADR-023, supersedes the ADR-017 Playwright path): cbo.gov direct is DataDome-blocked, and govinfo.gov was rejected because GPO-deposit coverage is uneven over time and would introduce a non-random time-varying filter into the CBO volume signal.
- Any deviation from the above requires a new ADR in `docs/architecture_decisions.md` first.

## Communication style

- For every file created or significantly modified, explain in chat what it does, why it exists, and how it connects to adjacent modules.
- Before every continuation step, summarize what was just completed and what the next step will do — never start a new step silently.
- Never say "shall I continue?" without that context attached.
- Never add Co-Authored-By lines to commit messages.

## Resuming a mid-pilot session

Phase 1 pilot is **complete** (NMI=1.000, soft landing recovered). Do not rerun or
modify pilot code. Resume instructions below are retained for reference only.

### Stage → checkpoint file mapping

| Stage | CLI command | Checkpoint file |
|---|---|---|
| ingest (wayback) | `run_pipeline.py ingest --sources wayback,fed --start … --end …` | `data/raw/articles/wayback_*.jsonl` |
| ingest (fed) | _(runs as part of wayback,fed above)_ | `data/raw/articles/fed_*.jsonl` |
| filter | `run_pipeline.py filter` | `data/processed/articles.parquet` |
| embed | `run_pipeline.py embed --role primary` | `data/processed/embeddings.npy` |
| cluster | `run_pipeline.py cluster` | `data/processed/clusters.parquet` |
| stability | `run_pipeline.py stability` | _(stdout only — re-run if unsure)_ |
| validate | `run_pipeline.py validate` _(all 10 anchors)_ or `validate --anchors anchor_01_svb,anchor_05_credit_suisse` _(comma-separated IDs)_. `--anchors` takes IDs, not a file path. | _(stdout only — re-run if unsure)_ |

## Phase status (update this when phases complete)

- [x] Phase 0 — scaffold, configs, anchor set, ingestors, embedding module
- [x] Phase 1 — filtering, dedup, clustering, dynamics, stages, validation, CLI
- [/] Phase 2 — first corpus built 2026-05-18 (21,289 articles, 63,600 chunks). Multiple coverage bugs since fixed across the ingestors. Awaiting the next FULL re-ingest (parallel fan-out, NUKE_PRIOR=1) with all fixes + the ADR-020 basis set baked in, then corpus-composition QA before ticking the box.
- [/] Phase 3 — first embedding + clustering 2026-05-18 (Qwen3 primary, BERTopic single-level, outlier 25.4%, stability NMI=0.880±0.003). Anchor recovery on that pre-fix corpus was 6/10 — the 4 misses were 2013-2020 events lost to corpus undercoverage in that era, which the re-ingest targets. Re-validation deferred until after the re-ingest.

- [ ] Phase 4 — pre-registration finalized, full anchor + fizzled validation
- [ ] Phase 5 — Streamlit dashboard, Hugging Face Spaces deploy
- [ ] Phase 6 — weekly cron update pipeline (basis-set re-ingest + Media Cloud Premium live, ADR-016)
- [ ] Phase 7 — technical report, reproducibility audit

The retrieval mechanics and coverage-bug history for each source live in their
ADRs (`docs/architecture_decisions.md`) and commit messages — not duplicated here.
Current ingestor behavior is whatever the code does now; the "Critical rules"
section above lists only the live, load-bearing constraints.

### Open work (priority order)

1. **One-time RCC setup:** install the mnd conda env from `requirements.txt` (pypdf + curl_cffi) and obtain a free GovInfo API key.
   ```bash
   conda activate mnd
   pip install -r requirements.txt          # includes pypdf==5.0.1 (ADR-020), curl_cffi==0.15.0 (ADR-014)
   # Sign up at https://api.govinfo.gov/signup/ and add GOVINFO_API_KEY=... to .env
   ```
   (CBO no longer needs Playwright — ADR-023 moved it to Wayback bounded-ID enumeration.)
2. **Per-source ingestion integration tests on RCC (25-case battery, ADR-020).** `pytest tests/integration/test_source_coverage.py -m integration -v` — validates each of the 12 active sub-ingestors against a narrow window. Now includes NBER 2014 + 2023h2 historical-edge cases, CEA ERP 2014 + 2023 cases, plus 2010-window historical-edge cases for Brookings / IMF / BIS and 2016 for Treasury OFR. Catches silent-zero failures before the full re-ingest. CEA cases skip gracefully if `pypdf` is missing.
3. **Full re-ingest via the parallel fan-out.** Submit `scripts/rcc/submit_parallel_ingest.sh` with `NUKE_PRIOR=1` (one SLURM job per source, per-source `--time` budgets, downstream filter→embed→cluster chained on afterok of every ingest job). This supersedes the single chained `submit_full_pipeline.sh`, where a long pole (CBO Wayback walk, NBER ID enumeration, Brookings ~44k articles) could starve the rest and risk the wall clock. Per-source runs don't touch the composite checkpoint, so a single source can fail and be re-run in isolation: `SOURCES="<src>" SKIP_DOWNSTREAM=1 SKIP_CLEANUP=1 bash scripts/rcc/submit_parallel_ingest.sh`.
4. **Post-re-ingest validation:** filter → embed → cluster → JEL post-classify → dynamics. Report anchor recovery rate; no pass/fail threshold (ADR-019). Run `mnd.clustering.jel_classifier.classify_clusters` on the BERTopic output and confirm sensible scope labels (≥40% in-scope for E/F/G/H given basis-set composition). If recovery looks reasonable, tick Phase 2 and Phase 3 boxes.
5. **Phase 4** — pre-registration finalize, citing METHODOLOGY.md and ADRs 015 / 016 / 017 / 018 / 019 / 020 as the methodology lock-in. Blocked by items 1-4.

## Environment

- Local compute: Apple Silicon MPS (MacBook Air M-series) — `embedding_device: auto` detects it
  - Set `MND_MAX_SEQ_LEN=512` in `.env` to avoid OOM on Qwen3-Embedding-0.6B (ADR-006)
- Full corpus runs: UChicago RCC (CUDA) — `MND_EMBEDDING_DEVICE=cuda` or set in `.env`; use SLURM scripts in `scripts/rcc/`
- FRED key: `FRED_API_KEY` in `.env` (validation only)
- GovInfo key: `GOVINFO_API_KEY` in `.env` (free signup at https://api.govinfo.gov/signup/; required by CEAIngestor via ADR-020 for ERP collection access; DEMO_KEY fallback is rate-limited to 30 req/hr and is for integration tests only — not the full ingest)
- WRDS: NOT REQUIRED. The prior RavenPack-via-WRDS plan was replaced by Media Cloud Premium (ADR-016, 2026-05-18). Any lingering `WRDS_*` mentions in older docs are obsolete.
- Media Cloud: `MEDIACLOUD_API_KEY` in `.env` for Layer 2 detection

## Phase 2 corpus architecture (updated 2026-05-20, ADR-020)

### Semantic corpus = basis set (ADR-020)

The corpus is a basis set, not a tier hierarchy: the minimum set of sources spanning every independent dimension of US macro discourse, with no redundancy.

| Dimension | Ingestor(s) | Retrieval |
|---|---|---|
| 1. US monetary authority | `FederalReserveIngestor` | Fed direct |
| 2. US monetary research | `FedRegionalIngestor` (NY, SF, Chicago, Atlanta) | Institutional RSS + sitemap |
| 3. International macro authority | `IMFIngestor` | Coveo + curl_cffi (ADR-014) |
| 4. International CB network | `BISIngestor` | Multi-section sitemap (ADR-017) |
| 5. US fiscal authority | `CBOIngestor` (legislative) + `CEAIngestor` (executive, NEW ADR-020) | Playwright+curl_cffi (CBO) / govinfo.gov ERP (CEA) |
| 6. US financial-stability research | `TreasuryOFRIngestor` | Direct fetch |
| 7. US policy think-tank | `BrookingsIngestor` + `PIIEIngestor` | WP REST + sitemap |
| 8. Academic primary work + column | `NBERIngestor` (RESTORED ADR-020) + `VoxEUIngestor` | Direct URL enum / CEPR full posts |
| Cross-cutting Q&A | `CongressionalIngestor` (Treasury Sec testimony) | Treasury press releases |

**Dropped by ADR-020:** CFR — basis-set redundancy with PIIE on dimension 7 (~80% of CFR output is foreign-policy non-macro). `CFRIngestor` class retained in `institutional.py` (unwired) for backwards-compat reads of pre-ADR-020 data.

**Removed from semantic corpus (ADR-010, 2026-05-11):** AP News, Reuters, MarketWatch. Their journalism propagation signal is captured by Media Cloud Premium Press (Layer 1B, cross-validation only). Raw ingested JSONL retained in `data/raw/articles/`; excluded from embedding by `run_pipeline.py filter-pre-embed`.

**No pre-clustering topic filter (ADR-020).** The basis-set source selection is the only macro-scope constraint at ingest. Topic relevance is decided post-clustering by `mnd.clustering.jel_classifier.classify_clusters` — each BERTopic cluster gets a primary JEL code from the AEA's published taxonomy via nearest-prototype matching in the same Qwen3 embedding space used for the clustering itself. Out-of-scope clusters (primary JEL ∉ {E, F, G, H}) are excluded from dynamics analysis only, NOT dropped from the embedded corpus. This is symmetric across sources and uses an externally-maintained taxonomy.

**Stated limitation:** Premium analytical press — WSJ opinion, Bloomberg Opinion, FT — is not represented in text form. Their VOLUME signal is captured by the Media Cloud Premium Press dynamics layer (single API surface, see below).

### Layer 1B — Dynamics layer (cross-validation signal, not the primary SIR fit target) — ADR-016 / ADR-019

**Source: Media Cloud API, premium-tier query.** Daily story counts by keyword/entity across the curated premium-press outlet collection (WSJ, Bloomberg, FT, Reuters, NYT, Barron's, Dow Jones Newswires, MarketWatch, etc.). Same Media Cloud API as Layer 2; the only difference is the outlet collection scoped to in the query.

- **Role (ADR-019):** Cross-validation signal — does the premium-press volume curve track the institutional volume curve? The SIR / logistic parameters are fit to the *institutional discourse volume* (the formation layer); Media Cloud premium and broad press volumes are reported alongside as independent traces. They are NOT averaged into the fit target. This separation lets us report propagation-into-journalism as an outcome, not bake it into the structural model.
- Output: weekly article volume time series per narrative cluster, written to `data/dynamics/mediacloud_premium/`.
- Use for: cross-validation, propagation-into-journalism analysis, dashboard overlay traces.
- Do NOT feed Media Cloud records into embedding or clustering — dynamics layer only.
- API key: `MEDIACLOUD_API_KEY` in `.env`.

**RavenPack is NOT used.** The prior plan (ADR-010, ADR-008) to source dynamics from RavenPack via WRDS was abandoned 2026-05-18 in favor of Media Cloud Premium because (a) Media Cloud is free and academically accessible without a WRDS subscription, (b) using one API surface for both Layer 1B and Layer 2 reduces architecture surface area, (c) Media Cloud has no monthly-vintage delivery lag. `src/mnd/ingestion/ravenpack.py` was deleted by ADR-019.

### Layer 2 — Detection (story counts only, broad outlets)

**Source: Media Cloud API, broad-tier query.** Same API as Layer 1B, queried against thousands of outlets across the wider Media Cloud collection. Fires candidate narrative emergence flags before institutional sources have characterized a topic in embeddable text. Output: `data/detection/mediacloud/`. Code: `src/mnd/detection/mediacloud.py`.

### Continuous update (Phase 6) — re-ingest, not RSS

New items detection uses periodic re-ingest of the ADR-020 basis set (all 12 sub-ingestors, NBER included). The same ingest jobs that power the historical run, scheduled weekly, with checkpoint-based dedup catching new publications since the prior run. Plus Media Cloud Premium Press for journalism volume (Layer 1B). Nothing outside the basis set is added in Phase 6 — no SSRN, no AP News RSS, no RavenPack live. The historical plan ("AP News RSS + RavenPack live") was abandoned in ADR-016.

### Anchor narratives (FINAL — 10 narratives)

| # | Name | Reference date |
|---|---|---|
| 01 | SVB collapse | 2023-03-09 |
| 02 | COVID market crash | 2020-02-24 |
| 03 | Brexit aftermath | 2016-06-24 |
| 04 | Transitory inflation debate | 2021-Q2 |
| 05 | Credit Suisse stress | 2023-03-15 |
| 06 | Regional banking contagion | 2023-03-13 |
| 07 | 2022 inflation peak narrative | 2022-Q2/Q3 |
| 08 | Soft landing emergence | 2023-Q3/Q4 |
| 09 | 2013 taper tantrum | 2013-05-22 |
| 10 | 2015 China devaluation scare | 2015-08-11 |

Removed from prior version: FTX collapse, GameStop short squeeze (out of macro scope).

### Locked architectural decisions

- **Source selection (ADR-020):** Basis set as tabled above. Twelve active ingestors mapping 1:1 to the eight dimensions of US macro discourse.
- **Pre-clustering filter (ADR-020):** None. Topical relevance is decided post-clustering via `mnd.clustering.jel_classifier`.
- **Timestamps:** Publication/release date throughout. FOMC minutes = release date.
- **Document chunking (ADR-019):** All documents chunked at **512 Qwen3 tokens** with ~64-token overlap (BEIR convention; Thakur et al. 2021). Chunker uses Qwen3's own SentencePiece tokenizer (not tiktoken cl100k). Count by document (not chunk) for dynamics. The prior 600-cl100k / 100-overlap / >2000-word rule is superseded.
- **Volume normalization:** Weekly counts per cluster / total corpus articles that week, before SIR/logistic fitting.
- **Smoothing:** 7-day centered moving average on weekly volume curves (natural weekly cycle for daily news count data; Shumway & Stoffer). Single combined series — source-stratified smoothing removed by ADR-019 as researcher-introduced complexity without literature anchor.
- **Economic calendar annotation:** Flag weeks within ±3 days of FOMC decisions, CPI, PCE, GDP advance, NFP, and Fed MPR releases. `calendar_event` (bool) and `calendar_event_label` (str) columns added to weekly series. Do not exclude flagged weeks from fitting — report count of flagged weeks in growth phase as a quality indicator. `src/mnd/dynamics/calendar.py`.
- **Dynamics fitting gate:** Parametric SIR/logistic models fit only when cluster has sustained volume (thresholds in config). Below threshold: descriptive stats only.
- **Stage classification:** Four stages keyed to R₀ direction: pre-emergence, growth (R₀>1), decay (R₀<1), dormant. Classical SIR threshold (Kermack & McKendrick 1927) — no arbitrary ±N-day windows or % thresholds.
- **Bayesian priors:** Weakly informative, anchored to Bjørnstad 2018 *Epidemics: Models and Data using R* and Gelman et al. *BDA3* conventions.

### Phase 5 dashboard design notes (locked)

**Dormant narrative display:** Dormant historical narratives must be displayed with their full fitted curves and parameters in the same visual format as active narratives. Do not gray out, visually diminish, or truncate dormant narratives. A clean SIR fit on a dormant narrative is more analytically valuable than an active narrative still in early-spread with poorly-identified R₀. Stage label (dormant / decay / peak / early-spread / pre-emergence) is displayed as an informational tag, not a quality or prominence signal.

**Calendar event markers:** Render vertical dotted lines at calendar-flagged weeks on volume curves, with event label on hover ("FOMC Meeting", "CPI Release", etc.). Users see the annotation rather than interpreting calendar-driven spikes as organic narrative growth.

**Media Cloud freshness labeling:** Layer 1B and Layer 2 panels both source Media Cloud (premium tier and broad tier respectively). Label data-as-of with the most recent ingest timestamp from `data/dynamics/mediacloud_premium/` / `data/detection/mediacloud/`. Media Cloud has near-realtime indexing — typically ≤24h lag — but the dashboard should still show the explicit timestamp.

**Raw vs. smoothed series:** Volume curve primary trace = smoothed_combined (stratified-smoothed). Background trace = raw_combined. Both always visible.

### Phase 2 pipeline (run on RCC, ADR-010)

```bash
# Full historical ingestion (2010-present) — parallel fan-out, one SLURM job
# per source, downstream filter→embed→cluster chained on afterok of all 12.
# Handles cleanup, per-source --time budgets, and the downstream chain itself.
NUKE_PRIOR=1 bash scripts/rcc/submit_parallel_ingest.sh

# Pre-embedding filter (excludes any archived journalism sources from raw JSONL)
# Already chained by submit_parallel_ingest.sh; shown here for a manual re-run.
python scripts/run_pipeline.py filter-pre-embed

# Corpus composition QA (run after filter)
python scripts/run_pipeline.py corpus-composition --by-tier --output data/processed/corpus_composition.csv

# Dynamics layer (Media Cloud Premium — separate from semantic corpus; ADR-016)
python scripts/run_pipeline.py ingest-dynamics --source mediacloud_premium --start 2010-01-01 --end auto
python scripts/run_pipeline.py smooth-dynamics        # source-stratified smoothing
python scripts/run_pipeline.py annotate-calendar      # ±3d economic calendar flags
python scripts/run_pipeline.py normalize-dynamics
```

## Key file locations

| What | Where |
|---|---|
| **Canonical methodology** | `docs/METHODOLOGY.md` |
| Master config | `config/config.yaml` |
| Outlet / source whitelist | `config/whitelist.yaml` |
| Topic filter keywords | `config/topic_filter_keywords.yaml` |
| Anchor narratives | `data/anchors/anchor_narratives.jsonl` |
| Topic seed articles | `data/anchors/topic_seed_articles.jsonl` |
| Architecture decisions | `docs/architecture_decisions.md` |
| Project specification | `MND_PROJECT_SPEC.md` |
| Pre-registration draft | `prereg/PREREGISTRATION.md` |
| Media Cloud module (premium dynamics + broad detection; not embedded) | `src/mnd/detection/mediacloud.py` |
| RCC SLURM scripts | `scripts/rcc/` |
| Integration test harness (per-source coverage) | `tests/integration/test_source_coverage.py` |
