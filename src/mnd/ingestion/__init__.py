"""Article ingestion sources."""

from mnd.ingestion.base import Article, Ingestor
from mnd.ingestion.proquest import PaywalledSourceIngestor
from mnd.ingestion.fed import FederalReserveIngestor
from mnd.ingestion.fred import FredFetcher
from mnd.ingestion.gdelt import GdeltIngestor

__all__ = [
    "Article",
    "Ingestor",
    "GdeltIngestor",
    "FederalReserveIngestor",
    "FredFetcher",
    "PaywalledSourceIngestor",
]
