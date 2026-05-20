# Related work — quantitative macro-narrative measurement

A survey of the published literature relevant to the Macro Narrative Dynamics project. Used to position the project's contribution, identify methodological precedents to cite, and surface insights to incorporate into the methodology and pre-registration.

The conclusion up front: **the project's specific combination — multi-source institutional+academic corpus, BERTopic on transformer embeddings, SIR/logistic lifecycle ODEs fit per narrative cluster, anchor-validated, and surfaced through a live public dashboard — does not exist as a single published artifact.** Every individual component is field-standard. The contribution is integrative and operational, not methodologically heroic. That framing is honest and pre-registration-friendly.

---

## 1. State of the field (2026)

Quantitative macro-narrative measurement is an active but still-consolidating subfield. Roos & Reccius (2024, *Journal of Economic Surveys*) — the most cited recent survey — concludes that "we cannot speak of *the* narrative approach to economics or a coherent field of narrative economics." Empirical methods have proliferated faster than theory; there is no generally accepted definition of an "economic narrative", and the choice of extraction method (dictionary, LDA, embedded topic model, BERTopic, LLM-extracted) is driven by tooling availability rather than theoretical commitment.

Shiller's 2017 AEA Presidential Address and 2019 book are universally cited as the conceptual anchor. But Shiller's actual empirical method — Google Ngrams keyword counts fit by visual analogy to epidemic curves — has rarely been operationalized rigorously.

The field has bifurcated into three streams:

1. **Topic-model-on-news/policy-text papers** — Hansen, McMahon & Prat (2018, *QJE*); Larsen & Thorsrud (2019, *Journal of Econometrics*); Bybee, Kelly, Manela & Xiu (2024); Bertsch, Hull, Lumsdaine & Zhang (2021, *Economics Letters*); Flynn & Sastry (2024, NBER WP). Extract latent themes from large corpora and correlate them with macro variables. This is the methodological mainstream and the closest comparator stream to this project.
2. **Dictionary/sentiment papers** — Tetlock (2007, *JF*); Garcia (2013, *JF*); Loughran & McDonald (2011, *JF*); Baker, Bloom & Davis (2016, *QJE*); Manela & Moreira (2017, *JFE*). Extract a single intensity index rather than narrative topics.
3. **Survey/experimental papers** — Andre, Haaland, Roth, Wiederholt & Wohlfart (forthcoming, *Review of Economic Studies*). Directly elicit narratives from households or experts and represent them as DAGs.

A fourth, very recent stream uses LLMs at sentence/document level (Schmidt et al. 2025; Gueta et al. 2025; Hartley 2025). These target the "what is a narrative" extraction problem rather than the lifecycle dynamics problem.

**No widely cited paper has fit SIR or logistic ODEs to topic-volume time series across a multi-source institutional/academic corpus and labeled lifecycle stages.** Shiller proposed the framework; published empirical work has stopped at descriptive trajectories or correlations with macro outcomes.

---

## 2. Closest methodological precedents

### Bybee, Kelly, Manela & Xiu (2024), "Business News and Business Cycles" — *Journal of Finance* 79(5), 3105-3147 (DOI 10.1111/jofi.13377)
LDA topic model fit to ~800,000 *Wall Street Journal* articles 1984-2017, 180 topics. Show news attention tracks aggregate activity, explains ~25% of stock returns, and adds incremental forecasting power beyond numerical indicators. Awarded Dimensional Fund Advisors Distinguished Paper Prize 2024.

**Overlap with this project:** HIGH (method), MEDIUM (corpus). Most architecturally similar published work. Single-source corpus (WSJ only); classical LDA rather than embedding-based clustering; no lifecycle/dynamics fitting (they correlate topic share with macro variables; this project fits ODEs to topic volume).

**Cite as:** the methodological precedent for "topic-share-on-business-news" measurement. Differentiation pivot: multi-source institutional corpus + ODE lifecycle modeling.

### Larsen & Thorsrud (2019), "The value of news for economic developments" — *Journal of Econometrics*
LDA on Norwegian business newspaper text. Extract topics, use them as conditioning variables for nowcasting GDP and inflation expectations. Companion paper Larsen, Thorsrud & Zhulanova (2021, *JME*) on news-driven inflation expectations shows some topics behave like "animal spirits" — disconnected from fundamentals.

**Overlap:** HIGH (intent), MEDIUM (method). Same Shiller-spirit framing (narratives in macro discourse, identifying which ones matter) but single-newspaper LDA rather than multi-source + BERTopic. No lifecycle modeling. Norway not U.S.

**Cite as:** the most direct prior demonstration that topic-model output behaves like narratives in the Shiller sense. "Animal spirits topics" is useful prereg framing.

### Hansen, McMahon & Prat (2018), "Transparency and Deliberation within the FOMC" — *QJE*
LDA on FOMC transcripts pre/post the 1993 transparency reform. Measure conformity, discipline, and topic concentration as functions of attribution.

**Overlap:** MEDIUM. Same institutional source (FOMC), same family of methods. Different aim — causal identification of transparency effects, not narrative-lifecycle measurement.

**Cite as:** precedent for LDA-on-Fed-text in a top-5 economics journal. Their topic-coherence and stability diagnostics are the field-standard validation approach.

### Bertsch, Hull, Lumsdaine & Zhang (2021), "Narrative Fragmentation and the Business Cycle" — *Economics Letters* + Riksbank WP 401
Dynamic embedded topic model (D-ETM) on 1950-2019 newspaper articles. Show narratives consolidate during expansions and fragment during contractions.

**Overlap:** HIGH (conceptual), MEDIUM (method). Closest published precedent for "narrative dynamics over time at the macro level." Uses neural-embedding-augmented topic model — conceptually a precursor to BERTopic-on-embeddings.

**Cite as:** the direct precedent for "tracking narrative dynamics across business cycles." Their fragmentation metric could be a useful descriptive output to add to the dashboard.

### Flynn & Sastry (2024), "The Macroeconomics of Narratives" — NBER WP 32602
NLP on 10-K filings to extract narrative shares; embed a viral narrative in a neoclassical business-cycle model; estimate narratives explain 32% of 2001 recession output decline and 18% of Great Recession.

**Overlap:** MEDIUM (theory), LOW (corpus, dynamics method). Most theoretically ambitious narrative-economics paper. They model narrative virality structurally; this project measures lifecycle empirically. Corpus is firm filings, not policy/academic text.

**Cite as:** the structural-theory benchmark. Useful positioning: this project provides the necessary descriptive/empirical measurement infrastructure for Flynn-Sastry-style structural work.

### Andre, Haaland, Roth, Wiederholt & Wohlfart (forthcoming, *Review of Economic Studies*), "Narratives about the Macroeconomy"
Open-ended surveys of 10,000+ U.S. households and 100 academic experts about inflation causes; represent narratives as DAGs; experiment shows narratives shape inflation expectations.

**Overlap:** LOW (method), HIGH (subject). Complementary, not competing — survey-elicited household narratives rather than text-extracted policy narratives.

**Cite as:** the field's strongest empirical demonstration that narratives causally shape macro expectations. Their experts-vs-households finding ("expert narratives differ qualitatively from household narratives") is the strongest single justification for this project's specific focus on *institutional/expert* discourse — that's the upstream supply side they don't measure.

---

## 3. Adjacent technical precedents

### Boutaleb, Picault & Grosjean (2024), "BERTrend: Neural Topic Modeling for Emerging Trends Detection" — ACL FuturED Workshop ([repo: rte-france/BERTrend](https://github.com/rte-france/BERTrend))

BERTopic adapted for **online incremental learning over time-sliced batches**. Documents arrive in time slices; BERTopic is run on each batch; topics from successive batches are merged via cosine similarity into a cumulative topic set; each topic gets a "popularity" score that considers both document count and update frequency over time; topics are classified into **noise / weak signal / strong signal** using dynamically chosen thresholds.

**What's actually novel vs. vanilla BERTopic:**
1. Time-sliced batch processing with cross-batch topic merging (supports incremental updates without re-running the full pipeline).
2. Temporal popularity metric combining count + recency.
3. Heuristic signal-strength classification with dynamic thresholds.

**Overlap with our project:** HIGH (technical adjacent), MEDIUM (intent), LOW (domain). Not economics — general weak-signal trend detection. But the closest published BERTopic+temporal-dynamics precedent, and the only widely-known open-source library for incremental BERTopic.

**Why we do NOT replace any part of our pipeline with BERTrend:**

1. **BERTrend's signal classification is heuristic; ours is anchored to classical SIR theory.** Our 4-stage lifecycle (pre-emergence, growth, decay, dormant) is keyed to R₀ direction (Kermack & McKendrick 1927) — a published epidemic threshold with a century of citation depth. BERTrend's noise/weak/strong scheme rests on dynamically chosen popularity thresholds — even if "data-driven", the threshold-selection rule is researcher-set. Replacing R₀-based with BERTrend's heuristic would WEAKEN our methodology under the "anchored or removed" principle.
2. **BERTrend fits no parametric model.** It reports a popularity trajectory and categorizes; we fit SIR and logistic with Bayesian inference and report R₀ with confidence intervals. Different epistemic claims.
3. **No cross-validation against external volume signals.** BERTrend has one popularity signal; we cross-validate institutional discourse against Media Cloud premium-press volume and broad-press volume.
4. **No anchor-event validation.** BERTrend validates qualitatively on weak-signal recovery; we validate against 10 documented macro events with ±14d Brown & Warner (1985) event-study windows.

**Could BERTrend usefully augment Phase 6 (weekly cron updates)?** Conceptually yes — its incremental learning would avoid re-running the full BERTopic batch each week. But our existing approach (re-run BERTopic on the cumulative corpus weekly, dedupe via MinHash) is more reproducible, avoids online-learning topic-drift, and produces an audit trail. We stay with batch re-runs in Phase 6.

**Cite as:** the only published BERTopic + temporal-dynamics precedent. Explicitly note in the prereg that we considered and rejected BERTrend's signal-classification scheme in favor of classical SIR anchoring — this is a deliberate methodological choice, not an oversight.

### Medeiros, Quigley & Revie (2026), "A Statistical Framework for Detecting Emergent Narratives in Longitudinal Text Corpora" — arXiv:2602.20939
LDA-based framework defining narrative emergence as "sustained increase in topic prominence." Validated on Nobel-Prize-recognized economic ideas 1970-2018.

**Overlap:** HIGH. Most direct contemporary precedent for the "emergence detection" half of this project's lifecycle classification.

**Cite as:** statistical-emergence-detection benchmark. Their Nobel-anchor validation is conceptually parallel to this project's 10-anchor validation.

---

## 4. LLM-frontier work (recent, 2025+)

### Schmidt et al. (2025), "Identifying economic narratives in large text corpora" — arXiv:2506.15041
### Hartley (2025), "Narratives to Numbers: LLMs and EPU" — arXiv:2511.17866
### Gueta et al. (2025), "Can LLMs Learn Macroeconomic Narratives from Social Media?" — *Findings of NAACL*

GPT-4o / multilingual LLMs to extract structured narratives from WSJ/NYT inflation articles (Schmidt); recast Baker-Bloom-Davis EPU with LLM classifiers across 360M articles (Hartley); test LLM narrative extraction from Twitter (Gueta — answer: barely works).

**Overlap:** LOW (method), HIGH (timeliness). These are the cutting edge. Schmidt's negative result — even GPT-4o "still falls short of expert-level performance" on complex narrative extraction — is evidence that BERTopic-on-Qwen3 is not an obsolete choice.

**Cite as:** the LLM-frontier reference set. Honest framing for the prereg:

> "Recent LLM-based narrative-extraction approaches (Schmidt et al. 2025; Hartley 2025; Gueta et al. 2025) are promising but remain bounded by inter-annotator agreement with expert gold standards and have not been validated at corpus scale or across multi-year time windows. The embedding+BERTopic pipeline used here trades expressive sophistication for reproducibility and explicit cluster-stability validation."

---

## 5. Dictionary / sentiment ancestors

Citation block to acknowledge the prior text-as-data literature without engaging it in depth:

- Tetlock (2007), "Giving Content to Investor Sentiment" — *JF*
- Garcia (2013), "Sentiment during Recessions" — *JF*
- Loughran & McDonald (2011), "When is a Liability not a Liability?" — *JF*
- Baker, Bloom & Davis (2016), "Measuring Economic Policy Uncertainty" — *QJE*
- Manela & Moreira (2017), "News Implied Volatility (NVIX)" — *JFE*

These measure intensity (one number per period), not narrative topics (many topic shares per period). Cite collectively in one introductory paragraph.

### Hassan, Hollander, van Lent & Tahoun (2019), "Firm-Level Political Risk" — *QJE*
Text-mine earnings calls for firm-level political risk exposure. Keyword-in-context measure, not topic model.

**Cite as:** evidence that text-as-data measurement of policy/risk constructs is now standard in top-5 economics journals.

---

## 6. Methodological survey papers

- **Ash & Hansen (2023), "Text Algorithms in Economics" — *Annual Review of Economics* 15: 659-688.** The canonical survey of text-as-data methods in economics. Reference Ash-Hansen's four-task taxonomy.
- **Gentzkow, Kelly & Taddy (2019), "Text as Data" — *JEL* 57(3): 535-574.** The earlier canonical survey.
- **Roos & Reccius (2024), "Narratives in economics" — *Journal of Economic Surveys*.** The most recent narrative-economics-specific survey. Useful for the "field is still consolidating" framing.

---

## 7. Public-facing dashboards and live tools

**Direct comparables: none found.** No published live or public-facing dashboard does what Macro Narrative Dynamics is building (multi-source institutional/academic corpus → clustered narratives → lifecycle-stage labels → dynamics curves with documented anchor validation).

**Adjacent tools that exist:**

- **Baker-Bloom-Davis EPU** at `policyuncertainty.com` — live, public, peer-reviewed, single-index (not narratives). The institutional precedent for an academic narrative-measurement tool with public output.
- **Firm-Level Political Risk dashboard (Hassan et al.)** at `firmlevelrisk.com` — firm-quarterly granularity, exposure scores, not narratives or lifecycle.
- **Truflation** — real-time inflation dashboard, sources millions of price points; not narrative measurement.
- **BIS Working Paper 1231 ("Monetary policy in the news") + BIS CB-LMs initiative (WP 1215)** — internal central-bank NLP tooling, not public.
- **BERTrend (RTE France, open source)** — pure trend-detection library, not a macro-narrative dashboard.

**What's missing from comparables that this project provides:**

1. Explicit lifecycle-stage labels grounded in SIR/logistic fits rather than ad-hoc thresholds.
2. Institutional+academic source mix rather than newspapers-only or filings-only.
3. Anchor-narrative validation as a published artifact.
4. Shiller-explicit framing as live operationalization.

---

## 8. Differentiation summary

### Where this project genuinely advances

- **No published work fits SIR/logistic ODEs to multi-source institutional+academic narrative volume series and labels lifecycle stages.** Bertsch et al. is closest but reports a single fragmentation index, not per-narrative lifecycle. Medeiros et al. (2026) defines emergence statistically but does not extend through peak and decay. This is genuinely new.
- **No published work releases a live, public, dashboard-facing version of narrative lifecycle measurement.** Baker-Bloom-Davis EPU is the only adjacent public artifact, and it is a single index.
- **The institutional+academic source mix is broader than any published comparable.** Bybee = WSJ only; Larsen-Thorsrud = one Norwegian paper; Bertsch = newspapers only; Hansen-McMahon-Prat = FOMC only.
- **Anchor-narrative validation against 10 pre-documented events with stability tested via bootstrap NMI** is more rigorous than the post-hoc validation in most precedent work.

### Where this project sits within field consensus

These items are not novel, and that's fine — the contribution is integrative:

- BERTopic-on-transformer-embeddings is now standard in non-economics NLP (BERTrend, many adjacent papers).
- LDA-and-relatives for macro discourse is well-established since Hansen et al. 2014/2018.
- Treating Shiller as the conceptual anchor is now standard (Roos & Reccius 2024).
- Validating text-based macro measures against known anchor dates is standard since Manela-Moreira (2017) and Baker-Bloom-Davis (2016).

### Honest limitations to acknowledge

- **No causal-economic-effect estimates.** Flynn-Sastry (2024) does this structurally; this project does not and should not claim to.
- **The "narrative" definition is operational, not theoretical.** A BERTopic cluster is a measurement-driven proxy for "narrative", not a theoretically grounded definition. Roos & Reccius (2024) would push us to define this more carefully — worth a half-page discussion in the eventual paper.
- **No household-vs-expert narrative comparison.** Andre et al. (forthcoming) does this with surveys; this project measures only the expert/policy side.

---

## 9. Insights to incorporate

Items to fold into `docs/METHODOLOGY.md`, the pre-registration, and the eventual paper:

1. **Cite Bybee et al. (2024) and Bertsch et al. (2021) as the two methodological pillars in `METHODOLOGY.md`.** Bybee = the topic-model-on-business-news *JF* precedent; Bertsch = the temporal-narrative-dynamics *Economics Letters* precedent. Differentiation: multi-source institutional+academic + lifecycle ODE + BERTopic-on-Qwen3 rather than LDA/D-ETM + public dashboard.
2. **Frame Shiller operationalization honestly in the prereg.** Roos & Reccius (2024) explicitly note no one has operationalized Shiller rigorously. Do not over-claim.
   > "We operationalize the lifecycle dynamics half of Shiller's framework — emergence, growth, peak, decay — by fitting SIR/logistic ODEs to BERTopic cluster volume. We do not claim to measure narrative virality or causal effects on macro outcomes; that is left to structural work in the Flynn-Sastry tradition."
3. **Position the LLM frontier explicitly** in `METHODOLOGY.md`. Cite Schmidt et al. (2025), Hartley (2025), and Gueta et al. (2025). Strong defense of methodology choice: LLM-based narrative extraction is promising but unvalidated at scale; embeddings + BERTopic remains the more reproducible 2026 approach.
4. **Andre et al. is the strongest justification for the institutional-discourse focus.** Their finding — household narratives differ qualitatively from expert narratives — implies the policy/academic discourse measured here is the *upstream supply side* of the narratives households eventually adopt. This is a stronger story than "we measure all narratives."
5. **Add BERTrend (Boutaleb et al. 2024) and Medeiros et al. (2026) as the methodological adjacents** in the stability/validation section.

---

## 10. Uncertainty / verification flags

All resolvable citations have been verified:

- ✅ **Bybee, Kelly, Manela & Xiu (2024)** — confirmed *Journal of Finance* 79(5), 3105-3147 (DOI 10.1111/jofi.13377). Won Dimensional Fund Advisors Distinguished Paper Prize 2024. The earlier "Review of Financial Studies" reference that appeared in some search summaries is incorrect.
- ✅ **Larsen & Thorsrud (2019)** — confirmed *Journal of Econometrics* 210(1), 203-218 ("The value of news for economic developments"). The "Larsen 2021 *International Journal of Forecasting*" citation that previously appeared in our docs (and in some web search summaries) is **misattributed / non-existent**; we use the correct citation now.
- ✅ **Larsen, Thorsrud & Zhulanova (2021)** — *Journal of Monetary Economics* 117, 507-520 (companion paper on news-driven inflation expectations).
- ✅ **Boutaleb, Picault & Grosjean (2024) BERTrend** — confirmed ACL FuturED Workshop; open source at `github.com/rte-france/BERTrend`. We have read the methodology and assessed augmentation vs. replacement (see §3 above).

Still worth fuller reading before the eventual paper's literature review (paywalled or PDF-only):
- Schmidt et al. (2025), Hartley (2025), Gueta et al. (2025) — LLM-frontier papers.
- Bertsch et al. (2021) — D-ETM methodology details.
- Medeiros et al. (2026) — emergence-detection thresholds.

---

## 11. Key references (consolidated)

| Citation | Why it matters here |
|---|---|
| Shiller (2017) AEA Presidential Address; Shiller (2019) *Narrative Economics* | The conceptual anchor |
| Bybee, Kelly, Manela & Xiu (2024), "Business News and Business Cycles" | Closest methodological precedent (LDA on WSJ) |
| Larsen & Thorsrud (2019, *JoE*); Larsen, Thorsrud & Zhulanova (2021, *JME*) | Narratives in macro discourse, single-newspaper LDA |
| Hansen, McMahon & Prat (2018, *QJE*) | LDA on Fed text — top-5 precedent |
| Bertsch, Hull, Lumsdaine & Zhang (2021, *Economics Letters*) | Narrative dynamics over time (D-ETM); closest temporal precedent |
| Flynn & Sastry (2024, NBER WP 32602) | Structural theory complement |
| Andre, Haaland, Roth, Wiederholt & Wohlfart (forthcoming *RES*) | Justifies institutional-focus |
| Roos & Reccius (2024, *Journal of Economic Surveys*) | Field-state survey |
| Boutaleb et al. (2024) BERTrend; Medeiros et al. (2026) | BERTopic+temporal, emergence detection precedents |
| Schmidt et al. (2025); Hartley (2025); Gueta et al. (2025) | LLM-frontier reference set |
| Tetlock (2007, *JF*); Garcia (2013, *JF*); Loughran-McDonald (2011, *JF*); Manela-Moreira (2017, *JFE*); Baker-Bloom-Davis (2016, *QJE*) | Dictionary/sentiment ancestors |
| Hassan, Hollander, van Lent & Tahoun (2019, *QJE*) | Text-mining firm political risk |
| Ash & Hansen (2023, *Annual Review of Economics*); Gentzkow, Kelly & Taddy (2019, *JEL*) | Text-as-data methodological surveys |

---

*Document version: 2026-05-19. Maintain by adding new entries as the literature evolves; flag obsolete claims with strikethroughs rather than deleting.*
