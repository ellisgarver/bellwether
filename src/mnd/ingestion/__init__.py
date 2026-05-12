"""Article ingestion sources.

Semantic corpus sources (Tiers 1–2, per ADR-010 / MND_PROJECT_SPEC.md):
  InstitutionalIngestor — composite: Fed, IMF, BIS, CEA, CBO, Treasury/OFR,
                          Regional Feds, Jackson Hole, Congressional testimony,
                          NBER (Phase 6 only), arXiv, VoxEU, Brookings, PIIE, CFR

Dynamics layer (not ingested as text):
  RavenPack via WRDS — see src/mnd/ingestion/ravenpack.py

Detection layer (story counts only, no text):
  Media Cloud — see src/mnd/detection/mediacloud.py

Archived journalism ingestors (removed in ADR-010):
  scripts/archive/apnews_ingestor.py    (AP News — Wayback CDX)
  scripts/archive/reuters_ingestor.py   (Reuters — Wayback CDX)
  MarketWatchIngestor was in apnews_ingestor.py
"""

from mnd.ingestion.base import Article, Ingestor
from mnd.ingestion.fed import FederalReserveIngestor
from mnd.ingestion.fred import FredFetcher
from mnd.ingestion.trafilatura_fetcher import fetch_free_outlet_bodies
from mnd.ingestion.wayback import WaybackIngestor
from mnd.ingestion.institutional import InstitutionalIngestor

__all__ = [
    "Article",
    "Ingestor",
    "FederalReserveIngestor",
    "FredFetcher",
    "InstitutionalIngestor",
    "WaybackIngestor",
    "fetch_free_outlet_bodies",
]
