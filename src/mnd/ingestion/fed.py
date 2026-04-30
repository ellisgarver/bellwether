"""Federal Reserve communications ingestion.

Pulls FOMC statements, minutes, Beige Book reports, Board speeches, and
Monetary Policy Reports. All public domain, all free, all directly from
federalreserve.gov.

This ingestor is structured around the Fed's calendar pages rather than a
catalog API (the Fed does not publish one). We scrape the index pages and
fetch each linked artifact.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Iterator

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from mnd.ingestion.base import Article, Ingestor, _now_utc_iso, _stable_article_id
from mnd.utils.logging import get_logger

log = get_logger(__name__)

USER_AGENT = "MacroNarrativeDynamics/0.1 (academic research; contact via project repo)"

FOMC_HISTORICAL_BASE = "https://www.federalreserve.gov/monetarypolicy"
FOMC_CALENDARS_URL = f"{FOMC_HISTORICAL_BASE}/fomccalendars.htm"
SPEECHES_BASE = "https://www.federalreserve.gov/newsevents/speech"
SPEECHES_INDEX = f"{SPEECHES_BASE}/{{year}}-speeches.htm"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def _get(url: str, *, timeout: float = 30.0) -> requests.Response:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    return resp


def _extract_text(html: str) -> str:
    """Strip nav/footer chrome from a Fed HTML page; return body text."""
    soup = BeautifulSoup(html, "lxml")
    # Fed body content lives inside <div id="article"> on most pages.
    article = soup.find("div", {"id": "article"}) or soup.find("div", class_="col-xs-12")
    if article is None:
        article = soup
    for tag in article.find_all(["nav", "footer", "script", "style"]):
        tag.decompose()
    return article.get_text(separator=" ", strip=True)


class FederalReserveIngestor(Ingestor):
    """Federal Reserve communications ingestor."""

    source_id = "federalreserve"

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        yield from self._fetch_fomc_statements(start, end)
        yield from self._fetch_speeches(start, end)
        # Minutes, Beige Book, MPRs follow the same pattern; implementations
        # to be filled in during Phase 2 against actual Fed page layouts.

    def _fetch_fomc_statements(self, start: date, end: date) -> Iterator[Article]:
        """Walk the FOMC calendars page; emit one Article per statement."""
        try:
            resp = _get(FOMC_CALENDARS_URL)
        except Exception as exc:  # pragma: no cover
            log.error("Failed to fetch FOMC calendar index: %s", exc)
            return
        soup = BeautifulSoup(resp.text, "lxml")
        # Statement links match patterns like /newsevents/pressreleases/monetary20240131a.htm
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "pressreleases/monetary" not in href:
                continue
            # Filename format: monetaryYYYYMMDD[a].htm
            try:
                stem = href.rsplit("/", 1)[-1]
                date_str = stem.replace("monetary", "")[:8]
                meeting_date = datetime.strptime(date_str, "%Y%m%d").date()
            except Exception:
                continue
            if meeting_date < start or meeting_date > end:
                continue

            full_url = href if href.startswith("http") else f"https://www.federalreserve.gov{href}"
            try:
                page = _get(full_url)
            except Exception as exc:  # pragma: no cover
                log.warning("Failed to fetch FOMC statement %s: %s", full_url, exc)
                continue

            body = _extract_text(page.text)
            if not body:
                continue
            title = f"FOMC Statement — {meeting_date.isoformat()}"
            yield Article(
                article_id=_stable_article_id(self.source_id, full_url),
                source_id="federalreserve",
                url=full_url,
                published_at=meeting_date.isoformat() + "T18:00:00Z",
                retrieved_at=_now_utc_iso(),
                title=title,
                body=body,
                author="FOMC",
                section="fomc_statement",
                language="en",
                tier=3,
                access="free",
                retrieval="fed_site",
                word_count=len(body.split()),
                raw_metadata={"document_type": "fomc_statement"},
            )

    def _fetch_speeches(self, start: date, end: date) -> Iterator[Article]:
        """Walk Board speech indexes year by year."""
        for year in range(start.year, end.year + 1):
            index_url = SPEECHES_INDEX.format(year=year)
            try:
                resp = _get(index_url)
            except Exception as exc:  # pragma: no cover
                log.warning("Failed to fetch speech index %s: %s", index_url, exc)
                continue
            soup = BeautifulSoup(resp.text, "lxml")
            for entry in soup.select("div.row"):
                date_node = entry.select_one("time")
                link_node = entry.select_one("a[href]")
                if not date_node or not link_node:
                    continue
                try:
                    speech_date = datetime.fromisoformat(date_node.get("datetime", "")[:10]).date()
                except Exception:
                    continue
                if speech_date < start or speech_date > end:
                    continue
                href = link_node["href"]
                full_url = href if href.startswith("http") else f"https://www.federalreserve.gov{href}"
                title = link_node.get_text(strip=True)
                speaker = entry.get_text(" ", strip=True)
                try:
                    page = _get(full_url)
                except Exception as exc:  # pragma: no cover
                    log.warning("Failed to fetch speech %s: %s", full_url, exc)
                    continue
                body = _extract_text(page.text)
                if not body or len(body.split()) < 200:
                    continue
                yield Article(
                    article_id=_stable_article_id(self.source_id, full_url),
                    source_id="federalreserve",
                    url=full_url,
                    published_at=speech_date.isoformat() + "T15:00:00Z",
                    retrieved_at=_now_utc_iso(),
                    title=title or "Federal Reserve speech",
                    body=body,
                    author=speaker,
                    section="speech",
                    language="en",
                    tier=3,
                    access="free",
                    retrieval="fed_site",
                    word_count=len(body.split()),
                    raw_metadata={"document_type": "speech"},
                )
