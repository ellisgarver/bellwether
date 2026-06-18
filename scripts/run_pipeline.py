"""Pipeline orchestration CLI.

Dispatches pipeline stages:
  ingest              — fetch raw articles from the basis-set sources
  filter-pre-embed    — drop archived journalism sources from raw JSONL
  filter              — date-range filter + near-duplicate removal
  embed               — encode articles (Qwen3-Embedding-8B)
  cluster             — BERTopic single-granularity clustering
  stability           — bootstrap stability diagnostic (mean NMI reported, not gated)
  validate            — anchor narrative recovery (reported as rate, not gated)
  analyze             — clusters → normalize → JEL → dynamics → stages →
                        similar → dashboard artifacts (the pipeline→front-end seam)
  corpus-composition  — report article counts per source per year

All paths default to config.paths.*. Override with --input / --output flags.

Full-corpus runs go on RCC via the parallel fan-out, which chains the downstream
stages automatically: NUKE_RAW=1 bash scripts/rcc/submit_parallel_ingest.sh
The per-stage commands below are for local spot-runs / manual re-runs:
  python scripts/run_pipeline.py ingest --start 2010-01-01 --end 2025-12-31 --sources institutional
  python scripts/run_pipeline.py filter-pre-embed
  python scripts/run_pipeline.py filter
  python scripts/run_pipeline.py embed --role primary
  python scripts/run_pipeline.py cluster
  python scripts/run_pipeline.py stability
  python scripts/run_pipeline.py validate --anchors all
  python scripts/run_pipeline.py corpus-composition
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
        "Comma-separated source IDs. 'institutional' runs the full basis-set composite: "
        "federalreserve, fed_regional, congressional, imf, bis, treasury_ofr, "
        "cea, voxeu, brookings, piie, cbo, nber. Any of those names can also be passed "
        "individually to run a single source standalone — used to split the ingest into "
        "parallel SLURM jobs so no source starves behind a long pole."
    ),
)
@click.option("--output-dir", default=None, help="Output directory for raw JSONL files (overrides config default)")
@click.option(
    "--shard", default=None,
    help=(
        "Shard the walk as 'k/N' (0-based k, N total) — CBO only (ADR-038). "
        "Each shard owns pids where pid % N == k and writes its own "
        "'<src>_<win>_shard{k}of{N}.jsonl'. Lets independent egress IPs "
        "(e.g. RCC + laptop) walk disjoint slices in parallel; merge after with "
        "'cbo-merge-shards'. Requires a pre-built CDX cache. Omit for unsharded."
    ),
)
@click.pass_context
def ingest(
    ctx: click.Context, start: str, end: str, sources: str, output_dir: str | None,
    shard: str | None,
) -> None:
    """Fetch raw articles from institutional/academic sources (ADR-010)."""
    from datetime import date as date_t

    from mnd.ingestion import InstitutionalIngestor
    from mnd.ingestion.institutional import (
        BISIngestor,
        BrookingsIngestor,
        CBOIngestor,
        CEAIngestor,
        CongressionalIngestor,
        FedRegionalIngestor,
        FederalReserveIngestor,
        IMFIngestor,
        NBERIngestor,
        PIIEIngestor,
        TreasuryOFRIngestor,
        VoxEUIngestor,
    )

    # The 12 basis-set sub-ingestors (ADR-020), individually addressable so the
    # full ingest can be split into parallel single-source SLURM jobs (no
    # sub-ingestor starves behind a long pole, and each gets its own wall clock).
    # Keyed by source_id; each runs standalone and writes its own raw JSONL,
    # which filter-pre-embed later globs together with every other source file.
    _SUB_INGESTORS = {
        "federalreserve": FederalReserveIngestor,
        "fed_regional": FedRegionalIngestor,
        "congressional": CongressionalIngestor,
        "imf": IMFIngestor,
        "bis": BISIngestor,
        "treasury_ofr": TreasuryOFRIngestor,
        "cea": CEAIngestor,
        "voxeu": VoxEUIngestor,
        "brookings": BrookingsIngestor,
        "piie": PIIEIngestor,
        "cbo": CBOIngestor,
        "nber": NBERIngestor,
    }

    cfg = ctx.obj["cfg"]
    root = project_root()
    raw_dir = Path(output_dir) if output_dir else root / cfg["paths"]["raw_articles"]
    raw_dir.mkdir(parents=True, exist_ok=True)

    start_d = date_t.fromisoformat(start)
    end_d = date_t.fromisoformat(end)

    requested = [s.strip() for s in sources.split(",")]

    # Parse --shard k/N once (ADR-038). shard_count=1 → unsharded default.
    shard_index, shard_count = 0, 1
    if shard:
        try:
            k_str, n_str = shard.split("/", 1)
            shard_index, shard_count = int(k_str), int(n_str)
        except ValueError:
            raise click.BadParameter(f"--shard must be 'k/N' (got {shard!r})")
        if shard_count < 1 or not (0 <= shard_index < shard_count):
            raise click.BadParameter(
                f"--shard {shard!r}: need N>=1 and 0<=k<N"
            )
        if shard_count > 1 and requested != ["cbo"]:
            raise click.BadParameter(
                "--shard is only supported for --sources cbo (ADR-038); "
                f"got --sources {sources!r}"
            )

    _checkpoint_ext = {"institutional": "json"}

    # Sources that accept a per-record resume checkpoint when run standalone.
    # CBO's Wayback walk (~13.6k pids at the IA-safe ~1 req/9-12s) exceeds the
    # 36h caslake QOS cap, so it must resume across sequential jobs (ADR-023).
    _CHECKPOINTED_SUBS = {"cbo"}

    def _make_ingestor(name: str, cp_path):
        if name == "institutional":
            return InstitutionalIngestor(checkpoint_path=cp_path)
        if name == "cbo":
            return CBOIngestor(
                checkpoint_path=cp_path,
                shard_index=shard_index,
                shard_count=shard_count,
            )
        if name in _CHECKPOINTED_SUBS:
            return _SUB_INGESTORS[name](checkpoint_path=cp_path)
        if name in _SUB_INGESTORS:
            return _SUB_INGESTORS[name]()
        raise ValueError(
            f"Unknown source: '{name}'. Valid: 'institutional' (full composite), or any "
            f"single basis-set source: {', '.join(sorted(_SUB_INGESTORS))}. "
            "AP News, Reuters, and MarketWatch have been removed from the semantic corpus (ADR-010)."
        )

    valid_sources = {"institutional", *_SUB_INGESTORS}

    failures: list[tuple[str, str]] = []
    for name in requested:
        if name not in valid_sources:
            log.error(
                "Unknown or inactive source '%s'. Valid: %s. "
                "AP News, Reuters, and MarketWatch have been removed from the semantic corpus (ADR-010).",
                name, valid_sources,
            )
            failures.append((name, "unknown source"))
            continue
        # Sharded CBO runs write disjoint per-shard files (and per-shard
        # checkpoints) so independent egress IPs never touch the same output or
        # resume state; merge them later with 'cbo-merge-shards' (ADR-038).
        shard_tag = f"_shard{shard_index}of{shard_count}" if shard_count > 1 else ""
        out_path = raw_dir / f"{name}_{start}_{end}{shard_tag}.jsonl"
        ext = _checkpoint_ext.get(name, "txt")
        # Co-key the checkpoint to the SAME window as the output file. The
        # submit script stamps the window end with "today" by default, so a
        # multi-day resumable walk (CBO ~45h) gets a new output filename each
        # calendar day. A date-independent checkpoint would then tell the new
        # day's run that pids written to YESTERDAY's file are "done" and skip
        # them — silent under-capture across a split pair of files. Keying the
        # checkpoint by window guarantees checkpoint and output are always the
        # same generation: a date roll simply starts a clean new walk rather
        # than corrupting one. (Pin END=<date> across re-fires to resume.)
        checkpoint_path = raw_dir / f".{name}_{start}_{end}{shard_tag}_checkpoint.{ext}"
        resume = checkpoint_path.exists() and out_path.exists()
        mode = "a" if resume else "w"
        log.info(
            "Ingesting %s → %s (%s)",
            name, out_path, "appending (checkpoint resume)" if resume else "new file",
        )
        # Any failure to fully capture a source is fatal to this command. A
        # sub-ingestor fail-loud RAISE (transient fetch error, CDX truncation,
        # listing break) — or a 0-article window — must propagate to a non-zero
        # process exit. The parallel fan-out chains filter→embed→cluster on
        # afterok of every ingest job; swallowing the raise (exit 0) would run
        # the embed chain on a holey/truncated corpus. Partial output already
        # written to out_path is preserved for checkpoint-resume and debugging.
        try:
            ingestor = _make_ingestor(name, checkpoint_path)
            count = 0
            with out_path.open(mode, encoding="utf-8") as fh:
                for article in ingestor.fetch(start_d, end_d):
                    fh.write(article.to_jsonl())
                    fh.write("\n")
                    # Flush each record so a checkpointed ingestor (CBO) never
                    # marks a pid done before its article is durable on disk —
                    # a kill between write and flush would otherwise lose a
                    # record that the checkpoint claims was captured.
                    fh.flush()
                    count += 1
            log.info("  Wrote %d articles to %s", count, out_path)
            if count == 0:
                # On a resume that simply finished the tail, this run can
                # legitimately yield 0 new records while the output file is
                # already populated from prior jobs — that is completion, not
                # under-capture. Only a fresh (non-resume) 0 is a real failure.
                if resume and out_path.exists() and out_path.stat().st_size > 0:
                    log.info("  %s: 0 new articles on resume — walk already "
                             "complete (existing %d bytes).", name,
                             out_path.stat().st_size)
                else:
                    log.error("  %s produced 0 articles — under-capture; failing.", name)
                    failures.append((name, "0 articles"))
        except Exception as exc:
            log.error("  %s failed: %s", name, exc, exc_info=True)
            failures.append((name, str(exc)))

    if failures:
        log.error(
            "ingest: %d/%d source(s) failed — exiting non-zero so the afterok "
            "downstream chain halts and the gap is noticed: %s",
            len(failures), len(requested),
            ", ".join(f"{n} ({e})" for n, e in failures),
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# cbo-merge-shards  (ADR-038)
# ---------------------------------------------------------------------------

@cli.command("cbo-merge-shards")
@click.option("--start", required=True, help="Start date YYYY-MM-DD (the ingest window)")
@click.option("--end", required=True, help="End date YYYY-MM-DD (the ingest window)")
@click.option("--output-dir", default=None, help="Raw JSONL directory (overrides config default)")
@click.pass_context
def cbo_merge_shards(
    ctx: click.Context, start: str, end: str, output_dir: str | None
) -> None:
    """Merge sharded CBO output into the canonical single file (ADR-038).

    A sharded CBO run (``ingest --sources cbo --shard k/N``) writes one file per
    shard: ``cbo_<win>_shard{k}of{N}.jsonl``. The shards partition the pid space
    by ``pid % N``, so they are disjoint by construction — but we still dedup on
    article_id defensively (a pid re-crawled across a window roll could appear
    twice). The merged file is named ``cbo_<win>.jsonl`` so the filter-pre-embed
    glob sees exactly ONE CBO file; the shard files are renamed ``.merged`` so a
    stale shard never double-counts into the corpus.
    """
    import json

    root = project_root()
    cfg = ctx.obj["cfg"]
    raw_dir = Path(output_dir) if output_dir else root / cfg["paths"]["raw_articles"]

    shard_glob = f"cbo_{start}_{end}_shard*of*.jsonl"
    shard_files = sorted(raw_dir.glob(shard_glob))
    if not shard_files:
        log.error("cbo-merge-shards: no shard files match %s in %s — nothing to "
                  "merge (did the sharded run write output?)", shard_glob, raw_dir)
        sys.exit(1)

    out_path = raw_dir / f"cbo_{start}_{end}.jsonl"
    seen: set[str] = set()
    kept = 0
    dupes = 0
    with out_path.open("w", encoding="utf-8") as out_fh:
        for sf in shard_files:
            n_file = 0
            with sf.open(encoding="utf-8") as in_fh:
                for line in in_fh:
                    line = line.strip()
                    if not line:
                        continue
                    aid = json.loads(line).get("article_id")
                    if aid in seen:
                        dupes += 1
                        continue
                    seen.add(aid)
                    out_fh.write(line + "\n")
                    kept += 1
                    n_file += 1
            log.info("  %s → %d records", sf.name, n_file)

    for sf in shard_files:
        sf.rename(sf.with_suffix(sf.suffix + ".merged"))

    log.info(
        "cbo-merge-shards: %d shard files → %s (%d unique articles, %d cross-shard "
        "dupes dropped); shard files renamed .merged",
        len(shard_files), out_path, kept, dupes,
    )


# ---------------------------------------------------------------------------
# filter-pre-embed
# ---------------------------------------------------------------------------

# Archived before embedding: the journalism tier, arXiv, and the standalone
# Jackson Hole feed (now covered by FederalReserveIngestor).
_EXCLUDED_SOURCES = {
    "ap_news", "apnews", "marketwatch", "reuters",
    "arxiv",
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
      2. Near-duplicate removal: MinHash-based dedup across the full corpus

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
    help="Embedding role. 'primary' is the production Qwen3 embedder.",
)
@click.option("--input", "input_path", default=None, help="Input parquet path")
@click.option("--output", default=None, help="Output .npy path")
@click.option(
    "--full",
    "full_rebuild",
    is_flag=True,
    default=False,
    help=(
        "Ignore any cached embeddings and re-encode every chunk. Use when the "
        "embedder/model changed (ADR-050). Also triggered by MND_EMBED_FULL=1."
    ),
)
@click.pass_context
def embed(
    ctx: click.Context,
    role: str,
    input_path: str | None,
    output: str | None,
    full_rebuild: bool,
) -> None:
    """Encode articles to embeddings with the Qwen3 production embedder."""
    import os

    from mnd.embedding import cache as embed_cache
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

    # Incremental embedding cache (ADR-050): reuse vectors for chunks whose
    # (chunk_id, embedded-text) is unchanged so a weekly delta re-embeds only the
    # new/changed chunks. A full rebuild (archive/NUKE wipes data/processed, or
    # --full / MND_EMBED_FULL=1) starts from no cache and re-encodes everything.
    # The chunker has already enforced the 512-Qwen3-token window (ADR-019); the
    # embedder's max_seq_len + tokenizer handle any final truncation.
    index_path = embed_cache.index_path_for(npy_path)
    full = full_rebuild or os.environ.get("MND_EMBED_FULL") == "1"

    cached_index = None
    cached_matrix = None
    if not full and npy_path.exists() and index_path.exists():
        cached_index = pd.read_parquet(index_path)
        cached_matrix = np.load(str(npy_path))
        if len(cached_index) != cached_matrix.shape[0]:
            log.warning(
                "Embedding cache index (%d rows) and matrix (%d rows) disagree — "
                "ignoring cache and re-embedding in full.",
                len(cached_index),
                cached_matrix.shape[0],
            )
            cached_index = cached_matrix = None

    plan = embed_cache.plan_incremental(chunk_df, cached_index)
    mode = "full rebuild" if cached_index is None else "incremental"
    log.info(
        "Embedding %d chunks (%s) with %s model → %s — reuse %d cached, encode %d new",
        len(chunk_df),
        mode,
        role,
        npy_path,
        plan.n_reuse,
        plan.n_encode,
    )

    embedder = Embedder.from_config(role)  # type: ignore[arg-type]
    if plan.n_encode:
        fresh = embedder.encode([plan.texts[i] for i in plan.encode_positions])
    else:
        fresh = np.empty((0, cached_matrix.shape[1]), dtype=np.float32)

    if plan.n_encode and cached_matrix is not None and fresh.shape[1] != cached_matrix.shape[1]:
        raise RuntimeError(
            f"Embedder output dim {fresh.shape[1]} != cached dim {cached_matrix.shape[1]}. "
            "The embedder/model changed — re-run `embed --full` to invalidate the cache."
        )

    embeddings = embed_cache.assemble_matrix(plan, cached_matrix, fresh)

    if embeddings.shape[0] != len(chunk_df):
        raise RuntimeError(
            f"Embedding row count {embeddings.shape[0]} does not match chunk count {len(chunk_df)}. "
            "Refusing to save misaligned matrix — downstream clustering would corrupt silently."
        )

    npy_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(str(npy_path), embeddings)
    embed_cache.index_frame(plan).to_parquet(index_path, index=False)
    log.info("Saved embeddings %s → %s (+ index → %s)", embeddings.shape, npy_path, index_path)


@cli.command(name="embed-index")
@click.pass_context
def embed_index(ctx: click.Context) -> None:
    """Backfill the embedding index sidecar for an existing embeddings.npy (ADR-050).

    No re-embedding: derives [chunk_id, text_sha1] from the current
    chunks.parquet, row-aligned to the existing matrix, so a later incremental
    `embed` can reuse those vectors. Run once after a full run whose embeddings
    predate the cache, before any delta re-ingest.
    """
    from mnd.embedding import cache as embed_cache

    cfg = ctx.obj["cfg"]
    root = project_root()
    chunks_path = root / cfg["paths"]["processed_chunks"]
    npy_path = root / cfg["paths"]["processed_embeddings"]
    index_path = embed_cache.index_path_for(npy_path)

    chunk_df = pd.read_parquet(chunks_path)
    emb = np.load(str(npy_path), mmap_mode="r")
    if emb.shape[0] != len(chunk_df):
        raise RuntimeError(
            f"Embedding matrix has {emb.shape[0]} rows but chunks parquet has {len(chunk_df)} rows. "
            "Cannot backfill an aligned index — re-run `embed` to regenerate the matrix first."
        )

    plan = embed_cache.plan_incremental(chunk_df, cached_index=None)
    embed_cache.index_frame(plan).to_parquet(index_path, index=False)
    log.info("Wrote embedding index (%d rows) → %s", len(chunk_df), index_path)


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
@click.pass_context
def validate(ctx: click.Context, anchors: str, clusters: str | None) -> None:
    """Anchor recovery validation -- rate reported, not gated (ADR-019)."""
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

    click.echo("\nAnchor Recovery Results")
    for r in results:
        mark = "+" if r["recovered"] else "-"
        click.echo(f"  {mark} {r['anchor_id']}: {r['note']}")

    click.echo(f"\n  Recovered : {n_recovered}/{len(results)}  (reported, not gated -- ADR-019)")


# ---------------------------------------------------------------------------
# analyze  (ADR-043/045 — the pipeline→front-end seam)
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--clusters", default=None, help="Clusters parquet path (default: config paths.processed_clusters)")
@click.option("--embeddings", default=None, help="Embeddings .npy path (default: config paths.processed_embeddings)")
@click.option("--topic-info", default=None, help="topic_info parquet (default: alongside clusters)")
@click.option("--output-dir", default=None, help="Dashboard artifacts dir (default: config paths.dashboard_artifacts)")
@click.pass_context
def analyze(
    ctx: click.Context,
    clusters: str | None,
    embeddings: str | None,
    topic_info: str | None,
    output_dir: str | None,
) -> None:
    """Recompute the analysis layer from clustering and write dashboard artifacts.

    Runs the full downstream chain — corpus-base-rate normalization (ADR-045),
    JEL scope (ADR-020), four-lens dynamics (ADR-039), stage classification
    (ADR-019), similar narratives + UMAP map (ADR-044) — and bakes the artifact
    JSON the static front end reads (ADR-043). No re-embedding: recomputes
    entirely from the persisted clusters.parquet / embeddings.npy.

    Loads the production Qwen3 embedder (for JEL prototype similarity) and runs
    PyMC sampling per in-scope cluster — run on RCC, not a laptop.
    """
    from mnd.dashboard.run import run_analysis

    cfg = ctx.obj["cfg"]
    root = project_root()
    clusters_path = Path(clusters) if clusters else root / cfg["paths"]["processed_clusters"]
    emb_path = Path(embeddings) if embeddings else root / cfg["paths"]["processed_embeddings"]
    ti_path = (
        Path(topic_info) if topic_info
        else clusters_path.parent / "topic_info.parquet"
    )
    out_dir = Path(output_dir) if output_dir else root / cfg["paths"]["dashboard_artifacts"]

    if not clusters_path.exists():
        log.error("Clusters parquet not found at %s — run `cluster` first.", clusters_path)
        sys.exit(1)
    if not emb_path.exists():
        log.error("Embeddings not found at %s — run `embed` first.", emb_path)
        sys.exit(1)

    out = run_analysis(
        clusters_path=clusters_path,
        embeddings_path=emb_path,
        topic_info_path=ti_path if ti_path.exists() else None,
        out_dir=out_dir,
        cfg=cfg,
    )
    log.info("analyze: wrote dashboard artifacts → %s", out)


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
