"""ProQuest TDM Studio pipeline ingestor (plan §6.1, ADR-004, ADR-007).

Reads a JSONL file exported from TDM Studio and yields Article objects.
The export itself is handled by scripts/tdm_studio_export.py, which runs
inside TDM Studio's Jupyter environment. See docs/proquest_tdm_setup.md.

Expected file location:
    data/raw/articles/proquest_{PROQUEST_DATASET_ID}.jsonl

Set PROQUEST_DATASET_ID in .env to the dataset ID used when exporting.
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Iterator

from mnd.ingestion.base import Article, Ingestor
from mnd.utils.config import project_root
from mnd.utils.logging import get_logger

log = get_logger(__name__)


class PaywalledSourceIngestor(Ingestor):
    """Reads a ProQuest TDM Studio JSONL export and yields Article objects.

    Run scripts/tdm_studio_export.py inside TDM Studio first to produce the
    export file, then place it at data/raw/articles/proquest_<id>.jsonl.
    """

    source_id = "proquest_tdm"

    def __init__(self) -> None:
        self._export_path: Path | None = None

    def _resolve_export_path(self) -> Path:
        if self._export_path is not None:
            return self._export_path
        dataset_id = os.environ.get("PROQUEST_DATASET_ID", "").strip()
        if not dataset_id:
            raise EnvironmentError(
                "PROQUEST_DATASET_ID is not set. "
                "Set it in .env to the dataset ID from your TDM Studio project. "
                "See docs/proquest_tdm_setup.md."
            )
        raw_dir = _raw_articles_dir()
        path = raw_dir / f"proquest_{dataset_id}.jsonl"
        if not path.exists():
            raise FileNotFoundError(
                f"ProQuest export file not found: {path}\n"
                f"Run scripts/tdm_studio_export.py inside TDM Studio (dataset ID: {dataset_id}), "
                f"download the result, and place it at the path above.\n"
                f"See docs/proquest_tdm_setup.md."
            )
        self._export_path = path
        return path

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        """Yield Articles from the TDM Studio export within [start, end]."""
        export_path = self._resolve_export_path()
        log.info("ProQuest TDM: reading %s", export_path)

        start_iso = start.isoformat()
        end_iso = end.isoformat()
        yielded = skipped = total = 0

        with export_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                total += 1
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    log.warning("Skipping malformed JSON line in %s", export_path)
                    skipped += 1
                    continue
                pub_date = data.get("published_at", "")[:10]
                if pub_date < start_iso or pub_date > end_iso:
                    continue
                try:
                    article = Article(**data)
                except (TypeError, KeyError) as exc:
                    log.warning("Skipping unreadable record: %s", exc)
                    skipped += 1
                    continue
                yielded += 1
                yield article

        log.info(
            "ProQuest TDM: yielded %d/%d articles in [%s, %s] (%d skipped)",
            yielded, total, start_iso, end_iso, skipped,
        )


def _raw_articles_dir() -> Path:
    try:
        from mnd.utils.config import load_config
        cfg = load_config()
        return project_root() / cfg["paths"]["raw_articles"]
    except Exception:
        return project_root() / "data/raw/articles"
