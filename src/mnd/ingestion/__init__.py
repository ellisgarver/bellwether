"""Article ingestion sources."""

from mnd.ingestion.base import Article, Ingestor
from mnd.ingestion.proquest import PaywalledSourceIngestor
from mnd.ingestion.fed import FederalReserveIngestor
from mnd.ingestion.fred import FredFetcher
from mnd.ingestion.gdelt import GdeltIngestor
from mnd.ingestion.trafilatura_fetcher import fetch_free_outlet_bodies
from mnd.ingestion.wayback import WaybackIngestor

__all__ = [
    "Article",
    "Ingestor",
    "GdeltIngestor",
    "FederalReserveIngestor",
    "FredFetcher",
    "PaywalledSourceIngestor",
    "WaybackIngestor",
    "fetch_free_outlet_bodies",
]
