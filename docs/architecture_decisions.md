# Architecture Decisions

This document records significant architectural and methodological decisions in
ADR (Architecture Decision Record) format. Each entry has a status, a date,
a context, the decision, and the consequences. Once an ADR is `Accepted`, it
is **not edited**. If the decision is reversed, a new ADR is added that
references and supersedes the old one. Bodies were editorially condensed (2026-07-11); 
decisions, values, and statuses are unchanged.

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
| 057 | **Phase-6 live emerging (design) — two display-only signals: institutional onset (existing) + press heating (4wk vs 52wk baseline, k=2, on Media Cloud attention-share); weekly refresh builds onto the model via BERTopic `merge_models` (ids/URLs/names preserved, new topics appended above τ); manual now → cron later; novel press-only clustering scoped out (ADR-010)** | Live design; press-heating + weekly-refresh implementations each need a follow-up ADR (relates 010/016/020/042/046/048/050/056) |
| 058 | **Peak-relative plateau test — `stable` vs `dormant` keyed to the narrative's own high-water window, not its quiet floor; fixes the all-`stable` collapse (342/365) where institutional tails made "above the floor" trivially true. MWU on the zero-heavy daily series was under-powered, so the split is by level: recent-window mean below `dormant_peak_fraction`=0.25 of the peak-window mean → dormant (a definition, not tuned to recovery)** | Live (amends 052 §2/§3 Level test; relates 040) |
| 059 | **Emerging flag is recency-only — a narrative is emerging iff its onset falls within the 4-week recency window of the corpus frontier, regardless of stage; drops the earlier `stage == growth` gate so a just-arrived narrative whose short history hasn't yet registered a significant trend is still surfaced as newly arrived** | Live (amends 052 emerging clause; relates 016/057) |
| 060 | **Fit lenses on the central-mass window + SIR robustness overhaul — nearly every fit-series spans ~14yr from sparse straggler tails, which broke SIR (0/365, γ→0 `HalfNormal` ridge + 855-step Euler scan). Fix: fit all three lenses on the central 95% of cumulative attention mass (α=0.05, keeps multi-wave, no new param; staging/display stay full-span); SIR gets LogNormal β/γ priors, an adaptive grid bounding the scan ≤200 steps, and a `max_treedepth` fail-fast cap so unfittable clusters go non-converged in seconds instead of grinding. Same convergence gate for all three, no outbreak-eligibility filter.** | Live (supersedes 053; amends 039/052; relates 040/058) |
| 061 | **Three representative-article panels — the narrative's core (most term-aligned + substantial), earliest, and newest, de-duplicated, `n_per_bucket`=3 each; the central panel also grounds the ADR-056 naming layer (replacing the BERTopic rep-doc excerpts). JEL scope keeps its ADR-055 representation unchanged.** | Live (extends 055/056; display + naming layer) |
| 062 | **SIR lens via the Schlickeiser–Kröger closed-form solution — retire the `pytensor.scan` Euler ODE (the sole compute pole: ~23 min × 365 clusters ≈ 140 CPU-h) for the near-exact analytic prevalence I(τ), elementary on both branches (rise `η·e^{g−1}`, decay `(k₀/κ)·cosh⁻²ζ`); fit collapses to logistic/Bass cost (1–3 ms). De-risk surfaced R₀ is NOT identifiable from a single curve (true of the current Euler fit too, and it contaminated logistic's R₀=1+k/γ), so DROP R₀ + J∞, RETIRE the Bjørnstad disease β/γ priors + the `N_pop=2·Σy` fudge, and report only curve-identifiable numbers in real units: SIR → rise/decay rates + asymmetry + peak; logistic → doubling time + inflection + plateau; Bass unchanged (field-anchored p/q, total reach m). Display-only + convergence gate + no-tuning intact.** | Live (supersedes SIR numerics + disease priors of 053/060; amends 039/052; relates 040) |
| 063 | **Portable weekly-update orchestration — a single-process `run_pipeline.py update` runs the weekly delta (per-source over-fetch since each source's own `max(published_at)` − buffer → filter → incremental embed → analyze) sequentially, CPU-only, with all paths behind a config `data_root` (env `MND_DATA_ROOT`), so it runs on a laptop / cron VM / GitHub Actions / RCC with no SLURM and no GPU. The parallel SLURM fan-out stays as the full-rebuild path only. Identity-stable institutional re-clustering (`merge_models`) is DEFERRED (ADR-057 §3) — until it lands, `update` refreshes the corpus delta + the Media Cloud press layer (ADR-064) and the narrative set is captioned "as of last full build". Scheduler documented backend-agnostically, not auto-enabled.** | Live (implements 057 §3 partial; relates 016/050; portability for README) |
| 064 | **Media Cloud Premium press layer + press-heating emerging signal — add the premium-press outlet collection (ADR-016: WSJ/Bloomberg/FT/Reuters/…) alongside the broad US-National collection, both via the one Media Cloud module. Wire ADR-057 §2: per already-tracked narrative, `detect_anomalies` on the attention-share ratio over a 4-week window vs a 52-week baseline at k=2σ, surfaced as a SEPARATE "heating in the press" signal beside the institutional recency flag in the Emerging view. Recomputes at bake time from live press against the existing narrative set — no re-embed, no re-cluster, never feeds embedding/clustering/scope (ADR-010/020/046). Degrades to absent when unkeyed.** | Live (implements 057 §2; extends 016/042/048; relates 040) |
| 065 | **Incremental `analyze` re-bake — per-lens fit cache + JEL-encode cache. The fit cache keyed the whole `cfg["dynamics"]` and stored one pickle per cluster (all 3 lenses), so a one-lens prior change refit logistic+Bass identically; now each lens's `FitResult` is cached under a sig hashing only that lens's priors+inference (+series, window, seed). JEL re-encoded all ~365 reps with the 8B model every run even on unchanged clusters (~1h); now each `ClusterJELAssignment` is cached by representation+prototypes+embedder-id, the embedder loads only if a cluster misses, and an unchanged `clusters.parquet` ⇒ zero encodes. Display-mechanics only, results identical (ADR-040).** | Live (relates 050/055/062/063) |
| 066 | **Weekly incremental re-cluster via BERTopic `merge_models` (design + prereq). Prereq (accepted): the `cluster` stage now persists the fitted BERTopic model (safetensors → `topic_model/`) — it was discarded, and `merge_models` needs the model object, not just `clusters.parquet`. Mechanism (proposed, pending validation): `update` fits a new-week model and `merge_models([base,new], min_similarity=τ)` to keep existing topic ids/URLs/names and append only genuinely-new topics; gated on an anchor-id-stability test (a synthetic weekly merge must not renumber any of the 10 anchors). τ + split/merge back-test + cron cadence deferred until that passes.** | Proposed (implements 057 §3; relates 050/056/063/065) |
| 067 | **Simplify the analysis layer — least-squares lens fits, centroid JEL, open-model naming. (1) Retire Bayesian NUTS for all three lenses → bounded `scipy.least_squares` point fits (same displayed numbers + curve, ~1–3 ms vs ~30–60 s); MCMC convergence gate → fit-quality gate (R² ≥ `min_fit_r2`, fixed a priori); posterior CIs dropped; NUTS budgets retired (amends 039). (2) JEL uses existing cluster centroids instead of re-encoding terms+docs with Qwen3-8B (~1 h → seconds; amends 055). (3) Naming swaps Anthropic→an OpenAI-compatible open-model client (key-free/reproducible; amends 056). Analyze now finishes in minutes, fully locally testable; reader-facing output unchanged. Kept: all three lenses, shape facts, all similar measures, Granger lead-lag, markets, press-heating.** | Live (amends 039/055/056; keeps 052/062/065/040/046) |
| 068 | **Overlay efficiency — VIX fetched once over the corpus span and sliced per narrative; Media Cloud per-narrative series delta-cached (stable history reused, recent window re-fetched) and fetched in a bounded thread pool** | Live (relates 042/047/048/063/065) |
| 069 | **Anchor recovery scoped to anchor-relevant articles — window rows filtered by the anchor's fixed `key_terms` (registry, Phase 0), chunks folded to articles (majority topic), concentration = largest single non-noise cluster share with outliers kept in the denominator, threshold 0.50 unchanged. Replaces whole-window concentration, which is unsatisfiable on the full-breadth ADR-020 corpus (0/10 with the outlier bucket winning every plurality — a metric artifact)** | Live (amends 019 validation clause; relates 020/040) |
| 070 | **Name-cache signature excludes the date span — a continuing narrative's weekly-extending span no longer invalidates its title, so weekly merges (066 Part C) keep display names stable; titles regenerate only when terms/excerpts/sources change. One-time full re-name absorbed into the post-rebuild naming pass** | Live (amends 056; relates 066/067) |
| 071 | **Forming narratives — the directory bakes a `forming` flag (non-surfaced, onset within the ADR-059 window, ≥ `display.forming.min_articles`=3 articles, so single-document clusters stay out) with terms for terms-only naming; the emerging page lists them compactly and they graduate to full pages past the ADR-051 floor via the weekly merge** | Flag still baked; page surface superseded by ADR-074 |
| 072 | **NBER not-found detection — a 403 whose final URL is on `www2.nber.org` (reached via redirect off the canonical host) counts toward the consecutive-not-found stop; a direct 403 on `www.nber.org` still aborts loud (real bot-blocking shape). NBER retired 404s at the series head, so the old stop rule could never fire** | Live (amends the ADR-030 fail-loud rule for this one signature) |
| 073 | **Directory-wide display titles + naming on RCC — every non-surfaced directory entry bakes its c-TF-IDF terms and gets a terms-grounded title (one uniform rule, no new size cutoff); descriptions/fits/pages stay surfaced-only (051 is identifiability, not compute). Naming runs as an `mnd-name` job chained after analyze (user-space Ollama on scratch, GPU), patching artifacts in place; publish.sh pulls the cache and keeps local naming as cache-hit no-op / gap-filler** | Live (amends 067 execution default + 071 scope; display-only) |
| 074 | **Corpus heating replaces onset recency as the emerging page's lead signal — a narrative heats when its trailing-16-week mean weekly volume sits ≥ 2 standard errors (z scaled by √16; counts too sparse for the press's raw weekly σ) above its own trailing-52-week baseline with ≥ 3 recent articles; computed at site build for surfaced narratives, baked into the directory for sub-floor clusters (unlinked, tagged cards). The 059 flag and 071 forming section leave the page: clusters are long-lived narrative families, new events are absorbed rather than founding clusters, so onset recency is structurally empty on surfaced narratives** | Live (supersedes 071 page surface; 059 flag still baked; display-only) |
| 075 | **Staleness override on the stage — a narrative whose last activity trails the corpus frontier by more than `stages.stale_dormant_weeks`=16 reads `dormant` regardless of its trend shape. The Mann-Kendall window is the tail of each narrative's OWN series, so without the override a narrative that stopped mid-rise reads `growth` forever (e.g. a cluster last active 2013); the site presents stage as "where it sits now", so the calendar must gate it. Decay stays in the taxonomy for genuine sharp mid-collapse; dormant is where post-decline narratives land** | Live (amends 058/059 stage; display-only; ADR-040 discipline intact) |
| 076 | **Full-corpus composition on the data page — the bake ships `corpus_composition` (article counts by source and by JEL code over EVERY non-noise cluster, not just the surfaced narratives) in index.json; the "what is in the corpus" charts read it, falling back to surfaced story-card aggregation when absent. Full-corpus JEL is cheap (nearest-prototype cosine over cluster centroids, ADR-067 — no re-encode), so all clusters are classified, not just the fit set** | Live (data-page display; front end falls back pre-bake) |
| 077 | **Remove anchor-recovery validation — the ten-anchor recovery diagnostic (amends 019/069) is deleted outright: the `mnd.validation` module, the `validate` CLI command, the `data/anchors/` fixtures, and the config keys. It was a standalone, never-run diagnostic that no rendered output depended on, and reporting it overstated the pipeline's guarantees. Credibility rests on the anchored-parameter discipline (no tuning toward any target), not on recovery scores; the "anchors validate only" methodology principle retires with it. The bootstrap-NMI stability diagnostic stays under a renamed `diagnostics` config block** | Live (removes 019 validation apparatus + 069 anchors) |

---

## ADR-001: Two-model embedding strategy (primary + comparator)

- **Status**: Accepted
- **Date**: 2026-04-30

### Context

The original project plan (§7.2) specified `all-mpnet-base-v2` (cutoff
~2020–2021) as the sole embedding model, to mitigate look-ahead bias on
historical articles. Model quality has since advanced: top self-hostable
options in April 2026 include the Qwen3-Embedding family (0.6B / 4B / 8B),
Voyage / Cohere / OpenAI proprietary, and several BAAI and Alibaba models,
with multi-point MTEB gains over mpnet-base. The look-ahead concern is
bounded: it can be **measured** by comparing cluster quality and stability
on pre-2021 vs post-2021 sub-periods.

### Decision

Adopt a **two-model strategy**:

1. **Primary**: `Qwen/Qwen3-Embedding-0.6B` (Apache 2.0, consumer GPU,
   top-tier MTEB), for all production work.
2. **Comparator**: `sentence-transformers/all-mpnet-base-v2`, used ONLY for
   the look-ahead sensitivity check on early anchor narratives.

If the comparator materially diverges from primary on pre-2021 data,
look-ahead bias is significant and we caveat; if they agree, it is bounded.

### Consequences

Stronger primary clustering, and the look-ahead argument becomes a formal
contaminated-but-strong vs clean-but-weaker comparison rather than an
implicit claim. Qwen3's 2025 training cutoff means look-ahead exposure is
HIGHER than mpnet on 2010–2024 articles — precisely what the comparator
measures. Qwen3 0.6B is ~600MB to download; instruction-aware prompting
needs a small prefix (handled in the `Embedder` class). Upgrade path:
Qwen3-Embedding-4B if RCC capacity allows, by editing
`embedding.primary.model` in `config.yaml` and documenting the change as
ADR-N.

---

## ADR-002: Logistic growth as MVP fallback in lieu of SIR

- **Status**: Accepted
- **Date**: 2026-04-30

### Context

The plan specifies multi-model dynamics fitting (SIR, logistic, Gompertz,
exponential). SIR is the project's intellectual centerpiece but has 3–4
parameters on noisy data; kill criterion 3 triggers a fallback to logistic
if posterior CIs are too wide or fits poor.

### Decision

Implement **logistic-first, SIR-second**: logistic (the most stable
two-parameter model, with $R_0$-equivalent characterizations via carrying
capacity $L$ and growth rate $k$) is the MVP path; SIR / Gompertz /
exponential are implemented in parallel but tagged "compress-able". Stage
classification consumes the best-fit model per cluster (AICc, logistic
preferred at ties).

### Consequences

If SIR fits poorly, the project still produces a credible artifact; the
"epidemiological dynamics" framing holds because logistic is the
deterministic limit of SIR under standard assumptions.

---

## ADR-003: Streamlit for dashboard (vs. Gradio / FastAPI)

- **Status**: Accepted
- **Date**: 2026-04-30

### Context

Dashboard options: Streamlit, Gradio, full FastAPI + React. Hosting target:
Hugging Face Spaces or Vercel free tier.

### Decision

Streamlit for MVP: tightest path from cluster artifacts to charts,
first-class HF Spaces support, built-in caching, and a single-developer
codebase (React would more than double frontend work). Richer interactivity
(2D narrative-map zoom-and-click) becomes a Phase 6 stretch goal via Gradio
or a custom frontend.

### Consequences

Streamlit rerenders the whole page on interaction, which can be slow with
large datasets. Mitigation: pre-compute artifacts heavily; the dashboard
reads cached JSON, never recomputes.

---

## ADR-004: GDELT as discovery layer only, not text source

- **Status**: Accepted
- **Date**: 2026-04-30

### Context

GDELT 2.0 is the primary candidate for free article discovery, but has
documented quality issues (~55% accuracy on key fields, ~20% redundancy,
Western/U.S. media overrepresentation) and provides URL + headline + source
domain, not full text.

### Decision

Use GDELT **only** to discover URLs from whitelisted outlets. Full text is
fetched downstream: free outlets via HTTP + Trafilatura; paywalled outlets
via library database (Factiva or ProQuest). False-positive URLs are
filtered when full-text retrieval fails or the content fails the topic
filter.

### Consequences

Paywalled-outlet text is gated on UChicago library access; discovery itself
is free. If library access fails, fall back to free outlets (CNBC,
MarketWatch, FT Alphaville, etc.) plus institutional sources, with the
reduced analytical-source layer acknowledged.

---

## ADR-005: Wayback Machine CDX replaces GDELT as historical discovery layer

- **Status**: Accepted
- **Date**: 2026-04-30

### Context

ADR-004 designated GDELT 2.0 as the discovery layer. During Phase 1
piloting, GDELT's free API applied IP-level throttling: 18 of 26 weekly
batches over the 6-month pilot window (September 2023 – February 2024)
failed with "Please limit requests to one every 5 seconds", and raising the
inter-request delay from 1 s to 6 s had no effect — the limit is an
IP-level quota, not per-request timing. Result: 0 GDELT-discovered
articles. GDELT's full-text endpoint (`api.gdeltproject.org/api/v2/doc`)
has separate limits but is untested for bulk historical queries from a
single academic IP.

The Wayback Machine CDX API: no authentication, no hard documented rate
limit, coverage of major outlets back to mid-2000s, one CDX call per domain
(so requests scale with ~20 outlets, not ~26–182 weeks), and an `if_`
endpoint modifier that returns raw archived HTML without the Wayback
toolbar, which trafilatura extracts cleanly.

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

GDELT (`src/mnd/ingestion/gdelt.py`) is **retained** for near-real-time
discovery (last 7 days, low request volume) and potential future
integration with GDELT's GFT (full-text) endpoint.

### Consequences

Bulk historical ingestion is reliable across the full ~20-outlet whitelist,
with no new keys or paid dependencies. Risks: Wayback is retrospective —
content < 24–48 h old may not be archived (fine for the pilot; Phase 6
weekly live updates should use GDELT for recent discovery); the `if_`
endpoint is stable but not formally part of the CDX contract — monitor for
breakage; page fetches are slow (~1.5 s/page), so a 150-article-per-domain
cap bounds runtime.

---

## ADR-006: Reduce `max_seq_len` from 32768 to 512 for local MPS runs

- **Status**: Accepted
- **Date**: 2026-04-30

### Context

`Qwen/Qwen3-Embedding-0.6B` (ADR-001) supports 32768-token sequences, and
`sentence-transformers` pads each batch to `max_seq_length`. On Apple
Silicon (MPS) the SDPA kernel materialises the full causal mask
`[batch_size × num_heads × seq_len × seq_len]`: at the default 32768 with
`embedding_batch_size = 32` that is ≈29 GB per batch; 2048 tokens still
needs 8 GB; 512 tokens is ≈536 MB, which fits alongside model weights
(~2.4 GB fp32 / ~1.2 GB fp16). `prepare_text_for_embedding` already caps
body text to 600 whitespace-words (≈780 BPE tokens at 1.3 tokens/word), so
truncating at 512 loses only the final ≈270 tokens of longer articles;
headline and lead paragraph are preserved. A second fix: `embedder.py`
never called `model.max_seq_length = self.max_seq_len` after loading, so
the config value was ignored — corrected in the same commit.

### Decision

Set `embedding.primary.max_seq_len: 512` in `config.yaml` for Phase 1 local
runs (Apple Silicon); restore to `32768` before Phase 2 full-corpus
embedding on UChicago RCC (CUDA). A comment in `config.yaml` flags the
restore point. Separately, always run with `USE_TF=0` (in `.env` or shell)
to stop `sentence-transformers` loading TensorFlow's ≈691 MB dylibs on
import, which stalled local runs 15+ minutes; added to `.env.example`.

### Consequences

The pilot runs on a MacBook Air without OOM; only long-article tails are
truncated. Risks: articles beyond ≈400 body words are silently truncated —
acceptable for the 148-article pilot but not for full-corpus Fed minutes
and papers (**must restore to 32768 before Phase 2**); `USE_TF=0` is
environment-level and unenforced — the `.env.example` comment is the only
guard.

---

## ADR-007: ProQuest ingestion via TDM Studio export script, not REST API

- **Status**: Accepted
- **Date**: 2026-05-01

### Context

The original `proquest.py` (ADR-004) assumed TDM Studio exposes a REST API
callable with a bearer token (`PROQUEST_API_TOKEN`). In practice TDM Studio
is a self-contained Jupyter environment behind institutional SSO with the
`proquest_tdm` client pre-installed; there is no external REST API. The
correct pattern: (1) manual dataset creation in the TDM Studio web UI
(stable UUID dataset ID); (2) an export script inside the TDM Jupyter
kernel writing JSONL matching our `Article` schema; (3) local pipeline
ingestion of the downloaded JSONL via `PaywalledSourceIngestor`.

### Decision

Rewrite `src/mnd/ingestion/proquest.py` as a **dual-role file**: run as
`__main__` inside TDM Studio it exports the dataset identified by
`PROQUEST_DATASET_ID`; imported by the pipeline,
`PaywalledSourceIngestor` reads
`data/raw/articles/proquest_{PROQUEST_DATASET_ID}.jsonl`. Replace
`PROQUEST_API_TOKEN` (and `PROQUEST_ACCOUNT_ID`, `PROQUEST_PROJECT_ID`) in
`.env.example` with `PROQUEST_DATASET_ID`. Add `docs/proquest_tdm_setup.md`
documenting the manual export-then-download workflow.

### Consequences

The path matches how TDM Studio actually works, stores no local credentials
(SSO), and the exported JSONL is a stable re-ingestable artifact. The
export must be re-run manually whenever the date range or query changes;
the `proquest_tdm` API should be spot-checked in-platform (`_FIELD_MAP`
handles common variants); `ingest --sources paywalled` without the file
raises a `FileNotFoundError` pointing to the setup docs.

---

## ADR-008: Phase 2 corpus overhaul — open institutional + AP News + RavenPack dynamics

- **Status**: Accepted
- **Date**: 2026-05-04
- **Supersedes**: ADR-005 (Wayback as discovery layer), ADR-007 (ProQuest TDM pipeline), prior Phase 2 corpus spec (tight corpus, finalized 2026-05-01)

### Context

The "tight corpus" architecture finalized 2026-05-01 relied on ProQuest TDM
Studio for Tier 1 financial press (WSJ, NYT, Economist) plus Wayback CDX
for wires. Compounding problems: (1) the ProQuest per-export workflow is
not automatable for Phase 6 live updates and license terms forbid bulk
download outside Studio; (2) ProQuest GN coverage is uneven over
2010–present (Barron's and MarketWatch already dropped 2026-05-01), and
cross-year volume comparisons carry index-change risk; (3) financial
journalism is downstream of institutional discourse — the narrative-lifecycle
hypothesis applies most cleanly to formation among policymakers,
researchers, and analysts; (4) RavenPack RPA 1.0 Global Macro Dow Jones
Edition (WSJ, Barron's, DJN, MarketWatch, PR Newswire, ~800 others, via
WRDS) is a cleaner dynamics layer than counting Wayback articles; (5)
anchor-set scope creep — FTX and GameStop are not macro-financial
narratives and risked reward-hacking the anchor recovery metric, while the
2013 taper tantrum and 2015 China devaluation are canonical macro events
with clean timestamps.

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

The pipeline is fully automatable with uniform 2010–present coverage, a
cleaner causal proxy, a higher-quality dynamics layer, and a tighter anchor
set. Risks: the semantic corpus skews toward formal institutional/academic
register — a disclosed design choice, with AP News (Tier 4) and RavenPack
covering the popular-press signal; AP Wayback coverage before ~2016 may be
sparse (flag in pre-registration if pre-2016 AP coverage < 50% of later
years); WRDS access requires institutional credentials — document the query
precisely so others can replicate.

---

## ADR-009: Journalism corpus scope — MarketWatch reinstatement and stated limitations

- **Status**: Accepted
- **Date**: 2026-05-04

### Context

ADR-008 made AP News the sole Tier 4 (journalism) source. AP is
wire-factual and does not produce the interpretive framing pieces where
narrative construction happens in financial journalism — the signal our
clustering needs. The design also left the absence of premium analytical
press (WSJ opinion, Bloomberg Opinion, FT) unstated; better to record it
explicitly as a scope constraint.

### Decision

**1. MarketWatch reinstated as Tier 4 journalism source.** It fills the
interpretive gap: 15–20 analytical macro pieces/day, fully open access, a
Dow Jones property also covered by the RavenPack layer
(rpa_source_id = 'MKW', enabling text-vs-volume cross-validation), with
historical coverage via Wayback CDX on `www.marketwatch.com/story/`.
Pre-2015 CDX coverage is thinner: ingest what exists, flag records with
`sparse_wayback_coverage=True` in raw_metadata, and treat the corpus as
consistent from 2015-01-01 onward for cross-year comparisons; the asymmetry
is documented in methodology and pre-registration.

**2. Stated limitation for premium analytical press.** WSJ opinion,
Bloomberg Opinion, and FT are excluded: WSJ requires ProQuest (removed in
ADR-008), Bloomberg is paywalled, FT's Factiva license prohibits pipeline
use. Their volume signal is partially captured by RavenPack (Dow Jones
edition: WSJ, DJN, Barron's, MarketWatch). Disclosed in the
pre-registration (Appendix A), the methodology section, and a dashboard
tooltip.

**3. RavenPack lag and vintage documented.** RPA 1.0 has ~5-week lag,
delivered as monthly vintages — a look-ahead protection feature. Panels
using it are labeled "as of [last delivered month]"; emergence detection
uses real-time own-corpus (Tier 4) counts.

### Consequences

Tier 4 now covers both event-factual (AP) and interpretive-analytical
(MarketWatch) registers, the premium-press gap is a documented limitation,
and MarketWatch's dual presence enables a cross-validation check. Risks:
the pre-2015 coverage asymmetry is a nuisance covariate (flag in QA;
restrict cross-year comparisons of MarketWatch-heavy clusters to 2015+);
two Tier 4 sources add volume, mitigated by a shared Wayback CDX + RSS
architecture (`src/mnd/ingestion/apnews.py`, class `MarketWatchIngestor`).

---

## ADR-010: Full project spec overhaul — corpus architecture, embedding model, detection layer

- **Status**: Accepted
- **Date**: 2026-05-11
- **Supersedes**: ADR-001 (two-model embedding), ADR-008 (Phase 2 corpus with AP News), ADR-009 (MarketWatch reinstatement)

### Context

MND_PROJECT_SPEC.md (rev2, 2026-05-11), written after Phase 2 ingestion
completed on RCC, consolidates decisions from Phase 1 piloting and early
Phase 2 planning. Key findings driving it: wire journalism (AP News added
in ADR-008, MarketWatch in ADR-009, Reuters added 2026-05-07) adds noise to
semantic clustering — narrative *identity* is determined in institutional
and academic discourse, and RavenPack carries the journalism propagation
signal more cleanly; Qwen3's modern cutoff raised look-ahead exposure; and
NBER/SSRN historical bulk retrieval failed (bot-protected,
JavaScript-rendered).

### Decision

**1. Journalism tier (Tier 4) removed from semantic corpus.** AP News, MarketWatch, and Reuters ingestors move to `scripts/archive/`. Raw data stays on RCC (`data/raw/articles/`) but is excluded from embedding by `scripts/filter_corpus_pre_embed.py`. RavenPack provides the journalism volume signal as Layer 1B (dynamics fitting only).

**2. Embedding model: `all-mpnet-base-v2` is the single production model**, superseding the ADR-001 two-model strategy; its pre-2021 cutoff matches the historical window. The look-ahead check becomes a pre-2021 vs post-2021 sub-period NMI comparison within this single model. The `comparator` config slot is removed.

**3. CFR added as Tier 2 source.** RSS: `cfr.org/rss/all`; `CFRIngestor` added to `institutional.py` and the composite. Its macro-financial coverage (dollar dynamics, sovereign debt, global monetary policy) supersedes the prior "geopolitical framing dominates" exclusion.

**4. Media Cloud detection layer added.** `src/mnd/detection/mediacloud.py` provides daily story-count queries by keyword/topic across thousands of outlets, to detect anomalous volume before institutional sources characterize it. API key: `MEDIACLOUD_API_KEY` in `.env`; output to `data/detection/mediacloud/`. Does not feed embedding or clustering.

**5. Validation: EPU replaces JLN.** The Baker-Bloom-Davis Economic Policy Uncertainty index (free from `policyuncertainty.com`) replaces the Jurado-Ludvigson-Ng index via WRDS; `WRDS_MFS_*` env vars removed. EPU is text-based, matching our discourse methodology, so it is the stronger benchmark.

**6. NBER and SSRN excluded from historical corpus ingestion.** Both ingestors remain in `institutional.py` for Phase 6 live RSS updates; the institutional SLURM job (`ingest_institutional_rcc.sh`) excludes them.

**7. FEDS Notes added explicitly to FederalReserveIngestor.** URL pattern: `federalreserve.gov/econres/notes/feds-notes/` (~70/yr), previously not distinguished from FEDS Working Papers.

### Consequences

The semantic corpus is purely institutional/academic register, with one
embedding model and a new pre-characterization detection layer. Risks:
existing Phase 2 output (AP News, Reuters, MarketWatch JSONL) must be
filtered pre-embed (`scripts/filter_corpus_pre_embed.py`);
`all-mpnet-base-v2` is weaker than Qwen3 on MTEB — accepted for the cleaner
look-ahead argument; CFR RSS history back to 2010 may be incomplete (QA
flags pre-2015 coverage); `umich_inflation_exp` stays in `whitelist.yaml`
validation supplements but is flagged for future removal.

---

## ADR-011: Revert primary embedding model to Qwen3-Embedding-0.6B; formalize look-ahead check

- **Status**: Accepted
- **Date**: 2026-05-11
- **Supersedes**: ADR-010 (embedding section only — all other ADR-010 decisions stand)
- **Restores**: ADR-001 (two-model strategy), with enhanced look-ahead check methodology

### Context

ADR-010 replaced Qwen3-Embedding-0.6B with `all-mpnet-base-v2` to minimize
look-ahead bias. Two problems:

**1. Context window mismatch.** With the journalism tier removed, the
corpus is almost entirely long-form: FOMC minutes 10,000–15,000 words, BIS
Quarterly Review articles 3,000–8,000, Jackson Hole papers 8,000–15,000,
VoxEU posts 800–2,500, NBER abstracts (Phase 6) 300–500.
`all-mpnet-base-v2` has a hard max_seq_len of 384 tokens (~280–300 words),
so a 12,000-word FOMC minutes document is embedded from its first ~2% —
systematically missing the staff outlook, participants' views, and forward
guidance. Acceptable for short wire articles (now removed), not for the
long-form institutional core.

**2. Look-ahead risk is measurable, not assumed.** For pre-2015 events
(2013 taper tantrum, 2015 China devaluation) Qwen3's knowledge is
effectively frozen; the at-risk window is 2020–2023 (COVID crash, SVB,
Credit Suisse, soft landing). The risk can be measured directly by
comparing NMI and silhouette on pre-2021 vs post-2021 sub-corpora across
Qwen3 and mpnet — and mpnet's 2020–2021 cutoff means it too has exposure on
2020–2021 data. Both models are exposed on part of the corpus; Qwen3 has
more exposure but far superior context and quality, so measure the
exposure rather than assume the weaker model is safe.

### Decision

**1. Restore Qwen3-Embedding-0.6B as primary.** 32,768-token context and representational quality are decisive; Apache 2.0. Full context on RCC (CUDA); local MPS uses `MND_MAX_SEQ_LEN=512` per ADR-006.

**2. Restore all-mpnet-base-v2 as comparator**, solely for the look-ahead sensitivity check.

**3. Formalize the look-ahead sensitivity check.** Embed a representative sample of all 10 anchor narratives (±3-month windows) with both models; compute NMI and mean pairwise silhouette separately for pre-2021 and post-2021 sub-corpora; report Δ_NMI(Qwen3) vs Δ_NMI(mpnet). Kill criterion: if Qwen3's post-2021 NMI exceeds pre-2021 by more than 0.15 AND mpnet does not show the same pattern, document significant look-ahead and caveat the pre-registration and methodology. Run once after full corpus embedding (Phase 3); a diagnostic for the methodology appendix, never used to change clustering.

**4. Keep the 600-token article truncation rule in config.** Well within Qwen3's capacity; mpnet simply truncates further internally at 384.

### Consequences

Full analytical content of long documents is encoded, and look-ahead risk
is measured rather than assumed, yielding a reportable finding either way.
Risks: Qwen3 has seen post-2020 events (SVB, Credit Suisse, soft landing
2023–2024) — disclosed in the pre-registration; the instruction prefix adds
small per-document overhead; local MPS still needs `MND_MAX_SEQ_LEN=512`
(ADR-006), which limits local testing only.

---

## ADR-012: Remove arXiv and Jackson Hole separate ingestor; remove topic filter from Stage 2

- **Status**: Accepted
- **Date**: 2026-05-13

### Context

MND_PROJECT_SPEC rev3 (2026-05-11) identified three pre-full-run fixes:
arXiv (econ category only exists from 2017, low macro volume, preprint
abstracts add noise) was cut from scope but still active;
`JacksonHoleIngestor` fetched only the Kansas City Fed proceedings index
page (overview text, not papers) and duplicated speeches already published
on `federalreserve.gov` and captured by `FederalReserveIngestor`; and the
Stage 2 keyword TopicFilter was designed for the now-removed journalism
sources — remaining Layer 1A sources are macro-relevant by construction,
and keyword filtering risks dropping valid institutional documents.

### Decision

1. **Remove arXiv** from `InstitutionalIngestor._sub_ingestors` and `config/whitelist.yaml`. Archive `src/mnd/ingestion/arxiv.py` → `scripts/archive/arxiv_ingestor.py`.

2. **Remove `JacksonHoleIngestor`** from the composite and delete the class from `institutional.py`; note in the whitelist that the Fed Board speeches ingestor covers Jackson Hole with no gap.

3. **Remove TopicFilter from the `filter` stage.** Stage 2 now runs: (a) date range filter [2010-01-01, present], (b) MinHash near-duplicate removal. No keyword filter.

### Consequences

Ingestion is cleaner and Stage 2 will not drop institutional documents
lacking keyword seeds. arXiv macro abstracts from 2017–present are an
acknowledged scope constraint (MND_PROJECT_SPEC rev3 §4 removed-sources
table); Jackson Hole speeches carry `source_id=fed_board`,
`document_type=speech` rather than a dedicated type — correct per the spec.

---

## ADR-013: Post-2024-dry-run fixes — ingestor repairs, IMF re-enable, embed OOM fix, filter-pre-embed in SLURM chain

- **Status**: Accepted
- **Date**: 2026-05-17

### Context

The 2024 dry-run SLURM chain (jobs 49622332–49622335, 2026-05-13/14) surfaced four bug classes to fix before the full 2010–present submission:

1. **CongressionalIngestor returned 0 articles**: the URL regex `^/news/press-releases/[a-zA-Z]{2}\d+` matched legacy `sb####`/`jy####` slugs only, missing modern `/statements/<slug>`, `/testimonies/<slug>`, `/readouts/<slug>` forms. The relevance filter also hardcoded "Economic Fury" as an exclusion, dropping legitimate Bessent-era macro-financial Treasury remarks.
2. **CBOIngestor returned 0 articles**: the Drupal listing scraper at `cbo.gov/publications` is behind DataDome bot protection (HTTP 403 for non-browser UAs); the RSS fallback hits the same wall. `cbo.gov/sitemap.xml` is NOT protected and indexes every publication URL with `<lastmod>`.
3. **CFRIngestor returned 0 articles**: `cfr.org/feed` exposes only ~24 recent items. CFR's sitemap (`/articles/`, `/backgrounders/`, `/reports/`) exposes 24K+ historical URLs but with `lastmod=current-sitemap-build-date`, so filtering must go by URL slug and then re-validate dates from each fetched page.
4. **Qwen3 primary embed OOMed on V100 16GB** (job 49622334, allocation 16.07 GiB): SDPA causal mask + KV-cache + activations at `(batch=32, seq=2048, fp16)` exceeded 16 GB. Batch size is a perf knob with zero quality impact, and `max_seq_len` reduction above the chunker's 600-BPE-token output is lossless; an A100 switch would work but adds queue-wait risk.

Also, the `filter-pre-embed` stage (ADR-010/012 archived-source exclusion writing `corpus_for_embedding.jsonl`) was not chained in `submit_full_pipeline.sh` — the filter stage fell back to inline exclusion and the canonical artifact was never produced. IMF had been set `_HISTORICAL_DISABLED = True` after its hardcoded slug URLs and `/api/v1/en/publications` JSON API began redirecting to `/en/errors/404`, pending a Next.js retrieval path.

### Decision

1. **CongressionalIngestor**: broaden URL regex to `(sb\d+|jy\d+|statements/<slug>|testimonies/<slug>|readouts/<slug>|remarks/<slug>)`. Switch date extraction to prefer `<time datetime=...>` over text regex. Replace the "Economic Fury" hardcoded exclusion with a generic sanctions filter that only excludes when no macro-financial term is present. Add INFO-level per-page diagnostics and a hard-fail when page 0 returns 0 release links (silent-failure prevention).
2. **CBOIngestor**: primary path is `cbo.gov/sitemap.xml` enumeration with a 365-day lastmod slop (CBO does periodic sitemap-wide rebuilds; ~6000 publications got stamped lastmod=2019). Page-date validation in `_fetch_page_full` is the final truth. Legacy archive scrape retained as fallback.
3. **CFRIngestor**: primary path is sitemap enumeration over `/articles/`, `/backgrounders/`, `/reports/` with URL-slug macro pre-filter (~7.6% match rate). Lastmod is ignored. Page-date filtering inside `fetch()` filters into the window. RSS retained as fallback.
4. **Embed OOM**: drop `compute.embedding_batch_size` 32 → 8; drop `embedding.primary.max_seq_len` 2048 → 1024. Both have zero quality impact. Add `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` to `embed_rcc.sh`. Stay on V100 partition.
5. **filter-pre-embed in SLURM chain**: new `scripts/rcc/filter_pre_embed_rcc.sh`, chained between ingest and filter in `submit_full_pipeline.sh`.
6. **IMF**: implement Next.js `__NEXT_DATA__` extraction → recursive walk of pageProps for publication-shaped dicts → `_next/data/<buildId>/<path>.json` SSG endpoint for individual publication bodies. Legacy hardcoded URL tables retained as fallback. Re-enable `IMFIngestor` in the composite list; if both paths return 0 on RCC, the composite handler marks it failed and the chain continues.

### Consequences

All four broken ingestors have functional historical paths; INFO-level
per-page diagnostics make silent failures impossible; the embed job fits
V100 (~6 GB working set vs 16 GB OOM); `filter-pre-embed` runs
automatically. Risks (all accepted): CFR's full scrape adds ~1800 pages at
~0.5s (~25 min); the CBO 365d lastmod slop may miss publications edited
>1 year after release; the IMF Next.js path is unverified from residential
IPs; broader Treasury filter terms (`interest rate`, `recession`, `growth`,
`banking`, `credit`, `tariff`, `trade`, `currency`, `dollar`, `tax`) may
admit lower-relevance items that dedup + clustering absorb.

### Verification

Local smoke tests (residential, 30-day windows):
- Congressional: 3 articles yielded ✓
- CFR: 22,454 + 1,046 + 712 sitemap URLs → 1,843 macro-slug candidates → 3 in-window articles fetched ✓
- CBO: sitemap enumeration yields 500+ in-window-with-slop candidates ✓ (page fetches RCC-only)
- IMF: Next.js + legacy paths execute cleanly with proper 403 handling; 0 yielded from residential (expected)

RCC verification (2026-05-17, Midway3 login node): all `imf.org` URLs
return HTTP 403 from RCC IP space regardless of User-Agent (via both
`requests` and `curl`); the Next.js path is correct but inaccessible from
RCC, so **`IMFIngestor` was re-disabled in the composite list** and
documented as a corpus limitation in CLAUDE.md. Other ingestors validated
on the next full RCC ingest run.

---

## ADR-014: IMF ingestion via curl_cffi Chrome impersonation + Coveo Search listing

- **Status**: Accepted
- **Date**: 2026-05-17
- **Amends**: ADR-013 (misdiagnosis correction — see "Context")

### Context

ADR-013 disabled `IMFIngestor` after HTTP 403 on every `imf.org` URL from RCC, diagnosed as "Cloudflare WAF IP block." Both halves are wrong: imf.org is fronted by **Akamai** (`server: AkamaiGHost`), whose Bot Manager fingerprints the TLS handshake (JA3/JA4) — stdlib `requests` does not match any real browser and is 403'd before the HTTP layer; and the block is **not IP-based** — the same `requests` call from T-Mobile residential (AS21928) also returned 403, while `curl_cffi` with `impersonate='chrome131'` returned 200 from both residential and RCC.

Separately, the Next.js `__NEXT_DATA__` walker no longer matches the live site. IMF migrated to Sitecore JSS: `pageProps.componentProps` is a GUID-keyed layout map, the sidebar `AsidePublicationList` exposes only the latest issue per series, and historical listings are rendered client-side via Sitecore GraphQL or — more usefully — the public Coveo Search endpoint behind the site search bar (`imfproduction561s308u.org.coveo.com/rest/search/v2`, public Bearer token harvested from the JS bundle).

### Decision

1. **Replace the TLS-layer fix.** `IMFIngestor._imf_get` routes all `imf.org` fetches through `curl_cffi.requests.get` with `impersonate='chrome131'`, falling back to stdlib `requests` only if `curl_cffi` is missing (a loud `ERROR` log makes the failure obvious). Already shipped in commit `ede1de6` (2026-05-17).
2. **Replace the listing-layer fix.** The Sitecore JSS walker (`_walk_publications` + `_NEXT_INDEX_PAGES` + hardcoded `_WEO_PATHS` / `_GFSR_PATHS` / `_FANDD_PATHS` / `_WP_API`) is removed. The new `_coveo_list` queries Coveo with `aq=@uri="<prefix>" @date>=… @date<=…` per series (`weo`, `gfsr`, `fandd`, `wp`, `blog`), paginates to Coveo's 1000-result cap, and recursively bisects the date window when a series exceeds the cap (only the WP series is dense enough to trigger this — ~700 papers/year).
3. **Reuse the existing body-extraction path** with one tweak. `_fetch_publication_body` continues to try `_next/data/<buildId>/<path>.json` first for `/en/publications/*` URLs and falls back to trafilatura on the HTML page. The buildId is now scraped once per `fetch()` from `/en/Publications/WEO` and cached. Blog URLs (`/en/blogs/articles/*`) are not covered by the SSG build (`_next/data` 404s) so they always take the trafilatura path; yields ~800 words/post.
4. **Re-enable `IMFIngestor()` in `InstitutionalIngestor._sub_ingestors`.** RCC composite runs include IMF from this commit forward. The class-level `_HISTORICAL_DISABLED` documentation flag is dropped (no code path consulted it).
5. **Keep `--sources imf` as a debug affordance in `run_pipeline.py`.** Useful for small-window probes of IMF specifically without paying for the full composite cycle; help text and error messages drop the "local-only" framing.
6. **`curl_cffi==0.15.0` is a hard dependency** in `requirements.txt` (MIT-licensed; wraps the curl-impersonate fork of libcurl). Must be installed in the RCC conda env (`mnd`) for IMF retrieval to work.

### Consequences

IMF coverage (WEO, GFSR, F&D, WP, Blog) is restored with no new
infrastructure, keeping RCC the single ingestion host. The Coveo path is
more comprehensive than the hardcoded tables (304 historical WEO entries
vs 30; 16,973 working papers vs none) and covers WEO/GFSR Updates and
individual F&D articles. Risks: the Coveo Bearer token may rotate
(failure mode is a 401 with a `WARNING` log; fix by re-fetching
`/_next/static/chunks/1166-*.js` and updating `IMFIngestor._COVEO_TOKEN`);
a missing `curl_cffi` fails loudly via the `ImportError` `ERROR` branch,
mitigated by the `requirements.txt` pin; Akamai could reject
curl-impersonate-chrome131 in the future — bump the `impersonate` profile
if 403s reappear on every IMF URL.

### Verification

- `from mnd.ingestion.institutional import IMFIngestor; IMFIngestor()` instantiates without error. ✓
- `InstitutionalIngestor()._sub_ingestors` includes `IMFIngestor`. ✓
- Small-window run (`date(2024,9,1)` … `date(2024,10,31)`) yields 80 articles: 1 WEO, 1 GFSR, 24 F&D, 39 WP, 15 Blog, all with body word-count ≥ 50. ✓
- WEO Oct 2024 issue specifically present in output with 254 words of executive-summary text. ✓

### Addendum (2026-06-05): legacy F&D article-level walker for pre-2018 coverage

**Problem.** The 2026-06-04 ADR-028 shape audit (`verify_coverage.py imf`) surfaced a 16x cliff at the `imf_fandd` 2017→2018 boundary (2017=5 vs 2018=81). For pre-2018 F&D the Coveo `@uri="/en/publications/fandd/issues/"` prefix query returns only whole-*issue* PDFs (one per issue per en/spa/fre variant), never individual articles — legacy F&D lived at a non-Next.js path the prefix never matches. Accepting the issue PDFs would trade one cliff for another (article-granularity 2018+ vs issue-granularity pre-2018), so the fix must preserve article-level granularity.

**Decision.** Add `IMFIngestor._fetch_legacy_fandd(start, end)`, wired into `fetch()` after the Coveo loop. For years in `[max(start.year, 2010), min(end.year, 2017)]` it walks `https://www.imf.org/external/pubs/ft/fandd/{year}/{mm}/index.htm` (all 12 months; non-issue months 404 and self-skip), regex-extracts same-directory `[a-z0-9_-]+\.htm` slugs (excluding `index.htm`), fetches bodies via `_imf_get` (curl_cffi — plain `requests` 403s at Akamai on the legacy path too, verified 2026-06-05), and dates each article from the issue path (year/month, first-of-month) — never a slug or snapshot guess. The ≥50-word floor applies; nav pages self-drop. Yielded as `document_type="imf_fandd"` so content-dedup collapses boundary overlap; the walker is hard-gated to ≤2017 so the two paths never double-walk.

**Verification.** Slug regex against the Wayback copy of `2013/06/index.htm` extracts 19 candidate slugs ✓; live legacy fetch 403s plain `curl`, confirming the curl_cffi requirement ✓; post-re-ingest check (pending): the 2017→2018 cliff gone, legacy years at plausible ~40-60 articles/year.

---

## ADR-015: JEL-anchored canonical filter; eliminate inline Stage 1 filters

- **Status**: Accepted (drafted, ratified, and implemented 2026-05-18 during Phase 2 closeout — same day a coverage-bug audit surfaced four ingestor fixes that share the methodology-hardening pre-Phase-4 re-ingest)
- **Date**: 2026-05-18
- **Supersedes**: portions of ADR-012 (which removed a separate Stage 2 topic filter but left inline Stage 1 filters in place)
- **Implemented in**: `config/topic_filter_keywords.yaml` (schema 2.0.0), `src/mnd/ingestion/institutional.py` (`_canonical_topic_keywords()` + `_title_matches_canonical()` helpers; six ingestors refactored), `src/mnd/filtering/topic_filter.py` (backward-compatible `_load_keywords` for both schemas)

### Context

The topic filter operates in two stages. Stage 1: six broad-source
ingestors (CBO, NBER, VoxEU, Brookings, CFR, Congressional) each carry a
bespoke, researcher-derived keyword list applied to titles at ingest time
(IMF, Fed, BIS, Treasury, OFR, fed_regional, PIIE have none). Stage 2: the
canonical filter (`src/mnd/filtering/topic_filter.py`) loads
`config/topic_filter_keywords.yaml` and applies a two-gate test (≥2
keyword matches AND embedding similarity vs seed articles). The Stage 1
lists are not a subset of Stage 2, so per-source researcher judgment shapes
the corpus in a non-pre-registered, non-audit-traceable way. Separately,
the Stage 2 list itself is not anchored to a field-standard taxonomy; the
AEA's JEL Classification System is the universal standard. Full audit:
`docs/filter_audit_jel.md`.

### Decision

1. **Anchor the canonical filter to JEL E/F/G/H scope.** Add a `methodology` block to `config/topic_filter_keywords.yaml` listing in-scope JEL codes (E, F, G; subcodes F1/F3/F4/F5/F6, G1/G2/G33, H6); annotate each keyword category with the JEL subcode(s) it operationalizes; bump schema_version to `2.0.0`.
2. **Apply the audit recommendations.** Add ~50 keywords across 11 categories to close JEL gaps (e.g., `r-star`, `inflation breakevens`, `SLOOS`, `BTFP`, `swap lines`, `financial conditions index`); add a `named_events` category (pandemic, Brexit, IRA, CHIPS Act) so anchor-relevant content is explicitly captured. Full list in `docs/filter_audit_jel.md`.
3. **Eliminate inline Stage 1 filters.** The six ingestors drop their bespoke `_MACRO_TERMS` / `_KEEP_KEYWORDS` lists; the canonical YAML keyword set is applied as a shared Stage 1 filter identical to Stage 2's. Same filter at both stages → no asymmetric loss; ingest stays bandwidth-bounded (Option B in the audit).
4. **Apply the canonical filter to PIIE** once its undercapture bug is fixed, for consistency with every other broad source.
5. **NBER's native JEL-based filter is retained** (papers carry JEL codes in metadata).
6. **Document in pre-registration**: a "Corpus scope" subsection citing JEL E/F/G/H, `config/topic_filter_keywords.yaml`, and the audit record.

### Consequences

"Macro narrative content" now has a citable operational definition, applied
by one filter consistently; the ~50 keyword additions close real gaps and
should improve recovery for COVID, Brexit, taper tantrum, and China
devaluation (the 4 anchors failing per `validate` 2026-05-18, 6/10). Risks:
the refactor touches six ingestors plus the YAML — mitigated by re-running
only the `filter` step and re-validating (~40 min loop); `named_events`
contains entity-like terms, kept small and cross-referenced to
`data/anchors/anchor_narratives.jsonl`; JEL is a 1990-vintage taxonomy and
some constructs cross subcode boundaries, consistent with practice (papers
declare 2–3 JEL codes).

### Verification

- `TopicFilter()` loads canonical keywords without error.
- `corpus-composition` post-refactor shows similar tier-1/tier-2 splits.
- `validate` recovers ≥7/10 anchors post-refactor (stretch: ≥8/10 given the
  new pandemic/Brexit coverage).

---

## ADR-016: Single-stage topic filtering + Media Cloud Premium as dynamics layer

- **Status**: Accepted (drafted, ratified, and implemented 2026-05-18)
- **Date**: 2026-05-18
- **Supersedes**:
  - ADR-015 partially (the "Option B: canonical Stage-1 mirror of Stage-2" recommendation is rejected here as methodologically asymmetric — see Context (a))
  - ADR-010 partially (the "RavenPack RPA via WRDS = Layer 1B" architecture is replaced by Media Cloud Premium Press — see Context (b))
  - ADR-008 partially (the "AP News + RavenPack" Phase 6 update plan is replaced by Tier 1/2 periodic re-ingest + Media Cloud Premium — see Context (c))

### Context

Three issues from the 2026-05-18 Phase 2 closeout review.

**(a) The ADR-015 Stage-1 inline filter is asymmetric to Stage-2.** Stage 1 filters on title only with ≥1 keyword; Stage 2 on title + body with ≥2 keywords + embedding similarity. An article titled "What Happens Next?" with a Fed-policy body fails Stage 1 but would pass Stage 2, so the corpus may already be asymmetrically truncated by a pre-filter Stage 2 doesn't apply.

**(b) The RavenPack-via-WRDS dynamics layer was never implemented or used.** It requires a WRDS subscription and ~5-week monthly-vintage delivery, while the detection layer already uses Media Cloud (free academic access, near-realtime). Media Cloud supports per-outlet-collection queries, so one API serves both Layer 1B (premium-press collection: WSJ, Bloomberg, FT, Reuters, Barron's, Dow Jones, MarketWatch, etc.) and Layer 2 (broad collection).

**(c) The Phase 6 update plan named "AP News RSS + RavenPack live"** — both now removed. Periodic re-ingest of Tier 1/2 sources captures new analytical text; Media Cloud Premium captures new journalism volume; no third mechanism is needed.

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

The corpus is shaped by exactly one topic decision at one place —
pre-registration sentence: *"Topic relevance is defined operationally by
`config/topic_filter_keywords.yaml` v2.0.0 applied with ≥2 keyword matches
+ embedding similarity threshold at `src/mnd/filtering/topic_filter.py`.
No ingest-time topic filter is applied."* One API serves both
journalism-volume roles, Phase 6 reuses historical-ingest code, and the
CBO gap is honestly stated. Risks: ingest throughput drops substantially
(content-neutral Brookings alone is ~48,000 articles at ~1 fetch/s ≈ 13h;
full-corpus ingest moves from ~6-8h to an estimated 20-30h, amortized per
major re-run); raw JSONL grows ~300 MB → 1-1.5 GB, within scratch budget;
filter-behavior regression tests are a TODO; the Media Cloud Premium
extension to `mediacloud.py` is a follow-on commit before Phase 4 freeze.

### Implementation steps (this commit)

1. **Code:** `src/mnd/ingestion/institutional.py` — strip topic title-filter call sites from CBO (sitemap, `_fetch_archive`, `_fetch_rss`), VoxEU `_fetch_year`, Brookings `fetch`, CFR sitemap walk + `_fetch_rss`; delete CFR `_URL_MACRO_TOKENS`; reduce Congressional `_is_relevant` to the role-guard only. NBER (inactive) retains its JEL-primary logic; flagged for a Phase-6 revisit.
2. **Code:** `ravenpack.py` — deprecation docstring.
3. **Docs:** CLAUDE.md, MND_PROJECT_SPEC.md, README.md — RavenPack/WRDS → Media Cloud Premium Press throughout; Phase 6 plan updated; WRDS env var instructions removed.

Deferred before Phase 4: extend `mediacloud.py` with `query_premium_collection()` (output `data/dynamics/mediacloud_premium/`); point `run_pipeline.py ingest-dynamics` at it; pre-registration updates.

### Verification

- `grep -nE "_MACRO_TERMS|_KEEP_KEYWORDS|_URL_MACRO_TOKENS" src/mnd/ingestion/institutional.py` returns no matches.
- `grep -nE "RavenPack|WRDS_" CLAUDE.md MND_PROJECT_SPEC.md README.md` returns only deprecation markers.
- 47/47 unit tests pass.
- After the full re-ingest (NUKE_RAW=1), `corpus-composition --by-tier` shows substantially higher raw and admission counts on Brookings / CFR / VoxEU. Anchor recovery target: ≥8/10 (was 6/10).

---

## ADR-017: Coverage-gap closures + Phase 6 scope freeze

- **Status**: Accepted (drafted, ratified, and implemented 2026-05-19)
- **Date**: 2026-05-19
- **Supersedes**:
  - ADR-013 (which characterized CBO as a coverage gap pending headless-browser layer)
  - ADR-010 partially (which kept NBER and SSRN on the books for Phase 6 live RSS — both are now removed entirely)
  - ADR-016 partially (which accepted CBO as a documented gap — now closed via Playwright)

### Context

Three issues from the 2026-05-19 source-coverage audit:

**(a) CBO is a needed source, not an acceptable gap.** CBO publications (Budget and Economic Outlook, Long-Term Budget Outlook, Working Papers, scoring reports) are foundational to U.S. fiscal narrative analysis; anchor coverage for debt ceiling, stimulus, and deficit framing is materially weaker without it.

**(b) Several Tier 1/2 sources are structurally undercaptured** in ways filter removal alone won't fix: PIIE has 179 records vs ~500-800/year expected (~10x undercapture; title-only listing fallback + too-narrow teaser selector); BIS's 1,057 records are Working Papers only, missing the Quarterly Review (~16-24/yr), Bulletins (~10-20/yr since 2020), and curated central-bank speeches (hundreds/yr); Treasury's 160 OFR-only count is correct but confusing — Treasury Secretary press releases are captured under the `congressional` source_id (documented rather than renamed, to preserve data alignment).

**(c) Phase 6 scope drift.** ADR-010 kept NBER and SSRN as Phase-6-only live RSS sources; ADR-016 defined Phase 6 as Tier 1/2 re-ingest + Media Cloud Premium. User directive (2026-05-18): "nothing new should be added to live except Media Cloud for premium press propagation."

### Decision

1. **CBO via Playwright + curl_cffi hybrid (ADR-013 reopened and closed).** `CBOIngestor._acquire_cookies()` launches a headless Chromium via Playwright once per ingest run to clear DataDome's JS challenge and capture clearance cookies (~3-5s, one-time). `_cbo_get()` then uses curl_cffi with those cookies for the ~25,000-URL sitemap walk (~3.5h at 0.5s/fetch). On a burst of 50 consecutive 403s mid-walk, cookies are invalidated and re-acquired up to 3 times before the run gives up. Requires `playwright==1.48.0` + `python -m playwright install chromium` (one-time per env; ~300 MB). Setup script: `scripts/install_playwright_for_cbo.sh`.

2. **PIIE rewrite.** Replace title-only listing fallback with explicit body-required emission. Broaden teaser selector to `.teaser` (handles `<article>` and `<div>` variants). Add per-page logging of in-window / body-failed / emitted counts. Expectation: PIIE volume jumps from ~179 to ~1,000-2,000.

3. **BIS expansion.** Replace the single working-paper regex with a dispatching list covering Working Papers + Quarterly Review articles + Bulletins + curated central-bank speeches + a catch-all for other `/publ/` HTML. Per-section count logging per year. Expectation: BIS volume jumps from ~1,057 to ~5,000-8,000 (most growth from BIS-republished speeches).

4. **Treasury: clarify, do not restructure.** Document that Treasury Secretary press releases are ingested under `congressional` source_id (and have been since the original design). OFR research stays under `treasury_ofr`. Both will pick up additional content under the ADR-016 content-neutral ingest. No code rename — would invalidate existing data alignment.

5. **NBER and SSRN removed entirely.** Already commented out of `InstitutionalIngestor._sub_ingestors` for historical runs. Now also removed from any Phase 6 plan. The classes survive in code as inactive reference but are NOT in any pipeline path. CLAUDE.md and MND_PROJECT_SPEC.md updated.

6. **Phase 6 scope frozen.** Phase 6 = (i) periodic re-ingest of every Tier 1/2 source already in `InstitutionalIngestor._sub_ingestors`, plus (ii) Media Cloud Premium Press live volume. Nothing else. No "live RSS only" sources. No AP News, no NBER, no SSRN, no separate live ingestors.

### Consequences

CBO becomes a first-class source (major signal for fiscal-narrative
anchors); PIIE and BIS jumps fill international-macro and
financial-stability coverage; Phase 6 scope is unambiguous. Risks:
Playwright + Chromium adds ~300 MB per conda env and a one-time RCC setup
step; DataDome cookie rotation costs 3-5s per re-acquisition, bounded by
the 3-attempt cap; DataDome may eventually challenge Playwright too
(revisit with `playwright-stealth` or a relocated Chromium binary); the
PIIE rewrite drops the title-only fallback, so body-fetch failures produce
no record at all — the per-page log surfaces the failure rate; BIS speeches
via `/review/r\d+.htm` are mostly third-party central bankers (Carney,
Lagarde, Powell at non-Fed events), distinguished by section labeling.

### Implementation steps (this commit)

1. `src/mnd/ingestion/institutional.py`:
   - `CBOIngestor`: `_cookie_cache` class state, `_acquire_cookies()`, `_invalidate_cookies()`; `_cbo_get()` uses cookies; 50-403 abort becomes cookie-reacquire-then-abort (3 attempts max).
   - `BISIngestor`: single regex → `_URL_PATTERNS` list (working_paper, quarterly_review, bulletin, speech, other_publication); per-section count logging.
   - `PIIEIngestor`: `.teaser` selector; title-only fallback removed; body ≥50 words; per-page logging.
2. `requirements.txt`: add `playwright==1.48.0` (+ `playwright install chromium` note); remove RavenPack/WRDS comment block.
3. `scripts/install_playwright_for_cbo.sh`: one-time setup script with sanity check.
4. Docs: CLAUDE.md and MND_PROJECT_SPEC.md drop NBER/SSRN Phase 6 mentions.

### Verification

- `scripts/install_playwright_for_cbo.sh` succeeds in the mnd conda env on RCC; `CBOIngestor._acquire_cookies()` returns True from RCC.
- 47/47 unit tests pass.
- After the next full re-ingest (NUKE_RAW=1): CBO >1,000 records; BIS records span `section in (working_paper, quarterly_review, bulletin, speech)`; PIIE >1,000; no NBER or SSRN records.

---

## ADR-018: Remove `named_events` keyword category to eliminate anchor-recovery circularity

- **Status**: Accepted (drafted, ratified, and implemented 2026-05-19)
- **Date**: 2026-05-19
- **Supersedes**: ADR-015 partially (canonical filter keyword list — `named_events` category dropped)

### Context

The `config/topic_filter_keywords.yaml` schema 2.0.0 (ADR-015) included a `named_events` category of 21 keywords explicitly added to capture anchor-relevant content. A 2026-05-19 audit surfaced a circularity: **13 of the 21 keywords are entries from the anchor `key_terms` lists themselves** — Silicon Valley Bank/SVB (anchor 01), COVID-19/COVID/pandemic/lockdown (02), Brexit/referendum/Article 50 (03), Credit Suisse (05), First Republic (06), taper tantrum (09) — so anchor-recovery scoring partially measured whether the system re-discovers narratives selected for in the filter. The remaining 8 (Ukraine invasion, Russian sanctions, Inflation Reduction Act, IRA, CHIPS Act, Build Back Better, American Rescue Plan, reopening) are researcher-named and redundant with JEL-anchored categories (Ukraine/sanctions → `shocks_and_geopolitics_macro`; IRA/CHIPS/BBB/ARP → `policy_fiscal`). Under `filtering.topic.keyword_min_matches: 2`, any genuine macro article hits ≥2 JEL-conceptual terms in body text anyway — an "SVB" article also contains "bank failure", "deposit run", "regional banks", "FDIC", "BTFP", all in `banking_and_financial_stability` (JEL G21/G28) — so the recall risk of dropping `named_events` is small.

### Decision

**Drop the entire `named_events` category from `config/topic_filter_keywords.yaml`.** No replacement, no relocated keywords, no migration — the JEL-anchored categories already cover the genuine macro signal. Companion edits in the same commit: the YAML header loses the stale Stage-1 application claim (post-ADR-016 there is no Stage 1 topic filter) and states explicitly that no anchor-named entities appear in the canonical list; `methodology.stage_policy` reflects Stage-2-only application (ADR-016 + ADR-018); `schema_version` bumps `"2.0.0"` → `"2.1.0"`; `docs/filter_audit_jel.md` moves to "ratified by ADR-015 / 016 / 018" with the pre-ADR-016 two-stage account preserved as a Historical section. No code changes: `src/mnd/filtering/topic_filter.py` iterates `categories` without referencing any category by name.

### Consequences

Anchor recovery becomes a clean test of body-text matching against JEL conceptual vocabulary; scope has a single source of truth (JEL E, F, G, H6, every subcode enumerated in the audit); the filter shrinks from 234 to 213 keywords. Risk: articles narrowly about IRA/CHIPS/BBB that name the bill but carry no other macro vocabulary are missed — estimated small for long-form content, re-verified during post-re-ingest filter QA. The filter doesn't need "SVB" in its list to find SVB articles; it needs to know what banking-stress vocabulary looks like.

Verification: `pytest tests/test_filtering.py` passes (8/8). After the next full re-ingest, post-Stage-2 corpus composition should stay within ±10% of the prior count (a larger drop would mean the named-entity hit was load-bearing). Anchor recovery target ≥8/10 — a notable drop below the pre-removal baseline would itself be evidence the prior filter was anchor-name-matching rather than genuine recovery.

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

A 2026-05-19 audit of `config/config.yaml` and the pipeline surfaced ~22 parameters and three architectural pieces that were researcher-chosen without a published anchor, plus silent BERTopic-default mismatches. The standing principle ("everything anchored or removed; no sensitivity sweeps") forces a comprehensive lock-in. Findings:

1. Five BERTopic parameters silently differed from library defaults (`umap.min_dist`, `hdbscan.min_cluster_size`, `hdbscan.min_samples`, `ctfidf.reduce_frequent_words`, `ctfidf.bm25_weighting`).
2. The 600/100/>2000 chunker recipe (ADR-008) had no anchor and mixed tokenizers (cl100k chunker vs. Qwen3 SentencePiece embedder). Field standard: 512 tokens, Thakur et al. 2021 *BEIR*.
3. Three-tier granularity merging (200/60/15 + silhouette thresholds) had no anchor; every published BERTopic/LDA narrative study (Bybee et al. 2024; Hansen et al. 2018; Larsen & Thorsrud 2019; Bertsch et al. 2021) reports a single granularity.
4. The mpnet comparator look-ahead apparatus (ADR-011) is researcher-introduced robustness machinery; its negative finding is preserved as evidence, the apparatus removed.
5. Kill-criterion thresholds (`required_anchors_recovered: 7/10`, `min_bootstrap_nmi: 0.40`, `min_r_squared: 0.30`, `max_r0_ci_width: 2.0`, `lookahead_check.fail_threshold: 0.15`) are unanchored binary cutoffs — report the values, don't gate on them.
6. Source-stratified smoothing had no anchor; a 7-day centered MA on combined volume is standard (Shumway & Stoffer).
7. `prepare_text_for_embedding(max_tokens=600)` had broken whitespace-token math (≈1662 Qwen3 tokens) and was bypassed by the embed pipeline anyway.
8. Inactive code paths (`ravenpack.py`, `wayback.py`, `NBERIngestor`/`SSRNIngestor`) violate "anchored or removed applies to abandoned pieces too".
9. Gompertz and bare exponential lack a narrative-economics anchor; SIR (Kermack & McKendrick 1927) and logistic (Verhulst 1838) are the classical fits.
10. `embedding_similarity_threshold: 0.55` had no anchor (Reimers & Gurevych 2019 report task-tuned operating points, not a universal value).
11. `bootstrap_replicates: 20` is too low for CIs; Efron & Tibshirani 1993 recommend ≥500–1000.
12. `dedup.window_hours: 48` had no anchor; full-corpus MinHash LSH is feasible at this scale.

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

Every methodology parameter now has a citation or library default behind
it; surface area shrinks (~22 parameter removals, 3 architectural pieces,
4 unused files/classes); bootstrap NMI gets a meaningful CI (20 → 1000
replicates, per published standard). Clustering output will change
measurably (`min_cluster_size` 20 → 10 gives more topics;
`bm25_weighting` off changes top-term lists) — outcomes are owned by
BERTopic, not by us, and if quality is worse the ADR remains correct.
The 3-stage R₀-keyed scheme is less informative than the prior 5-stage one
by design: peak day becomes a descriptive overlay, and a wide R₀ CI
communicates what "pre-emergence" used to, without a binary cutoff.
Borderline R₀ ≈ 1 narratives are reported with the CI straddling 1.
Removing the embedding gate may admit more articles — the principled
answer is the JEL keyword gate is the filter. Comparator removal loses the
look-ahead report; the ADR-011 negative finding is cited as historical
evidence.

Implemented in a follow-on commit pair: config + code changes per sections A–I, dead-code deletions per section J, test updates, and documentation alignment. All unit tests and the RCC per-source integration battery passed post-implementation.

---

## ADR-020: Basis-set corpus framing; NBER restored, CFR dropped, CEA added; pre-clustering JEL keyword filter removed

- **Status**: Accepted
- **Date**: 2026-05-20
- **Supersedes (partially)**: ADR-010 (corpus scope), ADR-015 (JEL-anchored canonical filter), ADR-016 (single-stage Stage-2 keyword filter), ADR-017 (NBER/SSRN removal), ADR-018 (named_events keyword category), ADR-019 (NBERIngestor deletion). The methodology lock-in from ADR-019 (chunker, BERTopic, dynamics, validation) remains in force.

### Context

ADR-010 / 012 / 016 / 017 evolved the corpus incrementally, leaving no single principle for "why these sources and not others?", plus accumulated researcher-derived edge cases (per-source title filters, the 213-keyword Stage-2 gate, `named_events`). Re-examined under a basis-set lens (minimal sources spanning every independent dimension of US macro discourse, no redundancy, no researcher-introduced filters):

1. **Eight independent dimensions**: (1) US monetary authority, (2) US monetary research voice, (3) international macro authority, (4) international central-bank network, (5) US fiscal authority, (6) US financial-stability research, (7) US policy think-tank commentary, (8) academic primary work (academic-policy column commentary as a sub-axis). Sources wholly covered by another source are redundancy.
2. **CFR is redundancy**: ~80% foreign-policy non-macro; the macro subset (dollar dynamics, sovereign debt, global monetary policy) is covered by PIIE on dimension 7.
3. **CEA is a basis hole**: the executive-branch fiscal-and-macro voice (dimension 5), distinct from legislative CBO; the Economic Report of the President is the US executive analog to IMF WEO. CEA was a notes-only stub.
4. **NBER deletion (ADR-017/019) was premature**: a 2026-05-20 spike confirmed the `/papers/wNNNNN` detail endpoints are NOT bot-protected — plain Drupal/nginx, `citation_*` meta tags, clean HTTP 200 across years. NBER is the only open source for academic primary working papers (dimension 8).
5. **CBO via govinfo.gov investigated and rejected**: a 2026-05-20 spike found 772 CBO publications via the JSON API (`governmentAuthor:"Congressional Budget Office"`) but unevenly distributed (41 records 2010 → 6 records 2024) — GPO deposit policy would inject a time-varying selection filter into the volume series. The ADR-017 cbo.gov ingestor covers the full ~25,000-URL archive; retained.
6. **The pre-clustering JEL keyword filter is double-filtering**: basis-set selection is already a coarse macro filter by institutional mandate. `run_pipeline.py` already did not invoke the topic filter, and `_title_matches_canonical` had zero call sites since ADR-016. Remove the apparatus; shift JEL classification post-clustering.

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
- **Add `CEAIngestor`** — govinfo.gov ERP collection via the `api.govinfo.gov` JSON API; one Article per chapter-level granule; PDF text via `pypdf` (added to `requirements.txt`); key in `GOVINFO_API_KEY`, `DEMO_KEY` fallback with warning. 61 historical ERPs (1947-present), ~3,040 chapter-level granules.
- **Restore `NBERIngestor`** — direct sequential enumeration of `/papers/wNNNNN`; year-floor paper-number table calibrated 2026-05-20; metadata from `citation_*` meta tags, body via trafilatura over the abstract block; polite 0.6s/request, one-time ~8h enumeration for 2010-2026 ≈ 30,000 IDs.
- **Drop `CFRIngestor` from `InstitutionalIngestor._sub_ingestors`** — class file retained unwired so pre-ADR-020 data files can still be re-read for QA.

**Filtering.** The pre-clustering JEL keyword filter is removed entirely: `src/mnd/filtering/topic_filter.py` deleted (and its `__init__.py` export); `config/topic_filter_keywords.yaml` archived to `scripts/archive/topic_filter_keywords_archived_adr020.yaml`; the `filtering.topic` block removed from `config/config.yaml`; the keyword-coverage checks removed from `scripts/preflight_check.py` and `tests/test_scaffold.py`; the `_title_matches_canonical` / `_canonical_topic_keywords` helpers removed from `institutional.py`. The `filter` stage in `run_pipeline.py` now does date-range filtering and MinHash near-duplicate removal only.

**Post-clustering JEL classification.** New module `src/mnd/clustering/jel_classifier.py` (`classify_clusters`, `ClusterJELAssignment`): embed each BERTopic cluster's c-TF-IDF top terms in the same Qwen3 space used for clustering; embed each top-level JEL code's official AEA description as a prototype; assign the primary JEL code by maximum cosine similarity. Macro-finance scope defaults to {E, F, G, H}. Out-of-scope clusters are reported with their JEL label and excluded from SIR/logistic dynamics only — NOT dropped from the embedded corpus.

**Symmetry.** No source receives a different pre-clustering filter from any other; every basis-set source is ingested in full, and macro/non-macro is decided once at the cluster level from a published external taxonomy.

### Consequences

Corpus justification becomes one sentence: *"The semantic corpus is the minimum set of sources spanning the eight independent dimensions of US macro discourse, with no redundant or noise-dominated entries."* Filtering likewise: *"No pre-clustering topical filter is applied. The basis-set source selection is the only macro-scope constraint at ingest. Topic relevance is decided post-clustering by assigning each BERTopic cluster a primary JEL code from the AEA's published JEL taxonomy, applied symmetrically across sources."* NBER and CEA close basis gaps; dropping CFR removes ~22,000 mostly non-macro sitemap candidates; ~600 lines of filter code go away. Risks: NBER enumeration is a one-time ~8h RCC cost (0.6s/request × 30k papers); CEA needs a free GovInfo API key (`DEMO_KEY` sustains only integration tests); NBER adds ~24,000 papers 2010-2026, ~70% non-macro (J, I, D, L, …), embedded and clustered then excluded from dynamics by the JEL classifier (compute cost accepted); JEL classifier accuracy is validated only after the first full ingest, with `ClusterJELAssignment.runner_up_gap` as the diagnostic — median gap <0.05 means ambiguous classification and a revisit (likely sub-code prototypes).

Verification: `_sub_ingestors` count returns 12; `TopicFilter` import raises `ImportError`; unit tests pass with the new assertions; the 25-case integration battery passes on RCC (including new NBER + CEA cases and 2010-window historical-edge cases for Brookings / IMF / BIS / Treasury OFR); `preflight_check.py --skip-embedding` reports 6/6 with no keyword step; the JEL classifier sanity-checked on 50 clusters after the first full re-ingest (≥40% in-scope for E/F/G/H expected). Code changes span `src/mnd/ingestion/institutional.py`, `src/mnd/filtering/__init__.py`, the new `src/mnd/clustering/jel_classifier.py`, `config/whitelist.yaml` (basis-set header; CBO Playwright path canonical, govinfo rejected), `config/config.yaml`, `requirements.txt` (`pypdf==5.0.1`), the test files, `scripts/preflight_check.py`, and the docs that now cite ADR-020 as the canonical filtering and source-selection authority.

---

## ADR-021: Post-ADR-020 upstream change patches — VoxEU Cloudflare, CBO Wayback, Atlanta JSON API, Congressional GovInfo CHRG

- **Status**: Accepted
- **Date**: 2026-05-21
- **Refines**: ADR-014 (curl_cffi pattern), ADR-017 (CBO+Atlanta+PIIE coverage closures), ADR-020 (basis-set framing)

### Context

Within 24 hours of the ADR-020 verification (2026-05-20 evening), the RCC integration battery surfaced four upstream regressions on basis-set sources. User mandate: preserve the basis-set and document HOW each source is accessed.

1. **VoxEU silent zero-yield (2012 + 2023 windows).** cepr.org enabled Cloudflare's JS challenge between 2026-05-19 and 2026-05-20; every stdlib `requests` call returned 403 with `cf-mitigated: challenge`, and the exception handler silently swallowed it. VoxEU is the sole academic-policy-column source.

2. **CBO DataDome blocks even fresh Playwright cookies.** DataDome now serves the challenge interstitial inside headless Chromium without resolving it (`title='cbo.gov'`, `body_len=0` after 20s+); the captured "clearance" cookie is a challenge-stub rotated on every response, so curl_cffi requests carrying it all 403, and re-acquiring 3× doesn't help. govinfo.gov was already rejected (ADR-020).

3. **Atlanta Fed redesigned, history culled.** The 2026 redesign 404'd `/sitemap.xml` and `/blogs/macroblog/rss` and removed historical content: working papers pre-2019, macroblog pre-2022, Economy Matters pre-2016.

4. **Congressional Treasury Drupal listing caps at ~130 pages (~2.5 years)** — the "next page" link disappears, leaving only Nov 2023 onward visible from the listing path.

### Decision

**VoxEU.** Add `VoxEUIngestor._cepr_get` using `curl_cffi.requests` with `impersonate='chrome131'` (the ADR-014 pattern); route listing and body fetches through it. Promote the `except: return` to a log line on page-0 zero-card results. No new dependency.

**CBO.** Replace the Playwright + curl_cffi hybrid with the **Wayback Machine CDX API** (`web.archive.org/cdx/search/cdx`) for enumeration plus `web.archive.org/web/{ts}id_/{url}` for snapshot fetches (raw archived body, no toolbar). The canonical `url` on each Article stays the cbo.gov publication URL, so dedupe and reporting still attribute to cbo.gov. Year-sharded CDX queries keep result sets under the 503 ceiling; 0.5s/shard and 0.3s/snapshot politeness. Wayback has clean snapshots of cbo.gov/publication/* back to 2010+ with no DataDome layer. `playwright==1.48.0` stays in `requirements.txt` but is no longer load-bearing.

**Atlanta Fed.** Switch from sitemap walk to the per-series JSON listing API (`atlantafed.org/api/feed/getFilteredResults?DataSourceId=…&ContextId=…&PageSize=…&PageNumber=…&StartDateRange=…&EndDateRange=…`), hitting four series — Working Papers, Policy Hub Papers, Policy Hub Macroblog, What-We-Study Macroeconomy hub (URL-filtered for Economy-Matters-style paths). Bodies still fetched via `_atlanta_get` (curl_cffi Chrome131). Content the redesign removed (working papers pre-2019, macroblog pre-2022, Economy Matters pre-2016) is not recoverable from atlantafed.org — documented upstream limitation; Wayback is a future option.

**Congressional.** Keep the Treasury Drupal listing as **Path A** (`_MAX_LISTING_PAGES` 1200 → 2500; ~21 min at 0.5s/page for a full 2010-anchored descent). Add **Path B** — the GovInfo `CHRG` (Congressional Hearings) collection via the same JSON API and `GOVINFO_API_KEY` pattern as `CEAIngestor`; CHRG is GPO's canonical record of hearing transcripts and includes every Treasury Secretary testimony before Senate Banking and House Financial Services back to the 1990s. Path A gives recent press-release-style remarks; Path B fills history with verbatim transcripts — the cross-cutting Q&A register ADR-020 named. One shared `seen` set dedupes overlap.

### Consequences

All four basis-set dimensions are preserved, three sources now run on more
durable mechanisms (JSON APIs, Wayback CDX), and each ingestor's docstring
documents the access path including failed approaches. Risks: Atlanta Fed
pre-2019/2022/2016 content is permanently absent absent a Wayback fallback
(bounded — 3 other regional Feds remain); CBO inherits Wayback's coverage
policy (weekly Phase 6 re-ingest will catch count drops); Path B without
`GOVINFO_API_KEY` falls back to DEMO_KEY (30 req/hr) and silently
undercovers — documented in `.env.example`; the RCC battery must re-run to
confirm floors and date spans.

### Verification

Local probes (2026-05-20→21): VoxEU 2023-01 → 4 articles via `_cepr_get`;
CBO Wayback CDX returns >2000 candidate URLs for the test window; Atlanta
Fed 2023 → 45 articles across 4 sections; Congressional Path B confirmed to
list Treasury Secretary hearings (RCC verification pending for CBO and
Congressional).

### Implementation notes

All edits in `src/mnd/ingestion/institutional.py` (VoxEUIngestor rewritten
around `_cepr_get`; CBOIngestor replaced with the Wayback CDX
implementation; `_fetch_atlanta` + constants; CongressionalIngestor Path A
extended, Path B added). No changes to `_sub_ingestors` or other ingestors.

---

## ADR-022: Methodology-principle-1 enforcement pass across all 12 ingestors

- **Status**: Accepted
- **Date**: 2026-05-21
- **Refines**: ADR-015, ADR-016, ADR-019, ADR-020, ADR-021

### Context

Post-ADR-021, a senior-engineer audit of all 12 active basis-set ingestors found seven violations of methodology principle 1 (`docs/METHODOLOGY.md` §7: every parameter anchored or removed) — three fabricating publication dates when source metadata was absent, four silently degrading to a lower-coverage fallback:

1. **CBO** (`institutional.py` line 1413): missing page date → fell back to the Wayback snapshot (crawl) timestamp; a local probe surfaced a 1993 NAFTA analysis tagged 2023-07-23.
2. **BIS** (line 845): missing sitemap `<lastmod>` → fabricated `date(year, 1, 1)`.
3. **Chicago Fed** (line 1125): meta_date/URL-year disagreement → fabricated `date(year, 6, 15)`.
4. **Congressional Path B + CEA**: unset `GOVINFO_API_KEY` → warned and fell back to GovInfo's public `DEMO_KEY` (30 req/hr), silently undercovering any full enumeration.
5. **CEA + Congressional `_extract_pdf_text`**: unimportable `pypdf` → returned `""`, silently zeroing both sources.
6. **Atlanta Fed** (line 1299): body < 50 words → substituted the API listing's `Teaser` as the body, leaking listing boilerplate into embedding text.
7. **VoxEU** (line 1805): any per-shard exception → warned and `return`ed, silently truncating the year (how the 2026-05-19 Cloudflare tightening went unnoticed for 24 hours).

A parallel audit of `tests/integration/test_source_coverage.py` found four more: (8) `pytest.skip` on ANY exception masked code defects as environment errors; (9) `requires_curl_cffi` / `requires_pypdf` / `requires_playwright` helpers skipped tests for deps that are mandatory per ADR-014/020; (10) the three contracts (floor count, section diversity, date span) never validated per-record dates or bodies; (11) per-record `min_body_word_count` was unenforced. Also: (12) **FSOC Annual Reports** — `_scrape_fsoc` returned silently, calling PDF-only content a "documented corpus limitation" although the reports are PDF-text-layered and major systemic-risk discourse; (13) the **Atlanta Fed docstring** framed the source's pre-2019 / pre-2022 / pre-2016 series starts as a "Hard site-side limitation" rather than a fact about the source's editorial choices.

### Decision

All thirteen defects fixed in one commit:

- **No fabricated dates.** No extractable authoritative date (URL slug, structured page meta, or sitemap `<lastmod>` with page-side cross-check) → drop the record and log DEBUG with the URL. A mis-dated record corrupts the SIR temporal axis.
- **No silent degradation.** Missing `GOVINFO_API_KEY` raises `RuntimeError`; `pypdf` ImportError propagates from `_extract_pdf_text`; `curl_cffi` already propagated loudly. A missing dependency is a configuration error, not a fallback target.
- **No teaser-as-body substitution.** Atlanta Fed's teaser-fallback removed (PIIE's title-only fallback already removed in ADR-017, audit-confirmed).
- **No silent zero-yield paths.** VoxEU tracks per-shard yield and raises `RuntimeError` if no shard yielded across a multi-year window; Atlanta Fed distinguishes legitimate page-1-empty (INFO) from HTTP/JSON failure (ERROR), and its artificial 20-page pagination cap is removed.
- **Per-record test contracts.** Every record's `published_at` must parse as an in-window ISO date and every `word_count` must meet a source-specific minimum; failures name the URL. `pytest.skip` is narrowed to `(requests.ConnectionError, requests.Timeout, socket.gaierror, ConnectionResetError)`; the `requires_*` skip helpers for mandatory deps are removed (missing deps now fail at import time).
- **FSOC included.** `TreasuryOFRIngestor._scrape_fsoc` implemented end-to-end: PDF discovery via `_FSOC_PDF_RE` on the canonical FSOC studies-and-reports index, body via the shared `_extract_pdf_text`, section/document_type `fsoc_annual_report`, dated December 31 of the reporting year. ~15 records across 2010-present.
- **Atlanta Fed docstring reframed** as a neutral statement of each series' inaugural date; the documented-but-never-implemented `stable_history_gap` marker dropped.
- **NBER dynamic ceiling.** Hardcoded `_ABSOLUTE_CEILING = 38000` (researcher judgment) replaced with `_compute_ceiling(end_year)`: prefer the calibrated next-year floor, else project +2500 paper-IDs per forecast year. The consecutive-404 stop remains the actual termination signal; the ceiling only needs `>=` the true head.

### Consequences

- Every emitted Article carries a real publication date and real body from authoritative metadata; coverage regressions surface as named test failures; missing deps/env vars fail at the first call, not after a 48-hour half-empty ingest; FSOC contributes to the financial-stability dimension.
- Strict dating may reduce counts where the upstream surface lacks reliable metadata; URL-year-only records (e.g. some Chicago Fed working papers) are now dropped — cleanliness over corpus size. NBER's ceiling is calibrated through 2026; end-year 2030+ projects +12,500 IDs, bounded in practice by the 404 stop.

**Open question — CBO Wayback yield (deferred to RCC; resolved in ADR-023).** The local probe returned 1 of 10,036 candidates, mis-dated ~30 years — either Wayback genuinely lacks metadata on ~99% of pages, or the time-bounded probe never fetched most candidates. `scripts/probe_cbo_wayback_dates.py` samples candidates through the real extraction path and reports `page_date_yield_pct`. Fallbacks if yield is too low (not pre-committed): (1) Common Crawl WARC; (2) paid residential-IP scraping; (3) govinfo CBO collection (sparse); (4) drop CBO.

Verification: `py_compile` clean; 51 non-integration tests pass; smoke-test of all 13 ingestor classes incl. `_govinfo_api_key()` raising when unset; 25 integration cases (with `cbo_2023_datadome` → `cbo_2023_wayback` and `fed_atlanta_2023_curl_cffi` → `fed_atlanta_2023_listing_api` renamed to reflect the actual access paths). All changes in `src/mnd/ingestion/institutional.py` (defects 1-7, 12, 13), `tests/integration/test_source_coverage.py` (8-11), and the new `scripts/probe_cbo_wayback_dates.py`; no changes to `_sub_ingestors`, the pipeline, the config, or any other module.

---

## ADR-023: CBO via bounded publication-ID enumeration; fail-loud hardening of WP-REST / BIS / CEA-govinfo paths

- **Status**: Accepted; **enumeration layer superseded by ADR-032** (the `_ID_DATE_ANCHORS` / `_estimate_id_range` / `_MIN_PUBLICATION_ID` id-floor estimation is removed — CBO node ids are NOT chronological, so no id floor is sound). The fail-loud hardening of WP-REST / BIS / CEA-govinfo, the per-pid checkpoint-resume, the 12s pacing, and the `_WaybackBanned` pause-and-resume (addendums below) all remain live.
- **Date**: 2026-06-01
- **Refines / resolves**: ADR-021 (CBO Wayback access path), ADR-022 (CBO yield open question)

### Context

ADR-022's CBO failure was in the enumeration layer, not the page-date layer. ADR-021's `CBOIngestor` queried Wayback CDX with `url=cbo.gov/publication/*` and `from`/`to` set to the publication window — but CDX `from`/`to` filter by **crawl date, not publication date**, so a 2-month window matched ~10k re-crawled back-catalog URLs. The bulk-wildcard endpoint is also non-deterministic under load (identical query returned 0 / 849 / 6,575 rows within one hour; routine 504s); a 77-minute production run yielded 0 records. Two empirical facts the ADR-022 probe could not see:

1. Wayback's coverage of cbo.gov publications is essentially complete — a density probe of `/publication/59400`–`59460` found 13/15 archived with clean 200/HTML bodies (the 2 misses were transient CDX 504s).
2. Narrow-prefix CDX queries are reliable and deterministic: `cbo.gov/publication/{id//100}` with `matchType=prefix`, `collapse=urlkey` returns ~90–99 IDs per 100-id block in 1–8s (collapse yields the earliest snapshot per URL). The 847/849 page-date drops in the ADR-022 probe were rate-limit 503 stubs, not missing metadata.

CBO assigns monotonically increasing integer node ids at `cbo.gov/publication/{id}` — the same structure `NBERIngestor` enumerates (ADR-020). Directive: fix CBO **without changing methodology** — CBO stays in the basis set (dimension 5), retrieval stays cbo.gov-via-Wayback, canonical Article.url stays cbo.gov.

### Decision

**1. `CBOIngestor` rewritten to bounded ID enumeration (mirrors `NBERIngestor`).** A calibrated `_ID_DATE_ANCHORS` table maps id↔date at six probed points (42000≈2010-01, 44000≈2013-03, 54000≈2018-06, 56000≈2020-01, 58000≈2022-04, 59460≈2023-07); the id rate is non-constant (~625/yr 2010-13, ~1900/yr 2013-18, ~800/yr since 2020), so `_estimate_id` interpolates piecewise-linearly and extrapolates at the recent slope. `_estimate_id_range` pads ±500 and clamps the floor at `_MIN_PUBLICATION_ID = 40000` (pre-2010 is out of scope). `fetch` walks 100-id blocks (`_cdx_block`), pre-filters by earliest-snapshot date, fetches the raw snapshot, extracts the authoritative page date, and keeps only `page_date ∈ [start, end]` with body ≥ 50 words — the ADR-022 strict-date policy unchanged (the snapshot timestamp is never the publication date). Yields lazily in id-ascending order so a bounded consumer short-circuits.

**2. Fail-loud on three more silent-truncation paths** (per ADR-022's principle: under-capture with yield > 0 is marked "completed" by the checkpoint; raising marks failed-for-retry, dedup absorbs re-yields):

- **`_wp_rest_fetch`** (Brookings, Liberty Street, FRBSF): was `break` on any exception mid-pagination. Now tuple timeout, retries 5xx/429/network with backoff, treats 400/404 as genuine end-of-list, raises `RuntimeError` on exhaustion.
- **`BISIngestor._fetch_year`**: was `return` (dropping the year) on any exception. Now retries transients, treats 404 as a legitimate per-year skip (WARNING), raises on exhaustion.
- **CEA govinfo**: govinfo throttles with 429 even on a real key, and the old code swallowed the `HTTPError` as `""`. New `_govinfo_get_json` / `_fetch_pdf_bytes` retry 429/5xx/network with jittered backoff and raise on exhaustion. PDF **parse** failure (permanent, per-granule) logs WARNING and skips; PDF **fetch** failure (transient) fails loudly. API keys redacted from logs (`_redact_key`).

### Consequences

- CBO yields cleanly: battery (2023-06-01..07-31, floor 5, cap 30) collected 30/30 in-window records, bodies ≥ 50 words, 56-day span — vs 0 from the ADR-021 path. None of ADR-022's fallbacks (Common Crawl, paid scraping, govinfo, drop CBO) are needed; no methodology change.
- **Runtime**: ~200 block queries + ~13,000–19,000 body fetches at ~0.3–0.5s politeness ≈ **15–22h for CBO alone**; with NBER (~5–8h) the 48h institutional-job limit is tight — bump to 72h or split CBO into its own SLURM job.
- **CEA cannot be validated with DEMO_KEY** (30 req/hr quota; local `n=3` is a quota artifact) — validate on RCC with a real `GOVINFO_API_KEY` via `pytest tests/integration/test_source_coverage.py -m integration`.
- Anchors are calibrated through 2023; later windows extrapolate at ~800 ids/yr, absorbed by the ±500 pad and page-date filter.

Verification: 51 unit tests pass; the CBO battery survived a Wayback `ConnectionResetError` burst on block 593 (retry budget raised to 7 attempts / 5s→320s backoff + jitter); Beige Book 2014 re-confirmed (8 records ≥ 200 words); the remaining 21 battery cases green. All code changes in `src/mnd/ingestion/institutional.py`; no changes to `_sub_ingestors`, pipeline, config, or test contracts (`cbo_2023_wayback` validates the rewrite unchanged).

### Addendum (2026-06-06): fetch the LATEST snapshot per publication, not the earliest

`collapse=urlkey` returns the **earliest** snapshot per URL, which for pre-~2013 publications is a degraded pre-re-platforming migration **stub**. Trigger: a 2010 audit showed only 28 records, almost all titled `"CBO"`, bodies ~60-130 words — vs 127 records in 2011. Probing `pub/41813`: the earliest capture (2012-04-28) has 22 words, title `CBO`, page date 2010-01-01; a later capture (2019-03-04) has 162 words, the real title, and the true date 2010-01-14. A later capture is strictly higher-fidelity for body, title, and date; some stubs had no extractable date and were dropped entirely.

A first fix via the `web/29991231000000id_/{url}` far-future redirect was rejected: it non-deterministically resolves to a ~350-word `"Wayback Machine"` interstitial dated *today*, which either polluted the latest-year column or dropped real publications (2010 stayed at 23 records). An independent non-collapsed CDX inventory of the 2010 ID band (`/publication/418xx-426xx`) found **695** archived pages vs **23** emitted — a processing bug, not a discovery gap. (The band is date-mixed: CBO's 2012 migration interleaved pre-2010 back-catalog ids, which the page-date filter sorts out correctly.)

**Fix.** `_cdx_block` drops `collapse=urlkey`: it fetches every snapshot row per block (bumped row limit, fail-loud if truncated) and aggregates `min(ts)`/`max(ts)` per id. `fetch()` pre-filters on `min(ts)`, fetches the **latest real capture** (`max(ts)` — a concrete archived timestamp, never the redirect), falls back to the earliest if unusable, and drops any page titled exactly `"Wayback Machine"`. The window gate, ≥50-word floor (ADR-022), and snapshot-timestamp rule are unchanged. Validated on the full 422xx block: real pages with correct dates (2010/2011 reports of 399-1588 words), zero interstitials.

### Addendum (2026-06-08): the earliest-snapshot upper-bound pre-filter dropped the ENTIRE corpus

A smoke run (2010-01-01..06-30) returned **0** publications despite correct enumeration of `[41500..42807]`. The pre-filter skipped any candidate whose earliest snapshot fell outside `[start, end + 90 days]` — but the `/publication/{id}` scheme only dates from CBO's 2012 migration, so every pre-2018 publication's earliest capture is ~2012 (CDX probe: all of `415xx–428xx` first appear 2012-04/2012-10), years past the bound. The filter dropped *every* candidate before any body fetch. **Fix**: removed the upper bound and the `_WAYBACK_DISCOVERY_LAG_DAYS`/`window_end_with_lag` machinery; the pre-filter keeps only the sound lower bound (`snap_date < start → skip` — a snapshot can never predate publication). The post-fetch `page_date` gate remains authoritative. Cost: ~500 bottom-of-range candidates are body-fetched then date-dropped — negligible. Re-smoke (2010 full year) returned real January-2010 publications (e.g. *H.R. 689, Shasta-Trinity National Forest…*) with correct dates, real titles, ≥50-word bodies, zero interstitials.

### Addendum (2026-06-09): per-pid checkpoint-resume — the Wayback walk can't fit one SLURM job

Two clean-reingest jobs failed at HTTP 429 after the `_wayback_get` retry budget (raised 7→10 attempts + honor `Retry-After`, commit `05b1e96`) was exhausted. A throwaway probe (`scripts/_probe_wayback_rate.py`, deleted) measured IA's replay endpoint: throttling at **both** the TCP layer and HTTP 429/503; burst tolerance **~15–31 requests and COUNT-based**; cooldown ~60–180s; sustained-safe rate **~1 request / 9–12s**. A CDX-only census counted **13,616 unique CBO pids** — ~45h at the safe rate, over the **36h caslake QOS cap**. Alternatives rejected: live cbo.gov is DataDome-blocked (ADR-017/021), govinfo has uneven GPO deposit coverage (ADR-020), ID-range sharding re-derives the same work with more bookkeeping.

**Fix.** `CBOIngestor` gains an optional `checkpoint_path` — a flat one-pid-per-line file. `fetch()` skips checkpointed pids; `_mark_done(pid)` appends **only after** the `yield` resumes, i.e. after the caller has written *and flushed* the record (`run_pipeline` now flushes per record and routes `cbo` through the checkpointed constructor). A pid is never marked before its record is durable; a kill in between costs at most one duplicate, absorbed by dedup. A pid that raises on ban-exhaustion is never marked (ADR-030 preserved). A resume that legitimately yields 0 new records is no longer treated as under-capture. The checkpoint is **window-keyed** (`.{source}_{start}_{end}_checkpoint.{ext}`) so it can't diverge from its date-stamped output file. Operation: `NUKE_RAW=1` archives the checkpoint with the raw dir; **pin `END=<date>`** across re-fires (`END=2026-06-08 SOURCES="cbo" SKIP_DOWNSTREAM=1 SKIP_CLEANUP=1 bash scripts/rcc/submit_parallel_ingest.sh`); repeat until complete, then re-fire downstream.

**Correction (2026-06-09) — pace at the safe rate.** The first checkpoint-enabled job (`50614480`) still failed at `pub/41672` after 52 minutes: at the old 0.3s/pid pace the walk bursts past IA's count threshold and the bans escalate until one exceeds the 10-attempt budget (~170 pids per job ⇒ ~80 submissions — not viable). `CBOIngestor._REQUEST_SPACING_S = 12.0` replaces the 0.3s inter-pid sleep, keeping the rolling-window request count under threshold; a job then runs to a clean walltime `TIMEOUT` and the checkpoint carries the ~45h walk into a second job. The retry cushion remains only as a safety net.

**Second correction (2026-06-09) — pace the CDX enumeration sweep too, and cache it.** Four consecutive jobs (`50595473`, `50604248`, `50614480`, `50623881`) died at `pub/41672` with 429, zero articles, checkpoint stuck at 172 pids: the 218-block CDX sweep was still unpaced (0.5s inter-block) and tripped the count-based ban *before* fetching began; every re-fire repeated the full sweep and re-escalated it. Two changes in `src/mnd/ingestion/institutional.py`: (1) pace the sweep at the same `_REQUEST_SPACING_S` (~44 min for 218 blocks); (2) `_build_or_load_cdx_map` writes `{pid: (earliest_ts, latest_ts)}` atomically (temp-file + rename) to a window-keyed `.{source}_{start}_{end}_cdxcache.json` once the sweep completes — a resume loads the cache, skips the sweep, and starts fetching immediately from the checkpoint. `fetch` consumes the map as a sorted-pid walk; uncheckpointed (composite) callers get the paced sweep but no cache. Operationally: IA escalates IP-level bans under repeated abuse, so wait several hours for IA to cool before the first fixed run; clean reset is `rm -f data/raw/articles/cbo_*.jsonl data/raw/articles/.cbo_*` then the pinned re-fire.

**Third correction (2026-06-09) — a ban must PAUSE the walk, not crash it; finishing is an egress-IP problem.** The cached, paced run (`50634074`) enumerated cleanly (cache wrote 13,616 pids, ~640 KB) and captured 124 publications, then failed at `pub/41672` with 429. Identical death regardless of pacing is the signature of a **cumulative request-count cap on the egress IP**, not a rate limiter — the Midway IP was flagged from five CBO jobs in ~19h. Consequences: (1) the fix is operational — finish CBO from a **fresh egress IP** or after a **long cooldown**; the client's job is to not waste or escalate either. (2) `_wayback_get` now keeps **two budgets**: a 429 honors `Retry-After` over up to `ban_cooldowns=20` multi-minute waits and continues the same request (patient cooldowns don't escalate the ban; the rapid 10-attempt hammer did). Only after that budget does it raise `_WaybackBanned(RuntimeError)`, which `fetch` catches to log `PAUSED at pub/N — … re-fire to resume` and cleanly `return`; the paused pid is not marked, so a later run resumes exactly there. 5xx/network stay on the separate `max_attempts=10` escalating-backoff budget and still RAISE on true exhaustion (ADR-030). Net: at the 12s pace a clean egress IP completes the full ~13.6k-pid walk in one shot (~49h wall + ~45min enumeration); a flagged IP pauses and resumes without re-paying enumeration.

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

PIIE is the second ingestor on dimension 7 (US policy think-tank, ADR-020), paired with Brookings. The 2026-06-03 full re-ingest captured only 857 PIIE records with a wrong shape: coverage **starts at 2016**, no 2010–2015 content, *declining* into recent years (2016: 255 → 2024: 38). PIIE `COMPLETED` clean, so this is silent under-capture. Root cause: PIIE migrated CMS around 2016 — pre-2016 publications live at flat-slug URLs (`/publications/policy-briefs/2008-oil-price-bubble`, often with a legacy `?ResearchID=NNNN`); 2016+ items use a `/YYYY/` segment. The ADR-021 discovery path walked the Drupal xmlsitemap (`sitemap.xml?page=N`), which lists **only the `/YYYY/` URLs** plus a thin recent blog slice, and the `_URL_PATTERNS` regex required a `/YYYY/` segment, so even a discovered flat-slug URL would be rejected. Wayback CDX enumeration of the publication/blog prefixes (verified live 2026-06-04) shows the true size:

| Type | distinct URLs | `/YYYY/` (in sitemap) | flat-slug (missing) |
|---|---|---|---|
| policy-briefs | 585 | 123 | 462 |
| working-papers | 535 | 135 | 400 |
| piie-briefings | 38 | 11 | 27 |
| blog: realtime-economic-issues-watch | 1,971 | — | — |
| blog: trade-and-investment-policy-watch | 446 | — | — |
| blog: trade-investment-policy-watch (old slug) | 459 | — | — |
| blog: china-economic-watch | 475 | — | — |

So the complete PIIE corpus is ~4,500 URLs vs the 857 captured. Two more sitemap-era defects: the trade blog exists under **two slug eras** (the `_URL_PATTERNS` regex matched only the no-`and-` form), and `china-economic-watch` (macro-relevant) was never targeted at all.

### Decision

Replace sitemap-only discovery with **Wayback CDX enumeration ∪ the live sitemap walk**, deduped into one candidate set (`PIIEIngestor._cdx_enumerate`, `_cdx_query`, `_cdx_get`):

1. **CDX is the workhorse.** One `collapse=urlkey&filter=statuscode:200&fl=original` query per content prefix returns the distinct canonical URL set across both URL schemes; results are cleaned (drop asset extensions, strip query/fragment, normalize host to `https://www.piie.com`, drop bare section and `/type/YYYY` index pages) and deduped. CDX hits archive.org directly — no Cloudflare — and `_cdx_get` retries transient 429/5xx/network with jittered backoff and **raises on exhaustion** (ADR-022/023).
2. **Sitemap walk retained as a freshness supplement** for brand-new items Wayback has not yet archived; CDX-listed first so its `doc_type` wins on collision; both merge on a canonical (https, no-trailing-slash, lowercased) key.
3. **Bodies fetched from LIVE piie.com via curl_cffi** (`_piie_get`, unchanged) — legacy flat-slug URLs still resolve 200.
4. **Date is page-authoritative.** Flat-slug URLs carry no path year, so every CDX URL is fetched-then-date-checked against the window using the page's own publication date (methodology principle 1, ADR-022); the slug year is never trusted (`2008-oil-price-bubble` is a brief *about* the 2008 oil price).
5. Blog coverage expanded to both trade-blog slug eras and `china-economic-watch`; `_URL_PATTERNS` (sitemap side) updated to match.

PIIE SLURM budget bumped 3h → 6h to cover ~4,500 live body fetches.

### Consequences

- PIIE capture roughly 5×'s and gains the full 2010–2015 history, including the taper/China/Brexit anchor-era policy briefs; dimension 7 is fully captured from both ingestors.
- Overlap with the sitemap or any earlier partial PIIE JSONL is harmless — the downstream filter dedups by URL/content.
- New runtime dependency on Wayback CDX for PIIE (already a CBO dependency, ADR-023); fail-loud `_cdx_get` means a CDX outage halts the job rather than silently truncating.
- `china-economic-watch` adds macro-China blog content — completion of the source, not a corpus change.

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

Applying the ADR-028 verification standard to PIIE (year × document_type pivot + independent Wayback CDX inventory) surfaced two silent under-capture defects that "no failure + all years present" had hidden:

1. **Blog tail hard-zeros after 2022.** `piie_blog_post` ran 2010→2022 then dropped to zero for 2023-2026: the RealTime blog migrated ~2022 from the legacy flat-slug path `/blogs/realtime-economic-issues-watch/<slug>` (the only realtime prefix enumerated) to `/blogs/realtime-economics/<YYYY>/<slug>`. CDX confirms ~423 posts existing *only* under the new path plus ~199 back-catalog posts under *both*.

2. **Pre-2016 publications all misdated to 2016.** `policy_brief` / `working_paper` / `piie_briefing` were zero 2010-2015 then spiked at 2016 (464 / 390 / 35): PIIE's 2016 Drupal migration stamped `article:published_time` with the migration timestamp (`2016-03-02T20:43:26-05:00`) across the entire back-catalog, and trafilatura reads that OpenGraph field. The true date survives in the page's `hero-banner-publication__date` `<time>` element (e.g. a 2009 brief shows `datetime="2009-08-01"`); sidebar "related" dates use a distinct `teaser__date` class and are not matched. (Blog article pages carry a correct `article:published_time` — but see the addendum: junk enumeration URLs do not.)

### Decision

**1. Blog tail.** Add `blogs/realtime-economics` to `PIIEIngestor._CDX_PREFIXES` (listed before `realtime-economic-issues-watch`) and `/blogs/realtime-economics/\d{4}/[^/]+$` to `_URL_PATTERNS`. To avoid double-counting the ~199 dual-path posts, blog-post candidates dedup on their **trailing slug** in `fetch()` (publications keep the full-path key); the new `/YYYY/` canonical URL wins the collision. This also collapses the pre-existing trade-blog dual-era duplication (`trade-and-investment-policy-watch` vs `trade-investment-policy-watch`).

**2. Publication dates.** Add an optional authoritative `date_extractor` hook to `_extract_from_html` / `_fetch_page_full`. When supplied it *replaces* trafilatura's metadata date even when it returns `None` (`None` = no authoritative date → drop per methodology principle 1; never fall back to the known-bad migration stamp). `_piie_publication_date_from_html` reads the `hero-banner-publication__date` `<time datetime>`; PIIE passes it for the three publication doc types. *(Blogs initially kept the default trafilatura path — superseded by the addendum.)*

### Consequences

- The RealTime blog series extends through 2026 (~423 recovered posts) and the pre-2016 back-catalog redistributes onto its true years; both require a PIIE re-run.
- Publication pages lacking a hero-banner date block are dropped rather than dated to 2016; the block is standard PIIE chrome, and the `no_date` counter surfaces any non-negligible loss.
- The `date_extractor` hook is generic for any future source whose CMS poisons `article:published_time` — the structured analogue of the Chicago Fed citation-block reader.
- Found purely by the ADR-028 standard, validating it as the standing pre-clear check.

### Addendum (2026-06-05): blogs also need extract-or-drop dating

Re-verifying the post-fix corpus surfaced a third defect: `piie_blog_post` showed a 6.8x cliff at 2022 (726 vs ~170 neighbours), and **581 of the 726 records were stamped to the single date `2022-05-18`**. They are **junk enumeration URLs** — soft-hyphen-mangled slugs (`case-raising-in-flation-...`, `debt-stand-stills`), truncations (`arms-and-`), trailing-punctuation fragments (`...relief-plan[8`, `...europe;`), text-fragment links (`...%23:~:text=`), and JS placeholder paths (`blur.placeholder`, `beforeunload.placeholder`) harvested by CDX from broken in-body links. Fetched live they all resolve to a fallback page whose `article:published_time` is the `2022-05-18` RealTime-blog migration stamp. This refutes the "blogs' `article:published_time` is correct" assumption for the fallback page junk URLs land on.

**Decision.** Blogs get the same extract-or-drop treatment via `_piie_blog_date_from_html`: the blog template nests its `<time datetime>` inside `<div class="field--name-field-blog-date">` (one wrapper deeper than `_PIIE_PUB_DATE_RE` expects), so the blog regex keys on that class. PIIE routes `blog_post` → blog extractor, the three publication types → publication extractor. A junk URL's fallback page has no `field--name-field-blog-date`, so it returns `None` and the record drops; real posts (old- and new-path alike) yield their true date. Regex verified against a 2020 old-path post (`2020-04-07`) and a 2022 new-path post (`2022-07-28`).

**Consequence.** No URL-shape allowlist — corrupted slugs are not reliably distinguishable by shape, and a shape filter risks dropping real articles (violating the under-capture-is-the-only-failure-mode rule). The date-drop is the robust backstop; the cost is wasted live fetches on junk URLs, within PIIE's 6h budget. Requires a PIIE re-run.

---

## ADR-030: Fail-loud hardening pass — silent under-capture is forbidden at every fetch boundary

- **Status**: Accepted
- **Date**: 2026-06-08

### Context

A 2026-06-07 audit of `src/mnd/ingestion/institutional.py` found a systemic
defect class: at many fetch/listing boundaries a transient or partial failure
was swallowed (`log.warning; return/break/continue`) and the sub-ingestor still
exited 0 — so the `afterok` `filter→embed→cluster` chain would run on a holey
corpus. This violates the locked principle that under-capture is the only
failure mode that matters (ADR-022): a silent partial masquerades as success.
Seven findings: orchestrator + CLI swallowed sub-ingestor exceptions;
`_fetch_page_full`/`_extract_body` parsed 5xx error pages into droppable short
bodies; listing truncation on any error across IMF Coveo, NBER, Fed-regional
(NY/Chicago/Atlanta), Treasury/OFR + FSOC, VoxEU, and Congressional pagination;
and scalar curl_cffi timeouts that only bound the inter-byte gap, not connect.

### Decision

A uniform fail-loud contract at every ingest fetch boundary, landed in one
pre-launch hardening pass. **Classification rule:** after the retry layer has
absorbed transient blips, 404/genuine 4xx = the resource does not exist → skip
(or `break` at a listing's true end); 5xx / network / parse failure after
retries = systemic → raise, failing the sub-ingestor, the composite, the CLI,
and the `afterok` chain.

Specifics, each closing one audited finding or a same-class boundary found in
review:

- **Orchestrator:** `InstitutionalIngestor.fetch` collects per-sub failures
  (exception *or* zero articles — a basis-set source is never legitimately
  empty) and raises after the loop; `run_pipeline ingest` exits 1.
- **Body classification:** status inspected before parsing (4xx skip, 5xx
  raise) in `_fetch_page_full`/`_extract_body` and IMF's parallel body path;
  the caller-side `except Exception: continue` swallow removed. Legacy F&D
  keeps 4xx as genuine absence (nav slugs legitimately 404).
- **curl_cffi cushion:** shared `_normalize_timeout` coerces scalar timeouts to
  a `(10.0, read)` connect/read tuple; shared `_cffi_get_retry` retries
  429/5xx/network 5× with backoff on the impersonating getters
  (`_imf_get`/`_atlanta_get`/`_cepr_get`/`_piie_get`), which deliberately don't
  `raise_for_status`. Without this cushion the new raises would nuke a
  multi-hour source on one flaky response.
- **Wayback snapshot getter:** `_wayback_get` (CBO) gained the CDX path's
  retry (Wayback is a single edge IP that resets under burst), then — after the
  clean re-ingest tripped IA's *sustained* rate limiter at 33 min — honors
  `Retry-After` (clamped to [current-backoff, 600s]), budget 7→10 attempts.
  Exhaustion still raises. Next lever if a hard block recurs: lower the 0.3s
  base inter-request rate.
- **GovInfo pagination:** `nextPage` is a fully-formed URL, but
  `_chrg_list_packages` spliced it into the base URL as if it were a bare
  cursor, producing a nested URL GovInfo 500s on (page 2+ only, so the
  single-page integration window never caught it). Fixed to follow `nextPage`
  directly (+api_key); the latent copy in `CEAIngestor._list_packages` fixed in
  the same pass.
- **Same-class boundaries:** Treasury remarks pagination (404 = end of pages;
  page-0 failure raises), FSOC annual-report PDFs (a fetch/parse failure raises
  rather than dropping a year), CEA package-list contract-drift bail.
- **One per-record refinement:** a syndicated WordPress post can carry a
  canonical link on a third-party domain (trigger: a Brookings article linking
  `chinafile.com` with an invalid TLS cert), which is genuine absence of one
  record, not a source outage. `_wp_post_to_article` takes `expected_host`:
  body-fetch failures on a *foreign* host degrade to excerpt; failures on the
  source's own host still raise. Threaded to Brookings, Liberty Street, FRBSF.

### Consequences

A persistent failure anywhere in the basis set now aborts the run loudly
instead of shipping a partial corpus downstream (correctness > convenience,
even for the long CBO/NBER runs); the `afterok` chain is a genuine gate. A
flaky upstream that survives all retries fails its source's job — the fix is
to re-run that source (`SOURCES="<src>" SKIP_DOWNSTREAM=1`), not to re-soften
the handler. No config or test-contract change. This is the standing contract
for any new ingestor: classify 404-skip vs systemic-raise, never
swallow-and-continue.

---

## ADR-031: WordPress sources restricted to own-domain content (source-identity rule)

- **Status**: Accepted
- **Date**: 2026-06-09

### Context

The clean re-ingest's Brookings job logged a stream of cross-domain warnings — WP `article` records whose canonical `link` resolved off `brookings.edu` (`washingtonpost.com`, `t20japan.org`, a `fengshows.com` TV-appearance video). Two kinds: (1) **syndicated op-eds** — a Brookings scholar's piece published *in* another outlet; (2) **press / media-mentions** — third-party coverage *about* a scholar. ADR-030's 2026-06-08 refinement kept off-domain records on their *excerpt* (threading `expected_host` into `_wp_post_to_article`), which fixed fail-loud over-aggression but still ingested third-party records. These are not Brookings-published content — every other basis-set source contributes only what it itself publishes. Ingesting them would re-import the journalism dimension ADR-010 removed through a side door, break ADR-020's dimensional independence (each sub-ingestor carries one source's own voice), and add little signal (off-domain entries are dominated by media-mentions; a genuine off-domain op-ed is excerpt-only anyway).

### Decision

A WordPress basis-set source contributes **only content hosted on its own domain family.** `_wp_post_to_article` drops any record whose `link` host is outside `expected_host`'s family **before any body fetch** (strip a leading `www.` from `expected_host`; keep iff `link_host == base` or ends with `"." + base`). This supersedes ADR-030's keep-on-excerpt refinement: off-domain records are dropped outright.

This is a **provenance filter on source identity, not a topical filter** — "did this source publish this?", never "is this about macro?" — so ADR-020's no-pre-cluster-topic-gate holds; scope is still decided post-clustering by the JEL classifier.

Checking *before* fetch is load-bearing: (1) it prevents silently keeping the full body of a *reachable* third-party page (keep-on-excerpt only degraded gracefully when the off-domain fetch *failed*); (2) it removes cross-domain fetch-timeout drag from paywalled third-party links, shortening the Brookings long-pole walltime.

The rule lives in the **shared** `_wp_post_to_article` helper, applying uniformly to all three WP-REST callers — Brookings, Liberty Street Economics (`fed_ny`), FRBSF (`fed_sf`); for the two Fed blogs it is a no-op that makes the invariant explicit. On-domain body-fetch failures still **raise** (ADR-030 preserved): every remaining fetch is on the source's own host, so a failure there is a real outage.

### Consequences

- Brookings (and any WP source) is strictly own-domain — closing the ADR-010 journalism re-import side door and preserving ADR-020 dimensional independence.
- **Reversal of an ADR-030 sub-decision**: `expected_host`'s semantics change from "keep-on-excerpt if off-domain fetch fails" to "drop if off-domain."
- The in-flight Brookings raw file can be corrected **post-hoc** by filtering off-domain lines with the identical host-family predicate, avoiding a ~15h re-run; if that run TIMEOUTs with no usable output, the re-run picks up the new rule (and runs faster for skipping the paywall stalls).
- No config/threshold/seed change; control-flow + scope only. Standing contract for any future WordPress ingestor: own-domain only, enforced in the shared helper.

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

A pre-downstream audit (2026-06-15) found every volume curve the dashboard plots — and every series the SIR/logistic/Bass lenses fit — is a **raw weekly article count**, while the corpus is not stationary (more basis-set sources are active in 2024 than 2013; per-source cadence drifts). Apparent rise is therefore confounded with corpus growth, biasing every curve and cross-narrative comparison toward recent narratives. The original normalizer (`dynamics/normalize.py`, ADR-008) divided by the **RavenPack** weekly volume — dead code since ADR-016 removed RavenPack/WRDS.

Three audited gaps are entangled: (#1) base-rate normalization is absent; (#2) cross-narrative dynamics (seeding/competition/transition) is absent; (#3) source-provenance / lead-lag is unquantified. All three recompute from the persisted `clusters.parquet` / `embeddings.npy` — only embed+cluster is irreversible — so this is a scope decision before the one-shot downstream run, not a re-embed.

### Decision

**1. Normalize by a single, global, whole-corpus base rate — expressed back in count units.** `N(d)` = unique articles published day *d* across the **entire embedded corpus** (including the BERTopic outlier bucket and out-of-scope clusters — the denominator of *all* discourse). Centered 7-day mean → `N̄(d)` (kills weekend zero-division and the Mon–Fri sawtooth; same window as `dynamics.smoothing_window_days`). `N̄_mean` = mean of `N̄` over the corpus span. Adjusted volume: **`adj_c(d) = c(d) / N̄(d) × N̄_mean`** (0 where `N̄(d) = 0`). Indexing back to `N̄_mean` rather than fitting the bare fraction removes the corpus-growth trend **while keeping article-count units**, so the PyMC priors (logistic `L`, SIR `N_pop`/`I0` — count-anchored per ADR-019/config) and AICc diagnostics stay valid unchanged: no prior re-anchoring, no schema bump.

**2. The adjusted series is what both the fit AND the display use.** No second "raw" curve on the headline chart; the y-axis is captioned **corpus-size-adjusted discourse volume**, not "articles/week". True raw counts remain recoverable from `clusters.parquet` for audit.

**3. The base rate is global and singular — one `N̄(d)`, one `N̄_mean` for all narratives** — which is what makes gap #2 valid when built: every adjusted curve is on the same yardstick (a per-narrative denominator would foreclose it). Building the cross-narrative model itself is **deferred**; it recomputes from persisted artifacts.

**4. Lead-lag (#3) is deferred, with one binding constraint**: any institutional-vs-press lead-lag (vs the ADR-042 Media Cloud series) or first-appearance statistic must consume the **adjusted** institutional series, or corpus growth re-enters as a fake lead. Per-source first-appearance recomputes from `clusters.parquet`'s `source_id`.

**5. Rewrite `normalize.py` to the live contract.** Drop the RavenPack denominator (ADR-016) and the `above_threshold` count gate (3/wk over 4wk AND 50 cumulative), which conflicts with ADR-019's report-don't-gate stance (low-volume clusters get a fit with a wide credible interval instead). Keep `compute_source_contamination` as a diagnostic.

### Consequences

- **Closes #1 everywhere** — fitted and displayed series are corpus-growth-adjusted; R₀ and stage no longer inherit the confound.
- **#2 and #3 stay out of the one-shot** but are unblocked by the single global denominator. The memory note `project_analysis_gaps.md` tracks #4 (stage-confidence) and #5 (anchor-recovery surfacing) — untouched here.
- **Priors / config unchanged** — the adjustment is a fixed deterministic transform, not a fitted knob (ADR-040 respected).
- **The denominator choice is a judgment call**: total-corpus treats "total written discourse" as the base of spread, matching the SIR framing (penetration of the whole stream); an in-scope-only denominator would measure share-of-macro-discourse instead. Revisiting is a new ADR.
- **Lands via the new analysis driver** (the CLI-gap subcommand): normalization computed there and fed to the fitter, so the one-shot run produces adjusted curves with no further wiring.

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

Three loose ends from the per-narrative life-cycle view: (1) **inconsistent market series** — narratives showed different FRED overlays (VIX / 10y yield / 10y–2y spread) only because `scripts/_sample_dashboard_artifacts.py` rotated series by `hash(label) % 3`; ADR-041 never fixed a canonical series. (2) **`wave_count` label** — shape-facts reports `wave_count = len(find_peaks(y, height=½·peak))` (half-maximum convention, ADR-019/039), but "wave count" reads as a modeled quantity when it is a plain peak count. (3) **coverage** — ADR-041 framed Granger as on-click, ADR-043 made it precomputed, production never wired it (`run.py` step 5 built artifacts with `markets` absent); computing it for *every* narrative raises a multiple-comparisons question.

### Decision

1. **VIX is the canonical market series.** `VIXCLS` is the default overlay for every narrative and the **only** series the Granger/lag readout is computed against — the broadest single risk-sentiment gauge, free on FRED, defined across the whole 2010-present window. Other series (10y, 2y, 10y–2y spread, HY/IG spreads) remain display-only toggles with **no lag test**, so the precedence claim is made once per narrative, against one series.
2. **Compute the overlay + bidirectional Granger for every narrative**, baked into the artifact (ADR-043), against the adjusted weekly volume (ADR-045). Fewer than `_MIN_OBS_PER_LAG·max_lag` (5·4 = 20) weekly observations → **"insufficient data"** rather than a fitted number. The lag test stays weekly-resolution and first-differenced (ADR-041); no daily resolution or per-series tuning.
3. **Strictly descriptive framing, with a multiple-comparison caveat.** One bidirectional test per narrative is a large test family; some "significant precedence" verdicts are false positives at α=0.05. No formal family-wise/FDR correction (consistent with ADR-040 — descriptive educational tool, not a registered inferential claim); instead the UI keeps the "this shows timing, not cause" caption plus a caveat that individual verdicts are suggestive, not confirmatory.
4. **Relabel `wave_count` → "peaks (≥ ½ max)"** in the front-end shape-facts list. Artifact key and computation unchanged (ADR-019/039); only the human label changes.

### Consequences

- `scripts/_sample_dashboard_artifacts.py` always emits VIX; sample artifacts match the production contract.
- `run.py` step 5 builds a VIX overlay per fitted narrative via `MarketsOverlay.from_env()` and passes the `markets` dict into `build_dashboard_artifacts`. FRED is free and validation-tier; the overlay is post-corpus, so ADR-020 is untouched.
- Single-series, single-test-per-narrative bounds the multiple-comparison surface to one family of `n_narratives` tests rather than `n_narratives × n_series` — the most defensible universal design without a formal correction.
- No artifact-schema change: `markets` is an already-defined optional block, now populated for real narratives.
- Narratives under 20 usable weeks show "insufficient data" for the lag readout but still get the VIX overlay drawn.

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

The first full-corpus cluster run produced 7,242 non-noise BERTopic topics from ~429k chunks at the locked, library-default `min_cluster_size=10` (ADR-019). The article-per-topic distribution is sharply power-law: median 7 articles, p90 27, max 492; only 268 topics have ≥50 articles, 79 have ≥100. Two problems follow: (1) **identifiability** — the lenses fit 3-parameter curves (logistic L/k/t₀, Bass p/q/m, SIR β/γ/I₀), and the ~10-observations-per-parameter heuristic implies ~30+ informative points before a fit means anything; a ~7-article topic is a near-flat series, so fitting the long tail emits noise dressed as dynamics. (2) **presentability** — 3 NUTS fits × 7,242 blows the 12 h analyze budget, and 7,242 nodes is unnavigable on the map/narratives/emerging/search. Raising `min_cluster_size` would "fix" the count but is exactly the hand-tuning ADR-040 forbids.

### Decision

Add a post-clustering **fit/display floor**, `dynamics.min_articles_to_fit` (default **42**). Only non-noise clusters with at least that many *unique articles* are fit, staged, and surfaced; sub-threshold clusters are retained verbatim in `clusters.parquet` and counted, but get no dynamics, stage, map point, story card, or search entry.

The floor is set by the **identifiability bound** (~30+), not navigability; within that band the value is fixed by convention to the project's `reproducibility.global_random_seed` (**42**) — a single, non-arbitrary anchor that clears the bound with margin, pinned to an existing constant rather than reverse-engineered from the output.

- Clustering is **untouched** — `min_cluster_size` and every BERTopic/UMAP parameter stay at ADR-019 defaults; stability and anchor-recovery metrics are still computed on the full clustering. The floor is a post-clustering selection, fixed a priori and **never** adjusted to improve anchor recovery (ADR-040 holds).
- `run_analysis` sets `fit_ids` to the ≥floor set; since `build_dashboard_artifacts` and centroids/UMAP/JEL/similar all key off `fit_ids`, restricting it thins the entire front-end surface in one place.
- Transparency: the index artifact carries `n_clusters_total` and `min_articles_to_fit`, so the data page reports "N detected, M surfaced (≥ floor articles)".

### Consequences

- 42 surfaces a few hundred narratives (between the measured ≥30 → 641 and ≥50 → 268; exact count logged by `analyze`) — a navigable map, a fast `analyze` well within 12 h, every cluster still in the corpus artifact.
- Map edges no longer render statically: the ADR-044 map draws each node's `similar_edges` only on hover (focus-lit, `mountMap3d` in `web/src/lib/chart.ts`), so node count no longer trades off against edge-hairball density — which is why the floor is governed purely by identifiability rather than pushed higher for graph legibility.
- The floor is a single config value; changing it is a presentation/identifiability call recorded here, not a model tune.
- A genuinely new narrative below 42 articles will not appear in the emerging lens until it crosses the floor — a deliberate static-corpus tradeoff; Phase-6 live emerging detection (Media Cloud, ADR-016) is a separate layer this floor does not gate.
- No artifact-schema break: existing fields unchanged, two optional index fields added.

---

## ADR-052: Lifecycle stage is a model-free attention-trajectory classification

- **Status**: Accepted
- **Date**: 2026-06-19

### Context

The first full-corpus `analyze` run staged 365 narratives as **253 growth / 112 dormant / 0 decay** — a compound failure.

**Proximate cause (a crash, not a result).** All 365 SIR fits raised `AttributeError: module 'pytensor.tensor' has no attribute 'scan'` (`fitting.py` calls `pt.scan(...)`; `scan` lives at `pytensor.scan`). The broad `except Exception` in `_fit_model` recorded each as ordinary `converged=False` — an ADR-030 fail-loud gap: a code error that killed *every* cluster logged 365× as benign non-convergence. Staging fell back to logistic, whose implied `R_0 = 1 + k/gamma` with `k >= 0` (HalfNormal) is **structurally >= 1**, so decay was mathematically unreachable: converged logistic → growth (253), failed → dormant (112).

**Deeper cause (R_0 is the wrong quantity).** R_0 = beta/gamma is the *basic* reproduction number — whether a narrative ever spread. `R_0 > 1` is exactly what *produces* a rise-and-fall hump, so a risen-and-fallen narrative gets mislabeled "growth." Decay is a *current-phase* statement (effective `R_t` crossing below 1 at the peak), and the corpus is full of it: 357/365 rose-then-fell, the median narrative is 55% of its span past peak, 31% decline over their last quarter.

**Framing has diverged.** The project is now an educational/analysis tool; Shiller's narrative economics and the SIR contagion analogy remain a *lens*, not the organizing law.

### Decision

1. **Stage is model-free**: the narrative's recent attention trajectory, decided by robust non-parametric tests on the smoothed daily volume series over a recent window `W`, independent of any fitted model. "Now" = the corpus end date; `W` = the existing 4-week emerging horizon, clamped to the series span.

2. **Two rank-based tests over `W`**: **trend** — modified Mann–Kendall with the Hamed–Rao (1998) autocorrelation correction (7-day smoothing induces serial correlation), with Theil–Sen slope on `log(1+y)` as the display growth-rate magnitude; **level** — Mann–Whitney U comparing the recent window to the narrative's own lowest-activity baseline window.

3. **Four mutually-exclusive states**: **growth** (significant upward trend), **decay** (significant downward trend), **stable** (no significant trend, level elevated above the narrative's own floor — perennial topics at steady volume), **dormant** (no trend, level at floor). `emerging` stays an **orthogonal recency flag** (significant upward trend AND first article within `W`) on the existing `is_emerging` field, not a fifth state; live emerging detection is Phase-6's Media Cloud job (ADR-016).

4. **Significance, not magnitude**: both splits use a field-standard `alpha` (0.05); no tuned volume thresholds; the only horizon (`W`) is reused from the emerging window. ADR-040's no-hand-tuning basis is preserved (the old `growth_min_r0` threshold no longer gates staging).

5. **Fitted models are display-only lenses**: logistic / SIR / Bass (ADR-039) no longer touch the stage label; `R_0` becomes the SIR lens's headline ("was it contagious?"), not the stage driver. The four-lens panel is unchanged.

6. **Reframe**: stages are described as *attention trajectory*, not epidemic compartments. Shiller (2017/2019) + SIR is the marquee interpretive lens; the growth-rate ↔ `R_t` link (Wallinga & Lipsitch 2007: `sign(R_t − 1) = sign(r)` regardless of the generation interval) is an optional connection, not the justification.

7. **Fail-loud hardening (ADR-030)**: a model lens that fails on *every* cluster must raise, never be silently recorded as per-cluster non-convergence.

### Consequences

- **Decay becomes expressible and abundant**; the dormant/decay boundary is a clean significance call, so the two cannot collide.
- **Dormant stops being polluted by fit-failure** — all 112 prior "dormant" clusters were dormant only because logistic did not converge; dormant now means "the series is quiet."
- **Robustness dividend**: a sampler failure now yields a broken SIR *display* but correct stages.
- **New `stable` state** needs a fourth colour/label in the front end (`Stage` union + `STAGE_COLOR`/`STAGE_LABEL` in `web/src/lib/data.ts` and `chart.ts`), plus a methodology/UI copy pass and an "as of <generated_at>" date line.
- **Left-censoring caveat**: a narrative already high before 2010 that stayed high has no in-window floor and may read dormant — rare, accepted (consistent with ADR-051's static-corpus tradeoff).
- **Dependency**: modified Mann–Kendall is not in scipy — either `pymannkendall` (BSD, allowed under the core-pipeline free/reproducible rule) or an in-repo Hamed–Rao correction on `scipy.stats.kendalltau`/`theilslopes`/`mannwhitneyu`.
- **Supersession**: supersedes ADR-002's staging-selection clause and ADR-019 §E's `R_0`-threshold staging. ADR-039 (four-lens display), ADR-045 (base-rate normalization), and ADR-051 (fit/display floor) unchanged. Amends `src/mnd/stages/classify.py`.

---

## ADR-053: SIR fit on a weekly integration grid + SIR-only reduced inference budget

- **Status**: Accepted
- **Date**: 2026-06-22

### Context

ADR-052 demoted SIR `R_0` to a display-only lens headline and fixed the `pt.scan` crash (commit `09bda0f`) that had silently made every SIR fit a no-op — so the next run will *actually* sample SIR for the first time. That exposed a compute wall: SIR is integrated for NUTS by a `pytensor.scan` discrete-time Euler loop with `n_steps = T − 1` (`fitting.py`), so its gradient cost is `O(series length)`; logistic and Bass are vectorized/closed-form. The Jun-19 `dashboard_full` produced 365 fittable clusters with series spanning their full active range — median ~5077 days (mean 4693, max 6000), since macro topics recur across the 16-year corpus. At the production NUTS budget (draws 2000 + tune 1000, 4 chains, `target_accept` 0.95) a single ~180-day fit did not finish in 13 min locally; a ~5000-day fit is ~28× that scan length → hours per cluster × 365 → hundreds–thousands of A100-hours, over the 12 h SLURM wall, and the per-cluster checkpoint/resume (commit `b1bc1b2`) has no mid-fit checkpoint. Jun-19 only "completed" because SIR was a no-op.

### Decision

1. **Weekly integration grid for SIR only.** Bin the already-7-day-smoothed daily series to a weekly grid (mean over `dynamics.sir_fit_grid_days = 7` days) before the SIR scan, cutting `n_steps` ~7×. The displayed volume curve and the model-free stage stay daily — only SIR's internal integration resolution changes.
2. **`R_0` is grid-invariant; time-unit outputs converted back to days.** The weekly step makes fitted `beta`/`gamma` per-week rates; `R_0 = beta/gamma` is dimensionless and reported unchanged. For the displayed curve and peak time the rates are divided by the grid and integrated on the daily grid via the existing `sir_prevalence` / `sir_peak_time`, keeping the ADR-039 daily-grid contract.
3. **Population scale held fixed.** `N_pop` is computed from the daily total, not the binned series — amplitude and identifiability identical; only integration resolution changes.
4. **SIR-only reduced inference budget.** SIR samples under a separate `dynamics.sir_inference` block (draws 500, tune 500, chains 2, `target_accept` 0.9); logistic and Bass keep `dynamics.inference` (2000 / 1000 / 4 / 0.95). A ~4–6× multiplier applied only to the expensive, display-only lens.
5. **The no-tuning rule (ADR-040) is untouched.** Anchor recovery is a clustering metric the grid/budget cannot change; a sampler budget is a Monte-Carlo-precision setting — a fit-mechanics decision (like ADR-051), not a methodology lock-in amendment.

### Consequences

- **Tractability.** Each SIR fit finishes well within a 12 h wall, so checkpoint/resume completes the run across resubmissions (the guarantee is sub-wall-per-fit, not a specific minutes figure).
- **Cache invalidation is automatic.** The fit-cache key hashes `repr(cfg["dynamics"])` (`run.py` `_fit_signature`); the new keys invalidate every stale Jun-19 SIR entry.
- **Accuracy caveat (accepted).** Weekly Euler is a coarser ODE approximation — acceptable for a decorative lens whose headline is dimensionless `R_0`, with the display curve re-integrated daily. Fewer draws + lower `target_accept` may push borderline fits below the convergence gate (`ess_bulk > 400`, `R-hat < 1.05`) — more `R_0` "n/a"; the front end already renders a missing lens, and logistic remains the fallback `R_0` headline.
- **Convergence is now observable.** The first weekly-grid run is the first real measurement of SIR's convergence rate on this corpus; if it converges on almost nothing, dropping it (its own ADR) is the obvious follow-up.
- **Scope.** Amends the SIR fit mechanics of ADR-039 and the SIR portion of the ADR-019 inference settings; relates ADR-052, ADR-051, and the `b1bc1b2` checkpoint/resume. Amends `src/mnd/dynamics/fitting.py` and `config/config.yaml`.

---

## ADR-054: Cross-document boilerplate stripping at the filter stage (sub-document recurring-passage removal)

- **Status**: Accepted
- **Date**: 2026-06-25

### Context

Whole-document near-duplicate removal (ADR-019, MinHash LSH at Jaccard 0.85) cannot catch a disclaimer, donation disclosure, media-contact block, or speech caveat repeated verbatim *inside* otherwise-distinct documents. Lexically identical across hundreds of documents, these passages dominate the c-TF-IDF signal and produce artifact clusters keyed on boilerplate. Observed in the Jun-19 bake: a 458-article Brookings cluster whose representative text is the donation-influence disclosure, and a BIS cluster keyed on the speaker disclaimer ("The views expressed are those of the author and do not necessarily reflect those of the BIS"). The same passages impoverish the JEL representation (ADR-046) and inflate single-source share. The fix must remove the *repetition*, not the *topic* — ADR-020's no-pre-cluster-topical-filter prohibition stands.

### Decision

Add a sub-document recurring-passage strip at the filter stage, immediately after MinHash dedup and before the filtered corpus is persisted (`scripts/run_pipeline.py` `cmd_filter`). New module `src/mnd/filtering/boilerplate.py`.

1. **Granularity: normalized sentences** (lowercase, whitespace-collapsed, surrounding punctuation stripped). Only sentences with ≥ `min_sentence_words` (6) tokens are eligible — short phrases collide legitimately.
2. **Criterion: cross-document frequency.** A normalized sentence appearing in ≥ `min_doc_frequency` (25) *distinct documents* is template and removed from every document. This is the template-detection criterion of Bar-Yossef & Rajagopalan 2002 and the boilerplate-removal lineage of Kohlschütter et al. 2010; the sub-document analogue of the Broder 1997 / Henzinger 2006 whole-document dedup locked in by ADR-019; consistent with Lee et al. 2022.
3. **Document count, not topical content, is the only input.** Real macro prose carries document-specific numbers, dates, and entities, so its exact normalized form rarely recurs across ≥25 documents; only invariant template text crosses the line. ADR-020's invariant is intact — this extends the ADR-019 dedup family, not a scope gate.
4. **Pure-boilerplate articles are dropped, but only if actually stripped**: stripped body below `min_content_words` (50) AND at least one sentence removed. A naturally short article from which nothing was stripped is always kept — under-capture is the failure mode that matters.
5. **Auditable removal (ADR-030).** Logs sentence-type/instance/modified/dropped counts and persists `boilerplate_report.json` beside the filtered parquet, listing every stripped sentence with its DF and every dropped `article_id`.
6. **Config-driven, no tuning.** Knobs under `filtering.boilerplate` (`enabled`, `min_doc_frequency`, `min_sentence_words`, `min_content_words`) — corpus-hygiene parameters, none set against the anchor metric (ADR-040). Thresholds are absolute document counts: template DF grows with the corpus while coincidental content repetition does not, so the floor stays valid as the corpus grows.

### Consequences

- **Artifact clusters dissolve at the root** — the Brookings- and BIS-disclaimer members re-cluster by actual content or fall below the ADR-051 fit floor.
- **JEL and source-mix improve for free** — c-TF-IDF terms and single-source share stop being dominated by template text.
- **Recompute required**: the strip rewrites bodies and `word_count`, so it lands with the pending catch-up re-ingest + re-embed.
- **Bounded false-positive risk, fully logged**: stripping an invariant template sentence that is technically content (e.g. a standing FOMC caveat) is possible but low-cost and enumerated in the report.
- **Scope**: extends ADR-019 to sub-document repetition; orthogonal to ADR-020; relates ADR-030/046/051. Adds `src/mnd/filtering/boilerplate.py`, a `filtering.boilerplate` config block, and one call in `cmd_filter`.

---

## ADR-055: Richer JEL cluster representation — c-TF-IDF terms + BERTopic representative documents

- **Status**: Accepted
- **Date**: 2026-06-25

### Context

JEL scope (ADR-020/046) is assigned per cluster by nearest-prototype against the AEA JEL code descriptions; the representation was the cluster's c-TF-IDF terms alone. Two failure modes: (1) **thin signal misses real macro clusters** — with terms only, the natural-rate / r-star cluster and the Basel cluster both fell to the "Y" (miscellaneous) catch-all instead of E and G; (2) **catch-all asymmetry** — "Y — Miscellaneous Categories" is a two-word prototype against ~60-word real-code descriptions, so an impoverished representation is drawn to it. (The earlier all-Y collapse was a separate parquet round-trip bug, fixed in 93ddaa4.) JEL is a display flag, not a gate (ADR-046), but sending r-star and Basel out of scope is a visible error worth fixing at the representation level rather than by tuning prototypes.

### Decision

Enrich the representation passed to `classify_clusters` with BERTopic's representative documents: the c-TF-IDF terms followed by the top `clustering.jel.n_representative_docs` (3) `Representative_Docs`, each a bounded leading excerpt.

1. **Source: BERTopic's own `Representative_Docs`** (already in `topic_info`) — consistent with the model's notion of the cluster; no ad-hoc re-ranking, no clustering→display dependency.
2. **Terms-first ordering** — terms always survive the embedder's sequence cap; document text fills the remaining budget.
3. **Taxonomy unchanged; Y kept.** Dropping Y was tested and rejected: without a miscellaneous home, genuinely off-topic clusters (Syria, pollution, drug trafficking) leak into E/F/G/H. The richer representation makes Y stop over-attracting on its own.
4. **Config-driven, no tuning**: `clustering.jel.n_representative_docs` is the only new knob — a representation-construction choice, not tuned against anchor recovery (ADR-040 holds).

### Consequences

- **Macro recall improves; Y normalizes.** On the Jun-19 narratives (0.6B proxy, title+excerpt as a stand-in), all nine macro probes land in scope (r-star → E and Basel → G recovered from Y), pollution stops leaking, and Y falls from 75 clusters to 43 with no taxonomy change. Production uses the 8B embedder and the fuller `Representative_Docs` text, expected at least as discriminating.
- **Residual imperfection is acceptable and non-gating**: one proxy leak remains (drug-trafficking → F, a genuine JEL ambiguity); the other apparent leak is the BIS-disclaimer cluster, eliminated upstream by ADR-054. A residual mislabel is shown with its code, never dropped (ADR-046).
- **Recompute required**: the representation is built at analyze time from `topic_info` and takes effect on the next bake/re-embed, where the doc text is already boilerplate-cleaned (ADR-054).
- **Scope**: amends the representation step of ADR-020/046; AEA taxonomy and {E,F,G,H} scope unchanged; relates ADR-054 and ADR-019. Adds `clustering.jel.n_representative_docs`, a `_representative_docs_from_topic_info` helper, one changed call in `dashboard/run.py`; corrects the stale `jel_classifier` docstring that still described JEL as a dynamics gate.

---

## ADR-056: Human-readable narrative names — display-layer LLM titling over c-TF-IDF labels

- **Status**: Accepted
- **Date**: 2026-06-30

### Context

Every surfaced narrative is labelled with BERTopic's default — cluster id + top c-TF-IDF terms, e.g. `23_nps_lands_acres_park` or `27_expressed speech_bank speech_speaker necessarily_reflect bis`. Fine internally, but the product goal is an educational tool for a non-expert reader, and a wall of underscore-joined stems is not a story name. Constraints: (1) the no-paid-dependency rule binds data fetching + analysis only — the display layer is exempt; (2) reproducibility — the LLM step must not sit on the analysis path, and the published artifact must rebuild without re-calling the model; (3) no hand-tuning toward anchor recovery (ADR-040) — the prompt must not smuggle in anchor names; (4) grounding — a title must describe the cluster's actual content, not invent a plausible macro story (ADR-046); (5) graceful degradation — like the ADR-047/048 overlays, no key means fall back to the c-TF-IDF label, never block a bake.

### Decision

Add a display-layer **narrative naming** step: each surfaced cluster's existing representation → a short human title plus a one-line description, via a paid LLM, cached and committed.

1. **Model + transport.** Claude Haiku 4.5 (`claude-haiku-4-5`) — cheapest current tier, ample for titling. One **synchronous** Messages call per cache miss, `temperature=0`, JSON-schema structured output (`{title, description}`). The Batches API was rejected: the committed cache makes each bake incremental, so batch throughput buys nothing while its polling lifecycle adds complexity, and at Haiku rates the 50% discount is a fraction of a cent (Batches remains a drop-in option for a cold full-corpus pass). A first-call failure (missing key, SDK, rate ceiling) aborts the pass; later one-off failures are skipped per cluster.
2. **Input is the same representation already built for JEL (ADR-055)**: c-TF-IDF terms, top representative-document excerpts, date range, source mix — nothing else. System prompt: name the cluster only from the supplied material, no outside knowledge, ≤6-word title, one factual sentence; non-economics material is named plainly, not forced into a macro framing. No anchor names in the prompt.
3. **Cache keyed on a representation hash; commit the cache** (mirroring the ADR-050 embedding cache and the per-cluster fit cache). A bake reuses unchanged clusters' titles and calls the model only for new/changed ones; the committed cache makes the static site rebuild deterministically with no key present.
4. **Additive artifact contract; front-end falls back.** `label_human` and `description` are added to the index/narrative artifacts (schema_version bump); the front end shows `label_human` when present, else the raw c-TF-IDF `label`. `label` and `top_terms` remain in the artifact, so cluster provenance stays inspectable.
5. **Display-only, never upstream.** The title never feeds embedding, clustering, JEL scope, fitting, staging, or anchor recovery — generated after clusters are fixed, from their frozen representation.

### Consequences

- **The catalog reads as stories, not term-dumps**; the macro-first relevance default (build_artifacts ordering + scope facet) decides which stories lead.
- **Reproducibility preserved**: the committed cache means a rebuild needs no API key and produces identical output; the free core (curves/stages/scope/fits) is untouched.
- **Honest about residual error**: a mislabel is a cosmetic display error shown alongside the unchanged terms and JEL code, never a gate (ADR-046 holds); out-of-scope clusters get a plain descriptive name.
- **New surfaces**: a `display.naming` config block (`model`, `enabled`, `max_title_words`, cache path), a naming module in the display layer, two artifact fields, a schema_version bump. No change to any ADR-019/020/039/045/046/051/052 analysis decision.
- **Cost + dependency**: introduces `anthropic` as a display-layer dependency and an `ANTHROPIC_API_KEY`, both gated behind `display.naming.enabled` and absent-tolerant; per-bake cost negligible.
- **Scope**: display-layer only; relates ADR-055 (shared representation), ADR-046 (flag-not-gate), ADR-043 (static-site contract), ADR-050 (cache pattern). Supersedes nothing.

---

## ADR-057: Phase-6 live emerging — press-heating detection + weekly institutional refresh (design)

- **Status**: Accepted
- **Date**: 2026-06-30 (parameters + `merge_models` mechanism settled 2026-07-01)

### Context

The Emerging view ranks narratives by `is_emerging` — a within-corpus recency flag (growth stage + last-active within the four-week window of the corpus frontier). Two limits: (1) **corpus staleness** — the frontier is the last ingest date, so "emerging" only means "recent as of the last build"; (2) **no press-led signal** — despite the ADR-042 press overlay and ADR-048 lead-lag readout, nothing flags a tracked narrative *spiking in the press right now*. Detection scaffolding exists but is unwired: `MediaCloudDetector.fetch_story_counts` and `detect_anomalies` (z-score: count above baseline mean + k·σ) in `src/mnd/detection/mediacloud.py`. Hard constraints: press text is never embedded or clustered (ADR-010); no emerging signal may feed embedding, clustering, or JEL scope (ADR-020/042/046); a weekly refresh must not leave per-source gaps (staggered per-source end dates).

### Decision (design; no pipeline code in this ADR)

Treat "emerging" as **two distinct display-only signals**, and scope out a third.

1. **Institutional onset (existing `is_emerging`), kept** — unchanged in meaning, refreshed by the weekly run (§3).

2. **Press heating (new, near-term, low-risk).** For each *already-tracked* narrative, run `detect_anomalies` on the **attention-share ratio** (robust to overall press-volume drift) using the ADR-042 per-narrative query: flag "heating in the press" when the most-recent **4-week window** (matching the institutional emerging horizon) sits ≥ **k·σ, k = 2** above the narrative's own **trailing 52-week baseline** (a year, so it carries seasonality). Surfaced in the Emerging view as a **separate signal beside** the institutional flag — never merged, so the reader can tell "our sources just started on this" from "the press is spiking on a story we already track." Recomputes entirely from the press series at bake time: no re-embed, no re-cluster, never touches embedding/clustering/scope. Window, baseline, and k are fixed config values, not tuned against anchor recovery (ADR-040); k = 2 (≈ upper 2.3% tail) is a deliberately sensitive start, captioned literally as "press attention more than 2σ above its yearly baseline."

3. **Weekly institutional refresh — build onto the existing model, don't re-cluster from scratch.** Per-source **over-fetch** delta (start each source's window before its own `max(published_at)`; dedup absorbs the overlap) → incremental embed of only the new chunks (ADR-050) → fit a model on the new-week docs and `merge_models([base, new], min_similarity=τ)`. `merge_models` **keeps every existing topic's id** — so its narrative-page URL and ADR-056 human name are stable by construction — and **appends only genuinely-new topics** (similarity to every existing topic below τ). `analyze` re-runs on the merged clusters: existing curves extend, new narratives are fit and staged, and the ADR-056 name cache pays the model only for new clusters. **The tracking invariant holds: ids, URLs, names, and histories persist, and new narratives can still form.** A full from-scratch re-fit — reconciled to the prior id set by Hungarian centroid-matching above a cosine floor — is kept only as an occasional rebuild path, never the weekly mechanism. A follow-up implementation ADR must choose τ, handle a topic that splits or merges across a weekly merge, and validate that anchors keep their ids.

4. **Scoped out: novel press-only narratives.** Detecting narratives that exist only in the press would require clustering press text (forbidden, ADR-010/020). Press stays a volume signal over the institutional narrative set.

### Consequences

- **Sequence.** §2 (press heating) is the near-term win: display-only, buildable now from persisted clusters + live Media Cloud, gated by a new config flag and degrading to absent when unkeyed. §3 (weekly refresh) is deferred until the identity-stability approach is validated — until then the feed is refreshed by manual re-runs and captioned "as of the last build."
- **Honesty.** The caption states which signal fired. Press coverage thins before ~2017 (ADR-042 `reliable_since_year`), so heating is only computed on the reliable window.
- **Invariants preserved.** Nothing feeds embedding/clustering/scope (ADR-020/046); press text never embedded (ADR-010); values fixed a priori (ADR-040). Relates ADR-016, ADR-042/048, ADR-050.
- **Settled here.** Recent window = 4 weeks, baseline = 52 weeks, k = 2; narrative identity via BERTopic `merge_models`; Hungarian centroid-match only for occasional full rebuilds; cadence starts **manual**, moves to a **cron on RCC** once identity stability is validated.
- **Deferred to the weekly-refresh implementation ADR**: the similarity floor τ, split/merge handling across a weekly merge, and the cron schedule. Press heating needs only its own small implementation ADR.

---

## ADR-058: Peak-relative plateau test — `stable` vs `dormant` keyed to the narrative's own high-water level

- **Status**: Accepted
- **Date**: 2026-07-02

### Context

The first clean `analyze` run under ADR-052 (job 51323109, 365 narratives, ADR-052/053/054/055 fixes in place, JEL scope validated — 185 in-scope, no all-Y collapse) staged **342 stable / 23 growth / 0 decay / 0 dormant** — the ADR-052 `Level` test failing on real data. Of the 342 `stable` narratives, **100% sit below 20% of their own peak volume**; median recent-window activity is **1.7% of peak** (p25 = 1.3%) — e.g. a cluster peaking Sept-2010 at 406 articles, now at 0.3% of that, labelled `stable`. Dead narratives called stable.

**Root cause.** ADR-052 defined the `Level` test as Mann–Whitney U against the narrative's **lowest**-activity baseline window ("elevated above its floor?") while describing `stable` as a "high plateau." Incompatible on this corpus: institutional sources never fully drop a topic, so every narrative keeps a low nonzero tail that is trivially "above the quiet floor" → essentially every no-trend narrative reads `stable`, `dormant` is nearly unreachable, and `decay` doesn't fire because a long-faded narrative is low-*flat*, not falling.

### Decision

Amend ADR-052 §2 (`Level` test) and §3 (`stable`/`dormant`). The trend test (Mann–Kendall → `growth`/`decay`) and the four-state vocabulary are unchanged; only the no-trend split is corrected.

1. **The reference flips from the quietest window to the narrative's own high-water window**: mirroring the minimum-sum width-`W` baseline construction, take the **maximum-sum** width-`W` window as the peak reference. Still the narrative judged against its own dynamic range — no absolute magnitude threshold.

2. **`stable` vs `dormant` becomes a peak-relative *level* comparison, not a rank test.** A Mann–Whitney U of recent vs peak window was implemented first and **empirically rejected**: the smoothed daily series is zero-heavy, so two tie-dominated 28-point windows give no power — narratives at a *tenth* of their peak returned `p ≈ 0.15–0.72` and stayed `stable` (265/365 on the first pass). The split is by level: **stable** — no significant trend AND recent-window mean ≥ `dormant_peak_fraction` × peak-window mean; **dormant** — no significant trend AND below that line.

3. **`growth` / `decay` / `emerging` unchanged.**

4. **One new parameter: `stages.dormant_peak_fraction = 0.25`.** A **definition** of where "faded" begins on the narrative's own scale, **not** a hyperparameter tuned for anchor recovery (ADR-040 binds tuning-for-recovery; this line is never touched by the anchor/fizzled set). The dormant share moves smoothly with it (≈8% at 0.10, ≈45% at 0.25, ≈85% at 0.50), so it is stated transparently and surfaced in the UI ("N% of its own peak"). `W` is still reused; the `max`-sum peak-window selection mirrors the prior `min`-sum floor construction (whole-life-inside-`W` and `W < n < 2W` prefix guards carry over).

### Consequences

- **Dormant becomes the honest majority** — most narratives peaked and faded. `stable` is reserved for narratives genuinely near their own peak; `growth` (23) is unaffected. `decay` stays rare by construction ("currently mid-decline over a 4-week window" is a narrow transient state; fully-faded = `dormant`); if a future run shows *exactly* zero decay, revisit the trend-window length (tracked separately).
- **Matches ADR-052's stated "high plateau" intent** — a correction to make the code do what ADR-052 claimed.
- **Front-end copy**: the stage glossary (`web/src/pages/guide.astro`) and stage-detail row (`web/src/pages/narratives/[id].astro`) reworded from floor- to peak-relative, showing "N% of peak level". `stage_detail` keys change: `recent_elevated` → `recent_near_peak`, `level_p` → `recent_peak_ratio`, `baseline_level` → `peak_level`, plus a new `dormant_peak_fraction`.
- **Left-censoring caveat slightly relaxed**: a pre-2010-high narrative that stays high now reads `stable`, more correct than the prior `dormant` misread.
- **Scope**: analysis-layer only — no re-embed, re-cluster, or change to JEL/fitting/anchor recovery. Amends `src/mnd/stages/classify.py` and the two front-end copy sites. Supersedes ADR-052 §2/§3's floor-relative `Level` clause; the rest of ADR-052 stands.

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

The first clean run under ADR-052/058 fit logistic and Bass acceptably (69% / 79% converged) but **SIR converged on 0 of 365 clusters** — every fit hit the sampler's exception path (empty `failure_reason`, no `R_0`, no AICc). Two causes, found by local reproduction:

1. **The γ→0 ridge.** The SIR priors were `HalfNormal`, which puts mass at γ→0; since `R_0 = β/γ`, γ near zero sends `R_0` and the infected compartment to infinity and the discrete Euler scan overflows to NaN.
2. **The 14-year scan.** The **median fit-series is 13.9 years (99% span > 3 years, 88% > 8)** — a BERTopic topic almost always has stray articles near 2010 and 2026, so its active span covers most of the corpus while the real signal is a concentrated hump. The SIR Euler scan runs ~855 weekly steps over mostly zeros; error compounds and the sampler NaNs or grinds at maximum leapfrog depth for tens of minutes. (The same sparse-tail pathology that broke staging in ADR-058.) Logistic and Bass are closed-form, so length is irrelevant to them.

An "only fit SIR on outbreak-shaped clusters" filter was **rejected** as a researcher-tuned distinction inconsistent with the other two lenses (fit on every cluster, convergence-gated uniformly).

### Decision

1. **Fit window = the central `1 − α` of cumulative attention mass** (`dynamics.fit_window_mass_alpha = 0.05`), for **all three lenses**: drop the sparse leading/trailing stragglers, keep the whole active lifecycle. Multi-wave narratives keep all their humps (a two-spike narrative fits both; single-wave models fail the gate while shape-facts reports `wave_count = 2`). "Central 95%" reuses the project α = 0.05 (the trend-test threshold) — no new tuned parameter. Each fitted curve is reprojected onto the full daily grid (nulls outside the window, peak-time shifted by the offset). **Staging (ADR-058) and the displayed volume series stay on the full span** — only the fitted lens curves are windowed.

2. **SIR numerical robustness** (SIR-only):
   - **LogNormal β, γ priors** centered on the field-anchored config means (β 0.3, γ 0.1; Bjørnstad 2018), replacing `HalfNormal` — strictly positive, no mass at γ→0, mirroring the Bass lens's LogNormal rates.
   - **Adaptive integration grid**: `grid = max(sir_fit_grid_days, ⌈window / sir_max_grid_steps⌉)`, bounding the Euler scan at `sir_max_grid_steps = 200` steps regardless of window length — a numerical step-count bound applied uniformly, not a data-dependent applicability filter.
   - **`max_treedepth = 8` fail-fast cap** on the SIR NUTS sampler: an unfittable cluster is marked non-converged in seconds. (LogNormal removed the NaN crash that used to make bad fits fail fast; the cap restores fast failure without the crash.)
   - **Fuller budget** (draws 1000 / tune 1000 / chains 4 / target_accept 0.95), affordable now that the window + adaptive grid make each fit short — a sharp cluster reached R-hat 1.010 / ESS 247 at half this budget.

3. **The convergence gate is unchanged and uniform** — R-hat < 1.05 **and** ESS > 400 (Vehtari et al. 2021) for all three lenses. SIR converges on genuinely outbreak-shaped narratives and fails the gate elsewhere; no eligibility threshold anywhere.

### Consequences

- **SIR becomes an honest, consistent lens** — converges where the data supports a single outbreak, grays out ("sir (no fit)") elsewhere. The front end already handles per-lens non-convergence (`[id].astro`); no UI change.
- **Displayed lens curves span the active lifecycle**, not 14 years of flat line with a tiny bump.
- **No new tuned parameter touching methodology**: the window α reuses 0.05; grid/tree-depth are numerical settings that cannot affect anchor recovery (ADR-040 holds).
- **Fit cache invalidated**: `cfg["dynamics"]` changed, so `run.py`'s `_fit_signature` re-fits all lenses on the next analyze.
- **Validation is on RCC, not local** — local Mac PyMC sampling of the SIR scan hangs (20+ min/cluster); the fix's direction was validated locally on a sharp cluster (R-hat 1.010), full convergence rates read from the RCC re-fit.
- **α tail sensitivity, tracked**: α = 0.05 trims 2.5% of mass each side, which clips the extreme rise/decay tips SIR uses for γ; if the RCC re-fit shows over-clipping, α = 0.02 (central 98%) is the one-line-config fallback.
- **Supersession**: supersedes ADR-053 (fixed weekly grid + reduced SIR budget); amends ADR-039 (lenses now windowed) and ADR-052/058 (staging unchanged; shared sparse-tail root cause noted). Amends `config/config.yaml`, `src/mnd/dynamics/fitting.py`, and METHODOLOGY §7.

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

> **Course-correction (2026-07-03, same day).** An earlier draft claimed the
> closed form "recovers R₀ to ~1%" — a circular test (fitting the KSSIR curve to
> KSSIR-generated data). Against a *numerically integrated* SIR, R₀ is **not
> identifiable** from a single attention bump: free amplitude drives the profile
> likelihood monotonically to R₀→1. This is intrinsic — recovering R₀ needs an
> independent removal rate γ, which one curve's shape does not pin. The
> Euler-scan fit shared this (its R₀ = β/γ was pinned by the LogNormal priors,
> mean ≈ 3, not measured), and the same disease priors contaminated the logistic
> lens (its R₀ = 1 + k/γ borrowed the SIR γ). Resolution: **drop R₀ entirely**
> (and J∞, bijective with R₀ and needing the unobservable population N), retire
> the disease priors, and report only curve-identifiable quantities in real units.

### Context

SIR was the compute pole of the analysis layer: its mean function was a
`pytensor.scan` Euler integration re-run on every leapfrog step of every NUTS
draw — measured at ~23 min/cluster × 365 clusters ≈ 140 CPU-h, overrunning the
18 h caslake wall and recurring on every weekly re-fit. Logistic and Bass are
closed-form and cost seconds. Schlickeiser & Kröger (*J. Phys. A* **53** 505601,
2020) derive an accurate analytic solution of the constant-reproduction-factor
SIR model whose prevalence I(τ) is elementary on both branches — an exponential
rise (their eq 88) meeting a shifted `cosh⁻²` decay (eq 76) — and asymmetric,
so it stays visually distinct from the logistic (unlike the symmetric 1927
`sech²` approximation). A scipy-only prototype confirmed: least-squares fit
1–3 ms/cluster; 1–4% nRMSE against numerical SIR for R₀ ≳ 2; R₀ itself not
identifiable (see course-correction); J∞ a monotone function of R₀ and equally
unidentified.

### Decision

Fit the Schlickeiser–Kröger closed-form prevalence; drop R₀ and J∞; retire the
disease priors from SIR and logistic; report per lens only curve-identifiable
quantities in real units. SIR stays a display-only lens (ADR-039/052) under the
same convergence gate as the others.

1. `_fit_sir` fits the analytic I(τ) — no ODE, no scan — reparametrized to
   peak height, peak time, early rise rate, and late decay rate (per day).
2. Disease priors deleted (`priors.sir.{beta,gamma}_*`, the `N_pop = 2·Σy`
   fudge); replacements are data-scaled and weakly informative, matching the
   logistic lens's existing pattern — no borrowed epidemiology.
3. SIR reports rise rate (→ doubling time up), decay rate (→ half-life down),
   peak date/height, and asymmetry = rise ÷ decay. `R₀`, `J∞`, `β`, `γ` removed
   from `FitResult`.
4. Logistic de-contaminated: the `r0 = 1 + k/γ` derivation deleted; it reports
   doubling time ln2/k, inflection date `t0`, plateau `L`. Dead
   `priors.logistic.k_mean` key removed.
5. Bass unchanged — `p, q` anchored to Sultan–Farley–Lehmann 1990 (213-study
   meta-analysis), `m` observable.
6. Scan-era numerics retired (`sir_fit_grid_days`, `sir_max_grid_steps`); the
   ADR-060 fail-fast carries over, now bounding a cheap elementary model.

Staging already does not key off R₀ (ADR-052), so removal touches only the
artifact builder and front-end wiring. Rejected: the symmetric 1927 `sech²`
(collapses onto the logistic's derivative); keeping the Euler scan (the pole);
keeping R₀ as a prior-regularized readout or fixing γ to a handcrafted
news-generation constant (false precision either way); reporting J∞.

### Consequences

The 140 CPU-h pole collapses to seconds/cluster — `analyze` fits in one caslake
job and weekly re-fits are cheap (the `.fit_cache` signature keys on
`cfg["dynamics"]`, so existing SIR pickles are invalidated — expected). Every
displayed dynamics number is now a direct curve measurement or a field-anchored
Bass parameter; nothing rests on an unobservable population or borrowed
epidemiological constants. The solution assumes a single epidemic-shaped hump —
the central-mass window (ADR-060) isolates it, and non-epidemic shapes fail the
gate rather than being force-fit. Supersedes the numerical-integration mechanics
of ADR-053/060; amends ADR-039 and ADR-052's R₀-display clause. Future
candidate, noted not adopted: Hawkes self-exciting point processes (Crane &
Sornette 2008) for the exogenous/endogenous question.

---

## ADR-063: Portable weekly-update orchestration (`update` command)

- **Status**: Accepted
- **Date**: 2026-07-04

### Context

Phase 6 needs the corpus to refresh on a cadence, and the mission pivot (a public educational tool, reproducible per the README) makes **portability** first-class: forking or checking the data must not require a UChicago RCC account. Two blockers: (1) **orchestration is RCC-coupled** — the only runner is `scripts/rcc/submit_parallel_ingest.sh` (hardcoded `/scratch/midway3/ehgarver` paths, SLURM fan-out, `afterok` chaining); the `run_pipeline.py` CLI is portable, the orchestration is not. (2) **ingest has no delta mode** — one global `--start/--end` leaves per-source gaps (staggered last-captured dates), and re-fetching 2010–present weekly is absurd. Incremental embedding already reuses vectors keyed on `(chunk_id, text_sha1)` (ADR-050), and a weekly delta is small (a few hundred articles) — no fan-out or A100 needed. Settled by the Phase-6 scoping discussion (2026-07-04): portable single-process command; `merge_models` re-clustering deferred (ADR-057 §3); schedule documented backend-agnostically, not auto-enabled.

### Decision

1. **A single-process `run_pipeline.py update` command** runs the weekly delta sequentially, CPU-only: per-source over-fetch ingest → filter → incremental embed (ADR-050, only new chunks) → analyze (which also refreshes the Media Cloud press layer, ADR-064). No SLURM, no GPU, no fan-out; runs unchanged on a laptop, cron VM, GitHub Actions, or an RCC node; minutes on CPU.
2. **Per-source over-fetch delta.** Each source ingests from `(its own corpus max(published_at) − buffer_days)` to today, so every source advances from its *own* frontier; the buffer overlap is absorbed by URL/content dedup — the only legitimate ingest filters (corpus-correctness invariant). `buffer_days` is a config value.
3. **Paths behind a config `data_root`.** All data locations derive from `paths.data_root` (env override `MND_DATA_ROOT`), defaulting to the repo's `data/`. The `/scratch/midway3/ehgarver` locations move into the RCC environment's `MND_DATA_ROOT`; the RCC SLURM scripts become thin adapters that set it and call the same CLI.
4. **The parallel SLURM fan-out is the full-rebuild path only** (`submit_parallel_ingest.sh` stays for the `NUKE_RAW` historical rebuild: 12 sources, long poles, A100 embed). `update` never fans out.
5. **Institutional re-clustering is deferred (ADR-057 §3).** Until `merge_models` lands with the anchor-id-stability check, `update` does **not** re-cluster: it keeps the corpus delta warm (ingested + embedded, ready to fold in) and refreshes what needs no re-cluster — the press layer and press-heating (ADR-064) against the existing narrative set, captioned **"as of the last full build."**
6. **Scheduling documented, not auto-enabled.** The README gets backend-agnostic `cron`, `systemd` timer, GitHub Actions, and RCC-`cron` snippets, all invoking the one `update` command; the operator turns it on.

### Consequences

- **Reproducibility.** A forker runs `pip install -e .` then `python scripts/run_pipeline.py update` with no RCC, SLURM, or GPU; weekly deltas are CPU-minutes, only a full rebuild wants the GPU fan-out.
- **Efficiency.** Weekly cost scales with *new* articles, not corpus size — no re-fetch, no re-embed of unchanged text.
- **Honesty.** Deferring `merge_models` is stated, not hidden: the narrative set is "as of last build" until validated; press-heating gives the live signal.
- **Relates.** ADR-050, ADR-016 (weekly cadence), ADR-057 (implements §3's portable-refresh half), ADR-064. The `merge_models` identity-stable re-cluster remains a separate, gated ADR.

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

- **Status**: Accepted (wired into `update` behind a default-off flag; awaiting
  one real-corpus gate validation before the flag flips)
- **Date**: 2026-07-04 (wiring 2026-07-06)

> **Part C — wiring (2026-07-06).** A `merge-week` command implements the production path: delta chunks (in `chunks.parquet`, absent from `clusters.parquet`) are fit as a new-week model and merged into the persisted base with `merge_models` at `update.merge_min_similarity` (0.7, the library default). The identity gate is **every** non-noise base topic id surviving the merge — stronger than the ten anchors — and runs **before anything is written**: on failure the command aborts, `clusters.parquet` and the site are untouched, the delta stays parked. On pass it rewrites `clusters.parquet` in `chunks.parquet` row order (embedding-matrix alignment preserved; prior file kept as `.bak`), refreshes `topic_info.parquet`, and swaps the persisted model. `update --merge` chains filter → incremental embed → merge-week ahead of the analyze re-bake; default **off** (`update.merge_enabled: false`) until the gate has passed once on the real corpus.

> **Validation note (2026-07-04).** `merge_models` probed on BERTopic 0.16.4: with realistic (angularly-separated) topic embeddings it **preserves base topic ids**, appends genuinely-new topics, and `merged.transform` routes new-week docs to the kept or appended id. An initial "scrambled assignment" observation was a degenerate-toy-data artifact (collinear blobs, on which cosine cannot separate topics), not a merge fault. `src/mnd/clustering/incremental.py` implements `merge_new_week` + the `anchors_keep_ids` gate; the synthetic anchor-id-stability test passes. Still gated on the **real** anchors.

### Context

ADR-057 §3 chose `merge_models` as the weekly-refresh mechanism (existing topic ids — hence URLs and ADR-056 names — stable by construction; only genuinely-new topics appended). ADR-063's `update` defers it: new articles are parked, the narrative set is "as of last build." A blocker surfaced on inspection: **the fitted BERTopic model is never persisted** — the `cluster` stage saves only `clusters.parquet` + `topic_info.parquet` + `embeddings.npy` and discards `pipeline._model`, but `merge_models([base, new])` operates on model objects. Persisting the model is a hard prerequisite for the whole weekly-refresh path.

### Decision

**Part A — model-persistence prereq (accepted, buildable now).** The `cluster` stage persists the fitted model with safetensors serialization to `topic_model/` alongside `clusters.parquet`; the embedding model is referenced by id, not re-serialized (matching `embed` and JEL). Saved model + `clusters.parquet` suffice to merge a new week and reproduce assignments. Self-contained; no effect on current outputs.

**Part B — weekly merge mechanism (proposed; pending validation).**

1. `update` flow: per-source delta ingest → filter → incremental embed of only new chunks (ADR-050) → fit a BERTopic model on the new-week docs → `merge_models([base_model, new_model], min_similarity=τ)` → persist merged model + refreshed `clusters.parquet` → `analyze` (via ADR-065, refitting only new/changed clusters).
2. **τ (the similarity floor).** Within τ of an existing topic → absorbed (id kept); below → appended as a new id. Higher τ fragments continuing stories; lower over-absorbs distinct new ones. The starting value is **reported, not tuned to anchor recovery** (ADR-040); the validation, not anchor performance, sizes it.
3. **Topic drift (split/merge)** is handled by `merge_models`' similarity step; observed behavior is documented on a back-test rather than via a bespoke assignment layer.
4. **Anchor-id-stability gate** (the credibility check ADR-057 required): a synthetic weekly merge that **fails loudly if any of the 10 anchor narratives changes topic id**. The weekly path does not ship until it passes.
5. **Occasional full rebuild** stays the clean-slate path (SLURM fan-out) with Hungarian centroid-matching back to the prior id set — never the weekly mechanism.

### Consequences

- **Unblocks true weekly narrative-set updates**: existing narratives extend, new ones appear, ids/URLs/names persist; with ADR-065 the re-bake refits only what changed.
- **Prereq is low-risk and immediately useful** (model reloadable for inspection/reproduction). Part B is gated on the anchor-id test.
- **Deferred until validated**: τ's final value, the split/merge back-test, the cron cadence (ADR-057: "manual → cron once identity stability is validated").
- **Relates**: ADR-057 §3, ADR-050, ADR-063 (the `update` this completes), ADR-065, ADR-056, the anchor set.

---

## ADR-067: Simplify the analysis layer — least-squares lens fits, centroid JEL, open-model naming

- **Status**: Accepted
- **Date**: 2026-07-05

> **Amendment (2026-07-05).** The fit-quality gate (R² ≥ `min_fit_r2`) **labels, it does not hide.** The first real run showed SIR R² ~0.02 at the median — most institutional narratives are diffuse/multi-wave, not clean single bumps — so a hide-on-low-R² gate blanked the lens on ~90% of narratives. The front end now surfaces **all three lens curves on every narrative**, each labelled with its R², poor fits **grayed but still selectable** (captioned "poor fit — numbers not meaningful, shown for comparison"); the default lens is the best-fitting one. `converged` is a *good-fit* label, not a show/hide switch. The model-free spine (volume curve + stage + shape facts) remains the always-present primary layer.

### Context

An analysis-layer review (2026-07-05) against the tool's purpose — an insightful, quick, *educational* landing page, not a predictor — found three places paying heavy cost for no display benefit, all display-mechanics:

1. **Bayesian NUTS lens fits are over-engineered.** After ADR-052 (model-free staging) and ADR-062 (R₀/J∞ dropped), the logistic/SIR/Bass fits feed only display point estimates + a curve, yet full PyMC NUTS is ~90% of analyze compute (~30–60 s/fit × 3 × 365, overrunning an 18 h wall); the ADR-062 de-risk showed the same curves fit by `scipy.least_squares` in **1–3 ms**.
2. **JEL re-encodes with the 8B model on CPU (~1 h/run)** although the cluster centroids already sit in `embeddings.npy`.
3. **Naming ships a paid Anthropic client**; an open model keeps the whole pipeline key-free/reproducible for spin-offs.

Kept deliberately (reviewed, earn their place): all three lenses; model-free shape facts + stage; all three similar-narrative measures; Media Cloud overlay + Granger lead-lag; markets overlay; press-heating.

### Decision

1. **Retire NUTS for least-squares/MAP point fits (all three lenses).** Bounded nonlinear least-squares (`scipy.optimize.least_squares`) with data-scaled initial values, the same reported numbers (logistic doubling time/inflection/plateau; SIR rise/decay/asymmetry/peak; Bass total-reach/p/q), the same displayed curve. The MCMC convergence gate (R̂/ESS) is replaced by a **fit-quality gate**: optimizer success AND R² ≥ `dynamics.min_fit_r2` (fixed a priori, not tuned to anchors — ADR-040). Posterior credible intervals are dropped (peak-time CI becomes optional/SE-based or absent); AICc unchanged (Gaussian log-likelihood from residuals). Amends ADR-039; the `dynamics.inference`/`sir_inference` NUTS budgets are retired. No PyMC in the fit path — the fit layer is fully testable off-cluster.
2. **JEL uses the existing cluster centroids** (mean of member embeddings from `embeddings.npy`), nearest-prototype as before — no 8B re-encode; prototypes still embedded once. Amends ADR-055 (the richer terms+docs representation is dropped for scope; centroids suffice for a display flag). Keeps the ADR-065 cache.
3. **Open-model naming via an OpenAI-compatible client.** Naming reads `display.naming.{base_url, model}` (env `MND_NAMING_BASE_URL`/`MND_NAMING_MODEL`); default points at a local Ollama endpoint (`qwen2.5:7b`); degrades to the c-TF-IDF label when unreachable. Amends ADR-056 (provider Anthropic → OpenAI-compatible open model); titles remain cached/committed for key-free rebuilds.

### Consequences

- **Runtime collapses**: fits ~30–60 s → ~ms; JEL ~1 h → seconds; analyze finishes in minutes on one node — the 18 h wall and the cluster-parallelism question both become moot.
- **Simpler + reproducible**: no PyMC, no 8B re-encode for scope, no paid key required anywhere.
- **What the reader sees is unchanged** except the lens curves are least-squares point fits (same numbers) and a lens grays out on low R² instead of non-convergence.
- **Relates**: amends ADR-039 (fit method), ADR-055 (JEL representation), ADR-056 (naming provider); keeps ADR-052/062, ADR-065, ADR-040/046.

---

## ADR-068: Overlay efficiency — fetch-once markets, delta-cached Media Cloud, parallel

- **Status**: Accepted
- **Date**: 2026-07-05

### Context

A full-pipeline efficiency audit (for the weekly-update cadence and publishing)
found the pipeline already incremental everywhere **except the two analyze display
overlays**, which are the entire remaining runtime after ADR-067:

- Verified incremental/cached: ingest per-source delta (ADR-063), embedding
  (ADR-050), cluster merge + model persist (ADR-066), lens fits per-lens (ADR-065),
  JEL centroid + prototype cache (ADR-067), naming (ADR-056).
- **Markets overlay re-fetches the *same* VIX series 365×** — `build_overlay` calls
  FRED once per narrative over that narrative's window, but VIX is one series. A
  clear redundancy: 365 calls where 1 (sliced) suffices.
- **Media Cloud overlay makes 365 distinct per-narrative queries, ~12 s each,
  uncached** (observed: ~73 min sequential on the live re-bake). Each query is the
  narrative's own terms, so calls are genuinely distinct — but a narrative's
  historical series is stable and re-fetched in full every run.

Hard constraint (correctness first): the cache must **capture all data changes**.
Media Cloud indexes with a lag (recent days unreliable; ADR-064), and FRED revises,
so a naive "cache and skip" would serve stale recent data. The cache must always
re-fetch the recent window.

### Decision

1. **Markets: fetch each FRED series once, slice per narrative.** `_markets_overlays`
   fetches the market series across the global span (min start → today) a single
   time and passes the weekly series into `build_overlay`, which slices/aligns per
   narrative instead of re-fetching. 365 FRED calls → 1.
2. **A generic delta-fetch series cache** (`detection/series_cache.py`): a daily
   time series is cached to JSON keyed on its identity (Media Cloud query hash; FRED
   series id). On each run it re-fetches only (a) any uncovered head range and (b)
   the **recent window** — `[min(cached_max, end) − refetch_days, end]` — whenever
   `end` is near today or the cache doesn't cover the request, then merges by date
   with the fresh values **overwriting** cached ones. `refetch_days` exceeds the
   indexing lag (Media Cloud default 28 d; FRED 7 d), so no data change in the
   updatable window is ever missed. A dead narrative fully covered by cache and
   ending far in the past triggers no re-fetch (stable → skipped). Cache key includes
   the query, so a re-cluster (new terms) re-fetches.
3. **Parallelize the Media Cloud loop** — I/O-bound distinct queries run in a bounded
   thread pool (`detection.mediacloud.max_workers`, default 6; each call keeps its
   tenacity backoff, so bursts respect the rate limit). Markets needs no pool (one
   fetch).

### Consequences

- **Cold analyze re-bake**: markets ~instant (1 fetch); Media Cloud ~365 parallel
  fetches / a few minutes instead of ~73 min. **Warm re-bake and the weekly
  `update`**: both overlays hit cache + a small recent-window delta — seconds.
- **Correctness preserved**: the recent, mutable window is always re-fetched and
  overwrites cache; only stable history is reused. New dates, indexing corrections,
  and FRED revisions in the window are captured. A changed query invalidates.
- **The weekly update is now fast end to end** — every stage incremental/cached,
  no long jobs. Caches live under the dashboard `out_dir` (git-ignored), safe to
  delete for a clean refetch.
- **Relates.** ADR-065 (same content-addressed caching philosophy), ADR-063 (the
  `update` this makes fast), ADR-064 (press-heating reads the same cached series),
  ADR-047/042/048 (the overlays), ADR-050 (incremental-delta precedent).

---

## ADR-069: Anchor recovery scoped to anchor-relevant articles

- **Status**: Accepted
- **Date**: 2026-07-06

### Context

Anchor recovery (ADR-019) measured cluster concentration over **every article the
corpus published inside the anchor window**. That criterion dates from the
pre-ADR-020 world, where the corpus was topically filtered and a window's
articles were mostly about the event. On the full-breadth basis set it is
mechanically unsatisfiable: the corpus publishes across all of macro (and, per
ADR-020, beyond) every week, so no single cluster can hold 50% of a month's
output, and the BERTopic outlier bucket wins every plurality. The first run on
the finished corpus scored 0/10 with `best cluster -1` on all ten anchors — a
property of the metric, not of the clustering.

The anchor registry (`data/anchors/anchor_narratives.jsonl`) has carried a fixed
`key_terms` list per anchor since Phase 0, chosen from the documentary record
when each anchor was specified — before any clustering existed.

### Decision

Recovery for an anchor is computed over the **anchor-relevant articles** in its
window, at the **article** level:

1. Window rows (reference window ± `tolerance_days`) are filtered to those whose
   title or body contains any of the anchor's `key_terms`
   (case-insensitive substring).
2. Chunks fold to articles on `article_id`; an article's cluster is the majority
   topic among its chunks.
3. Concentration is the largest share of those articles held by a single
   **non-noise** cluster; outlier-assigned articles stay in the denominator.
4. Recovered iff concentration ≥ 0.50 (threshold unchanged).

### Consequences

- The metric now tests what it was always meant to test: whether the writing
  about a documented event coheres into one cluster.
- No-tuning holds (ADR-040): `key_terms` were fixed in the registry before any
  clustering ran, the threshold is unchanged, and nothing is swept. Recovery
  stays reported, never gated (ADR-019).
- Keeping outliers in the denominator means heavy outlier assignment still
  costs recovery — the metric cannot be satisfied by discarding hard articles.
- The validation summary (`validate --output`) can ship with the dashboard
  artifacts, in which case the research page reports the per-anchor result.

### Outcome (first full-corpus run, 2026-07-06)

0/10 recovered (`data/validation/validation_2026-07-06.json`). The per-anchor
destinations show two distinct causes, neither of them cluster incoherence:

1. **Granularity split.** Entity-rich anchors resolve to the right material but
   spread across several fine clusters — Brexit's best cluster IS a Brexit
   cluster (5% of 235 matching articles); SVB and regional-banking both point
   at the same bank-liquidity cluster. BERTopic at library-default granularity
   yields 7,242 clusters, so one event's writing rarely concentrates 50% in one.
2. **Term breadth.** Anchors whose `key_terms` include generic words
   ("inflation", "expectations", "FOMC", "liquidity") match the entire macro
   discussion of their window (transitory-inflation: 1,369 articles), making
   concentration meaningless for them.

Per ADR-040 the criterion is **not** iterated further toward a passing score.
The binary scoreboard is not shipped on the site; the summary stays in the repo
as the recorded diagnostic. Any future criterion change requires its own ADR
justified on measurement grounds, not on the score it produces.

---

## ADR template (copy for new entries)

```
## ADR-070: Narrative-name cache signature excludes the date span

- **Status**: Accepted
- **Date**: 2026-07-06

### Context

The ADR-056 name cache keys each title on a content hash of the cluster's
representation: terms, central-article excerpts, sources, and date span. Under
the weekly merge (ADR-066 Part C), every narrative that merely *stays active*
extends its date span each week — which would invalidate its cache entry and
regenerate its title weekly. Titles would drift in wording for narratives whose
substance had not changed.

### Decision

Drop the date span from the cache signature. A title regenerates only when the
narrative's substance changes: its defining terms, its central excerpts, or its
source mix. The date span still appears in the generation prompt when a title
is genuinely (re)generated; the impurity (a cache hit reflects the span as of
generation time) is confined to a prompt line the model is instructed to use
only for period naming.

### Consequences

- Weekly merges keep every continuing narrative's display name stable.
- One-time cost: all existing signatures change, so the next bake regenerates
  every name — absorbed into the post-rebuild naming pass that a full
  re-cluster forces anyway.

---

## ADR-071: Forming narratives — sub-floor clusters with recent onsets surface on the emerging page

- **Status**: Superseded by ADR-074 (page surface; the baked `forming` flag remains)
- **Date**: 2026-07-06

### Context

The emerging flag (ADR-059) applies to surfaced narratives, but a narrative
must clear the ADR-051 charting floor (42 articles) to be surfaced at all — and
a story that first appeared within the last four weeks essentially never has 42
articles yet. The emerging page was therefore structurally near-empty: the true
frontier lives *below* the floor, among the small clusters the directory
artifact already records. Inspection also shows that the smallest recent-onset
clusters are single-document clusters (one long report chunked past HDBSCAN's
min size), which are not narratives.

### Decision

The cluster directory (`clusters_all.json`) gains a baked `forming` flag: a
non-surfaced cluster whose onset falls within the ADR-059 recency window
(`stages.newly_emerging_recency_weeks`) and which spans at least
`display.forming.min_articles` (3) distinct articles. Forming entries also
carry their c-TF-IDF `terms` so the naming layer can title them from terms
alone (no baked excerpts exist below the floor). The `name` command titles
forming clusters along with the surfaced narratives — a handful per week, not
a 7,000-cluster naming run. The emerging page lists forming clusters compactly
(name, article count, onset); they graduate to full narrative pages when they
grow past the ADR-051 floor, which the weekly merge (ADR-066 Part C) makes an
organic progression.

### Consequences

- The emerging page reflects the actual frontier instead of an empty window.
- Both thresholds live in config; the flag is baked at analyze time, so the
  front end reads data, not policy. Single-document clusters stay out.
- Display-only throughout: no effect on clustering, fitting, staging, or scope.

---

## ADR-072: NBER not-found detection — a 403 landed on www2.nber.org counts as a gap, not a block

- **Status**: Accepted
- **Date**: 2026-07-06

### Context

The NBER ingestor enumerates paper IDs (`w15500..ceiling`) and stops after a
run of consecutive 404s, which historically marked the head of the series
(ADR-030 fail-loud rules treat any other HTTP error as systemic — outage or
bot-blocking — and abort the run rather than silently skipping papers).

Observed 2026-07-06: nber.org changed its not-found behavior. A nonexistent
paper ID no longer returns 404 — `www.nber.org/papers/wNNNNN` now 301-redirects
to `www2.nber.org/papers/wNNNNN`, which answers 403. Verified from two
networks: existing papers (w35429 and below) return 200 directly on
`www.nber.org` with no redirect; every ID past the series head (w35430,
w38000, w99999) redirects to www2 and 403s. The full catch-up ingest walked
the entire series successfully, reached the head, and then failed loud on the
first nonexistent ID — the 404 stop rule can never fire again.

### Decision

Treat a 403 whose final response URL is on `www2.nber.org` (i.e. reached via
redirect off the canonical host) as a not-found equivalent: it increments the
consecutive-not-found counter that terminates the walk. A 403 answered
directly by `www.nber.org` — no redirect — remains a systemic failure and
still aborts loud, since that is the shape genuine bot-blocking takes.

### Consequences

- The head-of-series stop works again under NBER's new routing; full re-ingests
  complete instead of dying at head+1.
- The fail-loud guarantee of ADR-030 is preserved for real blocks and outages:
  only the specific redirect-to-www2 signature is reclassified, not 403s in
  general.
- If NBER changes routing again (e.g. www2 starts answering 200 for real
  papers), the enumeration stop depends on this signature and must be
  re-verified.

---

## ADR-073: Directory-wide display titles; naming runs on RCC chained after analyze

- **Status**: Accepted
- **Date**: 2026-07-07

### Context

ADR-067 made naming key-free (an open model via an OpenAI-compatible endpoint) but
execution stayed on the laptop, only because that is where an Ollama happened to
be running. ADR-071 then scoped directory naming to forming clusters ("a handful
per week, not a 7,000-cluster naming run").

The full rebuild exposes the cost profile behind that scoping. Since ADR-067 the
analyze bake itself finishes in minutes; naming is the only remaining hours-scale
display step (~6–8 s per cluster on laptop Ollama at ~13 tok/s), and a full
re-cluster invalidates every ADR-070 signature at once, so the first bake after a
rebuild pays the whole cost. Meanwhile the cluster directory lists all 7,242
non-noise clusters but only the 365 surfaced ones (plus forming) carry readable
names — the rest display raw c-TF-IDF labels (`23_nps_lands_acres_park`), leaving
the site's directory mostly unreadable.

Two facts frame the fix. First, the ADR-051 floor is an identifiability bound,
not a compute budget: sub-floor clusters (median 7 articles) cannot support a
3-parameter lifecycle fit, so fits, stages, and narrative pages must not extend
below it regardless of what naming costs. Second, titles are display-only
(ADR-056) and can extend to the whole directory freely. The directory JSON is
read at site build time (Node `fs`), not fetched by the browser, so baking terms
into every entry costs artifact bytes, not page weight.

### Decision

1. **Terms for every non-surfaced directory entry.** `clusters_all.json` bakes
   the c-TF-IDF `terms` for each non-surfaced cluster, not only forming ones.
   Surfaced clusters keep their full story-card grounding and need no directory
   terms.
2. **Titles for the whole directory.** The `name` command titles every
   non-surfaced entry that carries terms — terms-grounded titles exactly as
   forming clusters get today, one uniform rule with no new size cutoff to
   defend. Descriptions, fits, stages, and narrative pages remain surfaced-only
   (ADR-051 unchanged).
3. **Naming executes on RCC.** A new `mnd-name` job (`scripts/rcc/name_rcc.sh`)
   chains `afterok` on analyze: it serves a user-space Ollama from scratch
   storage (binary + models under `/scratch/.../ollama`, GPU-accelerated on the
   gpu partition) and runs the existing `name` command against the baked
   artifacts, patching them in place. Same open model, same endpoint scheme,
   same committed cache and ADR-070 signatures — only the execution host moves.
4. **Local publish becomes pull + fallback + deploy.** `publish.sh` additionally
   rsyncs `data/naming_cache/` back from the RCC repo and still runs the local
   `name` pass, which is a cache-hit no-op when the RCC job covered everything
   and a gap-filler (local Ollama) when it did not, then commits the cache.

### Consequences

- The directory is readable end to end; the one-time ~7k title backfill runs on
  an A100 in hours instead of overnight on the laptop, and weekly steady-state
  misses stay a handful either way (ADR-070 signatures survive the merge).
- The laptop is no longer on the critical path for naming; the remaining local
  steps are the site build and gh-pages deploy, kept local deliberately (git
  credentials, pre-deploy eyeball).
- Sub-floor titles are grounded on terms alone, so they are plainer than
  surfaced titles — acceptable for a directory index; the prompt's no-invention
  rule holds.
- `clusters_all.json` grows by the terms arrays (~1–2 MB on disk); build-time
  read only.
- If the a100 queue is backed up, the job degrades gracefully: Ollama falls back
  to CPU inference on any partition, slow but resumable, since every title is
  cache-incremental.
- Amends ADR-071 (directory naming scope) and the execution-location default of
  ADR-067; ADR-040/051/056/070 untouched.

---

## ADR-074: Corpus heating replaces onset recency on the emerging page

- **Status**: Accepted
- **Date**: 2026-07-12

### Context

The emerging page led with the ADR-059 onset flag (first appearance within
four weeks of the corpus frontier). On the full 2026-07 bake it selected zero
of the 348 surfaced narratives, and widening the window does not help: the
newest onset among surfaced narratives is 2022-07. The cause is structural.
Identity-preserving merges plus semantic clustering make clusters long-lived
narrative families, so new events are absorbed into old families
(2026 Iran-war writing lands in sanctions clusters born in 2010) rather than
founding clusters that could clear the ADR-051 floor quickly, and the twelve
institutional feeds respond to the news cycle at low volume and with a lag.
What actually registers current events in this corpus is a family's activity
rising against its own history, not new-cluster births. The forming section
(ADR-071) papered over the empty lead section with recent sub-floor onsets;
with the lead signal fixed, the user chose to drop it.

### Decision

The page leads with **heating in the corpus**, symmetric with the ADR-064
press-heating signal: a cluster heats when its mean weekly article count over
the trailing `recent_weeks`=16 sits ≥ `k_sigma`=2 standard errors above its own
trailing `baseline_weeks`=52 baseline, with ≥ `min_articles`=3 articles in the
recent window (params under `display.corpus_heating`). The z is scaled by
√recent_weeks — the standard error of the windowed mean — because institutional
volume is single-digit weekly counts and a windowed mean can never clear two
raw weekly deviations (the press signal, on dense daily attention share, keeps
its raw-σ form). Weeks with no articles count as zero. Surfaced narratives are
computed at site build time from their shipped volume series
(`web/src/lib/data.ts`); sub-floor directory clusters get an equivalent blob
baked into `clusters_all.json` (their series never ships) and render as
unlinked, tagged cards. The forming section and the pager leave the page;
"heating in the press" stays as the second section.

### Consequences

- The lead section is populated and tracks what institutions are newly turning
  to (on the 2026-07 bake: cross-strait relations, China's property market,
  trade deceleration, LLM/AI adoption, central-bank independence — 9 narratives).
- Honest limitation, documented in METHODOLOGY §3: the signal reads
  *institutional* attention, which trails the press cycle; a story hot in the
  press for a year (2025 tariffs) is already in its own 52-week baseline and
  will not re-fire.
- The spec lives in two implementations (TS for surfaced, Python for
  sub-floor); config comments cross-reference them and both default to the same
  constants.
- ADR-059's `is_emerging` stays baked and badged (it fires on any genuinely new
  family that ever clears the floor); ADR-071's `forming` flag stays baked but
  has no front-end surface — a removal candidate once ADR-074 has survived a
  few weekly bakes.

---

## ADR-075: Staleness override on the lifecycle stage

- **Status**: Accepted
- **Date**: 2026-07-12

### Context

The stage (growth / stable / decay / dormant) is read from a Mann-Kendall trend
test plus a peak-relative level test over a recent window (ADR-058). That window
is the tail of each narrative's *own* smoothed series, which ends at its last
article — not a calendar-recent window. So the stage describes the final chapter
of a narrative's life wherever it fell in time: a narrative that stopped while
still rising reads `growth` permanently. On the 2026-07 bake, 16 of the 27
`growth` narratives were last active before 2026, and one ("Albania central bank
governor speeches") last spoke in 2013. The site labels the stage "where it sits
now", so these are display falsehoods.

Two non-fixes were ruled out first. Widening the trend window produces no `decay`
at any width, and relaxing the Mann-Kendall α does not either: only 3 narratives
have any downward tendency in the recent window (smallest decreasing-side
p = 0.54), because decline in a sparse count series manifests as absence — zeros
are ties, which carry no rank signal, and the series is bounded below. Relaxing α
merely inflates `growth` (2 → 305 across α = 0.05 → 0.20) while `decay` stays 0.
The empty `decay` bucket is structural, not a threshold artifact: institutional
narratives stop rather than glide down, and their post-decline state is `dormant`.

### Decision

Add a staleness override: when a narrative's last active date trails the corpus
frontier by more than `stages.stale_dormant_weeks` (16 — a quarter, matching the
ADR-074 heating horizon), its stage is forced to `dormant` regardless of trend
shape. The underlying trend is still recorded in `stage_detail` (`trend`,
`days_since_active`, `stale`), so the shape is inspectable; only the headline
stage is overridden. `decay` remains a valid state for a genuine sharp collapse
observed while the narrative is still active. The frontier is derived in
`classify_all` as the latest last-active date across all narratives and passed to
`classify_stage`; with no frontier (unit tests) the override is inert.

### Consequences

- Stage now means "where it sits now" honestly: on the 2026-07 data the override
  moves the counts to roughly growth 11 / stable 47 / dormant 290, and the
  surviving `growth` narratives are the ones actually active at the frontier.
- `decay` stays defined but rare-to-empty on this corpus; METHODOLOGY §3
  documents that dormant is where faded narratives land, so the empty bucket is
  not read as a bug.
- Display-only and baked, so it lands on the next `analyze` bake (like the
  ADR-074 sub-floor heating blobs); the ADR-040 no-tuning discipline holds — the
  16-week line is a definition, not fit to anchor recovery.
- One new knob, `stages.stale_dormant_weeks`, deliberately equal to the heating
  window so the whole surface reads on one quarterly horizon.

---

## ADR-076: Full-corpus composition on the data page

- **Status**: Accepted
- **Date**: 2026-07-13

### Context

The "what is in the corpus" charts (articles by source, articles by JEL field)
aggregated the surfaced narratives' story cards. That covers only the charted
subset — ~28k of the ~123k clustered articles — so the charts silently described
a quarter of the corpus while the page headline advertised the whole thing. The
per-cluster source and JEL data needed to chart the full corpus were not in any
shipped artifact: `clusters_all.json` carries neither, and JEL was classified
only for the fit set.

### Decision

The bake ships a `corpus_composition` block in `index.json`: `by_source`
(distinct-article counts per `source_id`) and `by_jel` (article counts per JEL
code), both over every non-noise cluster. Full-corpus JEL is affordable because
classification is a nearest-prototype cosine over cluster centroids (ADR-067) —
no 8B re-encode and the prototypes are already cached from the surfaced scope —
so all clusters are classified, reusing the surfaced assignments and adding only
the sub-floor ones. The data page reads the block and labels the charts "full
corpus"; when it is absent (older bake, sample data, or a JEL-classification
failure that omits `by_jel`) the page falls back to the surfaced story-card
aggregation. Source labels on the chart revert to short acronyms (Fed, IMF, BIS,
CBO, …) rather than spelled-out institution names.

### Consequences

- The charts describe the whole corpus, matching the page's own headline counts.
- Composition is baked, so it lands on the next `analyze` run alongside the
  ADR-074 sub-floor heating and ADR-075 staleness stages; until then the front
  end falls back gracefully to the charted aggregation.
- Full-corpus JEL is wrapped defensively: a classification failure omits `by_jel`
  (JEL chart falls back) without breaking the source chart or the bake.
- Display-only: composition never feeds the filter, embedding, clustering, or fits
  (ADR-010/020/046 intact).

---

## ADR-077: Remove anchor-recovery validation

- **Status**: Accepted
- **Date**: 2026-07-13

### Context

The pipeline carried an anchor-recovery diagnostic (ADR-019/069): a `validate`
CLI command that scored how well ten hand-specified anchor narratives landed in
single clusters, backed by `mnd.validation` and the `data/anchors/` fixtures. It
was never part of the bake, no rendered output consumed it, and it was never run
to report a result. Documenting it as methodology overstated the pipeline's
guarantees.

### Decision

Remove it entirely: the `mnd.validation` module, the `validate` command, the
`data/anchors/` fixtures, `tests/test_anchor_recovery.py`, the dead
`loadValidation` loader on the site, and the `validation.anchor_tolerance_days`
config key. The remaining bootstrap-NMI stability diagnostic moves to a renamed
`diagnostics` config block (it is a diagnostic, not validation). METHODOLOGY
drops its validation section and the "anchors validate only" principle; the
credibility argument stands on the anchored-parameter discipline (each value is a
cited default or absent, and none is tuned toward any target).

### Consequences

- The docs claim only what the pipeline does. No held-out or recovery claim.
- The word "anchor" now means one thing: a parameter tied to cited literature.
- Suite unchanged in spirit (229 passing); the five anchor-recovery tests go with
  the feature.

---

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
