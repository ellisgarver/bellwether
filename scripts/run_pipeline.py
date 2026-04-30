"""Pipeline orchestration CLI (plan §9.1).

Dispatches the six Phase 1 pipeline stages:
  ingest    — fetch raw articles from configured sources
  filter    — topic filter + near-duplicate removal
  embed     — encode articles to embeddings (primary or comparator model)
  cluster   — BERTopic hierarchical clustering
  stability — bootstrap stability eval (kill criterion 1: mean NMI ≥ 0.40)
  validate  — anchor narrative recovery (kill criterion 2: ≥7/10 recovered)

All paths default to config.paths.*. Override with --input / --output flags.

Example Phase 1 pilot run:
  python scripts/run_pipeline.py ingest --start 2023-09-01 --end 2024-02-29
  python scripts/run_pipeline.py filter
  python scripts/run_pipeline.py embed --role primary
  python scripts/run_pipeline.py cluster
  python scripts/run_pipeline.py stability
  python scripts/run_pipeline.py validate --anchors anchor_01_svb,anchor_07_credit_suisse,anchor_10_soft_landing
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running as a script without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import click
import numpy as np
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

from mnd.utils.config import load_config, project_root
from mnd.utils.logging import get_logger

log = get_logger("run_pipeline")


@click.group()
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Macro Narrative Dynamics pipeline runner."""
    ctx.ensure_object(dict)
    ctx.obj["cfg"] = load_config()


# ---------------------------------------------------------------------------
# ingest
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--start", required=True, help="Start date YYYY-MM-DD")
@click.option("--end", required=True, help="End date YYYY-MM-DD")
@click.option(
    "--sources", default="gdelt,fed",
    show_default=True,
    help="Comma-separated source IDs: gdelt, fed, paywalled. Use 'paywalled' only "
         "when PROQUEST_API_TOKEN is set.",
)
@click.pass_context
def ingest(ctx: click.Context, start: str, end: str, sources: str) -> None:
    """Fetch raw articles from configured ingestion sources."""
    from datetime import date as date_t

    from mnd.ingestion import (
        FederalReserveIngestor,
        GdeltIngestor,
        PaywalledSourceIngestor,
    )

    cfg = ctx.obj["cfg"]
    root = project_root()
    raw_dir = root / cfg["paths"]["raw_articles"]
    raw_dir.mkdir(parents=True, exist_ok=True)

    start_d = date_t.fromisoformat(start)
    end_d = date_t.fromisoformat(end)

    ingestor_map = {
        "gdelt": GdeltIngestor,
        "fed": FederalReserveIngestor,
        "paywalled": PaywalledSourceIngestor,
    }

    for name in [s.strip() for s in sources.split(",")]:
        if name not in ingestor_map:
            log.warning("Unknown source '%s' — skipping", name)
            continue
        out_path = raw_dir / f"{name}_{start}_{end}.jsonl"
        log.info("Ingesting %s → %s", name, out_path)
        try:
            ingestor = ingestor_map[name]()
            articles = list(ingestor.fetch(start_d, end_d))
            ingestor.write_jsonl(iter(articles), out_path)
            log.info("  Wrote %d articles", len(articles))
        except NotImplementedError as exc:
            log.warning("  %s: not yet implemented — %s", name, exc)
        except EnvironmentError as exc:
            log.error("  %s: credentials not set — %s", name, exc)
        except Exception as exc:
            log.error("  %s failed: %s", name, exc, exc_info=True)


# ---------------------------------------------------------------------------
# filter
# ---------------------------------------------------------------------------

@cli.command("filter")
@click.option("--input-dir", default=None, help="Raw articles directory")
@click.option("--output", default=None, help="Output parquet path")
@click.pass_context
def filter_cmd(
    ctx: click.Context, input_dir: str | None, output: str | None
) -> None:
    """Apply topic filter and near-duplicate removal."""
    from mnd.filtering import Deduplicator, TopicFilter

    cfg = ctx.obj["cfg"]
    root = project_root()
    raw_dir = Path(input_dir) if input_dir else root / cfg["paths"]["raw_articles"]
    out_path = Path(output) if output else root / cfg["paths"]["processed_articles"]

    articles = _load_raw_articles(raw_dir)
    log.info("Loaded %d raw articles from %s", len(articles), raw_dir)
    if not articles:
        log.error("No articles found. Run `ingest` first.")
        sys.exit(1)

    tf = TopicFilter()
    tf.filter(articles)
    passed = [a for a in articles if a.raw_metadata.get("passed_filter")]
    log.info("Topic filter: %d/%d passed", len(passed), len(articles))

    unique = Deduplicator().deduplicate(passed)
    log.info("After dedup: %d unique articles", len(unique))

    _save_articles_parquet(unique, out_path)
    log.info("Saved filtered articles → %s", out_path)


# ---------------------------------------------------------------------------
# embed
# ---------------------------------------------------------------------------

@cli.command()
@click.option(
    "--role", default="primary",
    type=click.Choice(["primary", "comparator"]),
    show_default=True,
)
@click.option("--input", "input_path", default=None, help="Input parquet path")
@click.option("--output", default=None, help="Output .npy path")
@click.pass_context
def embed(
    ctx: click.Context, role: str, input_path: str | None, output: str | None
) -> None:
    """Encode articles to embeddings with primary or comparator model."""
    from mnd.embedding.embedder import Embedder, prepare_text_for_embedding

    cfg = ctx.obj["cfg"]
    root = project_root()
    parquet_path = (
        Path(input_path) if input_path else root / cfg["paths"]["processed_articles"]
    )
    npy_path = (
        Path(output) if output else root / cfg["paths"]["processed_embeddings"]
    )

    df = pd.read_parquet(parquet_path)
    texts = [
        prepare_text_for_embedding(
            str(row.get("title", "")), str(row.get("body", ""))
        )
        for row in df.to_dict("records")
    ]
    log.info("Embedding %d articles with %s model", len(texts), role)

    embedder = Embedder.from_config(role)  # type: ignore[arg-type]
    embeddings = embedder.encode(texts)

    npy_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(str(npy_path), embeddings)
    log.info("Saved embeddings %s → %s", embeddings.shape, npy_path)


# ---------------------------------------------------------------------------
# cluster
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--articles", default=None, help="Processed articles parquet path")
@click.option("--embeddings", default=None, help="Embeddings .npy path")
@click.option("--output", default=None, help="Output clusters parquet path")
@click.pass_context
def cluster(
    ctx: click.Context,
    articles: str | None,
    embeddings: str | None,
    output: str | None,
) -> None:
    """Run BERTopic hierarchical clustering."""
    from mnd.clustering import BertopicPipeline

    cfg = ctx.obj["cfg"]
    root = project_root()
    arts_path = Path(articles) if articles else root / cfg["paths"]["processed_articles"]
    emb_path = Path(embeddings) if embeddings else root / cfg["paths"]["processed_embeddings"]
    out_path = Path(output) if output else root / cfg["paths"]["processed_clusters"]

    df = pd.read_parquet(arts_path)
    emb = np.load(str(emb_path))
    docs = (df["title"].fillna("") + " " + df["body"].fillna("")).tolist()

    pipeline = BertopicPipeline.from_config()
    results = pipeline.fit_transform(docs, emb)

    df["topic_fine"] = results["hierarchical"]["fine"]
    df["topic_medium"] = results["hierarchical"]["medium"]
    df["topic_coarse"] = results["hierarchical"]["coarse"]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    results["topic_info"].to_parquet(
        out_path.parent / "topic_info.parquet", index=False
    )
    log.info(
        "Saved clusters (%d topics at fine level) → %s", results["n_topics"], out_path
    )


# ---------------------------------------------------------------------------
# stability
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--articles", default=None)
@click.option("--embeddings", default=None)
@click.pass_context
def stability(
    ctx: click.Context, articles: str | None, embeddings: str | None
) -> None:
    """Bootstrap stability evaluation — kill criterion 1 (NMI ≥ 0.40)."""
    from mnd.clustering import BertopicPipeline

    cfg = ctx.obj["cfg"]
    root = project_root()
    arts_path = Path(articles) if articles else root / cfg["paths"]["processed_articles"]
    emb_path = Path(embeddings) if embeddings else root / cfg["paths"]["processed_embeddings"]

    df = pd.read_parquet(arts_path)
    emb = np.load(str(emb_path))
    docs = (df["title"].fillna("") + " " + df["body"].fillna("")).tolist()

    pipeline = BertopicPipeline.from_config()
    result = pipeline.evaluate_stability(docs, emb)

    click.echo("\nBootstrap Stability Results")
    click.echo(f"  Replicates : {result['n_replicates']}")
    click.echo(f"  Mean NMI   : {result['mean_nmi']:.3f} ± {result['std_nmi']:.3f}")
    click.echo(f"  Mean ARI   : {result['mean_ari']:.3f} ± {result['std_ari']:.3f}")
    click.echo(f"  Threshold  : NMI ≥ {result['min_nmi_threshold']:.2f}")
    click.echo(f"  Status     : {'PASS' if result['passed'] else 'FAIL — kill criterion 1 triggered'}")

    if not result["passed"]:
        sys.exit(1)


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

@cli.command()
@click.option(
    "--anchors", default="all",
    help="Comma-separated anchor IDs or 'all'",
)
@click.option("--clusters", default=None, help="Clusters parquet path")
@click.pass_context
def validate(
    ctx: click.Context, anchors: str, clusters: str | None
) -> None:
    """Anchor recovery validation — kill criterion 2 (≥7/10 recovered)."""
    from mnd.validation import validate_anchor_recovery

    cfg = ctx.obj["cfg"]
    root = project_root()
    clusters_path = (
        Path(clusters) if clusters else root / cfg["paths"]["processed_clusters"]
    )

    df = pd.read_parquet(clusters_path)
    anchor_ids = None if anchors == "all" else [a.strip() for a in anchors.split(",")]

    results = validate_anchor_recovery(df, anchor_ids=anchor_ids, cfg=cfg)
    n_recovered = sum(1 for r in results if r["recovered"])
    required = cfg["validation"]["required_anchors_recovered"]

    click.echo("\nAnchor Recovery Results")
    for r in results:
        mark = "✓" if r["recovered"] else "✗"
        click.echo(f"  {mark} {r['anchor_id']}: {r['note']}")

    click.echo(f"\n  Recovered : {n_recovered}/{len(results)}")
    click.echo(f"  Required  : {required}")
    passed = n_recovered >= required
    click.echo(f"  Status    : {'PASS' if passed else 'FAIL — kill criterion 2 triggered'}")

    if not passed:
        sys.exit(1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_raw_articles(raw_dir: Path):
    from mnd.ingestion.base import Article

    articles = []
    for jsonl_file in sorted(raw_dir.glob("*.jsonl")):
        with jsonl_file.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                articles.append(
                    Article(**{k: v for k, v in data.items() if k in Article.__dataclass_fields__})
                )
    return articles


def _save_articles_parquet(articles, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([a.to_dict() for a in articles]).to_parquet(str(out_path), index=False)


if __name__ == "__main__":
    cli()
