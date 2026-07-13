"""Pipeline orchestration CLI.

Dispatches pipeline stages:
  ingest              — fetch raw articles from the basis-set sources
  filter-pre-embed    — drop archived journalism sources from raw JSONL
  filter              — date-range filter + near-duplicate removal
  embed               — encode articles (Qwen3-Embedding-8B)
  cluster             — BERTopic single-granularity clustering
  stability           — bootstrap stability diagnostic (mean NMI reported, not gated)
  analyze             — clusters → normalize → JEL → dynamics → stages →
                        similar → dashboard artifacts (the pipeline→front-end seam)
  name                — resolve display names for baked artifacts in place (ADR-056)
  update              — portable weekly delta: per-source over-fetch + analyze (ADR-063)
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

from mnd.utils.config import data_root, load_config, project_root
from mnd.utils.logging import get_logger

log = get_logger("run_pipeline")

# The ADR-020 basis set — the 12 sub-ingestors mapping 1:1 to the dimensions of US
# macro discourse. Used by `update` to advance each source from its own frontier.
BASIS_SET_SOURCES = (
    "federalreserve", "fed_regional", "congressional", "imf", "bis",
    "treasury_ofr", "cea", "voxeu", "brookings", "piie", "cbo", "nber",
)

# Composite sources whose ingested articles carry per-sub source_ids — the
# corpus never contains the composite id itself, so the composite's frontier
# must be computed across its subs. Without this mapping the lookup always
# misses and the weekly delta silently restarts at full_start: a 16-year
# re-walk of all four regional Feds, every single week.
COMPOSITE_SOURCE_IDS: dict[str, tuple[str, ...]] = {
    "fed_regional": ("fed_atlanta", "fed_chicago", "fed_ny", "fed_sf"),
}


def _source_delta_windows(
    articles_df: "pd.DataFrame",
    sources: tuple[str, ...],
    buffer_days: int,
    today: str,
    full_start: str,
) -> list[tuple[str, str, str]]:
    """Per-source over-fetch windows for a weekly delta (ADR-063).

    Each source advances from its *own* last-captured ``published_at`` minus
    ``buffer_days`` (so the staggered per-source frontiers do not leave gaps), to
    ``today``; the buffer overlap is absorbed by URL/content dedup. A source with no
    articles yet starts at ``full_start``. A composite source (see
    ``COMPOSITE_SOURCE_IDS``) advances from the *minimum* frontier across its
    subs — the laggiest sub governs, so no sub is left with a gap; the fresher
    subs' overlap is absorbed by dedup. Returns ``[(source, start, end), ...]``.
    """
    import pandas as pd

    windows: list[tuple[str, str, str]] = []
    if "source_id" in articles_df.columns and "published_at" in articles_df.columns:
        pub = pd.to_datetime(articles_df["published_at"], errors="coerce", utc=True)
        max_by_source = pub.groupby(articles_df["source_id"]).max()
    else:
        max_by_source = pd.Series(dtype="datetime64[ns, UTC]")
    for src in sources:
        sub_ids = COMPOSITE_SOURCE_IDS.get(src, (src,))
        lasts = [max_by_source.get(s) for s in sub_ids]
        lasts = [t for t in lasts if t is not None and not pd.isna(t)]
        if not lasts:
            start = full_start
        else:
            start = (min(lasts) - pd.Timedelta(days=buffer_days)).date().isoformat()
        windows.append((src, start, today))
    return windows


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
    root = data_root()
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

    root = data_root()
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
    root = data_root()
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

    Per ADR-020: no topic filter is applied — all Layer 1A
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

    from mnd.filtering import BoilerplateStripper, Deduplicator

    cfg = ctx.obj["cfg"]
    root = data_root()
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

    # Sub-document boilerplate strip (ADR-054) — remove recurring passages that
    # whole-document dedup cannot catch, before the corpus reaches the embedder.
    stripper = BoilerplateStripper.from_config(cfg)
    if stripper.enabled:
        before = len(unique)
        unique = stripper.strip(unique)
        rep = stripper.report
        log.info(
            "Boilerplate strip: %d template sentences, %d instances removed; "
            "%d articles cleaned, %d dropped as content-free (%d → %d)",
            rep.n_boilerplate_sentences, rep.n_instances_removed,
            rep.n_articles_modified, rep.n_articles_dropped, before, len(unique),
        )
        report_path = out_path.parent / "boilerplate_report.json"
        report_path.write_text(json.dumps(rep.to_dict(), ensure_ascii=False, indent=2))
        log.info("Boilerplate report → %s", report_path)

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
    root = data_root()
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
        # Incremental chunking (ADR-066 Part C): articles that arrived after the
        # chunks file was built (a weekly delta) are chunked and appended, so the
        # existing rows keep their positions and cached embedding rows stay
        # aligned while the delta gets encoded fresh.
        if parquet_path.exists():
            articles_df = pd.read_parquet(parquet_path)
            have = set(chunk_df["article_id"].astype(str))
            fresh_articles = articles_df[~articles_df["article_id"].astype(str).isin(have)]
            if len(fresh_articles):
                log.info(
                    "Chunking %d new articles (delta) and appending to %s",
                    len(fresh_articles), chunks_path,
                )
                chunk_df = pd.concat(
                    [chunk_df, chunk_corpus(fresh_articles)], ignore_index=True
                )
                chunk_df.to_parquet(chunks_path, index=False)
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
    root = data_root()
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
    root = data_root()
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
    # Persist the fitted model (ADR-066): required for the weekly `merge_models`
    # re-cluster. Non-fatal if it fails — clustering outputs are already written.
    try:
        pipeline.save_model(out_path.parent / "topic_model")
    except Exception as exc:
        log.warning("BERTopic model persistence skipped (%s); merge path will need a rebuild", exc)
    log.info(
        "Saved clusters (%d topics) → %s", results["n_topics"], out_path
    )


# ---------------------------------------------------------------------------
# merge-week  (ADR-066 Part C — identity-stable weekly re-cluster)
# ---------------------------------------------------------------------------

@cli.command("merge-week")
@click.option("--min-similarity", default=None, type=float,
              help="merge_models threshold (default: config update.merge_min_similarity)")
@click.pass_context
def merge_week(ctx: click.Context, min_similarity: float | None) -> None:
    """Fold newly embedded chunks into the narrative set, ids preserved (ADR-066).

    Delta chunks (present in chunks.parquet, absent from clusters.parquet) are
    fit as a new-week BERTopic model and merged into the persisted base model,
    so every existing topic keeps its id, URL, and name; genuinely-new stories
    append as new topics. The identity gate runs before anything is written:
    if any existing non-noise topic id fails to survive the merge, the command
    aborts and the narrative set is untouched.
    """
    from mnd.clustering.incremental import (
        _nonnoise_ids,
        anchors_keep_ids,
        assemble_merged_clusters,
        load_base_model,
        merge_new_week,
        save_merged_model,
    )

    cfg = ctx.obj["cfg"]
    root = data_root()
    chunks_path = root / cfg["paths"]["processed_chunks"]
    emb_path = root / cfg["paths"]["processed_embeddings"]
    clusters_path = root / cfg["paths"]["processed_clusters"]
    model_dir = clusters_path.parent / "topic_model"

    for p, hint in [
        (chunks_path, "run `embed` first"),
        (emb_path, "run `embed` first"),
        (clusters_path, "run a full `cluster` first"),
        (model_dir, "the base model is persisted by `cluster`; run a full rebuild first"),
    ]:
        if not p.exists():
            log.error("merge-week: %s missing — %s.", p, hint)
            sys.exit(1)

    chunk_df = pd.read_parquet(chunks_path)
    emb = np.load(str(emb_path))
    if emb.shape[0] != len(chunk_df):
        log.error(
            "merge-week: embeddings (%d rows) and chunks (%d rows) misaligned — "
            "re-run `embed` before merging.", emb.shape[0], len(chunk_df),
        )
        sys.exit(1)
    clusters_df = pd.read_parquet(clusters_path)

    known = set(clusters_df["chunk_id"].astype(str))
    delta_mask = ~chunk_df["chunk_id"].astype(str).isin(known)
    n_delta = int(delta_mask.sum())
    if n_delta == 0:
        log.info("merge-week: no new chunks since the last cluster/merge — nothing to do.")
        return
    log.info("merge-week: %d delta chunks to fold in (of %d total).", n_delta, len(chunk_df))

    delta_df = chunk_df[delta_mask]
    delta_docs = (delta_df["title"].fillna("") + " " + delta_df["body"].fillna("")).tolist()
    delta_emb = emb[delta_mask.to_numpy()]

    upd = cfg.get("update", {})
    min_sim = float(min_similarity if min_similarity is not None
                    else upd.get("merge_min_similarity", 0.7))

    base_model = load_base_model(model_dir)
    merged, new_topics = merge_new_week(base_model, delta_docs, delta_emb, cfg, min_sim)

    # Identity gate (ADR-066): every existing non-noise topic id must survive.
    base_ids = _nonnoise_ids(base_model)
    ok, missing = anchors_keep_ids(base_model, merged, base_ids)
    if not ok:
        log.error(
            "merge-week: identity gate FAILED — %d of %d existing topic ids missing "
            "after the merge (e.g. %s). Nothing was written; the narrative set is "
            "unchanged and the delta stays parked.",
            len(missing), len(base_ids), missing[:5],
        )
        sys.exit(1)
    log.info("merge-week: identity gate passed — all %d existing topic ids preserved.",
             len(base_ids))

    delta_topics = dict(zip(delta_df["chunk_id"].astype(str), new_topics))
    out_df = assemble_merged_clusters(chunk_df, clusters_df, delta_topics)

    backup = clusters_path.with_suffix(".parquet.bak")
    clusters_path.replace(backup)
    out_df.to_parquet(clusters_path, index=False)
    merged.get_topic_info().to_parquet(clusters_path.parent / "topic_info.parquet", index=False)
    save_merged_model(merged, model_dir, cfg)
    log.info(
        "merge-week: wrote %d rows (%d delta) → %s (previous kept at %s); "
        "topic_info + base model updated.",
        len(out_df), n_delta, clusters_path, backup,
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
    root = data_root()
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
    JEL scope on cluster centroids (ADR-067), least-squares lens fits (ADR-067),
    model-free stage classification (ADR-052), similar narratives + UMAP map
    (ADR-044), display naming (ADR-056) — and bakes the artifact JSON the static
    front end reads (ADR-043). No re-embedding: recomputes entirely from the
    persisted clusters.parquet / embeddings.npy, CPU-only and cache-incremental
    (ADR-065), so a re-bake is minutes anywhere.
    """
    from mnd.dashboard.run import run_analysis

    cfg = ctx.obj["cfg"]
    root = data_root()
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
# name  (ADR-056/067 — display naming for already-baked artifacts)
# ---------------------------------------------------------------------------

@cli.command("name")
@click.option("--artifacts-dir", default=None,
              help="Dashboard artifacts dir (default: config paths.dashboard_artifacts)")
@click.pass_context
def name_artifacts(ctx: click.Context, artifacts_dir: str | None) -> None:
    """Resolve display names for baked artifacts and patch them in place.

    Rebuilds each surfaced narrative's naming input from its baked story card —
    the same terms, central-article excerpts, date span, and source mix the
    ``analyze`` bake feeds the namer — so the cache signatures are identical and
    every name written to ``display.naming.cache_dir`` is reused verbatim by the
    next bake, wherever it runs. Lets naming run on any machine with an
    OpenAI-compatible endpoint (a local Ollama by default) after the artifacts
    were baked elsewhere. Display layer only; idempotent and safe to re-run.
    """
    from mnd.dashboard.naming import NamingInput, generate_names

    cfg = ctx.obj["cfg"]
    art_dir = (
        Path(artifacts_dir) if artifacts_dir
        else data_root() / cfg["paths"]["dashboard_artifacts"]
    )
    index_path = art_dir / "index.json"
    if not index_path.exists():
        log.error("No artifacts at %s — run `analyze` first.", art_dir)
        sys.exit(1)
    index = json.loads(index_path.read_text(encoding="utf-8"))

    inputs: list[NamingInput] = []
    narr_files: dict[int, tuple[Path, dict]] = {}
    for entry in index["narratives"]:
        cid = int(entry["cluster_id"])
        path = art_dir / f"narrative_{cid}.json"
        if not path.exists():
            log.warning("name: missing %s; skipped", path.name)
            continue
        narr = json.loads(path.read_text(encoding="utf-8"))
        card = narr.get("card") or {}
        panels = card.get("central_articles") or card.get("representative_articles") or []
        inputs.append(
            NamingInput(
                cluster_id=cid,
                terms=[str(t) for t in (card.get("top_terms") or [])],
                excerpts=[a["excerpt"] for a in panels if a.get("excerpt")],
                date_range=tuple(card["date_range"]) if card.get("date_range") else None,
                sources=[s for s, _ in (card.get("source_mix") or [])[:4]],
            )
        )
        narr_files[cid] = (path, narr)

    names = generate_names(inputs, cfg)
    for cid, nm in names.items():
        path, narr = narr_files[cid]
        narr["label_human"] = nm.title
        narr["description"] = nm.description
        path.write_text(json.dumps(narr, ensure_ascii=False), encoding="utf-8")
    for entry in index["narratives"]:
        nm = names.get(int(entry["cluster_id"]))
        if nm is not None:
            entry["label_human"] = nm.title
    index_path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    log.info(
        "name: %d/%d narratives carry display names; artifacts patched in %s",
        len(names), len(inputs), art_dir,
    )

    # Directory titles (ADR-073): every non-surfaced cluster with baked terms
    # gets a terms-grounded title — the whole directory, forming and sub-floor
    # alike, not just the forming handful (ADR-071). Surfaced entries pick up
    # the titles generated above so the directory matches the narrative pages.
    dir_path = art_dir / "clusters_all.json"
    if dir_path.exists():
        directory = json.loads(dir_path.read_text(encoding="utf-8"))
        directory_inputs = [
            NamingInput(
                cluster_id=int(c["cluster_id"]),
                terms=[str(t) for t in (c.get("terms") or [])],
                excerpts=[],
                date_range=tuple(c["date_range"]) if c.get("date_range") else None,
                sources=[],
            )
            for c in directory.get("clusters", [])
            if not c.get("surfaced") and (c.get("terms") or [])
        ]
        directory_names = generate_names(directory_inputs, cfg) if directory_inputs else {}
        patched = 0
        for c in directory.get("clusters", []):
            cid = int(c["cluster_id"])
            nm = directory_names.get(cid) or names.get(cid)
            if nm is not None and c.get("label_human") != nm.title:
                c["label_human"] = nm.title
                patched += 1
        if patched:
            dir_path.write_text(json.dumps(directory, ensure_ascii=False), encoding="utf-8")
        log.info(
            "name: %d directory clusters titled, %d directory entries patched",
            len(directory_names), patched,
        )


# ---------------------------------------------------------------------------
# update  (ADR-063 — portable weekly refresh)
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--sources", default="all", show_default=True,
              help="'all' = the 12 basis-set sources, or a comma-separated subset.")
@click.option("--buffer-days", type=int, default=None,
              help="Over-fetch each source from its frontier minus this many days "
                   "(default: config update.buffer_days).")
@click.option("--skip-ingest", is_flag=True, default=False,
              help="Skip the delta ingest; only refresh analyze / the press layer.")
@click.option("--skip-analyze", is_flag=True, default=False,
              help="Skip the analyze re-bake; only fetch the delta.")
@click.option("--merge/--no-merge", "merge_flag", default=None,
              help="Fold the delta into the narrative set via merge-week "
                   "(ADR-066 Part C). Default comes from config "
                   "update.merge_enabled (off until the identity gate has "
                   "passed once on the real corpus).")
@click.pass_context
def update(
    ctx: click.Context,
    sources: str,
    buffer_days: int | None,
    skip_ingest: bool,
    skip_analyze: bool,
    merge_flag: bool | None,
) -> None:
    """Portable weekly refresh (ADR-063): per-source delta ingest + analyze.

    Single-process and CPU-only, with all paths under ``MND_DATA_ROOT`` — it runs
    unchanged on a laptop, a cron VM, GitHub Actions, or an RCC node, no SLURM and
    no GPU. Each source advances from its own last-captured date (minus a buffer;
    dedup absorbs the overlap), and ``analyze`` re-bakes the artifacts, refreshing
    the Media Cloud press layer + press-heating against the current narrative set.

    With the merge path enabled (``--merge`` or ``update.merge_enabled``), the
    delta is also filtered, chunked, incrementally embedded, and folded into the
    narrative set with existing topic ids preserved (ADR-066 Part C) — so the
    volume charts extend weekly. The merge is gated: if any existing topic id
    would change, nothing is written and the delta stays parked, exactly as in
    the merge-off path.
    """
    from datetime import date as date_t

    cfg = ctx.obj["cfg"]
    upd = cfg.get("update", {})
    buffer = int(buffer_days if buffer_days is not None else upd.get("buffer_days", 14))
    full_start = str(upd.get("full_start", "2010-01-01"))
    do_merge = bool(upd.get("merge_enabled", False)) if merge_flag is None else merge_flag
    today = date_t.today().isoformat()
    src_tuple = (
        BASIS_SET_SOURCES if sources.strip() == "all"
        else tuple(s.strip() for s in sources.split(",") if s.strip())
    )

    if not skip_ingest:
        articles_path = data_root() / cfg["paths"]["processed_articles"]
        articles_df = (
            pd.read_parquet(str(articles_path)) if articles_path.exists()
            else pd.DataFrame()
        )
        windows = _source_delta_windows(articles_df, src_tuple, buffer, today, full_start)
        log.info("update: delta ingest for %d sources (buffer=%dd → %s)",
                 len(windows), buffer, today)
        for src, start, end in windows:
            log.info("update: ingest %-15s %s → %s", src, start, end)
            ctx.invoke(ingest, start=start, end=end, sources=src,
                       output_dir=None, shard=None)

    if do_merge:
        log.info("update: merge path (ADR-066) — filter-pre-embed, filter, "
                 "incremental embed, merge-week")
        # Rebuild corpus_for_embedding.jsonl from the raw dir FIRST: `filter`
        # prefers that file whenever it exists, and the full build leaves a
        # stale copy behind — without this refresh the weekly delta would
        # never reach embed/merge (merge-week reports "no new chunks" forever
        # while the site keeps re-baking, a silent ADR-030 violation).
        ctx.invoke(filter_pre_embed, input_dir=None, output=None)
        ctx.invoke(filter_cmd, input_dir=None, input_jsonl=None, output=None)
        ctx.invoke(embed, role="primary", input_path=None, output=None, full_rebuild=False)
        try:
            ctx.invoke(merge_week, min_similarity=None)
        except SystemExit:
            # Gate failure or missing prerequisite: merge-week wrote nothing, so
            # the delta stays parked; the press layer still refreshes below.
            log.warning(
                "update: merge-week did not apply (see errors above); continuing "
                "with the narrative set unchanged."
            )
    elif not skip_ingest:
        log.warning(
            "update: new institutional articles are PARKED in raw (merge path "
            "disabled — update.merge_enabled: false); the narrative set stays "
            "'as of the last full build'. The Media Cloud press layer refreshes "
            "in the analyze step below."
        )

    if not skip_analyze:
        log.info("update: re-baking artifacts (refreshes the Media Cloud press layer)")
        ctx.invoke(analyze, clusters=None, embeddings=None, topic_info=None,
                   output_dir=None)

    log.info("update: complete")


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
    root = data_root()
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
