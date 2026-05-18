# Deviations from Project Plan

Tracks every meaningful departure from `docs/Macro_Narrative_Dynamics_Project_Plan.pdf`
(the authoritative plan document) to the actual implementation. Organized by topic.
Each entry states what the plan specified, what was implemented instead, and why.

ADR-documented decisions are cross-referenced; un-ADR'd changes are noted as such.

---

## 1. Embedding Model

**Plan (§3 Stage 3, §7 §A):** `sentence-transformers/all-mpnet-base-v2` as the sole
embedding model. Chosen explicitly to mitigate look-ahead bias — training cutoff
≈2020–2021, and finance-specialized models were rejected as amplifying bias.
Appendix A locks `all-mpnet-base-v2` as the pre-specified parameter.

**Implemented:** Two-model strategy:
- **Primary**: `Qwen/Qwen3-Embedding-0.6B` (Apache 2.0, 1024-d, instruction-aware,
  2025 training cutoff) — used for all production work.
- **Comparator**: `all-mpnet-base-v2` (768-d) — retained but demoted to the mandatory
  look-ahead sensitivity check only.

**Reason (ADR-001):** MTEB leaderboard showed a multi-point quality advantage for
Qwen3-Embedding over mpnet at the time of implementation. The look-ahead concern is
addressed formally rather than implicitly: the comparator measures how much
look-ahead bias matters by comparing cluster quality across pre-/post-2021 sub-periods.
This makes the look-ahead argument stronger, not weaker.

**Downstream effect:** The comparator (mpnet) is the plan's original primary model.
Results from both models will be reported; if they materially diverge on pre-2021
data, look-ahead is flagged as a significant caveat.

---

## 2. Embedding Sequence Length

**Plan (§3 Stage 3, §A):** "headline + first 600 tokens of body." No explicit
max_seq_len specified for the embedding model; the plan was written assuming
`all-mpnet-base-v2`, whose natural max is 384 tokens.

**Implemented:** `max_seq_len: 512` in `config.yaml` (for the Qwen3 primary);
`prepare_text_for_embedding()` continues to cap at 600 whitespace-words before
the tokenizer runs.

**Reason (not ADR'd — hardware constraint):** On Apple Silicon (MPS), Qwen3's
attention mask allocates `batch_size × num_heads × seq_len²` bytes. The model's
theoretical max (32768) requires 29 GB; 2048 tokens requires 8 GB — both exceed
available unified memory with a batch of 32. At 512 tokens, the attention matrix
is ≈ 536 MB, which fits. Because `prepare_text_for_embedding` already limits body
text to ≈780 BPE tokens, truncation at 512 tokens affects the final ≈270 tokens of
longer articles; headline and lead content are preserved. This is acceptable for the
local pilot; the RCC target (CUDA, more VRAM) can use a larger value.

---

## 3. Discovery Layer: GDELT → Wayback CDX

**Plan (§5.1, §6.1, §6 Phase 1):** GDELT 2.0 as the article discovery layer for
free outlets. Phase 1 pilot specified "Pull six months of GDELT data filtered to
the curated whitelist." GDELT's known issues (≈55% field accuracy, ≈20% redundancy)
were mitigated by using it only for URL discovery, not as a text source.

**Implemented:** The Internet Archive Wayback Machine CDX API replaces GDELT for all
historical bulk ingestion (date ranges > 7 days). GDELT is retained only for
near-real-time discovery (last 7 days), where request volume is low enough to avoid
IP-level rate limits.

**Reason (ADR-005):** During Phase 1 piloting, GDELT's free API applied IP-level
rate throttling that rejected requests regardless of per-request delay. 18 of 26
weekly batches failed with "Please limit requests to one every 5 seconds"; increasing
the inter-request delay from 1 s to 6 s had no effect. Result: 0 GDELT-discovered
articles. The CDX API scales with outlet count (≈20 requests) rather than calendar
weeks (≈26–182 requests), making it far more robust for bulk historical queries.

**Pilot corpus result:** 131 Wayback + 17 Fed = 148 raw articles
(2023-09-01 → 2024-02-29), 57 passing the topic filter.

---

## 4. Paywalled Outlet Access: Factiva / ProQuest → not in semantic corpus

**Plan (§5 data table, §6.1):** "Library databases (Factiva, ProQuest News,
LexisNexis Academic)" listed as equivalent options for full-text retrieval from
paywalled outlets. Critical pre-flight check flagged: "confirm UChicago library
access to Factiva or ProQuest News."

**Initially implemented (Phase 1):** ProQuest TDM Studio exclusively, via the
TDM-Studio export workflow (ADR-007). Factiva stub removed; LexisNexis not
investigated.

**Currently implemented (Phase 2, ADR-010):** No paywalled-press text source.
The semantic corpus is restricted to institutional + academic open sources
(Layer 1A). Premium press volume signal is supplied by the RavenPack dynamics
layer (Layer 1B via WRDS); RavenPack metadata covers WSJ, Barron's, Dow Jones
Newswires, MarketWatch, PR Newswire, and ~800 other outlets but is NOT used for
embedding. ProQuest TDM Studio code archived to `scripts/archive/`.

**Reason:** The "narrative identity in analytical discourse, propagation in
journalism" framing (MND_PROJECT_SPEC rev3 §4) makes institutional and academic
text the primary clustering substrate; RavenPack supplies the journalism volume
signal more consistently than scraping. The "Factiva/ProQuest kill criterion"
from the original plan therefore no longer applies — the pipeline is fully open
on the text side.

---

## 5. Dynamics Model Priority: SIR-First → Logistic-First

**Plan (§4.1, §5 Stage 5, §6 Phase 3):** SIR is described as "the primary
epidemiological model" and the project's "intellectual centerpiece." Logistic
growth is identified as a fallback. Phase 3 MVP item: "Logistic growth fitting for
all clusters (the most stable model; suitable as MVP fallback)." SIR fitting is
labeled `[Compress]` — compressible without core damage.

**Implemented:** Logistic is the MVP path and is the default model selected at ties
in AICc-based model comparison. SIR, Gompertz, and exponential are implemented in
parallel but are secondary paths. Stage classification consumes whichever model has
the best fit per cluster (AICc), with logistic preferred at ties.

**Reason (ADR-002):** SIR has 3–4 parameters on noisy pilot data; posterior CIs
are wide and convergence can fail. Logistic is the deterministic limit of SIR under
standard assumptions, preserves the epidemiological framing, and is robust enough
to deliver a credible artifact even if SIR fits poorly. This matches the plan's own
`[Compress]` labeling of multi-model fitting.

---

## 6. Transformers Library Version

**Plan:** `requirements.txt` pinned `transformers==4.45.2` at scaffold time.

**Implemented:** Upgraded to `transformers==4.51.3`.

**Reason (not ADR'd — dependency requirement):** `Qwen/Qwen3-Embedding-0.6B`
(selected in ADR-001) requires transformers ≥ 4.51.0, which first added the `qwen3`
model-type to `AutoConfig`. Version 4.45.2 raised `KeyError: 'qwen3'` at load time.
Upgrading to 4.51.3 is a direct consequence of the ADR-001 model choice; the
constraint cascade is: ADR-001 → Qwen3 model → transformers ≥ 4.51.

---

## 7. Institutional Source Ingestors — built and broadened in Phase 2

**Plan (§5 data table, §6 Phase 2):** "Build Federal Reserve, IMF, BIS, OECD, NBER
ingestion for 2010–present."

**Implemented (Phase 2, ADR-010 / ADR-012 / ADR-014):** Composite
`InstitutionalIngestor` covers Federal Reserve (FOMC, speeches incl. Jackson Hole,
Beige Book, FEDS Notes, MPR, FSR), Regional Feds (NY/SF/Chicago/Atlanta),
IMF (WEO/GFSR/F&D/WPs/Blog via Coveo Search + curl_cffi Chrome impersonation,
ADR-014), BIS (QR/WPs via sitemap), CBO (sitemap path, ADR-013), Treasury/OFR/FSOC,
Congressional testimony, VoxEU/CEPR, Brookings, PIIE, CFR.

**Removed from plan scope:** OECD (no working free-text retrieval path identified).
NBER and SSRN have historical-bulk retrieval blocked (bot protection / no public
archive); both ingestors remain in code for Phase 6 live RSS only.

**Reason:** Phase 2 deliverable, completed. The IMF path is the most operationally
fragile — Akamai TLS-fingerprint rejection of stdlib `requests` required the
`curl_cffi==0.15.0` dependency and Chrome impersonation (ADR-014).

---

## 8. Validation Data Not Yet Integrated (Phase 3–4)

**Plan (§6.2 validation table):** FRED (CPI, PCE, yield curve, VIX, credit spreads),
Yahoo Finance/Alpha Vantage (security prices), NBER Business Cycle Dating, and
University of Michigan consumer sentiment are listed as validation data sources for
the outcome-correlation analysis.

**Implemented:** None of these are integrated yet. A `fredapi` dependency is pinned
in `requirements.txt` but the client is not called by any pipeline stage.

**Reason:** Validation-data integration is a Phase 3–4 deliverable. The Phase 1 pilot
validates methodology (cluster stability, anchor recovery) without requiring outcome
data. FRED is explicitly noted in CLAUDE.md as "not required for pilot."

---

## 9. Cross-Source and Earlier-Embedding Robustness Checks Not Yet Built

**Plan (§8.6, §7.2):** Two compressible robustness checks:
1. **Cross-source check** `[Compress]`: Re-validate on a second data source (Alpha
   Vantage news API) to confirm results are not GDELT-specific artifacts.
2. **Earlier-embedding robustness check** `[Compress]`: Re-run validation on early
   anchor narratives using a pre-2018 sentence transformer (e.g.,
   `bert-base-nli-stsb-mean-tokens`) to isolate look-ahead exposure.

**Implemented:** Neither check is built. The two-model strategy (ADR-001) partially
subsumes the earlier-embedding check: `all-mpnet-base-v2` as comparator serves
exactly the role described, but the specific model named in the plan
(`bert-base-nli-stsb-mean-tokens`) was not used.

**Reason:** Both are `[Compress]` items, appropriately deferred. The Alpha Vantage
check becomes relevant in Phase 3 when the full corpus is ingested. The
earlier-embedding check is partially satisfied by ADR-001's comparator architecture.

---

## 10. Whitelist Restructured Around Institutional + Academic Tiers

**Plan (§5.1, §6.1):** "Curated U.S. financial press whitelist: approximately
30–50 U.S. financial publications."

**Implemented (ADR-010):** The semantic-corpus whitelist is restructured around
institutional and academic tiers, not press outlets. The active tiers
(`config/whitelist.yaml`) are:

- `tier_1_institutional_policy` — Fed Board, Regional Feds, IMF, BIS, CEA, CBO,
  Treasury/OFR, Congressional testimony.
- `tier_2_academic_analytical` — VoxEU, NBER (Phase 6 only), SSRN (Phase 6 only).
- `tier_2_policy_analytical` — Brookings, PIIE, CFR.

The press outlets the original plan counted (WSJ, Bloomberg, FT, Reuters, AP, etc.)
are not in the semantic corpus by design. Their volume signal is the RavenPack
dynamics layer (Layer 1B). The "30–50 outlets" target was a Phase 1 metric and
is superseded by source-type coverage at the institutional + academic level.

**Reason:** See deviation #4 and ADR-010. Narrative identity is determined in
analytical discourse; counting press outlets as the unit of coverage is the wrong
yardstick for the current architecture.

---

## 11. TensorFlow Removed; KERAS_BACKEND=torch Required

**Plan:** No mention of TensorFlow — the project uses PyTorch throughout (embedding,
clustering, dynamics). TF was never a planned dependency.

**Implemented:** During Phase 1 pilot, the Keras 3 / transformers compatibility error
(`ValueError: Your currently installed version of Keras is Keras 3`) was initially
fixed by `pip install tf-keras`, which pulled in TensorFlow 2.21 as a transitive
dependency. This caused a fatal deadlock: TF's `libtensorflow_cc.2.dylib` (691 MB)
was loaded by BERTopic's import chain despite `USE_TF=0`, and TF's `absl::Mutex`
initialization deadlocked during protobuf registration on Apple Silicon, stalling
the cluster run for 30+ minutes with no output.

**Fix:** TensorFlow and tf-keras were uninstalled entirely (`pip uninstall tensorflow
tf-keras`). The Keras 3 compatibility issue is resolved by setting `KERAS_BACKEND=torch`
in the environment, which directs Keras 3 to use the PyTorch backend and prevents any
TF initialization. Both `USE_TF=0` and `KERAS_BACKEND=torch` are required on any machine
without TensorFlow installed and are documented in `.env.example`. See ADR-006.

---

## 12. Validate CLI --required Override

**Plan:** No mention of a `--required` CLI flag — the plan assumed the full 10-anchor
validation set would be tested at once.

**Implemented:** A `--required` override was added to `run_pipeline.py validate` during
Phase 1 to allow the pilot's 3-anchor subset to be gated correctly. Without this flag,
the exit code always fails when testing fewer than 7 anchors because the config
hardcodes `required_anchors_recovered: 7` for the Phase 4 full-corpus gate. The pilot
command is now `validate --anchors ... --required 1` (1 of the 3 pilot anchors is
structurally recoverable given the Sep 2023–Feb 2024 corpus window; SVB and Credit
Suisse predate it). The production 7/10 threshold remains locked in config.yaml and
is the default when `--required` is omitted.

---

## 13. Phase 2 Corpus Overhaul, RavenPack Dynamics Layer, Media Cloud Detection

**Plan:** Phase 2 corpus was described as a press whitelist extended to 30–50
outlets, plus institutional sources. Dynamics fitting consumed institutional
counts. No detection layer.

**Implemented (ADR-010, MND_PROJECT_SPEC rev3, 2026-05-11):**

- Journalism tier (AP News, MarketWatch, Reuters) removed from the semantic corpus.
- RavenPack RPA 1.0 Global Macro via WRDS added as Layer 1B (Signal A) — weekly
  article volume time series for SIR/logistic fitting; metadata only, no text.
- Media Cloud added as Layer 2 detection (`src/mnd/detection/mediacloud.py`) — daily
  story counts by keyword query; does not feed embedding or clustering.
- EPU (Baker-Bloom-Davis) replaces JLN in validation; text-based, free direct
  download from policyuncertainty.com.
- CFR reinstated as Tier 2 source.
- FEDS Notes added explicitly to FederalReserveIngestor.

**Reason:** Restructured around the Shiller propagation framework — narrative
identity in institutional/academic text (Layer 1A), propagation in press volume
(Layer 1B), pre-characterization detection in broad story counts (Layer 2).
RavenPack supplies a cleaner dynamics signal than Wayback-counted journalism
articles, and is consistent across the 2010–present window.

---

## 14. Embedding Model Re-Decided: Qwen3 Restored

**Plan / ADR-010:** ADR-010 briefly switched the primary model to
`all-mpnet-base-v2` to minimize look-ahead bias.

**Implemented (ADR-011, 2026-05-11, same day):** Qwen3-Embedding-0.6B restored
as primary. mpnet retained as comparator for a formalized look-ahead sensitivity
check (NMI delta on pre-2021 vs post-2021 sub-corpora).

**Reason:** With the journalism tier removed, the corpus is now overwhelmingly
long-form institutional/academic documents (FOMC minutes 10–15k words, BIS QR
3–8k words, Jackson Hole 8–15k words). mpnet's hard 384-token cap means only
the first ~280 words are encoded, missing the analytical content. Qwen3's
32,768-token context preserves it. Look-ahead risk is measured (Δ_NMI
comparison vs mpnet) rather than assumed.

---

## 15. arXiv and Separate Jackson Hole Ingestor Removed

**Plan / Earlier scope:** arXiv as Tier 2 academic source; Jackson Hole
proceedings as a separate Tier 1 source.

**Implemented (ADR-012, 2026-05-13):** Both removed. arXiv has 2017-only
coverage of the econ category (low macro volume; not in MND_PROJECT_SPEC rev3).
Jackson Hole speeches are Fed Chair / governor speeches published on
federalreserve.gov and already captured by FederalReserveIngestor; a separate
ingestor only created duplicates.

**Also in ADR-012:** TopicFilter removed from the `filter` pipeline stage.
With the journalism tier removed, all remaining sources are macro-relevant by
construction; keyword filtering risked incorrectly dropping institutional docs.

---

## 16. Embedding Sequence Length: 32768 → 2048 → 1024 (V100 OOM)

**ADR-006 / ADR-011 baseline:** `max_seq_len = 32768` (Qwen3 native max) on RCC.

**Implemented (ADR-013, 2026-05-17):** Reduced 2048 → 1024 after job 49622334
OOMed on a V100-16GB at (batch=32, seq=2048, fp16). The SDPA causal mask is
cloned per layer; the combined working set blew past 16 GB. At (batch=8,
seq=1024, fp16) the working set is ~6 GB. The chunker outputs 600-BPE-token
chunks, so 1024 still gives 1.7x headroom.

`compute.embedding_batch_size` also dropped 32 → 8. Same vectors come out;
zero quality impact. `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` added
to `embed_rcc.sh`.

---

## 17. Ingestor Repairs After 2024 Dry Run (ADR-013)

**Pre-fix bugs (jobs 49622332–49622335, 2024 window, 0 articles):**

- CongressionalIngestor — URL regex matched only legacy `sb####`/`jy####` slugs,
  missing modern `/statements/`, `/testimonies/`, `/readouts/` forms. Fixed +
  hardcoded "Economic Fury" exclusion replaced with conditional sanctions filter.
- CBOIngestor — Drupal listing behind DataDome (403); replaced with sitemap.xml
  enumeration + page-date validation.
- CFRIngestor — RSS feed exposes only ~24 recent items; replaced with sitemap
  enumeration over /articles, /backgrounders, /reports + URL-slug macro pre-filter.
- IMFIngestor — Misdiagnosed as Cloudflare IP block; corrected to Akamai TLS
  fingerprint (see ADR-014).

**Pipeline-level fix:** `filter-pre-embed` (canonical ADR-010/012 archived-source
exclusion writing `corpus_for_embedding.jsonl`) was missing from the SLURM
chain. Added as `scripts/rcc/filter_pre_embed_rcc.sh` between ingest and filter
in `submit_full_pipeline.sh`.

---

## 18. IMF Via Coveo Search + curl_cffi Chrome Impersonation (ADR-014)

**Pre-fix (ADR-013 misdiagnosis):** IMFIngestor was disabled in the composite
after observing HTTP 403 on every imf.org URL from RCC. Misdiagnosis: "Cloudflare
WAF IP block."

**Correct diagnosis (ADR-014, 2026-05-17):**

- imf.org is fronted by Akamai (`server: AkamaiGHost`), not Cloudflare.
- Akamai Bot Manager fingerprints the TLS handshake (JA3/JA4). stdlib `requests`
  / urllib3's OpenSSL cipher list and extension order do not match a real browser
  and are 403'd at the TLS layer before HTTP is consulted.
- Re-running with `curl_cffi` and `impersonate='chrome131'` returns 200 from
  residential, mobile, and university (RCC) IPs.

**Listing path:** Replaced the Sitecore JSS walker with the public Coveo Search
endpoint that powers imf.org's own search bar. Per-series URL-prefix queries
(`weo`, `gfsr`, `fandd`, `wp`, `blog`) with date-range bisection on series that
exceed Coveo's 1000-result cap.

**Body extraction:** Tries `_next/data/<buildId>/<path>.json` SSG endpoint first
for /en/publications/* URLs; falls back to trafilatura on the HTML page. Blog
URLs (/en/blogs/articles/*) always take the trafilatura path.

**Dependency:** `curl_cffi==0.15.0` is pinned in `requirements.txt` and must
be installed in the RCC `mnd` conda env.

---

## Summary Table

| # | Area | Plan Said | Implemented | ADR? |
|---|------|-----------|-------------|------|
| 1 | Embedding model | `all-mpnet-base-v2` (sole) | Qwen3-0.6B (primary) + mpnet (comparator) | ADR-001 / ADR-011 |
| 2 | Sequence length | Implicit 384 (mpnet max) | 1024 on RCC; 512 on MPS (ADR-006 / ADR-013) | ADR-006 / ADR-013 |
| 3 | Discovery layer | GDELT 2.0 | Wayback CDX archived in ADR-010 (no longer in active flow) | ADR-005 |
| 4 | Paywalled text | Factiva or ProQuest | Not in semantic corpus; RavenPack volume signal only | ADR-010 |
| 5 | Dynamics priority | SIR first, logistic fallback | Logistic first, SIR parallel | ADR-002 |
| 6 | `transformers` version | 4.45.2 (pinned) | 4.51.3 (Qwen3 requires ≥4.51) | No |
| 7 | Institutional ingestors | Fed + IMF + BIS + OECD + NBER | Fed + IMF + BIS + CBO + Treasury/OFR + Congressional + Regional Feds + VoxEU + Brookings + PIIE + CFR | ADR-010 / ADR-012 / ADR-014 |
| 8 | Validation data | FRED, Yahoo, NBER, Michigan | FRED + EPU + NBER cycles + Michigan (Phase 4 deliverable) | ADR-010 (JLN→EPU) |
| 9 | Robustness checks | Cross-source + earlier-embedding | Look-ahead sensitivity formalized as Δ_NMI on anchor sub-corpora | ADR-011 |
| 10 | Outlet count | 30–50 press outlets | Restructured around institutional/academic tiers; press signal via RavenPack | ADR-010 |
| 11 | TensorFlow | Not a dependency | Installed then removed; `KERAS_BACKEND=torch` required | ADR-006 |
| 12 | Validate `--required` | Not planned | Added for pilot subset testing | No |
| 13 | Detection layer | Not in plan | Media Cloud daily story counts, Layer 2 | ADR-010 |
| 14 | Dynamics layer | Institutional counts only | RavenPack RPA 1.0 weekly volume (Signal A) + institutional (Signal B) | ADR-010 |
| 15 | Journalism tier | AP / MarketWatch / Reuters in semantic corpus | Removed from semantic corpus; RavenPack volume signal instead | ADR-010 |
| 16 | arXiv / Jackson Hole | In scope | Removed (arXiv 2017-only; Jackson Hole covered by Fed speeches) | ADR-012 |
| 17 | Topic filter in Stage 2 | Hybrid keyword + embedding gate | Removed; date-range + dedup only | ADR-012 |
| 18 | IMF retrieval | Direct HTTP | Coveo Search API + curl_cffi Chrome impersonation (Akamai TLS fingerprint) | ADR-014 |
| 19 | Embedding batch size | 32 | 8 (V100 16 GB OOM safety) | ADR-013 |
