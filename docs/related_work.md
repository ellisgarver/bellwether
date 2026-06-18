# Related work — quantitative macro-narrative measurement

A survey of the published literature relevant to quantitative macro-narrative measurement.

The individual components are field-standard, and most have precedents: epidemic models of idea and rumour spread go back to Goffman & Newill (1964) and Daley & Kendall (1965); SIR and logistic curves have since been fit to news, citations, and online topics; topic-model studies of macro discourse are an established stream. What is uncommon as a single artifact is the combination — a multi-source institutional and academic corpus → BERTopic on transformer embeddings → SIR/logistic/Bass life-cycle fits per narrative cluster → anchor validation → a public dashboard. The contribution is integrative and operational: a tool for reading past and present macro narratives rather than a new method.

---

## 1. State of the field (2026)

Quantitative macro-narrative measurement is an active but still-consolidating subfield. Roos & Reccius (2024, *Journal of Economic Surveys*) — the most cited recent survey — concludes that "we cannot speak of *the* narrative approach to economics or a coherent field of narrative economics." Empirical methods have proliferated faster than theory; there is no generally accepted definition of an "economic narrative", and the choice of extraction method (dictionary, LDA, embedded topic model, BERTopic, LLM-extracted) is driven by tooling availability rather than theoretical commitment.

Shiller's 2017 AEA Presidential Address and 2019 book are universally cited as the conceptual anchor. Shiller's actual empirical method — Google Ngrams keyword counts fit by visual analogy to epidemic curves — has rarely been operationalized rigorously.

The field has bifurcated into three streams:

1. **Topic-model-on-news/policy-text papers** — Hansen, McMahon & Prat (2018, *QJE*); Larsen & Thorsrud (2019, *Journal of Econometrics*); Bybee, Kelly, Manela & Xiu (2024); Bertsch, Hull, Lumsdaine & Zhang (2021, *Economics Letters*); Flynn & Sastry (2024, NBER WP). Extract latent themes from large corpora and correlate them with macro variables. This is the methodological mainstream and the closest comparator stream.
2. **Dictionary/sentiment papers** — Tetlock (2007, *JF*); Garcia (2013, *JF*); Loughran & McDonald (2011, *JF*); Baker, Bloom & Davis (2016, *QJE*); Manela & Moreira (2017, *JFE*). Extract a single intensity index rather than narrative topics.
3. **Survey/experimental papers** — Andre, Haaland, Roth, Wiederholt & Wohlfart (forthcoming, *Review of Economic Studies*). Directly elicit narratives from households or experts and represent them as DAGs.

A fourth, very recent stream uses LLMs at sentence/document level (Schmidt et al. 2025; Gueta et al. 2025; Hartley 2025). These target the "what is a narrative" extraction problem rather than the lifecycle dynamics problem.

Epidemic-style models have been fit to the spread of ideas and information — Goffman & Newill (1964) on scientific ideas, Daley & Kendall (1965) on rumors, and a more recent literature on news and citation cascades — so the model itself is not new. What is uncommon is fitting these lifecycle curves to a multi-source institutional/academic macro corpus, labeling stages, and surfacing the result publicly. Shiller proposed the macro framing; published empirical work in this subfield has largely stopped at descriptive trajectories or correlations with macro outcomes.

---

## 2. Closest methodological precedents

### Bybee, Kelly, Manela & Xiu (2024), "Business News and Business Cycles" — *Journal of Finance* 79(5), 3105-3147 (DOI 10.1111/jofi.13377)
LDA topic model fit to ~800,000 *Wall Street Journal* articles 1984-2017, 180 topics. Show news attention tracks aggregate activity, explains ~25% of stock returns, and adds incremental forecasting power beyond numerical indicators. Awarded Dimensional Fund Advisors Distinguished Paper Prize 2024.

**Overlap:** HIGH (method), MEDIUM (corpus). The most architecturally similar published work, and the methodological precedent for topic-share-on-business-news measurement. Single-source corpus (WSJ only); classical LDA rather than embedding-based clustering; no lifecycle/dynamics fitting — the topic share is correlated with macro variables rather than fit with ODEs.

### Larsen & Thorsrud (2019), "The value of news for economic developments" — *Journal of Econometrics*
LDA on Norwegian business newspaper text. Extract topics, use them as conditioning variables for nowcasting GDP and inflation expectations. Companion paper Larsen, Thorsrud & Zhulanova (2021, *JME*) on news-driven inflation expectations shows some topics behave like "animal spirits" — disconnected from fundamentals.

**Overlap:** HIGH (intent), MEDIUM (method). The most direct prior demonstration that topic-model output behaves like narratives in the Shiller sense. Single-newspaper LDA rather than multi-source + BERTopic; no lifecycle modeling; Norway, not the U.S.

### Hansen, McMahon & Prat (2018), "Transparency and Deliberation within the FOMC" — *QJE*
LDA on FOMC transcripts pre/post the 1993 transparency reform. Measure conformity, discipline, and topic concentration as functions of attribution.

**Overlap:** MEDIUM. The same institutional source (FOMC) and family of methods, applied to causal identification of transparency effects rather than narrative-lifecycle measurement. Its topic-coherence and stability diagnostics are a field-standard validation approach.

### Bertsch, Hull, Lumsdaine & Zhang (2021), "Narrative Fragmentation and the Business Cycle" — *Economics Letters* + Riksbank WP 401
Dynamic embedded topic model (D-ETM) on 1950-2019 newspaper articles. Show narratives consolidate during expansions and fragment during contractions.

**Overlap:** HIGH (conceptual), MEDIUM (method). The closest published precedent for narrative dynamics over time at the macro level. Uses a neural-embedding-augmented topic model — conceptually a precursor to BERTopic-on-embeddings — and reports a single fragmentation index rather than per-narrative lifecycle curves.

### Flynn & Sastry (2024), "The Macroeconomics of Narratives" — NBER WP 32602
NLP on 10-K filings to extract narrative shares; embed a viral narrative in a neoclassical business-cycle model; estimate narratives explain 32% of the 2001 recession output decline and 18% of the Great Recession.

**Overlap:** MEDIUM (theory), LOW (corpus, dynamics method). The most theoretically ambitious narrative-economics paper, modelling narrative virality structurally over a corpus of firm filings. This project measures lifecycle empirically over policy/academic text and supplies the descriptive measurement infrastructure that structural work of this kind requires.

### Andre, Haaland, Roth, Wiederholt & Wohlfart (forthcoming, *Review of Economic Studies*), "Narratives about the Macroeconomy"
Open-ended surveys of 10,000+ U.S. households and 100 academic experts about inflation causes; represent narratives as DAGs; experiment shows narratives shape inflation expectations.

**Overlap:** LOW (method), HIGH (subject). Complementary survey-elicited household narratives rather than text-extracted policy narratives. Its central empirical finding — expert narratives differ qualitatively from household narratives — bears directly on a focus on institutional/expert discourse, which is the upstream supply side that surveys of households do not measure.

---

## 3. Adjacent technical precedents

### Boutaleb, Picault & Grosjean (2024), "BERTrend: Neural Topic Modeling for Emerging Trends Detection" — ACL FuturED Workshop ([repo: rte-france/BERTrend](https://github.com/rte-france/BERTrend))

BERTopic adapted for **online incremental learning over time-sliced batches**. Documents arrive in time slices; BERTopic is run on each batch; topics from successive batches are merged via cosine similarity into a cumulative topic set; each topic gets a "popularity" score that considers both document count and update frequency over time; topics are classified into **noise / weak signal / strong signal** using dynamically chosen thresholds.

Novel relative to vanilla BERTopic:
1. Time-sliced batch processing with cross-batch topic merging (supports incremental updates without re-running the full pipeline).
2. A temporal popularity metric combining count and recency.
3. Heuristic signal-strength classification with dynamic thresholds.

**Overlap:** HIGH (technical adjacent), MEDIUM (intent), LOW (domain). The closest published BERTopic + temporal-dynamics precedent and the most widely-known open-source library for incremental BERTopic, applied to general weak-signal trend detection rather than economics.

The two approaches differ in their dynamics layer. BERTrend's signal classification rests on dynamically chosen popularity thresholds; the life-cycle staging here is keyed to the R₀ epidemic threshold (Kermack & McKendrick 1927). BERTrend reports a popularity trajectory and categorises it; this project fits parametric SIR and logistic models with Bayesian inference and reports R₀ with confidence intervals. BERTrend works from a single popularity signal; this project cross-validates institutional discourse against Media Cloud premium-press and broad-press volume. BERTrend validates qualitatively on weak-signal recovery; this project validates against 10 documented macro events with ±14d Brown & Warner (1985) event-study windows.

### Medeiros, Quigley & Revie (2026), "A Statistical Framework for Detecting Emergent Narratives in Longitudinal Text Corpora" — arXiv:2602.20939
LDA-based framework defining narrative emergence as "sustained increase in topic prominence." Validated on Nobel-Prize-recognized economic ideas 1970-2018.

**Overlap:** HIGH. The most direct contemporary precedent for the emergence-detection half of lifecycle classification; its Nobel-anchor validation is conceptually parallel to the 10-anchor validation here, and it defines emergence statistically without extending through peak and decay.

---

## 4. LLM-frontier work (recent, 2025+)

### Schmidt et al. (2025), "Identifying economic narratives in large text corpora" — arXiv:2506.15041
### Hartley (2025), "Narratives to Numbers: LLMs and EPU" — arXiv:2511.17866
### Gueta et al. (2025), "Can LLMs Learn Macroeconomic Narratives from Social Media?" — *Findings of NAACL*

GPT-4o / multilingual LLMs to extract structured narratives from WSJ/NYT inflation articles (Schmidt); recast Baker-Bloom-Davis EPU with LLM classifiers across 360M articles (Hartley); test LLM narrative extraction from Twitter (Gueta — answer: barely works).

**Overlap:** LOW (method), HIGH (timeliness). The current cutting edge. These approaches remain bounded by inter-annotator agreement with expert gold standards and have not been validated at corpus scale or across multi-year time windows; Schmidt's result is that even GPT-4o "still falls short of expert-level performance" on complex narrative extraction. Embedding + BERTopic trades expressive sophistication for reproducibility and explicit cluster-stability validation.

---

## 5. Dictionary / sentiment ancestors

The prior text-as-data literature measures intensity (one number per period) rather than narrative topics (many topic shares per period):

- Tetlock (2007), "Giving Content to Investor Sentiment" — *JF*
- Garcia (2013), "Sentiment during Recessions" — *JF*
- Loughran & McDonald (2011), "When is a Liability not a Liability?" — *JF*
- Baker, Bloom & Davis (2016), "Measuring Economic Policy Uncertainty" — *QJE*
- Manela & Moreira (2017), "News Implied Volatility (NVIX)" — *JFE*

### Hassan, Hollander, van Lent & Tahoun (2019), "Firm-Level Political Risk" — *QJE*
Text-mine earnings calls for firm-level political risk exposure via a keyword-in-context measure rather than a topic model — evidence that text-as-data measurement of policy/risk constructs is now standard in top-5 economics journals.

---

## 6. Methodological survey papers

- **Ash & Hansen (2023), "Text Algorithms in Economics" — *Annual Review of Economics* 15: 659-688.** The canonical survey of text-as-data methods in economics, organised around a four-task taxonomy.
- **Gentzkow, Kelly & Taddy (2019), "Text as Data" — *JEL* 57(3): 535-574.** The earlier canonical survey.
- **Roos & Reccius (2024), "Narratives in economics" — *Journal of Economic Surveys*.** The most recent narrative-economics-specific survey; the source for the "field is still consolidating" characterization.

---

## 7. Public-facing dashboards and live tools

No published live or public-facing dashboard combines a multi-source institutional/academic corpus, clustered narratives, lifecycle-stage labels, and dynamics curves with documented anchor validation.

Adjacent public tools:

- **Baker-Bloom-Davis EPU** at `policyuncertainty.com` — live, public, peer-reviewed, single-index. The institutional precedent for an academic narrative-measurement tool with public output.
- **Firm-Level Political Risk dashboard (Hassan et al.)** at `firmlevelrisk.com` — firm-quarterly exposure scores, not narratives or lifecycle.
- **Truflation** — real-time inflation dashboard sourced from millions of price points; not narrative measurement.
- **BIS Working Paper 1231 ("Monetary policy in the news") + BIS CB-LMs initiative (WP 1215)** — internal central-bank NLP tooling, not public.
- **BERTrend (RTE France, open source)** — a trend-detection library, not a macro-narrative dashboard.

Elements distinctive relative to these comparables:

1. Explicit lifecycle-stage labels grounded in SIR/logistic fits rather than ad-hoc thresholds.
2. An institutional and academic source mix rather than newspapers-only or filings-only.
3. Anchor-narrative validation as a published artifact.
4. Shiller-explicit framing as live operationalization.

---

## 8. Positioning

### Distinctive elements

- Fitting SIR/logistic/Bass lifecycle curves to a multi-source institutional and academic macro corpus and labeling per-narrative stages is uncommon. The epidemic-of-ideas lineage (Goffman & Newill 1964; Daley & Kendall 1965) and later news/citation-SIR work establish the model; Bertsch et al. is closest in spirit but reports a single fragmentation index, and Medeiros et al. (2026) defines emergence statistically without extending through peak and decay.
- Packaging narrative lifecycle measurement as a public, open-source dashboard is uncommon; the main adjacent public artifact, Baker-Bloom-Davis EPU, is a single index rather than a browsable set of staged narratives.
- The institutional and academic source mix is broader than the published comparables: Bybee = WSJ only; Larsen-Thorsrud = one Norwegian paper; Bertsch = newspapers only; Hansen-McMahon-Prat = FOMC only.
- Anchor-narrative validation against 10 pre-documented events, with stability tested via bootstrap NMI.

### Shared with field consensus

The following elements are standard in the field:

- BERTopic-on-transformer-embeddings is standard in non-economics NLP (BERTrend and many adjacent papers).
- LDA-and-relatives for macro discourse is well-established since Hansen et al. 2014/2018.
- Shiller as the conceptual anchor is standard (Roos & Reccius 2024).
- Validating text-based macro measures against known anchor dates is standard since Manela-Moreira (2017) and Baker-Bloom-Davis (2016).

---

## 9. Key references (consolidated)

| Citation | Why it matters here |
|---|---|
| Shiller (2017) AEA Presidential Address; Shiller (2019) *Narrative Economics* | The conceptual anchor |
| Goffman & Newill (1964, *Nature*); Daley & Kendall (1965, *Nature*) | Epidemic-of-ideas lineage the SIR framing builds on |
| Kermack & McKendrick (1927); Verhulst (1838); Bass (1969) | The lifecycle models fit per narrative |
| Bybee, Kelly, Manela & Xiu (2024), "Business News and Business Cycles" | Closest methodological precedent (LDA on WSJ) |
| Larsen & Thorsrud (2019, *JoE*); Larsen, Thorsrud & Zhulanova (2021, *JME*) | Narratives in macro discourse, single-newspaper LDA |
| Hansen, McMahon & Prat (2018, *QJE*) | LDA on Fed text — top-5 precedent |
| Bertsch, Hull, Lumsdaine & Zhang (2021, *Economics Letters*) | Narrative dynamics over time (D-ETM); closest temporal precedent |
| Flynn & Sastry (2024, NBER WP 32602) | Structural theory complement |
| Andre, Haaland, Roth, Wiederholt & Wohlfart (forthcoming *RES*) | Bears on the institutional-discourse focus |
| Roos & Reccius (2024, *Journal of Economic Surveys*) | Field-state survey |
| Boutaleb et al. (2024) BERTrend; Medeiros et al. (2026) | BERTopic+temporal, emergence detection precedents |
| Schmidt et al. (2025); Hartley (2025); Gueta et al. (2025) | LLM-frontier reference set |
| Tetlock (2007, *JF*); Garcia (2013, *JF*); Loughran-McDonald (2011, *JF*); Manela-Moreira (2017, *JFE*); Baker-Bloom-Davis (2016, *QJE*) | Dictionary/sentiment ancestors |
| Hassan, Hollander, van Lent & Tahoun (2019, *QJE*) | Text-mining firm political risk |
| Ash & Hansen (2023, *Annual Review of Economics*); Gentzkow, Kelly & Taddy (2019, *JEL*) | Text-as-data methodological surveys |
