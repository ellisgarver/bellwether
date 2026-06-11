"""Federal Reserve communications ingestion.

Pulls FOMC statements, minutes, Beige Book reports, Board speeches and
testimony, FEDS Notes, Monetary Policy Reports, and Financial Stability
Reports. All public domain, all free, all directly from federalreserve.gov.

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

# Board testimony (Humphrey-Hawkins + governors before House/Senate committees)
# shares the speech CMS template exactly: same .eventlist markup, same legacy
# (no-hyphen) URL fallback for pre-2011. A distinct monetary-discourse stream
# parallel to CongressionalIngestor's Treasury-Secretary testimony capture.
TESTIMONY_BASE = "https://www.federalreserve.gov/newsevents/testimony"
TESTIMONY_INDEX = f"{TESTIMONY_BASE}/{{year}}-testimony.htm"
TESTIMONY_INDEX_LEGACY = f"{TESTIMONY_BASE}/{{year}}testimony.htm"
TESTIMONY_RSS = "https://www.federalreserve.gov/feeds/testimony.xml"


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
        yield from self._fetch_testimony(start, end)
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
        yield from self._walk_eventlist_stream(
            start, end, index_tmpl=SPEECHES_INDEX, legacy_tmpl=SPEECHES_INDEX_LEGACY,
            rss_url=SPEECHES_RSS, section="speech", doc_type="speech", label="speech",
        )

    def _fetch_testimony(self, start: date, end: date) -> Iterator[Article]:
        yield from self._walk_eventlist_stream(
            start, end, index_tmpl=TESTIMONY_INDEX, legacy_tmpl=TESTIMONY_INDEX_LEGACY,
            rss_url=TESTIMONY_RSS, section="testimony", doc_type="testimony", label="testimony",
        )

    def _walk_eventlist_stream(
        self, start: date, end: date, *, index_tmpl: str, legacy_tmpl: str,
        rss_url: str, section: str, doc_type: str, label: str,
    ) -> Iterator[Article]:
        """Walk Board eventlist index pages year by year; RSS fallback on index failure.

        Shared by speeches and testimony, which use the same CMS template:
        div.eventlist > div.row > (div.eventlist__time > time,
        div.eventlist__event > p > a).  Date text is MM/DD/YYYY (no datetime attr).
        Pre-2011 uses the no-hyphen legacy filename ({year}speech.htm /
        {year}testimony.htm). RSS only holds recent content, so it is a fallback
        for the current/last year only; an older-year index failure is logged as a
        COVERAGE GAP rather than silently returning zero.
        """
        for year in range(start.year, end.year + 1):
            index_url = index_tmpl.format(year=year)
            resp = None
            try:
                resp = _get(index_url)
            except Exception as exc_primary:
                legacy_url = legacy_tmpl.format(year=year)
                try:
                    resp = _get(legacy_url)
                    log.info("%s index %d: primary URL failed; legacy URL succeeded (%s)",
                             label, year, legacy_url)
                    index_url = legacy_url
                except Exception as exc_legacy:
                    current_year = date.today().year
                    if year >= current_year - 1:
                        log.warning(
                            "%s index %s failed: %s — trying RSS fallback",
                            label, index_tmpl.format(year=year), exc_primary,
                        )
                        yield from self._fetch_eventlist_rss_year(
                            year, start, end, rss_url=rss_url,
                            section=section, doc_type=doc_type, label=label,
                        )
                    else:
                        log.error(
                            "%s index for %d failed on both URL patterns "
                            "(primary: %s; legacy: %s) — COVERAGE GAP: %s for %d "
                            "will be missing from corpus",
                            label, year, exc_primary, exc_legacy, label, year,
                        )
                    continue
            soup = BeautifulSoup(resp.text, "lxml")
            eventlist = soup.select_one(".eventlist")
            if not eventlist:
                log.error(
                    "%s index %s: .eventlist container not found — "
                    "COVERAGE GAP: %s for %d will be missing from corpus",
                    label, index_url, label, year,
                )
                continue
            for entry in eventlist.select("div.row"):
                date_node = entry.select_one("time")
                # Link is inside div.eventlist__event; skip watch-live / other links
                link_node = entry.select_one("div.eventlist__event a[href]")
                if not date_node or not link_node:
                    continue
                try:
                    # Date text is M/D/YYYY (e.g. "1/10/2023"), no datetime attribute
                    item_date = datetime.strptime(date_node.get_text(strip=True), "%m/%d/%Y").date()
                except Exception:
                    continue
                if item_date < start or item_date > end:
                    continue
                href = link_node["href"]
                full_url = href if href.startswith("http") else f"https://www.federalreserve.gov{href}"
                title = link_node.get_text(strip=True)
                speaker_el = entry.select_one("p.news__speaker")
                speaker = speaker_el.get_text(strip=True) if speaker_el else ""
                try:
                    page = _get(full_url)
                except Exception as exc:
                    log.warning("Failed to fetch %s %s: %s", label, full_url, exc)
                    continue
                body = _extract_text(page.text)
                # 50-word floor matches every other ingestor; it drops the
                # short quantitative/notice posts while keeping brief remarks.
                if not body or len(body.split()) < 50:
                    continue
                yield Article(
                    article_id=_stable_article_id(self.source_id, full_url),
                    source_id="federalreserve",
                    url=full_url,
                    published_at=item_date.isoformat() + "T15:00:00Z",
                    retrieved_at=_now_utc_iso(),
                    title=title or f"Federal Reserve {label}",
                    body=body,
                    author=speaker,
                    section=section,
                    language="en",
                    tier=1,
                    access="free",
                    retrieval="fed_site",
                    word_count=len(body.split()),
                    raw_metadata={"document_type": doc_type},
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
        URL patterns on the index, by era:
          - 2017+ : /monetarypolicy/YYYY-MM-mpr-summary.htm
          - 2007-2016 : /monetarypolicy/mpr_YYYYMMDD_part1.htm | _summary.htm
            (underscore + 8 digits; the report is split into several parts —
            we keep one page per issue, preferring the summary)
        One MPR issue = one document on its release date; multiple legacy
        parts are deduped to a single record per (year, month) so a split
        report doesn't inflate that week's volume.
        """
        import re as _re
        index_url = "https://www.federalreserve.gov/monetarypolicy/mpr_default.htm"
        try:
            resp = _get(index_url)
        except Exception as exc:
            log.error("Failed to fetch MPR index: %s", exc)
            return
        soup = BeautifulSoup(resp.text, "lxml")
        # Gather one candidate URL per (year, month), preferring a summary page.
        candidates: dict[tuple[int, int], tuple[date, str, bool]] = {}
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "mpr" not in href.lower():
                continue
            if href.lower().endswith(".pdf"):
                continue
            pub_date: date | None = None
            # Modern: YYYY-MM-mpr (e.g. /monetarypolicy/2024-02-mpr-summary.htm)
            m = _re.search(r"(\d{4})-(\d{2})-mpr", href)
            if m:
                try:
                    pub_date = date(int(m.group(1)), int(m.group(2)), 1)
                except ValueError:
                    pass
            # Legacy underscore: mpr_YYYYMMDD_part1.htm / _summary.htm (2007-2016)
            if pub_date is None:
                m = _re.search(r"mpr_(\d{4})(\d{2})(\d{2})", href)
                if m:
                    try:
                        pub_date = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                    except ValueError:
                        pass
            # Other compact forms: mprYYYYMMDD or mprYYYYMM
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
            key = (pub_date.year, pub_date.month)
            is_summary = "summary" in href.lower()
            existing = candidates.get(key)
            # Keep the first hit, but let a summary page override a part page.
            if existing is None or (is_summary and not existing[2]):
                candidates[key] = (pub_date, full_url, is_summary)

        for pub_date, full_url, _is_summary in candidates.values():
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
        """Fetch Financial Stability Reports (2x/yr, May and Nov; since Nov 2018).

        Index: federalreserve.gov/publications/financial-stability-report.htm
        URL patterns seen on the index (order of month/year varies by era):
          - financial-stability-report-YYYYMM.htm
          - YYYY-{month}-financial-stability-report... (year-first)
          - {month}-YYYY-financial-stability-report... (month-first, 2024+)
          - YYYY-financial-stability-report... (bare year — the Nov issue)
        Month tokens may be abbreviated or full names. Deduped by
        (year, month) so the same issue under two URL forms isn't doubled.
        """
        import re as _re
        index_url = "https://www.federalreserve.gov/publications/financial-stability-report.htm"
        try:
            resp = _get(index_url)
        except Exception as exc:
            log.error("Failed to fetch FSR index: %s", exc)
            return
        soup = BeautifulSoup(resp.text, "lxml")
        _MONTH_ABBR = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        # Gather one candidate per (year, month), preferring a month-dated
        # hit over a bare-year fallback for the same year.
        candidates: dict[tuple[int, int], tuple[date, str, bool]] = {}
        for link in soup.find_all("a", href=True):
            href = link["href"]
            low = href.lower()
            if "financial-stability-report" not in low:
                continue
            if low.endswith(".pdf"):
                continue
            if href.rstrip("/").endswith("financial-stability-report"):
                continue
            pub_date: date | None = None
            is_bare_year = False
            # financial-stability-report-YYYYMM
            m = _re.search(r"financial-stability-report-(\d{4})(\d{2})", low)
            if m:
                try:
                    pub_date = date(int(m.group(1)), int(m.group(2)), 1)
                except ValueError:
                    pass
            # year-first: YYYY-{month}-financial-stability-report
            if pub_date is None:
                m = _re.search(r"(\d{4})-([a-z]+)-financial-stability-report", low)
                if m and (month := _MONTH_ABBR.get(m.group(2)[:3])):
                    try:
                        pub_date = date(int(m.group(1)), month, 1)
                    except ValueError:
                        pass
            # month-first: {month}-YYYY-financial-stability-report
            if pub_date is None:
                m = _re.search(r"([a-z]+)-(\d{4})-financial-stability-report", low)
                if m and (month := _MONTH_ABBR.get(m.group(1)[:3])):
                    try:
                        pub_date = date(int(m.group(2)), month, 1)
                    except ValueError:
                        pass
            # bare year: YYYY-financial-stability-report — the Nov year-end issue
            if pub_date is None:
                m = _re.search(r"(\d{4})-financial-stability-report", low)
                if m:
                    try:
                        pub_date = date(int(m.group(1)), 11, 1)
                        is_bare_year = True
                    except ValueError:
                        pass
            if pub_date is None:
                continue
            if pub_date < start or pub_date > end:
                continue
            full_url = href if href.startswith("http") else f"https://www.federalreserve.gov{href}"
            key = (pub_date.year, pub_date.month)
            existing = candidates.get(key)
            # Prefer a precisely-dated hit over the bare-year guess.
            if existing is None or (existing[2] and not is_bare_year):
                candidates[key] = (pub_date, full_url, is_bare_year)

        for pub_date, full_url, _bare in candidates.values():
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

    def _fetch_eventlist_rss_year(
        self, year: int, start: date, end: date, *,
        rss_url: str, section: str, doc_type: str, label: str,
    ) -> Iterator[Article]:
        """RSS fallback for Fed eventlist streams (speeches/testimony) when annual
        index pages are unreachable."""
        log.info("Fed %s RSS fallback: fetching %s for year %d", label, rss_url, year)
        try:
            feed = feedparser.parse(rss_url, request_headers={"User-Agent": USER_AGENT})
        except Exception as exc:
            log.error("Fed %s RSS fallback also failed for %d: %s", label, year, exc)
            return
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)
        for entry in feed.entries:
            pub_parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
            if not pub_parsed:
                continue
            try:
                item_date = date(*pub_parsed[:3])
            except Exception:
                continue
            if not (year_start <= item_date <= year_end):
                continue
            if item_date < start or item_date > end:
                continue
            url = entry.get("link", "")
            if not url:
                continue
            title = entry.get("title", f"Federal Reserve {label}")
            try:
                page = _get(url)
                body = _extract_text(page.text)
            except Exception as exc:
                log.debug("RSS fallback %s fetch failed %s: %s", label, url, exc)
                body = BeautifulSoup(entry.get("summary", ""), "lxml").get_text(strip=True)
            if not body or len(body.split()) < 50:
                continue
            yield Article(
                article_id=_stable_article_id(self.source_id, url),
                source_id="federalreserve",
                url=url,
                published_at=item_date.isoformat() + "T15:00:00Z",
                retrieved_at=_now_utc_iso(),
                title=title,
                body=body,
                author=entry.get("author"),
                section=section,
                language="en",
                tier=1,
                access="free",
                retrieval="fed_rss_fallback",
                word_count=len(body.split()),
                raw_metadata={"document_type": doc_type, "retrieval_fallback": True},
            )
