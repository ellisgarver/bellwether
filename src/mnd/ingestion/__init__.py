"""Article ingestion sources.

Semantic corpus = the ADR-020 basis set: the minimum set of sources spanning
the eight independent dimensions of US macro discourse, no redundancy.
  InstitutionalIngestor — composite over the basis set: Federal Reserve
                          (FOMC, speeches, Beige Book, FEDS Notes, MPR, FSR,
                          testimony), 4 Regional Feds (NY/SF/Chicago/Atlanta),
                          IMF, BIS, CBO, CEA, Treasury/OFR, Brookings, PIIE,
                          NBER, VoxEU, Congressional Treasury Sec testimony.
  See docs/architecture_decisions.md ADR-020 for the dimension table and the
  per-source retrieval mechanics.

Dynamics + detection layers (not ingested as embeddable text):
  Media Cloud — see src/mnd/detection/mediacloud.py (premium tier for the
                Layer 1B journalism-dynamics cross-validation signal, broad
                tier for Layer 2 detection).
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
