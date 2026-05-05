"""Article ingestion sources."""

from mnd.ingestion.base import Article, Ingestor
from mnd.ingestion.fed import FederalReserveIngestor
from mnd.ingestion.fred import FredFetcher
from mnd.ingestion.trafilatura_fetcher import fetch_free_outlet_bodies
from mnd.ingestion.wayback import WaybackIngestor
from mnd.ingestion.institutional import InstitutionalIngestor
from mnd.ingestion.apnews import APNewsIngestor, MarketWatchIngestor

__all__ = [
    "Article",
    "Ingestor",
    "APNewsIngestor",
    "FederalReserveIngestor",
    "FredFetcher",
    "InstitutionalIngestor",
    "MarketWatchIngestor",
    "WaybackIngestor",
    "fetch_free_outlet_bodies",
]
