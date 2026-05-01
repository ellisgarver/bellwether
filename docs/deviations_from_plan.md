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

## 4. Paywalled Outlet Access: Factiva → ProQuest TDM Studio

**Plan (§5 data table, §6.1):** "Library databases (Factiva, ProQuest News,
LexisNexis Academic)" listed as equivalent options for full-text retrieval from
paywalled outlets. Critical pre-flight check flagged: "confirm UChicago library
access to Factiva or ProQuest News."

**Implemented:** ProQuest TDM Studio exclusively, via a `database_native` ingestor
(`src/mnd/ingestion/proquest.py`). Factiva stub removed. LexisNexis not
investigated.

**Reason (not ADR'd):** UChicago library provides ProQuest TDM Studio with a
programmatic Python API (`PROQUEST_API_TOKEN`). Factiva's license terms prohibit
automated/bulk extraction, making it unusable for this pipeline. ProQuest TDM is
designed precisely for text-data-mining academic use cases.

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

## 7. Institutional Source Ingestors Not Yet Built (Phase 2)

**Plan (§5 data table, §6 Phase 2):** "Build Federal Reserve, IMF, BIS, OECD, NBER
ingestion for 2010–present."

**Implemented:** Federal Reserve ingestor is complete (FOMC statements, minutes,
Beige Books, speeches). IMF, BIS, OECD, and NBER ingestors are not yet built.

**Reason:** These are Phase 2 deliverables. The Fed source alone provides high-quality
institutional text sufficient for the Phase 1 pilot. IMF/BIS/OECD/NBER ingestion
will be built in Phase 2 alongside full historical corpus ingestion.

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

## 10. Whitelist Size Below Plan Target

**Plan (§5.1, §6.1):** "Curated U.S. financial press whitelist: approximately
30–50 U.S. financial publications."

**Implemented:** 21 free/mixed-access outlets in `config/whitelist.yaml`.
Paywalled outlets (WSJ, Bloomberg, FT, Barron's, Economist) are in the whitelist
but are not retrievable without `PROQUEST_API_TOKEN`, which is not yet configured
for the pilot.

**Reason:** The 21 free outlets are sufficient for Phase 1 pilot validation. The
full 30–50 outlet target is a Phase 2 goal once ProQuest TDM Studio access is
confirmed and the token is set. Paywalled outlets are already in the whitelist YAML
and will activate automatically when the token is available.

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

## Summary Table

| # | Area | Plan Said | Implemented | ADR? |
|---|------|-----------|-------------|------|
| 1 | Embedding model | `all-mpnet-base-v2` (sole) | Qwen3-0.6B (primary) + mpnet (comparator) | ADR-001 |
| 2 | Sequence length | Implicit 384 (mpnet max) | 512 tokens (MPS memory bound) | ADR-006 |
| 3 | Discovery layer | GDELT 2.0 | Wayback CDX (historical); GDELT retained for <7d | ADR-005 |
| 4 | Paywalled text | Factiva or ProQuest | ProQuest TDM Studio only | No |
| 5 | Dynamics priority | SIR first, logistic fallback | Logistic first, SIR parallel | ADR-002 |
| 6 | `transformers` version | 4.45.2 (pinned) | 4.51.3 (Qwen3 requires ≥4.51) | No |
| 7 | Institutional ingestors | Fed + IMF + BIS + OECD + NBER | Fed only (Phase 2 deferred) | No |
| 8 | Validation data | FRED, Yahoo, NBER, Michigan | Not yet integrated (Phase 3–4) | No |
| 9 | Robustness checks | Cross-source + earlier-embedding | Not yet built (`[Compress]`) | Partial (ADR-001) |
| 10 | Outlet count | 30–50 outlets | 21 free outlets (paywalled pending token) | No |
| 11 | TensorFlow | Not a dependency | Installed then removed; `KERAS_BACKEND=torch` required | ADR-006 |
| 12 | Validate `--required` | Not planned | Added for pilot subset testing | No |
