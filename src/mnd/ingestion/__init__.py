"""Article ingestion sources.

Semantic corpus sources (Tiers 1–2, per ADR-010 / ADR-012):
  InstitutionalIngestor — composite: Federal Reserve (FOMC, speeches incl.
                          Jackson Hole, Beige Book, FEDS Notes, MPR, FSR),
                          Regional Feds, IMF, BIS, CBO, Treasury/OFR,
                          Congressional testimony, VoxEU, Brookings, PIIE, CFR.
                          NBER and SSRN remain in the codebase for Phase 6
                          live RSS but are excluded from historical runs.

Dynamics layer (not ingested as text):
  RavenPack via WRDS — see src/mnd/ingestion/ravenpack.py

Detection layer (story counts only, no text):
  Media Cloud — see src/mnd/detection/mediacloud.py

Removed sources (do not reinstate without a new ADR):
  ADR-010: AP News, Reuters, MarketWatch (journalism tier)
  ADR-012: arXiv (2017-only coverage), separate Jackson Hole ingestor
           (covered by FederalReserveIngestor)
  Archived code lives under scripts/archive/.
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
