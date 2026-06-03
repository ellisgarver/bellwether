"""Federal Reserve communications ingestion.

Pulls FOMC statements, minutes, Beige Book reports, Board speeches, and
Monetary Policy Reports. All public domain, all free, all directly from
federalreserve.gov.

This ingestor is structured around the Fed's calendar pages rather than a
catalog API (the Fed does not publish one). We scrape the index pages and
fetch each linked artifact.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Iterator

import feedparser
import requests
from bs4 import BeautifulSoup
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)

from mnd.ingestion.base import Article, Ingestor, _now_utc_iso, _stable_article_id
from mnd.utils.logging import get_logger

log = get_logger(__name__)

USER_AGENT = "MacroNarrativeDynamics/0.1 (academic research; contact via project repo)"

FOMC_HISTORICAL_BASE = "https://www.federalreserve.gov/monetarypolicy"
FOMC_CALENDARS_URL = f"{FOMC_HISTORICAL_BASE}/fomccalendars.htm"
SPEECHES_BASE = "https://www.federalreserve.gov/newsevents/speech"
# Primary URL pattern works for 2011-present.
# Pre-2011 uses a different filename (no hyphen, singular "speech"):
#   2010 → /newsevents/speech/2010speech.htm
# We try the primary pattern first, then fall back to the legacy pattern.
SPEECHES_INDEX = f"{SPEECHES_BASE}/{{year}}-speeches.htm"
SPEECHES_INDEX_LEGACY = f"{SPEECHES_BASE}/{{year}}speech.htm"
SPEECHES_RSS = "https://www.federalreserve.gov/feeds/speeches.xml"


def _is_retryable(exc: Exception) -> bool:
    """Retry on server errors and transient network failures; not on 4xx.

    The Fed ingestor probes many URLs that legitimately 404 (Beige Book
    backstop enumeration tries both era URL variants for every month;
    speech-index fallback probes legacy filenames; FOMC pages that don't
    exist yet for a window edge). Retrying a 404 is pointless and — with
    ``wait_random_exponential(max=120)`` over 8 attempts — could stall the
    walk for minutes per dead URL, compounding to hours across a full
    ingest. Mirror institutional.py's predicate: only 5xx and true
    transient transport errors are retried.
    """
    if isinstance(exc, requests.exceptions.HTTPError):
        resp = getattr(exc, "response", None)
        return resp is not None and resp.status_code >= 500
    return True


@retry(
    stop=stop_after_attempt(5),
    wait=wait_random_exponential(multiplier=1, max=30),
    retry=retry_if_exception(_is_retryable),
)
def _get(url: str, *, timeout=30.0) -> requests.Response:
    # Normalize float timeout to a (connect, read) tuple. Single-value timeouts
    # in stdlib `requests` are unreliable on TCP-level stalls — the read timeout
    # only counts inter-byte gaps, not total time, so a server that drips one
    # byte every 29s never trips a 30s timeout. The 2026-05-18 patch ingest
    # hung for 2+ hours on a single Fed speech URL in exactly that state.
    if isinstance(timeout, (int, float)):
        timeout = (10.0, float(timeout))
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

    # FOMC statement URL: /newsevents/pressreleases/monetary{YYYYMMDD}[a].htm
    # Implementation notes (separate documents, ~9 words of operational
    # directive): monetary{YYYYMMDD}a1.htm, a2.htm. These aren't part of
    # the narrative discourse and should not be in the corpus. The regex
    # matches statements (optional single trailing letter) but rejects
    # implementation notes (letter followed by digit).
    _FOMC_STATEMENT_HREF_RE = re.compile(
        r"/newsevents/pressreleases/monetary(\d{8})[a-z]?\.htm$"
    )
    # Pre-2014 statements live under the legacy press path
    # (/newsevents/press/monetary/{YYYYMMDD}a.htm). Same aN.htm
    # implementation-note rejection applies via the [a-z]? + $ anchor.
    _FOMC_STATEMENT_HREF_RE_LEGACY = re.compile(
        r"/newsevents/press/monetary/(\d{8})[a-z]?\.htm$"
    )

    def _fomc_index_soups(self, start: date, end: date) -> list[BeautifulSoup]:
        """Return the FOMC index pages covering [start, end], memoized.

        The live calendars page only lists ~2021-present. Meetings from
        2020 and earlier live on per-year historical pages
        (fomchistorical{YYYY}.htm). We always include the calendars page,
        then add a historical page for each year in range; years still on
        the calendar 404 their historical page and are skipped. Both the
        statement and minutes walks share this result so each page is
        fetched once per ingest.
        """
        cache = getattr(self, "_fomc_soup_cache", None)
        if cache is not None and cache[0] == (start, end):
            return cache[1]
        soups: list[BeautifulSoup] = []
        try:
            resp = _get(FOMC_CALENDARS_URL)
        except Exception as exc:
            raise RuntimeError(
                f"FOMC calendar index fetch failed after retries: {exc}"
            ) from exc
        soups.append(BeautifulSoup(resp.text, "lxml"))
        for year in range(start.year, min(end.year, date.today().year) + 1):
            url = f"{FOMC_HISTORICAL_BASE}/fomchistorical{year}.htm"
            try:
                resp = _get(url)
            except Exception:
                continue  # no historical page for years still on the calendar
            soups.append(BeautifulSoup(resp.text, "lxml"))
        self._fomc_soup_cache = ((start, end), soups)
        return soups

    def _fetch_fomc_statements(self, start: date, end: date) -> Iterator[Article]:
        """Walk the FOMC index pages; emit one Article per statement.

        Filters out FOMC implementation notes (URLs ending in
        ``aN.htm`` where N is a digit) — these are short operational
        directives about reserve balance management, not the narrative-
        carrying statement itself.
        """
        seen: set[str] = set()
        for soup in self._fomc_index_soups(start, end):
            for link in soup.find_all("a", href=True):
                href = link["href"]
                m = (self._FOMC_STATEMENT_HREF_RE.search(href)
                     or self._FOMC_STATEMENT_HREF_RE_LEGACY.search(href))
                if not m:
                    continue
                try:
                    meeting_date = datetime.strptime(m.group(1), "%Y%m%d").date()
                except Exception:
                    continue
                if meeting_date < start or meeting_date > end:
                    continue

                full_url = href if href.startswith("http") else f"https://www.federalreserve.gov{href}"
                if full_url in seen:
                    continue
                seen.add(full_url)
                try:
                    page = _get(full_url)
                except Exception as exc:  # pragma: no cover
                    log.warning("Failed to fetch FOMC statement %s: %s", full_url, exc)
                    continue

                body = _extract_text(page.text)
                if not body or len(body.split()) < 50:
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
        """Fetch FOMC meeting minutes from the calendars + historical pages.

        Skips the .pdf minutes variant present on pre-2014 historical pages
        (the .htm copy is always present alongside it and extracts cleanly).
        """
        seen: set[str] = set()
        for soup in self._fomc_index_soups(start, end):
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if "fomcminutes" not in href or not href.endswith(".htm"):
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
                if full_url in seen:
                    continue
                seen.add(full_url)
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
        """Fetch Beige Book reports.

        Three-source strategy:
          1. The default index page (beige-book-default.htm) — current year only.
          2. The archive index (beige-book-archive.htm) — links to per-year
             landing pages (beigebookYYYY.htm) which in turn list each issue.
             This is the canonical way to discover historical issues.
          3. Direct URL enumeration as a backstop for years where the archive
             index walk yields nothing. URL pattern is era-dependent:
               - 2017+:   /monetarypolicy/beigebookYYYYMM.htm
               - 2010-16: /monetarypolicy/beigebook/beigebookYYYYMM.htm
                          (extra `beigebook/` subdirectory)
             We try both variants for every (year, month) and accept 404s.

        Earlier code relied only on (1) and missed ~97% of historical Beige
        Books because beige-book-default.htm doesn't link to prior years.
        The single-pattern enumeration added on 2026-05-18 fixed 2017+ but
        still missed 2010-2016 because that era uses the subdirectory variant.
        """
        seen_urls: set[str] = set()

        def _emit_from_url(full_url: str, pub_date: date) -> Iterator[Article]:
            if full_url in seen_urls:
                return
            seen_urls.add(full_url)
            try:
                page = _get(full_url)
            except Exception as exc:
                log.debug("Beige Book %s fetch failed: %s", full_url, exc)
                return
            body = _extract_text(page.text)
            if not body or len(body.split()) < 200:
                return
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

        import re as _re
        import time as _time

        # Matches both /monetarypolicy/beigebook201906.htm (2017+) and
        # /monetarypolicy/beigebook/beigebook201406.htm (2010-16).
        issue_pat = _re.compile(r"/monetarypolicy/(?:beigebook/)?beigebook(\d{4})(\d{2})\.htm$")

        # (1) Default index page — covers the current year.
        index_url = "https://www.federalreserve.gov/monetarypolicy/beige-book-default.htm"
        try:
            resp = _get(index_url)
        except Exception as exc:
            log.warning("Beige Book index fetch failed: %s", exc)
            resp = None
        if resp is not None:
            soup = BeautifulSoup(resp.text, "lxml")
            for link in soup.find_all("a", href=True):
                href = link["href"]
                m = issue_pat.search(href)
                if not m:
                    continue
                try:
                    pub_date = date(int(m.group(1)), int(m.group(2)), 1)
                except ValueError:
                    continue
                if pub_date < start or pub_date > end:
                    continue
                full_url = href if href.startswith("http") else f"https://www.federalreserve.gov{href}"
                yield from _emit_from_url(full_url, pub_date)

        # (2) Archive index — walks per-year landing pages for historical issues.
        archive_url = "https://www.federalreserve.gov/monetarypolicy/beige-book-archive.htm"
        try:
            archive_resp = _get(archive_url)
            archive_soup = BeautifulSoup(archive_resp.text, "lxml")
            year_pages: list[str] = []
            for link in archive_soup.find_all("a", href=True):
                href = link["href"]
                ym = _re.search(r"/monetarypolicy/beigebook(\d{4})\.htm$", href)
                if not ym:
                    continue
                year = int(ym.group(1))
                if year < start.year or year > end.year:
                    continue
                full = href if href.startswith("http") else f"https://www.federalreserve.gov{href}"
                year_pages.append(full)
            for year_page in year_pages:
                try:
                    page_resp = _get(year_page)
                except Exception as exc:
                    log.debug("Beige Book year page %s fetch failed: %s", year_page, exc)
                    continue
                year_soup = BeautifulSoup(page_resp.text, "lxml")
                for link in year_soup.find_all("a", href=True):
                    href = link["href"]
                    m = issue_pat.search(href)
                    if not m:
                        continue
                    try:
                        pub_date = date(int(m.group(1)), int(m.group(2)), 1)
                    except ValueError:
                        continue
                    if pub_date < start or pub_date > end:
                        continue
                    full_url = href if href.startswith("http") else f"https://www.federalreserve.gov{href}"
                    yield from _emit_from_url(full_url, pub_date)
                _time.sleep(0.2)
        except Exception as exc:
            log.warning("Beige Book archive index fetch failed: %s", exc)

        # (3) Backstop direct enumeration — try both URL variants for each
        # (year, month) in window. Most 404; cheap to attempt.
        for year in range(start.year, end.year + 1):
            for month in range(1, 13):
                pub_date = date(year, month, 1)
                if pub_date < start or pub_date > end:
                    continue
                for variant in (
                    f"https://www.federalreserve.gov/monetarypolicy/beigebook"
                    f"{year:04d}{month:02d}.htm",
                    f"https://www.federalreserve.gov/monetarypolicy/beigebook/beigebook"
                    f"{year:04d}{month:02d}.htm",
                ):
                    if variant in seen_urls:
                        continue
                    yield from _emit_from_url(variant, pub_date)
                    _time.sleep(0.2)

    def _fetch_speeches(self, start: date, end: date) -> Iterator[Article]:
        """Walk Board speech indexes year by year; fall back to RSS on index failure.

        Page structure: div.eventlist > div.row > (div.eventlist__time > time,
        div.eventlist__event > p > a).  Date text is MM/DD/YYYY (no datetime attr).
        """
        for year in range(start.year, end.year + 1):
            index_url = SPEECHES_INDEX.format(year=year)
            resp = None
            try:
                resp = _get(index_url)
            except Exception as exc_primary:
                # Pre-2011 the Fed used /newsevents/speech/YYYYspeech.htm instead
                # of the YYYY-speeches.htm pattern. Try the legacy URL once before
                # giving up.
                legacy_url = SPEECHES_INDEX_LEGACY.format(year=year)
                try:
                    resp = _get(legacy_url)
                    log.info("Speech index %d: primary URL failed; legacy URL succeeded (%s)",
                             year, legacy_url)
                    index_url = legacy_url
                except Exception as exc_legacy:
                    current_year = date.today().year
                    if year >= current_year - 1:
                        # RSS feed only holds recent content — useful for current/last year
                        log.warning(
                            "Speech index %s failed: %s — trying RSS fallback",
                            SPEECHES_INDEX.format(year=year), exc_primary,
                        )
                        yield from self._fetch_speeches_rss_year(year, start, end)
                    else:
                        # RSS has no historical content; RSS fallback would silently return 0
                        # articles, creating an invisible coverage gap. Log error and skip.
                        log.error(
                            "Speech index for %d failed on both URL patterns "
                            "(primary: %s; legacy: %s) — COVERAGE GAP: speeches for %d "
                            "will be missing from corpus",
                            year, exc_primary, exc_legacy, year,
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
        """Fetch FEDS Notes from the Fed's econres/notes listing pages.

        FEDS Notes are short analytical pieces (1,000–3,000 words, ~70/year) written
        by Board economists. Faster than working papers; authoritative within days of
        events.

        URL pattern (modern, 2017+):
            /econres/notes/feds-notes/{slug}-{YYYYMMDD}.html
        URL pattern (legacy, 2013-2016):
            /econresdata/notes/feds-notes/{YEAR}/{slug}-{YYYYMMDD}.html
            (extra ``data`` segment and per-year subdirectory)

        The per-year index pages (.../feds-notes/{YEAR}-index.htm) link to BOTH
        URL variants depending on the publication date, so walking the per-year
        indexes for the full window discovers the historical legacy URLs that
        the modern-only regex previously dropped.
        """
        import re as _re
        import time as _time

        seen: set[str] = set()
        # Match both URL formats:
        #   /econres/notes/feds-notes/{slug}-YYYYMMDD.html         (2017+)
        #   /econresdata/notes/feds-notes/{YEAR}/{slug}-YYYYMMDD.html  (2013-16)
        # The `{slug}-` portion may be a complete slug or omitted (rare).
        slug_pattern = _re.compile(
            r"/econres(?:data)?/notes/feds-notes/(?:\d{4}/)?"
            r"[^/\"]+?-(\d{4})(\d{2})(\d{2})\.html?$"
        )

        index_urls = ["https://www.federalreserve.gov/econres/notes/feds-notes/"]
        # Per-year archive pages exist (e.g. .../feds-notes/2024-index.htm) and
        # serve as the canonical discovery path for legacy-URL notes.
        for year in range(start.year, end.year + 1):
            index_urls.append(
                f"https://www.federalreserve.gov/econres/notes/feds-notes/{year}-index.htm"
            )

        for index_url in index_urls:
            try:
                resp = _get(index_url)
            except Exception as exc:
                log.debug("FEDS Notes index %s fetch failed: %s", index_url, exc)
                continue
            soup = BeautifulSoup(resp.text, "lxml")
            for link in soup.find_all("a", href=True):
                href = link["href"]
                m = slug_pattern.search(href)
                if not m:
                    continue
                try:
                    pub_date = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                except ValueError:
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
                    log.debug("FEDS Notes fetch failed %s: %s", full_url, exc)
                    continue
                body = _extract_text(page.text)
                if not body or len(body.split()) < 100:
                    continue
                title = link.get_text(strip=True) or f"FEDS Note {pub_date.year}"
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
