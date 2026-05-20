"""Pipeline orchestration CLI.

Dispatches pipeline stages:
  ingest              — fetch raw articles from institutional/academic sources
  filter-pre-embed    — filter raw JSONL to exclude archived journalism sources
  filter              — topic filter + near-duplicate removal
  embed               — encode articles to embeddings (all-mpnet-base-v2)
  cluster             — BERTopic single-granularity clustering (ADR-019)
  stability           — bootstrap stability diagnostic (mean NMI reported, not gated)
  validate            — anchor narrative recovery (reported as rate, not gated)
  corpus-composition  — report article counts per source per year (Phase 2 QA step)

All paths default to config.paths.*. Override with --input / --output flags.

Phase 2 full-corpus ingestion (ADR-010; run on RCC via SLURM scripts):
  python scripts/run_pipeline.py ingest --start 2010-01-01 --end 2025-12-31 --sources institutional
  python scripts/run_pipeline.py filter-pre-embed   # excludes archived journalism sources
  python scripts/run_pipeline.py filter
  python scripts/run_pipeline.py embed --role primary
  python scripts/run_pipeline.py cluster
  python scripts/run_pipeline.py stability
  python scripts/run_pipeline.py validate --anchors all

Phase 2 corpus QA (after full ingestion):
  python scripts/run_pipeline.py corpus-composition
  python scripts/run_pipeline.py corpus-composition --by-tier --output data/processed/corpus_composition.csv

Note: AP News, Reuters, and MarketWatch have been removed from the semantic corpus
(ADR-010). Their raw JSONL is retained in data/raw/articles/ but excluded from
embedding by the filter-pre-embed step. RavenPack provides the journalism dynamics
signal (Layer 1B); see src/mnd/ingestion/ravenpack.py.
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
    "--sources", default="institutional",
    show_default=True,
    help=(
        "Comma-separated source IDs. 'institutional' is the standard composite covering "
        "Fed (FOMC/speeches/Beige Book/FEDS Notes), Regional Feds, IMF, BIS, CBO, Treasury/OFR, "
        "Congressional testimony, VoxEU, Brookings, PIIE, CFR (Tiers 1–2). 'imf' runs the "
        "IMFIngestor standalone — useful for small-window debug probes without paying for "
        "the full composite cycle (ADR-014). arXiv and Jackson Hole removed in ADR-012. "
        "AP News, Reuters, and MarketWatch removed in ADR-010 — see scripts/archive/."
    ),
)
@click.option("--output-dir", default=None, help="Output directory for raw JSONL files (overrides config default)")
@click.pass_context
def ingest(
    ctx: click.Context, start: str, end: str, sources: str, output_dir: str | None,
) -> None:
    """Fetch raw articles from institutional/academic sources (ADR-010)."""
    from datetime import date as date_t

    from mnd.ingestion import InstitutionalIngestor
    from mnd.ingestion.institutional import IMFIngestor

    cfg = ctx.obj["cfg"]
    root = project_root()
    raw_dir = Path(output_dir) if output_dir else root / cfg["paths"]["raw_articles"]
    raw_dir.mkdir(parents=True, exist_ok=True)

    start_d = date_t.fromisoformat(start)
    end_d = date_t.fromisoformat(end)

    _checkpoint_ext = {"institutional": "json"}

    def _make_ingestor(name: str, cp_path):
        if name == "institutional":
            return InstitutionalIngestor(checkpoint_path=cp_path)
        if name == "imf":
            return IMFIngestor()
        raise ValueError(
            f"Unknown source: '{name}'. Valid: 'institutional', 'imf' (standalone debug — ADR-014). "
            "AP News, Reuters, and MarketWatch have been removed from the semantic corpus (ADR-010)."
        )

    valid_sources = {"institutional", "imf"}

    for name in [s.strip() for s in sources.split(",")]:
        if name not in valid_sources:
            log.error(
                "Unknown or inactive source '%s'. Valid: %s. "
                "AP News, Reuters, and MarketWatch have been removed from the semantic corpus (ADR-010).",
                name, valid_sources,
            )
            continue
        out_path = raw_dir / f"{name}_{start}_{end}.jsonl"
        ext = _checkpoint_ext.get(name, "txt")
        checkpoint_path = raw_dir / f".{name}_checkpoint.{ext}"
        resume = checkpoint_path.exists() and out_path.exists()
        mode = "a" if resume else "w"
        log.info(
            "Ingesting %s → %s (%s)",
            name, out_path, "appending (checkpoint resume)" if resume else "new file",
        )
        try:
            ingestor = _make_ingestor(name, checkpoint_path)
            count = 0
            with out_path.open(mode, encoding="utf-8") as fh:
                for article in ingestor.fetch(start_d, end_d):
                    fh.write(article.to_jsonl())
                    fh.write("\n")
                    count += 1
            log.info("  Wrote %d articles to %s", count, out_path)
        except NotImplementedError as exc:
            log.warning("  %s: not yet implemented — %s", name, exc)
        except EnvironmentError as exc:
            log.error("  %s: credentials not set — %s", name, exc)
        except Exception as exc:
            log.error("  %s failed: %s", name, exc, exc_info=True)


# ---------------------------------------------------------------------------
# filter-pre-embed  (new in ADR-010)
# ---------------------------------------------------------------------------

_EXCLUDED_SOURCES = {
    # Journalism tier removed in ADR-010 (2026-05-11)
    "ap_news", "apnews", "marketwatch", "reuters",
    # arXiv removed in ADR-012 (2026-05-13): 2017-only coverage, low macro volume
    "arxiv",
    # Jackson Hole removed in ADR-012: covered by FederalReserveIngestor
    "jackson_hole",
}


@cli.command("filter-pre-embed")
@click.option("--input-dir", default=None, help="Raw articles directory (default: config paths.raw_articles)")
@click.option("--output", default=None, help="Output JSONL path (default: config paths.corpus_for_embedding)")
@click.pass_context
def filter_pre_embed(
    ctx: click.Context, input_dir: str | None, output: str | None
) -> None:
    """Filter raw JSONL to exclude removed sources before embedding.

    Reads all JSONL files from the raw articles directory, drops records where
    source_id is in the excluded set (journalism tier, arXiv, Jackson Hole),
    and writes the filtered corpus to corpus_for_embedding.jsonl.

    Excluded sources: ap_news, apnews, marketwatch, reuters (ADR-010);
    arxiv, jackson_hole (ADR-012).

    Run this after ingestion and before the filter / embed stages.
    """
    cfg = ctx.obj["cfg"]
    root = project_root()
    raw_dir = Path(input_dir) if input_dir else root / cfg["paths"]["raw_articles"]
    out_path = Path(output) if output else root / cfg["paths"]["corpus_for_embedding"]
    out_path.parent.mkdir(parents=True, exist_ok=True)

    jsonl_files = sorted(raw_dir.glob("*.jsonl"))
    if not jsonl_files:
        log.error("No JSONL files found in %s. Run `ingest` first.", raw_dir)
        sys.exit(1)

    total = 0
    kept = 0
    excluded = 0
    excluded_sources: dict[str, int] = {}

    with out_path.open("w", encoding="utf-8") as fh:
        for jsonl_file in jsonl_files:
            with jsonl_file.open(encoding="utf-8") as src:
                for line in src:
                    line = line.strip()
                    if not line:
                        continue
                    total += 1
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    source_id = record.get("source_id", record.get("source", ""))
                    if source_id.lower() in _EXCLUDED_SOURCES:
                        excluded += 1
                        excluded_sources[source_id] = excluded_sources.get(source_id, 0) + 1
                        continue
                    fh.write(line + "\n")
                    kept += 1

    log.info("filter-pre-embed: %d total → %d kept, %d excluded", total, kept, excluded)
    if excluded_sources:
        for src, n in sorted(excluded_sources.items()):
            log.info("  excluded %s: %d articles", src, n)
    log.info("Output: %s", out_path)


# ---------------------------------------------------------------------------
# filter
# ---------------------------------------------------------------------------

@cli.command("filter")
@click.option("--input-dir", default=None, help="Raw articles directory (used only if corpus_for_embedding is absent)")
@click.option("--input", "input_jsonl", default=None, help="Filtered corpus JSONL (overrides corpus_for_embedding)")
@click.option("--output", default=None, help="Output parquet path")
@click.pass_context
def filter_cmd(
    ctx: click.Context, input_dir: str | None, input_jsonl: str | None, output: str | None
) -> None:
    """Date-range filter and near-duplicate removal.

    Per MND_PROJECT_SPEC rev3 Stage 2: no topic filter is applied — all Layer 1A
    sources are macro-relevant by construction. Only two operations run:
      1. Date range filter: retain documents with publication_date in [2010-01-01, present]
      2. Near-duplicate removal: MinHash-based dedup within rolling 48-hour windows

    Input precedence (auto-detected to enforce ADR-010 / ADR-012 source exclusion):
      1. --input <jsonl>                           (explicit override)
      2. cfg.paths.corpus_for_embedding            (written by `filter-pre-embed`)
      3. cfg.paths.raw_articles directory          (with inline source exclusion)

    When falling back to (3), records whose source_id is in _EXCLUDED_SOURCES are
    dropped at load time so AP News / MarketWatch / Reuters / arXiv / Jackson Hole
    JSONL files never reach embedding even if `filter-pre-embed` was skipped.
    """
    from datetime import date as date_t

    from mnd.filtering import Deduplicator

    cfg = ctx.obj["cfg"]
    root = project_root()
    out_path = Path(output) if output else root / cfg["paths"]["processed_articles"]

    corpus_path = root / cfg["paths"]["corpus_for_embedding"]
    raw_dir = Path(input_dir) if input_dir else root / cfg["paths"]["raw_articles"]

    if input_jsonl:
        src_path = Path(input_jsonl)
        if not src_path.exists():
            log.error("--input %s not found", src_path)
            sys.exit(1)
        log.info("Loading filtered corpus JSONL: %s", src_path)
        articles = _load_jsonl_articles(src_path, exclude_sources=_EXCLUDED_SOURCES)
    elif corpus_path.exists():
        log.info("Loading corpus_for_embedding JSONL (filter-pre-embed output): %s", corpus_path)
        # filter-pre-embed already excluded archived sources, but defensively re-apply
        articles = _load_jsonl_articles(corpus_path, exclude_sources=_EXCLUDED_SOURCES)
    else:
        log.warning(
            "corpus_for_embedding.jsonl missing at %s — falling back to raw_articles directory %s. "
            "Run `filter-pre-embed` first for canonical ADR-010/012 enforcement. Inline exclusion is applied here as a backstop.",
            corpus_path, raw_dir,
        )
        articles = _load_raw_articles(raw_dir, exclude_sources=_EXCLUDED_SOURCES)

    log.info("Loaded %d articles for filtering (after archived-source exclusion)", len(articles))
    if not articles:
        log.error("No articles found. Run `ingest` (and optionally `filter-pre-embed`) first.")
        sys.exit(1)

    # Date range filter — keep 2010-01-01 to today
    date_start = date_t(2010, 1, 1)
    date_end = date_t.today()
    in_range = []
    for a in articles:
        pub = getattr(a, "published_at", None) or ""
        try:
            pub_date = date_t.fromisoformat(pub[:10])
            if date_start <= pub_date <= date_end:
                in_range.append(a)
        except (ValueError, TypeError):
            continue  # drop articles with unparseable dates
    log.info("Date range filter: %d/%d in [2010-01-01, %s]", len(in_range), len(articles), date_end)

    unique = Deduplicator().deduplicate(in_range)
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
    help=(
        "Embedding role (ADR-011). 'primary' = Qwen3-Embedding-0.6B (production). "
        "'comparator' = all-mpnet-base-v2 (look-ahead sensitivity check only — "
        "compares Δ_NMI pre-2021 vs post-2021 against primary)."
    ),
)
@click.option("--input", "input_path", default=None, help="Input parquet path")
@click.option("--output", default=None, help="Output .npy path")
@click.pass_context
def embed(
    ctx: click.Context, role: str, input_path: str | None, output: str | None
) -> None:
    """Encode articles to embeddings (Qwen3 primary; mpnet comparator for look-ahead check)."""
    from mnd.embedding.embedder import Embedder

    cfg = ctx.obj["cfg"]
    root = project_root()
    parquet_path = (
        Path(input_path) if input_path else root / cfg["paths"]["processed_articles"]
    )
    if output:
        npy_path = Path(output)
    elif role == "comparator":
        base = root / cfg["paths"]["processed_embeddings"]
        npy_path = base.with_name("embeddings_comparator.npy")
    else:
        npy_path = root / cfg["paths"]["processed_embeddings"]

    from mnd.processing.chunker import chunk_corpus

    chunks_path = root / cfg["paths"]["processed_chunks"]
    if chunks_path.exists():
        log.info("Loading existing chunks from %s", chunks_path)
        chunk_df = pd.read_parquet(chunks_path)
    else:
        log.info("Chunking corpus from %s", parquet_path)
        df = pd.read_parquet(parquet_path)
        chunk_df = chunk_corpus(df)
        chunks_path.parent.mkdir(parents=True, exist_ok=True)
        chunk_df.to_parquet(chunks_path, index=False)
        log.info("Saved %d chunks → %s", len(chunk_df), chunks_path)

    # Build the per-chunk text fed to the embedder. The chunker (chunk_corpus)
    # has already enforced the 600-BPE-token chunk window; we therefore do NOT
    # additionally call prepare_text_for_embedding (which would re-truncate to
    # 600 *whitespace* tokens and defeat the long-context strategy on RCC).
    # The embedder's max_seq_len + the model tokenizer handle final truncation.
    texts: list[str] = []
    for row in chunk_df.to_dict("records"):
        title = str(row.get("title") or "").strip()
        body = str(row.get("body") or "").strip()
        if title and body:
            texts.append(f"{title}. {body}")
        else:
            texts.append(title or body)
    log.info("Embedding %d chunks with %s model → %s", len(texts), role, npy_path)

    embedder = Embedder.from_config(role)  # type: ignore[arg-type]
    embeddings = embedder.encode(texts)

    if embeddings.shape[0] != len(chunk_df):
        raise RuntimeError(
            f"Embedding row count {embeddings.shape[0]} does not match chunk count {len(chunk_df)}. "
            "Refusing to save misaligned matrix — downstream clustering would corrupt silently."
        )

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
@click.option(
    "--min-cluster-size",
    default=None,
    type=int,
    help=(
        "Override config hdbscan.min_cluster_size for this run only. "
        "PILOT USE ONLY — do not use for Phase 2+ runs. "
        "Production value (20) stays locked in config.yaml."
    ),
)
@click.pass_context
def cluster(
    ctx: click.Context,
    articles: str | None,
    embeddings: str | None,
    output: str | None,
    min_cluster_size: int | None,
) -> None:
    """Run BERTopic single-granularity clustering (ADR-019)."""
    from mnd.clustering import BertopicPipeline

    cfg = ctx.obj["cfg"]
    root = project_root()
    arts_path = Path(articles) if articles else root / cfg["paths"]["processed_chunks"]
    emb_path = Path(embeddings) if embeddings else root / cfg["paths"]["processed_embeddings"]
    out_path = Path(output) if output else root / cfg["paths"]["processed_clusters"]

    df = pd.read_parquet(arts_path)
    emb = np.load(str(emb_path))
    if emb.shape[0] != len(df):
        raise RuntimeError(
            f"Embedding matrix has {emb.shape[0]} rows but chunks parquet has {len(df)} rows. "
            "Refusing to cluster — row misalignment would silently corrupt cluster assignments. "
            "Re-run `embed` to regenerate the embedding matrix against the current chunks.parquet."
        )
    docs = (df["title"].fillna("") + " " + df["body"].fillna("")).tolist()

    if min_cluster_size is not None:
        locked_value = cfg["clustering"]["hdbscan"]["min_cluster_size"]
        log.warning(
            "PILOT OVERRIDE: hdbscan.min_cluster_size set to %d "
            "(config.yaml production value: %d). "
            "This in-memory override does not modify config.yaml. "
            "Restore to %d for Phase 2 full-corpus runs.",
            min_cluster_size,
            locked_value,
            locked_value,
        )
        cfg["clustering"]["hdbscan"]["min_cluster_size"] = min_cluster_size

    pipeline = BertopicPipeline(cfg)
    results = pipeline.fit_transform(docs, emb)

    df["topic"] = results["topics"]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    results["topic_info"].to_parquet(
        out_path.parent / "topic_info.parquet", index=False
    )
    log.info(
        "Saved clusters (%d topics) → %s", results["n_topics"], out_path
    )


# ---------------------------------------------------------------------------
# stability
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--articles", default=None)
@click.option("--embeddings", default=None)
@click.option(
    "--min-cluster-size",
    default=None,
    type=int,
    help=(
        "Override config hdbscan.min_cluster_size for this run only. "
        "PILOT USE ONLY — production value stays locked in config.yaml."
    ),
)
@click.pass_context
def stability(
    ctx: click.Context,
    articles: str | None,
    embeddings: str | None,
    min_cluster_size: int | None,
) -> None:
    """Bootstrap stability diagnostic — mean NMI reported, not gated (ADR-019)."""
    from mnd.clustering import BertopicPipeline

    cfg = ctx.obj["cfg"]
    root = project_root()
    # Embeddings are chunk-aligned (chunk_corpus splits long docs), so docs must
    # come from processed_chunks — not processed_articles — to match row counts.
    arts_path = Path(articles) if articles else root / cfg["paths"]["processed_chunks"]
    emb_path = Path(embeddings) if embeddings else root / cfg["paths"]["processed_embeddings"]

    df = pd.read_parquet(arts_path)
    emb = np.load(str(emb_path))
    if emb.shape[0] != len(df):
        raise RuntimeError(
            f"Embedding matrix has {emb.shape[0]} rows but chunks parquet has {len(df)} rows. "
            "Refusing to evaluate stability — row misalignment would silently corrupt NMI/ARI. "
            "Re-run `embed` to regenerate the embedding matrix against the current chunks.parquet."
        )
    docs = (df["title"].fillna("") + " " + df["body"].fillna("")).tolist()

    if min_cluster_size is not None:
        locked_value = cfg["clustering"]["hdbscan"]["min_cluster_size"]
        log.warning(
            "PILOT OVERRIDE: hdbscan.min_cluster_size set to %d "
            "(config.yaml production value: %d). "
            "This in-memory override does not modify config.yaml. "
            "Restore to %d for Phase 2 full-corpus runs.",
            min_cluster_size,
            locked_value,
            locked_value,
        )
        cfg["clustering"]["hdbscan"]["min_cluster_size"] = min_cluster_size

    pipeline = BertopicPipeline(cfg)
    result = pipeline.evaluate_stability(docs, emb)

    all_nmi = result["all_nmi"]
    median_nmi = float(np.median(all_nmi)) if all_nmi else 0.0

    click.echo("\nBootstrap Stability Results")
    click.echo(f"  Replicates : {result['n_replicates']}")
    click.echo(f"  Mean NMI   : {result['mean_nmi']:.3f} ± {result['std_nmi']:.3f}")
    click.echo(f"  Median NMI : {median_nmi:.3f}")
    click.echo(f"  Mean ARI   : {result['mean_ari']:.3f} ± {result['std_ari']:.3f}")
    click.echo("\n  Per-replicate NMI scores:")
    for i, nmi in enumerate(all_nmi, 1):
        click.echo(f"    [{i:02d}] {nmi:.3f}")


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

@cli.command()
@click.option(
    "--anchors", default="all",
    help="Comma-separated anchor IDs or 'all'",
)
@click.option("--clusters", default=None, help="Clusters parquet path")
@click.option(
    "--required",
    default=None,
    type=int,
    help=(
        "Override the minimum number of anchors that must be recovered for PASS. "
        "Defaults to config.validation.required_anchors_recovered (7). "
        "Use for pilot runs where fewer than 10 anchors are tested, or where "
        "some anchors are structurally absent from the corpus window."
    ),
)
@click.pass_context
def validate(
    ctx: click.Context, anchors: str, clusters: str | None, required: int | None
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

    config_required = cfg["validation"]["required_anchors_recovered"]
    if required is not None and required != config_required:
        log.warning(
            "PILOT OVERRIDE: --required set to %d (config.yaml production value: %d). "
            "Use only when testing a subset of anchors whose corpus window excludes "
            "some reference events. Full 10-anchor gate (required=%d) applies in Phase 4.",
            required,
            config_required,
            config_required,
        )
    effective_required = required if required is not None else config_required

    click.echo("\nAnchor Recovery Results")
    for r in results:
        mark = "✓" if r["recovered"] else "✗"
        click.echo(f"  {mark} {r['anchor_id']}: {r['note']}")

    click.echo(f"\n  Recovered : {n_recovered}/{len(results)}")
    click.echo(f"  Required  : {effective_required}" +
               (f"  (config default: {config_required})" if required is not None else ""))
    passed = n_recovered >= effective_required
    click.echo(f"  Status    : {'PASS' if passed else 'FAIL — kill criterion 2 triggered'}")

    if not passed:
        sys.exit(1)


# ---------------------------------------------------------------------------
# corpus-composition
# ---------------------------------------------------------------------------

@cli.command("corpus-composition")
@click.option("--input-dir", default=None, help="Raw articles directory (default: config.paths.raw_articles)")
@click.option("--articles", default=None, help="Processed articles parquet path (used if raw dir is empty)")
@click.option("--output", default=None, help="Write CSV to this path (default: stdout only)")
@click.option("--by-tier", is_flag=True, default=False, help="Break down counts by tier in addition to source")
@click.pass_context
def corpus_composition(
    ctx: click.Context,
    input_dir: str | None,
    articles: str | None,
    output: str | None,
    by_tier: bool,
) -> None:
    """Report article counts per source per year — Phase 2 corpus QA.

    Reads either the raw JSONL files (preferred) or the processed parquet.
    Outputs a table to stdout; optionally writes a CSV for downstream analysis.

    Use this after full ingestion to detect:
      - Coverage gaps (years with zero articles for an outlet)
      - Balance issues (one outlet dominating the corpus)
      - Missing Tier 4 coverage (AP News / MarketWatch absent pre-2015)
    """
    cfg = ctx.obj["cfg"]
    root = project_root()
    raw_dir = Path(input_dir) if input_dir else root / cfg["paths"]["raw_articles"]

    # Load from raw JSONL if available; fall back to processed parquet
    if raw_dir.exists() and any(raw_dir.glob("*.jsonl")):
        art_list = _load_raw_articles(raw_dir)
        records = [
            {
                "source_id": a.source_id,
                "year": a.published_at[:4] if a.published_at else "unknown",
                "tier": a.tier,
                "retrieval": a.retrieval,
            }
            for a in art_list
        ]
        log.info("Loaded %d raw articles from %s", len(records), raw_dir)
    else:
        arts_path = Path(articles) if articles else root / cfg["paths"]["processed_articles"]
        if not arts_path.exists():
            log.error("No raw articles in %s and no processed parquet at %s. Run `ingest` first.", raw_dir, arts_path)
            sys.exit(1)
        df_arts = pd.read_parquet(arts_path)
        records = []
        for _, row in df_arts.iterrows():
            pub = str(row.get("published_at", ""))
            records.append({
                "source_id": row.get("source_id", "unknown"),
                "year": pub[:4] if pub else "unknown",
                "tier": row.get("tier", 0),
                "retrieval": row.get("retrieval", "unknown"),
            })
        log.info("Loaded %d processed articles from %s", len(records), arts_path)

    if not records:
        log.warning("No articles found.")
        sys.exit(0)

    df = pd.DataFrame(records)
    total = len(df)

    # Count by source × year
    pivot = (
        df.groupby(["source_id", "year"])
        .size()
        .unstack(fill_value=0)
        .sort_index()
    )

    click.echo(f"\nCorpus composition — {total} total articles\n")
    click.echo(pivot.to_string())
    click.echo(f"\nTotal by source:\n{df.groupby('source_id').size().sort_values(ascending=False).to_string()}")

    if by_tier:
        click.echo(f"\nTotal by tier:\n{df.groupby('tier').size().sort_index().to_string()}")
        click.echo(f"\nTotal by retrieval method:\n{df.groupby('retrieval').size().sort_values(ascending=False).to_string()}")

    # Coverage gaps: sources with years that have 0 articles while other sources have >0
    all_years = sorted(df["year"].unique())
    sources = sorted(df["source_id"].unique())
    gaps = []
    for src in sources:
        src_years = set(df[df["source_id"] == src]["year"].unique())
        missing = [y for y in all_years if y not in src_years and y != "unknown"]
        if missing:
            gaps.append((src, missing))

    if gaps:
        click.echo("\nCoverage gaps (sources missing in year):")
        for src, missing_years in gaps:
            click.echo(f"  {src}: missing {', '.join(missing_years)}")
    else:
        click.echo("\nNo coverage gaps detected.")

    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        pivot.to_csv(out_path)
        log.info("Wrote corpus composition CSV → %s", out_path)


# ---------------------------------------------------------------------------
# sample-check
# ---------------------------------------------------------------------------

# Minimum article count per institutional sub-source when sampling up to
# --max-per-source articles from a full calendar year.  These are conservative
# floors; hitting zero for any source with min > 0 indicates a fetch failure.
# NBER and SSRN are not in the historical composite (Phase 6 live RSS only)
# and are therefore not probed here. AP News / MarketWatch / Reuters and arXiv
# / Jackson Hole are removed per ADR-010 / ADR-012.
_INST_MIN_COUNTS: dict[str, int] = {
    "federalreserve": 5,
    "fed_regional":   3,
    "congressional":  0,   # sparse; best-effort
    "imf":            2,   # Coveo + curl_cffi path (ADR-014); WEO/GFSR are 2x/yr
    "bis":            3,
    "cbo":            0,   # sitemap path (ADR-013); publication pages 403 on residential IPs
    "treasury_ofr":   0,   # sparse; best-effort
    "voxeu":          5,
    "brookings":      2,
    "piie":           2,
    "cfr":            2,
}


@cli.command("sample-check")
@click.option(
    "--source", required=True,
    type=click.Choice(["institutional"]),
    help="Which source to probe (only 'institutional' is active per ADR-010/012)",
)
@click.option("--start", default=None, help="Override start date (YYYY-MM-DD)")
@click.option("--end", default=None, help="Override end date (YYYY-MM-DD)")
@click.option(
    "--max-per-source", default=20, show_default=True,
    help="Max articles fetched per institutional sub-source (limits runtime)",
)
@click.pass_context
def sample_check(
    ctx: click.Context,
    source: str,
    start: str | None,
    end: str | None,
    max_per_source: int,
) -> None:
    """Connectivity and content-quality probe — run before any RCC submission.

    Institutional: fetches up to --max-per-source articles per sub-source for
    the given year (default 2024) and reports counts against minimum thresholds.

    Journalism probes (apnews / marketwatch) were removed in ADR-010 — the
    archived ingestors live under scripts/archive/ and are not part of the
    semantic corpus.
    """
    from datetime import date as date_t

    # only 'institutional' is accepted; click already validates the choice
    start_d = date_t.fromisoformat(start) if start else date_t(2024, 1, 1)
    end_d = date_t.fromisoformat(end) if end else date_t(2024, 12, 31)
    _sample_check_institutional(start_d, end_d, max_per_source)


def _sample_check_institutional(
    start, end, max_per_source: int
) -> None:
    from mnd.ingestion.institutional import (
        BISIngestor, BrookingsIngestor, CBOIngestor, CFRIngestor,
        CongressionalIngestor, FedRegionalIngestor, IMFIngestor,
        PIIEIngestor, TreasuryOFRIngestor, VoxEUIngestor,
    )
    from mnd.ingestion.fed import FederalReserveIngestor

    # Mirror InstitutionalIngestor._sub_ingestors exactly. IMF re-enabled in
    # ADR-014 via Coveo Search + curl_cffi Chrome impersonation.
    # NBER and SSRN are Phase-6 live RSS only.
    sub_ingestors = [
        FederalReserveIngestor(),
        FedRegionalIngestor(),
        CongressionalIngestor(),
        IMFIngestor(),
        BISIngestor(),
        TreasuryOFRIngestor(),
        CBOIngestor(),
        VoxEUIngestor(),
        BrookingsIngestor(),
        PIIEIngestor(),
        CFRIngestor(),
    ]

    click.echo(f"\n=== Institutional sample-check ({start} → {end}, cap {max_per_source}/source) ===\n")
    failures = []
    for ingestor in sub_ingestors:
        sid = ingestor.source_id
        min_expected = _INST_MIN_COUNTS.get(sid, 0)
        articles = []
        try:
            for art in ingestor.fetch(start, end):
                articles.append(art)
                if len(articles) >= max_per_source:
                    break
        except Exception as exc:
            click.echo(f"  {sid:20s}  ERROR: {exc}", err=True)
            failures.append(sid)
            continue

        count = len(articles)
        status = "OK" if count >= min_expected else ("WARN (0 articles)" if count == 0 else "WARN (below min)")
        mark = "✓" if count >= min_expected else "✗"
        click.echo(f"  {mark} {sid:20s}  {count:3d} articles (min expected: {min_expected}) [{status}]")

        if articles:
            for art in articles[:3]:
                snippet = (art.body or "")[:120].replace("\n", " ")
                click.echo(f"      title: {art.title}")
                click.echo(f"      body:  {snippet}…")
        click.echo()

        if count < min_expected:
            failures.append(sid)

    click.echo("─" * 60)
    if failures:
        click.echo(f"FAIL — {len(failures)} source(s) below threshold: {', '.join(failures)}", err=True)
        sys.exit(1)
    else:
        click.echo("PASS — all sources at or above minimum expected counts")


# Journalism sample-check (apnews / marketwatch) was removed with the journalism
# tier in ADR-010. See scripts/archive/ for the archived ingestor code.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_raw_articles(raw_dir: Path, exclude_sources: set[str] | None = None):
    """Load every JSONL under raw_dir into Article objects.

    Skips malformed lines (counted) and records whose source_id is in
    exclude_sources (case-insensitive). Returns the list of Article objects.
    """
    from mnd.ingestion.base import Article

    excluded = {s.lower() for s in (exclude_sources or set())}
    articles = []
    n_malformed = 0
    n_excluded = 0
    excluded_breakdown: dict[str, int] = {}
    for jsonl_file in sorted(raw_dir.glob("*.jsonl")):
        with jsonl_file.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    n_malformed += 1
                    continue
                source_id = (data.get("source_id") or data.get("source") or "").lower()
                if source_id in excluded:
                    n_excluded += 1
                    excluded_breakdown[source_id] = excluded_breakdown.get(source_id, 0) + 1
                    continue
                try:
                    articles.append(
                        Article(**{k: v for k, v in data.items() if k in Article.__dataclass_fields__})
                    )
                except (TypeError, ValueError) as exc:
                    n_malformed += 1
                    log.debug("Article construct failed: %s", exc)
    if n_malformed:
        log.warning("_load_raw_articles: skipped %d malformed JSONL lines", n_malformed)
    if n_excluded:
        log.info("_load_raw_articles: excluded %d archived-source records (%s)",
                 n_excluded,
                 ", ".join(f"{s}={n}" for s, n in sorted(excluded_breakdown.items())))
    return articles


def _load_jsonl_articles(jsonl_path: Path, exclude_sources: set[str] | None = None):
    """Load a single JSONL file (typically corpus_for_embedding.jsonl) into Articles."""
    from mnd.ingestion.base import Article

    excluded = {s.lower() for s in (exclude_sources or set())}
    articles = []
    n_malformed = 0
    n_excluded = 0
    with jsonl_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                n_malformed += 1
                continue
            source_id = (data.get("source_id") or data.get("source") or "").lower()
            if source_id in excluded:
                n_excluded += 1
                continue
            try:
                articles.append(
                    Article(**{k: v for k, v in data.items() if k in Article.__dataclass_fields__})
                )
            except (TypeError, ValueError) as exc:
                n_malformed += 1
                log.debug("Article construct failed: %s", exc)
    if n_malformed:
        log.warning("_load_jsonl_articles: skipped %d malformed JSONL lines in %s", n_malformed, jsonl_path)
    if n_excluded:
        log.info("_load_jsonl_articles: excluded %d archived-source records from %s", n_excluded, jsonl_path)
    return articles


def _save_articles_parquet(articles, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([a.to_dict() for a in articles]).to_parquet(str(out_path), index=False)


if __name__ == "__main__":
    cli()
