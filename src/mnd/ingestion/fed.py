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

import feedparser
import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_random_exponential

from mnd.ingestion.base import Article, Ingestor, _now_utc_iso, _stable_article_id
from mnd.utils.logging import get_logger

log = get_logger(__name__)

USER_AGENT = "MacroNarrativeDynamics/0.1 (academic research; contact via project repo)"

FOMC_HISTORICAL_BASE = "https://www.federalreserve.gov/monetarypolicy"
FOMC_CALENDARS_URL = f"{FOMC_HISTORICAL_BASE}/fomccalendars.htm"
SPEECHES_BASE = "https://www.federalreserve.gov/newsevents/speech"
SPEECHES_INDEX = f"{SPEECHES_BASE}/{{year}}-speeches.htm"
SPEECHES_RSS = "https://www.federalreserve.gov/feeds/speeches.xml"


@retry(stop=stop_after_attempt(8), wait=wait_random_exponential(multiplier=2, max=120))
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
        yield from self._fetch_fomc_minutes(start, end)
        yield from self._fetch_speeches(start, end)
        yield from self._fetch_beige_books(start, end)
        yield from self._fetch_feds_notes(start, end)
        yield from self._fetch_mpr(start, end)
        yield from self._fetch_fsr(start, end)

    def _fetch_fomc_statements(self, start: date, end: date) -> Iterator[Article]:
        """Walk the FOMC calendars page; emit one Article per statement."""
        try:
            resp = _get(FOMC_CALENDARS_URL)
        except Exception as exc:
            raise RuntimeError(f"FOMC calendar index fetch failed after retries: {exc}") from exc
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
                tier=1,
                access="free",
                retrieval="fed_site",
                word_count=len(body.split()),
                raw_metadata={"document_type": "fomc_statement"},
            )

    def _fetch_fomc_minutes(self, start: date, end: date) -> Iterator[Article]:
        """Fetch FOMC meeting minutes linked from the calendars page."""
        try:
            resp = _get(FOMC_CALENDARS_URL)
        except Exception as exc:
            raise RuntimeError(f"FOMC calendar index fetch failed after retries (minutes): {exc}") from exc
        soup = BeautifulSoup(resp.text, "lxml")
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "fomcminutes" not in href:
                continue
            try:
                stem = href.rsplit("/", 1)[-1]
                date_str = stem.replace("fomcminutes", "")[:8]
                meeting_date = datetime.strptime(date_str, "%Y%m%d").date()
            except Exception:
                continue
            if meeting_date < start or meeting_date > end:
                continue
            full_url = href if href.startswith("http") else f"https://www.federalreserve.gov{href}"
            try:
                page = _get(full_url)
            except Exception as exc:
                log.warning("Failed to fetch FOMC minutes %s: %s", full_url, exc)
                continue
            body = _extract_text(page.text)
            if not body:
                continue
            yield Article(
                article_id=_stable_article_id(self.source_id, full_url),
                source_id="federalreserve",
                url=full_url,
                published_at=meeting_date.isoformat() + "T18:00:00Z",
                retrieved_at=_now_utc_iso(),
                title=f"FOMC Minutes — {meeting_date.isoformat()}",
                body=body,
                author="FOMC",
                section="fomc_minutes",
                language="en",
                tier=1,
                access="free",
                retrieval="fed_site",
                word_count=len(body.split()),
                raw_metadata={"document_type": "fomc_minutes"},
            )

    def _fetch_beige_books(self, start: date, end: date) -> Iterator[Article]:
        """Fetch Beige Book reports from the Fed's beige book index page."""
        index_url = "https://www.federalreserve.gov/monetarypolicy/beige-book-default.htm"
        try:
            resp = _get(index_url)
        except Exception as exc:
            log.error("Failed to fetch Beige Book index: %s", exc)
            return
        soup = BeautifulSoup(resp.text, "lxml")
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "beigebook" not in href.lower():
                continue
            # URL pattern: /monetarypolicy/beigebook202309.htm or beigebook/2023/...
            try:
                stem = href.rsplit("/", 1)[-1].replace("beigebook", "").replace(".htm", "")
                pub_date = datetime.strptime(stem[:6], "%Y%m").date()
            except Exception:
                continue
            if pub_date < start or pub_date > end:
                continue
            full_url = href if href.startswith("http") else f"https://www.federalreserve.gov{href}"
            try:
                page = _get(full_url)
            except Exception as exc:
                log.warning("Failed to fetch Beige Book %s: %s", full_url, exc)
                continue
            body = _extract_text(page.text)
            if not body or len(body.split()) < 200:
                continue
            yield Article(
                article_id=_stable_article_id(self.source_id, full_url),
                source_id="federalreserve",
                url=full_url,
                published_at=pub_date.isoformat() + "T14:00:00Z",
                retrieved_at=_now_utc_iso(),
                title=f"Beige Book — {pub_date.strftime('%B %Y')}",
                body=body,
                author="Federal Reserve",
                section="beige_book",
                language="en",
                tier=1,
                access="free",
                retrieval="fed_site",
                word_count=len(body.split()),
                raw_metadata={"document_type": "beige_book"},
            )

    def _fetch_speeches(self, start: date, end: date) -> Iterator[Article]:
        """Walk Board speech indexes year by year; fall back to RSS on index failure.

        Page structure: div.eventlist > div.row > (div.eventlist__time > time,
        div.eventlist__event > p > a).  Date text is MM/DD/YYYY (no datetime attr).
        """
        for year in range(start.year, end.year + 1):
            index_url = SPEECHES_INDEX.format(year=year)
            try:
                resp = _get(index_url)
            except Exception as exc:
                current_year = date.today().year
                if year >= current_year - 1:
                    # RSS feed only holds recent content — useful for current/last year
                    log.warning("Speech index %s failed: %s — trying RSS fallback", index_url, exc)
                    yield from self._fetch_speeches_rss_year(year, start, end)
                else:
                    # RSS has no historical content; RSS fallback would silently return 0
                    # articles, creating an invisible coverage gap. Log error and skip.
                    log.error(
                        "Speech index %s failed after %d retries: %s — "
                        "COVERAGE GAP: speeches for %d will be missing from corpus",
                        index_url, 8, exc, year,
                    )
                continue
            soup = BeautifulSoup(resp.text, "lxml")
            eventlist = soup.select_one(".eventlist")
            if not eventlist:
                log.error(
                    "Speech index %s: .eventlist container not found — "
                    "COVERAGE GAP: speeches for %d will be missing from corpus",
                    index_url, year,
                )
                continue
            for entry in eventlist.select("div.row"):
                date_node = entry.select_one("time")
                # Speech link is inside div.eventlist__event; skip watch-live / other links
                link_node = entry.select_one("div.eventlist__event a[href]")
                if not date_node or not link_node:
                    continue
                try:
                    # Date text is M/D/YYYY (e.g. "1/10/2023"), no datetime attribute
                    speech_date = datetime.strptime(date_node.get_text(strip=True), "%m/%d/%Y").date()
                except Exception:
                    continue
                if speech_date < start or speech_date > end:
                    continue
                href = link_node["href"]
                full_url = href if href.startswith("http") else f"https://www.federalreserve.gov{href}"
                title = link_node.get_text(strip=True)
                speaker_el = entry.select_one("p.news__speaker")
                speaker = speaker_el.get_text(strip=True) if speaker_el else ""
                try:
                    page = _get(full_url)
                except Exception as exc:
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
                    tier=1,
                    access="free",
                    retrieval="fed_site",
                    word_count=len(body.split()),
                    raw_metadata={"document_type": "speech"},
                )

    def _fetch_feds_notes(self, start: date, end: date) -> Iterator[Article]:
        """Fetch FEDS Notes from the Fed's econres/notes listing page.

        FEDS Notes are short analytical pieces (1,000–3,000 words, ~70/year) written
        by Board economists. Faster than working papers; authoritative within days of
        events. URL pattern: /econres/notes/feds-notes/YYYY/slug.htm
        """
        import re as _re
        index_url = "https://www.federalreserve.gov/econres/notes/feds-notes/"
        try:
            resp = _get(index_url)
        except Exception as exc:
            log.warning("FEDS Notes index fetch failed: %s", exc)
            return
        soup = BeautifulSoup(resp.text, "lxml")
        seen: set[str] = set()
        for link in soup.find_all("a", href=True):
            href = link["href"]
            m = _re.search(r"/econres/notes/feds-notes/(\d{4})/", href)
            if not m:
                continue
            try:
                note_year = int(m.group(1))
            except ValueError:
                continue
            if note_year < start.year or note_year > end.year:
                continue
            full_url = href if href.startswith("http") else f"https://www.federalreserve.gov{href}"
            if full_url in seen:
                continue
            seen.add(full_url)
            try:
                page = _get(full_url)
            except Exception as exc:
                log.debug("FEDS Notes fetch failed %s: %s", full_url, exc)
                continue
            body = _extract_text(page.text)
            if not body or len(body.split()) < 100:
                continue
            title = link.get_text(strip=True) or f"FEDS Note {note_year}"
            pub_date = date(note_year, 1, 1)
            # Try path-embedded date: /YYYY/MM/DD/
            date_m = _re.search(r"/(\d{4})/(\d{2})/(\d{2})/", href)
            if date_m:
                try:
                    pub_date = date(int(date_m.group(1)), int(date_m.group(2)), int(date_m.group(3)))
                except ValueError:
                    pass
            # Try filename-embedded date: fn20240115.htm → 20240115
            if pub_date == date(note_year, 1, 1):
                stem = href.rsplit("/", 1)[-1]
                stem_m = _re.search(r"(\d{4})(\d{2})(\d{2})", stem)
                if stem_m:
                    try:
                        pub_date = date(int(stem_m.group(1)), int(stem_m.group(2)), int(stem_m.group(3)))
                    except ValueError:
                        pass
            if pub_date < start or pub_date > end:
                continue
            yield Article(
                article_id=_stable_article_id(self.source_id, full_url),
                source_id="federalreserve",
                url=full_url,
                published_at=pub_date.isoformat() + "T12:00:00Z",
                retrieved_at=_now_utc_iso(),
                title=title,
                body=body,
                author="Federal Reserve Board",
                section="feds_notes",
                language="en",
                tier=1,
                access="free",
                retrieval="fed_site",
                word_count=len(body.split()),
                raw_metadata={"document_type": "feds_notes"},
            )
            import time as _time
            _time.sleep(0.5)

    def _fetch_mpr(self, start: date, end: date) -> Iterator[Article]:
        """Fetch Monetary Policy Reports (2x/yr, Feb and Jul).

        Index: federalreserve.gov/monetarypolicy/mpr_default.htm
        HTML summary pattern: /monetarypolicy/YYYY-MM-mpr-summary.htm
        """
        import re as _re
        index_url = "https://www.federalreserve.gov/monetarypolicy/mpr_default.htm"
        try:
            resp = _get(index_url)
        except Exception as exc:
            log.error("Failed to fetch MPR index: %s", exc)
            return
        soup = BeautifulSoup(resp.text, "lxml")
        seen: set[str] = set()
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "mpr" not in href.lower():
                continue
            if href.lower().endswith(".pdf"):
                continue
            pub_date: date | None = None
            # Pattern: YYYY-MM-mpr (e.g. /monetarypolicy/2024-02-mpr-summary.htm)
            m = _re.search(r"(\d{4})-(\d{2})-mpr", href)
            if m:
                try:
                    pub_date = date(int(m.group(1)), int(m.group(2)), 1)
                except ValueError:
                    pass
            # Pattern: mprYYYYMMDD or mprYYYYMM
            if pub_date is None:
                m = _re.search(r"mpr(\d{4})(\d{2})(\d{2})", href)
                if m:
                    try:
                        pub_date = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                    except ValueError:
                        pass
            if pub_date is None:
                m = _re.search(r"mpr(\d{4})(\d{2})", href)
                if m:
                    try:
                        pub_date = date(int(m.group(1)), int(m.group(2)), 1)
                    except ValueError:
                        pass
            if pub_date is None:
                continue
            if pub_date < start or pub_date > end:
                continue
            full_url = href if href.startswith("http") else f"https://www.federalreserve.gov{href}"
            if full_url in seen:
                continue
            seen.add(full_url)
            try:
                page = _get(full_url)
            except Exception as exc:
                log.warning("Failed to fetch MPR %s: %s", full_url, exc)
                continue
            body = _extract_text(page.text)
            if not body or len(body.split()) < 200:
                continue
            yield Article(
                article_id=_stable_article_id(self.source_id, full_url),
                source_id="federalreserve",
                url=full_url,
                published_at=pub_date.isoformat() + "T14:00:00Z",
                retrieved_at=_now_utc_iso(),
                title=f"Monetary Policy Report — {pub_date.strftime('%B %Y')}",
                body=body,
                author="Federal Reserve",
                section="monetary_policy_report",
                language="en",
                tier=1,
                access="free",
                retrieval="fed_site",
                word_count=len(body.split()),
                raw_metadata={"document_type": "monetary_policy_report"},
            )

    def _fetch_fsr(self, start: date, end: date) -> Iterator[Article]:
        """Fetch Financial Stability Reports (2x/yr, May and Nov).

        Index: federalreserve.gov/publications/financial-stability-report.htm
        HTML pattern: /publications/financial-stability-report-YYYYMM.htm
                   or /publications/YYYY-mon-financial-stability-report.htm
        """
        import re as _re
        index_url = "https://www.federalreserve.gov/publications/financial-stability-report.htm"
        try:
            resp = _get(index_url)
        except Exception as exc:
            log.error("Failed to fetch FSR index: %s", exc)
            return
        soup = BeautifulSoup(resp.text, "lxml")
        seen: set[str] = set()
        _MONTH_ABBR = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "financial-stability-report" not in href.lower():
                continue
            if href.lower().endswith(".pdf"):
                continue
            # Skip the index page itself
            if href.rstrip("/").endswith("financial-stability-report"):
                continue
            pub_date: date | None = None
            # Pattern: financial-stability-report-YYYYMM
            m = _re.search(r"financial-stability-report-(\d{4})(\d{2})", href)
            if m:
                try:
                    pub_date = date(int(m.group(1)), int(m.group(2)), 1)
                except ValueError:
                    pass
            # Pattern: YYYY-mon-financial-stability-report (e.g. 2024-may-financial-stability-report)
            if pub_date is None:
                m = _re.search(r"(\d{4})-([a-z]{3})-financial-stability-report", href.lower())
                if m:
                    month = _MONTH_ABBR.get(m.group(2))
                    if month:
                        try:
                            pub_date = date(int(m.group(1)), month, 1)
                        except ValueError:
                            pass
            if pub_date is None:
                continue
            if pub_date < start or pub_date > end:
                continue
            full_url = href if href.startswith("http") else f"https://www.federalreserve.gov{href}"
            if full_url in seen:
                continue
            seen.add(full_url)
            try:
                page = _get(full_url)
            except Exception as exc:
                log.warning("Failed to fetch FSR %s: %s", full_url, exc)
                continue
            body = _extract_text(page.text)
            if not body or len(body.split()) < 200:
                continue
            yield Article(
                article_id=_stable_article_id(self.source_id, full_url),
                source_id="federalreserve",
                url=full_url,
                published_at=pub_date.isoformat() + "T14:00:00Z",
                retrieved_at=_now_utc_iso(),
                title=f"Financial Stability Report — {pub_date.strftime('%B %Y')}",
                body=body,
                author="Federal Reserve",
                section="financial_stability_report",
                language="en",
                tier=1,
                access="free",
                retrieval="fed_site",
                word_count=len(body.split()),
                raw_metadata={"document_type": "financial_stability_report"},
            )

    def _fetch_speeches_rss_year(self, year: int, start: date, end: date) -> Iterator[Article]:
        """RSS fallback for Fed speeches when annual index pages are unreachable."""
        log.info("Fed speech RSS fallback: fetching %s for year %d", SPEECHES_RSS, year)
        try:
            feed = feedparser.parse(SPEECHES_RSS, request_headers={"User-Agent": USER_AGENT})
        except Exception as exc:
            log.error("Fed speech RSS fallback also failed for %d: %s", year, exc)
            return
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)
        for entry in feed.entries:
            pub_parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
            if not pub_parsed:
                continue
            try:
                speech_date = date(*pub_parsed[:3])
            except Exception:
                continue
            if not (year_start <= speech_date <= year_end):
                continue
            if speech_date < start or speech_date > end:
                continue
            url = entry.get("link", "")
            if not url:
                continue
            title = entry.get("title", "Federal Reserve speech")
            try:
                page = _get(url)
                body = _extract_text(page.text)
            except Exception as exc:
                log.debug("RSS fallback speech fetch failed %s: %s", url, exc)
                body = BeautifulSoup(entry.get("summary", ""), "lxml").get_text(strip=True)
            if not body or len(body.split()) < 50:
                continue
            yield Article(
                article_id=_stable_article_id(self.source_id, url),
                source_id="federalreserve",
                url=url,
                published_at=speech_date.isoformat() + "T15:00:00Z",
                retrieved_at=_now_utc_iso(),
                title=title,
                body=body,
                author=entry.get("author"),
                section="speech",
                language="en",
                tier=1,
                access="free",
                retrieval="fed_rss_fallback",
                word_count=len(body.split()),
                raw_metadata={"document_type": "speech", "retrieval_fallback": True},
            )
