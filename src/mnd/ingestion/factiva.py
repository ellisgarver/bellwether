"""Paywalled-source ingestion (Factiva / ProQuest / LexisNexis).

This is a **stub** — concrete implementation is gated on confirming
UChicago library access (see plan §6.1 critical pre-flight check).

When access is confirmed, the implementation will use one of:
  - Factiva API (preferred where licensed; per-query metering)
  - Factiva Snapshot Direct (bulk, requires special academic agreement)
  - ProQuest TDM Studio (preferred for academic use; contact UChicago library)
  - LexisNexis Academic via institutional SSO

The interface here is intentionally empty so that downstream code that
depends on URL-keyed full-text retrieval can be written and tested against
mocks now, and switched to real retrieval later without touching the
consumers.
"""
from __future__ import annotations

from datetime import date
from typing import Iterator

from mnd.ingestion.base import Article, Ingestor


class PaywalledSourceIngestor(Ingestor):
    """Interface for paywalled-source ingestion. Concrete impl pending.

    Two operating modes are anticipated:

    1. **Discovery + body fetch.** Given URLs from GdeltIngestor, retrieve
       full text via library database. Pros: respects the discovery layer's
       outlet filtering. Cons: brittle URL-to-database matching.

    2. **Database-native search.** Query Factiva/ProQuest directly with
       outlet + date filters; ignore GDELT entirely for paywalled outlets.
       Pros: cleaner, more reliable. Cons: duplicates discovery logic.

    Mode 2 is preferred where licenses permit.
    """

    source_id = "paywalled"

    def __init__(self, mode: str = "database_native") -> None:
        if mode not in ("database_native", "url_keyed"):
            raise ValueError(f"Invalid mode: {mode}")
        self.mode = mode

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        raise NotImplementedError(
            "Paywalled-source ingestion is not yet implemented. "
            "Confirm UChicago library access (Factiva or ProQuest TDM Studio) "
            "before contacting your library systems team for credentials. "
            "Then fill in this class with the chosen retrieval pathway. "
            "See docs/handoff_to_claude_code.md for the implementation prompt."
        )
        yield  # type: ignore[unreachable]
