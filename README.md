# bellwether

A tool to examine how macroeconomic narratives form, rise, and fade. This project reads sixteen years (2010–present) of
U.S. macro-financial discourse from academic and institutional sources — the Fed, the IMF, the BIS, the NBER and their
peers — clusters it into narratives, and tracks each story.

**Live site: [ellisgarver.github.io/bellwether](https://ellisgarver.github.io/bellwether/)**

The analysis surfaces a 3-D map of the narrative landscape, a catalog of
every charted narrative with its life-cycle stage, an emerging-signals feed, and
per-narrative pages that chart each story's volume against classical growth
curves, broad-press coverage, and market series.

## The idea

The original idea was inspired by Robert Shiller's *Narrative Economics*: economic stories spread
through a population like contagious ideas, and the stories people carry shape
the decisions they make. This tool extends that idea to what can be
measured and incorporates other models and lenses of analysis.

## How it works

- **Corpus** — a fixed basis set of twelve feeds spanning the independent
  dimensions of U.S. macro discourse: the Federal Reserve Board and four
  regional Feds, the IMF, the BIS, the CBO and CEA, the Treasury's OFR,
  Brookings, PIIE, the NBER, VoxEU, and Congressional testimony. Everything
  from every source is ingested; nothing is filtered by topic.
- **Narratives** — documents are embedded with Qwen3-Embedding-8B and clustered
  with BERTopic; each cluster of related writing is a narrative candidate,
  scoped after the fact against the standard AEA JEL taxonomy. Narratives with
  at least 42 unique articles are charted in full; smaller clusters stay in the
  directory as forming signals.
- **Life-cycles** — each narrative's stage (growth, stable, decay, dormant) is
  read model-free from its own volume trajectory with a trend test. Epidemic (SIR),
  logistic, and Bass adoption curves are fit alongside as interpretive lenses,
  each reported with its fit quality, but not used to decide the stage.
- **Context** — broad-press story counts (Media Cloud) and market series (FRED)
  serve as overlays for each narrative for lead–lag comparison; both are display-only and
  don't directly contribute to the analysis.

Every threshold is a published library default or a value cited from primary
literature, every random step flows from the one fixed seed, and parameters aren't
ever tuned toward recovering known events. The full methodology, with the
citation behind each choice, can be found in
[`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).

## Repository

| | |
|---|---|
| `src/mnd/` | the full pipeline: ingestion, filtering, embedding, clustering, dynamics, staging, overlays, artifact baking |
| `scripts/run_pipeline.py` | one CLI for every stage |
| `config/config.yaml` | every threshold and seed |
| `web/` | the static Astro site, built from baked JSON artifacts |
| `docs/` | methodology and the architecture-decision log |
| `data/anchors/` | the ten documented anchor narratives used for validation |

## References

The core anchors; the full cited set, with the choice each one backs, is in
[`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) §7 and the literature survey in
[`docs/related_work.md`](docs/related_work.md).

- **Framing** — Shiller (2017), "Narrative Economics," *AER* 107(4); Shiller (2019), *Narrative Economics*, Princeton; Roos & Reccius (2024), *J. Economic Surveys* 38(2).
- **Closest precedents** — Bybee, Kelly, Manela & Xiu (2024), *J. Finance* 79(5); Larsen & Thorsrud (2019), *J. Econometrics* 210(1); Hansen, McMahon & Prat (2018), *QJE* 133(2); Bertsch et al. (2021), *Economics Letters* 201; Flynn & Sastry (2024), NBER WP 32602; Andre et al. (2025), *REStud* advance article.
- **Method** — Grootendorst (2022), BERTopic, arXiv:2203.05794; McInnes et al. (2018), UMAP; McInnes & Healy (2017), HDBSCAN; Thakur et al. (2021), BEIR (NeurIPS); Qwen3-Embedding-8B model card; Broder (1997) MinHash; Henzinger (2006).
- **Dynamics & staging** — Kermack & McKendrick (1927); Schlickeiser & Kröger (2020), *J. Phys. A* 53:505601; Verhulst (1838); Bass (1969); Sultan, Farley & Lehmann (1990); Mann (1945); Kendall (1948); Hamed & Rao (1998); Sen (1968); Wallinga & Lipsitch (2007).
- **Overlays & validation** — Granger (1969); Brown & Warner (1985); Media Cloud (search.mediacloud.org); FRED (Federal Reserve Bank of St. Louis).

## License

MIT for code. Data ingested from third-party sources retains its original
license terms. Raw articles are not redistributed; only derived analyses
(cluster assignments, life-cycle parameters, narrative summaries) are
published.
