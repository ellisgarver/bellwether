# Macro Narrative Dynamics

How macro narratives form, rise, and fade. This project reads fifteen years of U.S.
macro-financial discourse from academic and institutional sources — the Fed, the IMF, the BIS, the NBER and their peers
— clusters into narratives, and tracks each story.

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
  scoped after the fact against the standard AEA JEL taxonomy and seeded by >= 42.
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
citation behind each choice, is in
[`docs/METHODOLOGY.md`](docs/METHODOLOGY.md); every decision is logged in
[`docs/architecture_decisions.md`](docs/architecture_decisions.md).

## Repository

| | |
|---|---|
| `src/mnd/` | pipeline: ingestion, filtering, embedding, clustering, dynamics, staging, overlays, artifact baking |
| `scripts/run_pipeline.py` | one CLI for every stage |
| `config/config.yaml` | every threshold and seed |
| `web/` | the static Astro site, built from baked JSON artifacts |
| `docs/` | methodology and the architecture-decision log |
| `data/anchors/` | the ten documented anchor narratives used for validation |

## License

MIT for code. Data ingested from third-party sources retains its original
license terms. Raw articles are not redistributed; only derived analyses
(cluster assignments, life-cycle parameters, narrative summaries) are
published.
