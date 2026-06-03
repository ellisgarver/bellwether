"""Article ingestion sources.

Semantic corpus sources (Tiers 1–2, per ADR-010 / ADR-012 / ADR-014):
  InstitutionalIngestor — composite: Federal Reserve (FOMC, speeches incl.
                          Jackson Hole, Beige Book, FEDS Notes, MPR, FSR),
                          Regional Feds, IMF (Coveo + curl_cffi, ADR-014),
                          BIS, CBO, Treasury/OFR, Congressional testimony,
                          VoxEU, Brookings, PIIE, CFR.

Dynamics + detection layers (not ingested as embeddable text):
  Media Cloud — see src/mnd/detection/mediacloud.py (ADR-016/019: premium
                tier for Layer 1B journalism dynamics, broad tier for
                Layer 2 detection)

Removed sources (do not reinstate without a new ADR):
  ADR-010: AP News, Reuters, MarketWatch — journalism tier. Their volume
           signal is captured by Media Cloud Premium (ADR-016).
  ADR-012: arXiv (2017-only coverage), separate Jackson Hole ingestor
           (covered by FederalReserveIngestor).
  ADR-017/019: NBER + SSRN — Phase 6 = Tier 1/2 re-ingest + Media Cloud
               only; NBER historical access is blocked and SSRN exposes
               no historical archive. RavenPack via WRDS — abandoned in
               ADR-016/019; Media Cloud Premium replaces it.
  Removed-ingestor code is recoverable from git history (ADR-024 cleanse).
"""

from mnd.ingestion.base import Article, Ingestor
from mnd.ingestion.fed import FederalReserveIngestor
from mnd.ingestion.fred import FredFetcher
from mnd.ingestion.institutional import InstitutionalIngestor

__all__ = [
    "Article",
    "Ingestor",
    "FederalReserveIngestor",
    "FredFetcher",
    "InstitutionalIngestor",
]
