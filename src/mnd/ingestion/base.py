"""Abstract base class for all article ingestion sources.

Every ingestor produces a stream of ``Article`` records. The pipeline
downstream of ingestion consumes only ``Article`` instances; concrete
sources differ only in how they fetch and parse.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterator


@dataclass
class Article:
    """Canonical article record consumed by every downstream stage.

    Field semantics:
        article_id     Stable hash of (source_id, url). Use for dedup.
        source_id      Outlet ID matching whitelist.yaml entry.
        url            Original URL (canonicalized — no tracking params).
        published_at   ISO 8601 datetime (UTC).
        retrieved_at   ISO 8601 datetime (UTC) — when this record was fetched.
        title          Article headline.
        body           Full article body text. Empty string if metadata-only.
        author         Author byline if available.
        section        Outlet-specific section tag if available.
        language       BCP 47 language tag (default 'en').
        tier           Outlet tier (1, 2, or 3) from whitelist.
        access         'free' | 'paywalled' | 'mixed'.
        retrieval      Which retrieval pathway produced this record.
        word_count     Length of body in whitespace-tokens (for filtering).
        raw_metadata   Source-specific metadata for traceability.
    """

    article_id: str
    source_id: str
    url: str
    published_at: str
    retrieved_at: str
    title: str
    body: str = ""
    author: str | None = None
    section: str | None = None
    language: str = "en"
    tier: int = 1
    access: str = "free"
    retrieval: str = "gdelt_url"
    word_count: int = 0
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_jsonl(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class Ingestor(ABC):
    """Abstract base class for all ingestion sources.

    Concrete ingestors must implement ``fetch`` to return an iterable of
    Articles for a given date range. The pipeline takes care of writing
    output and checkpointing.
    """

    source_id: str = "unknown"

    @abstractmethod
    def fetch(self, start: date, end: date) -> Iterator[Article]:
        """Yield articles within the inclusive date range [start, end]."""

    def write_jsonl(self, articles: Iterator[Article], output_path: Path) -> int:
        """Materialize the iterator to a JSONL file. Returns the count written."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with output_path.open("w", encoding="utf-8") as fh:
            for article in articles:
                fh.write(article.to_jsonl())
                fh.write("\n")
                count += 1
        return count


def _stable_article_id(source_id: str, url: str) -> str:
    """Produce a stable article ID from source + URL."""
    import hashlib

    payload = f"{source_id}|{url}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def _now_utc_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
