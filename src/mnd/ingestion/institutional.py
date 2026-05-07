"""Institutional, academic, and policy-journalism ingestors.

Covers the semantic corpus tiers defined in ADR-008 and config/whitelist.yaml:

  Tier 1 — Institutional policy
    IMFIngestor           imf.org — WPs, WEO/GFSR summaries, IMF Blog
    BISIngestor           bis.org — Quarterly Review, WPs
    FedRegionalIngestor   Regional Fed blogs and Economic Letters (RSS)
    CBOIngestor           cbo.gov publications (RSS)
    TreasuryOFRIngestor   OFR Annual Reports + WPs, FSOC Annual Reports

  Tier 2 — Academic analytical
    NBERIngestor          nber.org — WP abstracts + introductions (JEL E/F/G)
    SSRNIngestor          ssrn.com — Financial Economics Network abstracts
    VoxEUIngestor         cepr.org/voxeu — full posts (RSS)

  Tier 3 — Policy-journalism bridge
    BrookingsIngestor     brookings.edu — Economic Studies full posts (RSS)
    PIIEIngestor          piie.com — full posts (RSS)

  InstitutionalIngestor   Composite: runs all of the above and merges output.

Note: FederalReserveIngestor (FOMC statements, minutes, speeches, Beige Book)
lives in fed.py and is not repeated here. InstitutionalIngestor calls it too.

All timestamps follow the ADR-008 rule: publication/release date only.
FOMC minutes = release date. NBER papers = posting date.
"""
from __future__ import annotations

import json
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterator
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

import feedparser
import requests
import trafilatura
from bs4 import BeautifulSoup
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_random_exponential

from mnd.ingestion.base import Article, Ingestor, _now_utc_iso, _stable_article_id
from mnd.ingestion.fed import FederalReserveIngestor
from mnd.utils.logging import get_logger

log = get_logger(__name__)

USER_AGENT = "MacroNarrativeDynamics/0.1 (academic research; contact via project repo)"
_HEADERS = {"User-Agent": USER_AGENT}

# JEL codes that indicate macro/finance relevance for NBER filtering
_NBER_JEL_PREFIXES = ("E", "F", "G")


def _is_retryable(exc: Exception) -> bool:
    """Retry on server errors and transient network failures; not on 4xx."""
    if isinstance(exc, requests.exceptions.HTTPError):
        resp = getattr(exc, "response", None)
        return resp is not None and resp.status_code >= 500
    return True


@retry(
    stop=stop_after_attempt(5),
    wait=wait_random_exponential(multiplier=1, max=30),
    retry=retry_if_exception(_is_retryable),
)
def _get(url: str, *, timeout: float = 30.0) -> requests.Response:
    resp = requests.get(url, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp


def _parse_rss(feed_url: str) -> list[feedparser.FeedParserDict]:
    """Fetch and parse an RSS/Atom feed. Returns list of entries."""
    try:
        feed = feedparser.parse(feed_url, request_headers={"User-Agent": USER_AGENT})
        return feed.entries
    except Exception as exc:
        log.warning("RSS parse failed for %s: %s", feed_url, exc)
        return []


def _extract_body(url: str, *, min_words: int = 50) -> str | None:
    """Fetch URL and extract article text with trafilatura. Returns None on failure."""
    try:
        resp = _get(url, timeout=30.0)
        text = trafilatura.extract(
            resp.text,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
        )
        if text and len(text.split()) >= min_words:
            return text
        # Fallback: BeautifulSoup paragraph extraction
        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup.find_all(["nav", "footer", "script", "style", "header"]):
            tag.decompose()
        content = soup.find("main") or soup.find("article") or soup.find("body")
        if content:
            text = content.get_text(separator=" ", strip=True)
            if len(text.split()) >= min_words:
                return text
    except Exception as exc:
        log.debug("Body extraction failed for %s: %s", url, exc)
    return None


def _entry_date(entry: feedparser.FeedParserDict) -> date | None:
    """Extract publication date from an RSS entry. Returns None if unparseable."""
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        val = getattr(entry, attr, None)
        if val:
            try:
                return date(*val[:3])
            except Exception:
                pass
    return None


def _make_article(
    *,
    source_id: str,
    url: str,
    published_at: str,
    title: str,
    body: str,
    author: str | None = None,
    section: str | None = None,
    tier: int,
    document_type: str,
    extra_meta: dict | None = None,
) -> Article:
    return Article(
        article_id=_stable_article_id(source_id, url),
        source_id=source_id,
        url=url,
        published_at=published_at,
        retrieved_at=_now_utc_iso(),
        title=title,
        body=body,
        author=author,
        section=section,
        language="en",
        tier=tier,
        access="free",
        retrieval="institutional_rss",
        word_count=len(body.split()),
        raw_metadata={"document_type": document_type, **(extra_meta or {})},
    )


_DATE_FMTS = [
    "%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%B %d, %Y",
    "%b %d, %Y", "%b. %d, %Y", "%Y/%m/%d", "%m/%d/%Y",
    "%B %Y", "%b %Y",
]


def _parse_date_flexible(text: str) -> date | None:
    """Try common date format strings then regex fallbacks."""
    text = text.strip()
    for fmt in _DATE_FMTS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if m:
        try:
            return date.fromisoformat(m.group(1))
        except ValueError:
            pass
    return None


def _fetch_page_full(
    url: str, *, min_words: int = 30
) -> tuple[str, str, str | None, date | None]:
    """Fetch url; return (body_text, title, author, pub_date). Empty/None on failure."""
    try:
        resp = _get(url, timeout=30.0)
    except Exception as exc:
        log.debug("Fetch failed %s: %s", url, exc)
        return "", "", None, None
    try:
        body = trafilatura.extract(resp.text, include_comments=False, include_tables=False)
        meta = trafilatura.extract_metadata(resp.text)
    except Exception:
        body, meta = None, None
    title = (meta.title or "") if meta else ""
    author = (meta.author or None) if meta else None
    pub_date: date | None = None
    if meta and meta.date:
        pub_date = _parse_date_flexible(str(meta.date))
    if not body or len(body.split()) < min_words:
        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup.find_all(["nav", "footer", "script", "style", "header"]):
            tag.decompose()
        content = soup.find("main") or soup.find("article") or soup.find("body")
        if content:
            body = content.get_text(separator=" ", strip=True)
    return (body or ""), title, author, pub_date


def _wp_rest_fetch(
    api_base: str,
    post_type: str,
    start: date,
    end: date,
    *,
    extra_fields: str = "link,date,title,excerpt",
) -> Iterator[dict]:
    """Yield raw post dicts from a WordPress REST API for the given date range."""
    page = 1
    while True:
        params = {
            "per_page": 100,
            "page": page,
            "after": (start - timedelta(days=1)).isoformat() + "T00:00:00Z",
            "before": (end + timedelta(days=1)).isoformat() + "T00:00:00Z",
            "_fields": extra_fields,
        }
        try:
            resp = requests.get(
                f"{api_base}/wp-json/wp/v2/{post_type}",
                params=params,
                headers=_HEADERS,
                timeout=30.0,
            )
            if resp.status_code in (400, 404):
                break
            resp.raise_for_status()
        except Exception as exc:
            log.warning("WP REST %s/%s page %d: %s", api_base, post_type, page, exc)
            break

        posts = resp.json()
        if not isinstance(posts, list) or not posts:
            break
        yield from posts

        total_pages = int(resp.headers.get("X-WP-TotalPages", "1"))
        if page >= total_pages:
            break
        page += 1
        time.sleep(0.5)


def _wp_post_to_article(
    post: dict,
    *,
    source_id: str,
    section: str,
    tier: int,
    document_type: str,
    start: date,
    end: date,
    fetch_full_body: bool = True,
) -> Article | None:
    """Convert a WP REST API post dict to an Article. Returns None if out of range."""
    post_date_str = post.get("date", "")
    try:
        pub_date = datetime.fromisoformat(post_date_str.replace("Z", "+00:00")).date()
    except (ValueError, AttributeError):
        return None
    if pub_date < start or pub_date > end:
        return None

    url = post.get("link", "")
    if not url:
        return None

    title_raw = post.get("title", {})
    title = BeautifulSoup(
        title_raw.get("rendered", "") if isinstance(title_raw, dict) else str(title_raw),
        "lxml",
    ).get_text(strip=True)

    excerpt_raw = post.get("excerpt", {})
    excerpt = BeautifulSoup(
        excerpt_raw.get("rendered", "") if isinstance(excerpt_raw, dict) else "",
        "lxml",
    ).get_text(strip=True)

    if fetch_full_body:
        body, fetched_title, author, _ = _fetch_page_full(url, min_words=50)
        if not body or len(body.split()) < 50:
            body = excerpt
        if fetched_title and not title:
            title = fetched_title
    else:
        body, author = excerpt, None

    if not body or len(body.split()) < 30:
        return None

    return _make_article(
        source_id=source_id,
        url=url,
        published_at=pub_date.isoformat() + "T00:00:00Z",
        title=title or url,
        body=body,
        author=author,
        section=section,
        tier=tier,
        document_type=document_type,
    )


# ---------------------------------------------------------------------------
# Tier 1 — Institutional policy
# ---------------------------------------------------------------------------


class IMFIngestor(Ingestor):
    """IMF: working papers (RSS), IMF Blog (RSS), WEO/GFSR narrative summaries.

    WEO and GFSR full texts are large PDFs — we fetch only the HTML landing
    page text (Overview / Chapter 1 excerpts) which captures the narrative
    framing without pulling a 200-page PDF.
    """

    source_id = "imf"

    _FEEDS = [
        ("https://www.imf.org/en/Publications/WP/rss", "working_paper"),
        ("https://www.imf.org/en/Blogs/rss", "imf_blog"),
    ]

    # WEO and GFSR index pages — extract chapter links dynamically
    _WEO_INDEX = "https://www.imf.org/en/Publications/WEO"
    _GFSR_INDEX = "https://www.imf.org/en/Publications/GFSR"

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        yield from self._fetch_feeds(start, end)
        yield from self._fetch_flagship_overviews(start, end, self._WEO_INDEX, "weo")
        yield from self._fetch_flagship_overviews(start, end, self._GFSR_INDEX, "gfsr")

    def _fetch_feeds(self, start: date, end: date) -> Iterator[Article]:
        for feed_url, doc_type in self._FEEDS:
            for entry in _parse_rss(feed_url):
                pub_date = _entry_date(entry)
                if not pub_date or pub_date < start or pub_date > end:
                    continue
                url = entry.get("link", "")
                if not url:
                    continue
                title = entry.get("title", "IMF publication")
                # Use summary as body if full text unavailable; otherwise fetch
                summary = entry.get("summary", "")
                body = _extract_body(url) or summary
                if not body or len(body.split()) < 30:
                    continue
                yield _make_article(
                    source_id=self.source_id,
                    url=url,
                    published_at=pub_date.isoformat() + "T00:00:00Z",
                    title=title,
                    body=body,
                    author=entry.get("author"),
                    section=doc_type,
                    tier=1,
                    document_type=doc_type,
                )
                time.sleep(0.5)

    def _fetch_flagship_overviews(
        self, start: date, end: date, index_url: str, doc_type: str
    ) -> Iterator[Article]:
        """Scrape IMF flagship publication index and fetch HTML overview pages."""
        try:
            resp = _get(index_url)
        except Exception as exc:
            log.warning("IMF %s index fetch failed: %s", doc_type.upper(), exc)
            return
        soup = BeautifulSoup(resp.text, "lxml")
        for link in soup.find_all("a", href=True):
            href = link["href"]
            # Overview/executive-summary links contain year and edition indicators
            if not any(kw in href.lower() for kw in ["overview", "executive-summary", "chapter-1"]):
                continue
            full_url = urljoin("https://www.imf.org", href)
            # Try to parse year from URL
            try:
                year_str = next(
                    p for p in urlparse(full_url).path.split("/") if len(p) == 4 and p.isdigit()
                )
                pub_date = date(int(year_str), 1, 1)
            except StopIteration:
                continue
            if pub_date.year < start.year or pub_date.year > end.year:
                continue
            body = _extract_body(full_url, min_words=100)
            if not body:
                continue
            title = link.get_text(strip=True) or f"IMF {doc_type.upper()} {year_str} Overview"
            yield _make_article(
                source_id=self.source_id,
                url=full_url,
                published_at=pub_date.isoformat() + "T00:00:00Z",
                title=title,
                body=body,
                author="IMF",
                section=doc_type,
                tier=1,
                document_type=doc_type,
            )
            time.sleep(1.0)


class BISIngestor(Ingestor):
    """BIS Working Papers via year-based XML sitemaps.

    BIS publishes ~60-80 working papers per year. We discover them from
    ``bis.org/sitemap_documents_{year}.xml`` (URL pattern ``/publ/workNNNN.htm``)
    and use the ``lastmod`` date as the publication date.

    The old RSS feed (bis_rss.rss) only carries recent items; the sitemap
    approach gives full historical coverage back to the 1990s.
    """

    source_id = "bis"

    _SITEMAP_TMPL = "https://www.bis.org/sitemap_documents_{year}.xml"
    _BASE = "https://www.bis.org"

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        seen: set[str] = set()
        for year in range(start.year, end.year + 1):
            yield from self._fetch_year(year, start, end, seen)

    def _fetch_year(
        self, year: int, start: date, end: date, seen: set[str]
    ) -> Iterator[Article]:
        sitemap_url = self._SITEMAP_TMPL.format(year=year)
        try:
            resp = requests.get(sitemap_url, headers=_HEADERS, timeout=30.0)
            resp.raise_for_status()
            tree = ET.fromstring(resp.content)
        except Exception as exc:
            log.warning("BIS sitemap %d: %s", year, exc)
            return

        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        for url_el in tree.findall("s:url", ns):
            loc_el = url_el.find("s:loc", ns)
            mod_el = url_el.find("s:lastmod", ns)
            if loc_el is None:
                continue
            url = loc_el.text or ""
            if not re.search(r"/publ/work\d+\.htm$", url):
                continue

            pub_date: date | None = None
            if mod_el is not None and mod_el.text:
                try:
                    pub_date = date.fromisoformat(mod_el.text[:10])
                except ValueError:
                    pass
            if pub_date is None:
                pub_date = date(year, 1, 1)

            if pub_date < start or pub_date > end:
                continue
            if url in seen:
                continue
            seen.add(url)

            body, title, author, _ = _fetch_page_full(url, min_words=50)
            if not body or len(body.split()) < 50:
                continue

            yield _make_article(
                source_id=self.source_id,
                url=url,
                published_at=pub_date.isoformat() + "T00:00:00Z",
                title=title or url.split("/")[-1],
                body=body,
                author=author,
                section="working_paper",
                tier=1,
                document_type="bis_working_paper",
            )
            time.sleep(1.0)


class FedRegionalIngestor(Ingestor):
    """Regional Fed publication blogs: archive-based retrieval.

    Sources and retrieval strategies:
      Liberty Street Economics (NY Fed) — WordPress REST API
      FRBSF Economic Letter/Working Papers — sffed_publications WP REST API
      Chicago Fed Letter — XML sitemap URL discovery + trafilatura extraction
      Atlanta macroblog — RSS (historical listing is JS-gated; no static archive)

    The main FederalReserveIngestor (fed.py) covers Board communications.
    This ingestor captures regional analytical content.
    """

    source_id = "fed_regional"

    # RSS fallback for Atlanta (historical gap documented)
    _ATLANTA_RSS = "https://www.atlantafed.org/blogs/macroblog/rss"

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        seen: set[str] = set()
        yield from self._fetch_liberty_street(start, end, seen)
        yield from self._fetch_frbsf(start, end, seen)
        yield from self._fetch_chicago_fed_letter(start, end, seen)
        yield from self._fetch_atlanta(start, end, seen)

    # ------------------------------------------------------------------
    # Liberty Street Economics — WP REST API
    # ------------------------------------------------------------------

    def _fetch_liberty_street(
        self, start: date, end: date, seen: set[str]
    ) -> Iterator[Article]:
        base = "https://libertystreeteconomics.newyorkfed.org"
        for post in _wp_rest_fetch(base, "posts", start, end):
            url = post.get("link", "")
            if not url or url in seen:
                continue
            seen.add(url)
            article = _wp_post_to_article(
                post,
                source_id="fed_ny",
                section="liberty_street_economics",
                tier=1,
                document_type="fed_regional_research",
                start=start,
                end=end,
                fetch_full_body=True,
            )
            if article:
                yield article
                time.sleep(0.5)

    # ------------------------------------------------------------------
    # FRBSF — sffed_publications WP REST API
    # ------------------------------------------------------------------

    def _fetch_frbsf(
        self, start: date, end: date, seen: set[str]
    ) -> Iterator[Article]:
        base = "https://www.frbsf.org"
        for post in _wp_rest_fetch(base, "sffed_publications", start, end):
            url = post.get("link", "")
            if not url or url in seen:
                continue
            seen.add(url)
            article = _wp_post_to_article(
                post,
                source_id="fed_sf",
                section="frbsf_economic_letter",
                tier=1,
                document_type="fed_regional_research",
                start=start,
                end=end,
                fetch_full_body=True,
            )
            if article:
                yield article
                time.sleep(0.5)

    # ------------------------------------------------------------------
    # Chicago Fed Letter — sitemap URL discovery
    # ------------------------------------------------------------------

    def _fetch_chicago_fed_letter(
        self, start: date, end: date, seen: set[str]
    ) -> Iterator[Article]:
        """Discover letter URLs from chicagofed.org sitemap, filter by year in URL path."""
        sitemap_url = "https://www.chicagofed.org/sitemap.xml"
        try:
            resp = requests.get(sitemap_url, headers=_HEADERS, timeout=30.0)
            resp.raise_for_status()
            tree = ET.fromstring(resp.content)
        except Exception as exc:
            log.warning("Chicago Fed sitemap failed: %s", exc)
            return

        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        # Collect letter URLs grouped by year extracted from path
        for url_el in tree.findall("s:url", ns):
            loc_el = url_el.find("s:loc", ns)
            if loc_el is None:
                continue
            url = loc_el.text or ""
            # Pattern: /publications/chicago-fed-letter/YYYY/NNN
            m = re.search(r"/chicago-fed-letter/(\d{4})/\d+$", url)
            if not m:
                continue
            year = int(m.group(1))
            if year < start.year or year > end.year:
                continue
            if url in seen:
                continue
            seen.add(url)

            body, title, author, meta_date = _fetch_page_full(url, min_words=50)
            if not body or len(body.split()) < 50:
                continue

            # Prefer trafilatura's parsed date; fall back to year-start
            pub_date = date(year, 1, 1)
            if meta_date and start <= meta_date <= end:
                pub_date = meta_date

            if pub_date < start or pub_date > end:
                continue

            yield _make_article(
                source_id="fed_chicago",
                url=url,
                published_at=pub_date.isoformat() + "T00:00:00Z",
                title=title or f"Chicago Fed Letter {year}",
                body=body,
                author=author,
                section="chicago_fed_letter",
                tier=1,
                document_type="fed_regional_research",
            )
            time.sleep(1.0)

    # ------------------------------------------------------------------
    # Atlanta macroblog — RSS (no historical archive accessible)
    # ------------------------------------------------------------------

    def _fetch_atlanta(
        self, start: date, end: date, seen: set[str]
    ) -> Iterator[Article]:
        """Atlanta macroblog RSS — provides recent content only.

        The historic macroblog content (pre-2022) is behind a JS-gated listing
        and old URLs were removed during the site redesign. RSS covers
        approximately the last 30–60 days.
        """
        for entry in _parse_rss(self._ATLANTA_RSS):
            pub_date = _entry_date(entry)
            if not pub_date or pub_date < start or pub_date > end:
                continue
            url = entry.get("link", "")
            if not url or url in seen:
                continue
            seen.add(url)
            title = entry.get("title", "Atlanta Fed macroblog")
            body = _extract_body(url) or BeautifulSoup(
                entry.get("summary", ""), "lxml"
            ).get_text(strip=True)
            if not body or len(body.split()) < 50:
                continue
            yield _make_article(
                source_id="fed_atlanta",
                url=url,
                published_at=pub_date.isoformat() + "T00:00:00Z",
                title=title,
                body=body,
                author=entry.get("author"),
                section="macroblog",
                tier=1,
                document_type="fed_regional_research",
                extra_meta={"historical_gap": True},
            )
            time.sleep(0.5)


class CBOIngestor(Ingestor):
    """Congressional Budget Office publications.

    Historical archive: scrapes cbo.gov/publications (paginated HTML).
    Note: cbo.gov returns HTTP 403 from residential IPs due to bot protection.
    This scraper is expected to work from university networks (e.g., RCC Midway3).
    Falls back to RSS for recent content if the archive is blocked.
    """

    source_id = "cbo"

    _LIST_URL = "https://www.cbo.gov/publications"
    _RSS_URL = "https://www.cbo.gov/publication/rss"

    _KEEP_KEYWORDS = {
        "budget and economic outlook", "economic outlook", "working paper",
        "budget outlook", "long-term budget", "monthly budget review",
        "economic effects", "labor market", "inflation", "fiscal", "recession",
    }

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        seen: set[str] = set()
        yielded = False
        for article in self._fetch_archive(start, end, seen):
            yield article
            yielded = True
        if not yielded:
            log.info(
                "CBO archive unavailable (likely residential IP block); "
                "falling back to RSS (recent content only)"
            )
            yield from self._fetch_rss(start, end, seen)

    def _fetch_archive(
        self, start: date, end: date, seen: set[str]
    ) -> Iterator[Article]:
        """Scrape cbo.gov/publications paginated listing."""
        page = 0
        past_window = False
        while not past_window:
            try:
                resp = requests.get(
                    self._LIST_URL,
                    params={"page": page},
                    headers=_HEADERS,
                    timeout=30.0,
                )
                if resp.status_code == 403:
                    log.debug("CBO publications blocked (HTTP 403) — skipping archive")
                    return
                resp.raise_for_status()
            except Exception as exc:
                log.warning("CBO archive page %d: %s", page, exc)
                return

            soup = BeautifulSoup(resp.text, "lxml")
            # CBO Drupal listing: items inside .views-row or similar
            rows = (
                soup.select(".views-row")
                or soup.select("li.views-row")
                or soup.select("article")
                or soup.select(".pub-listing-item")
            )
            if not rows:
                break

            for row in rows:
                link = row.find("a", href=True)
                if not link:
                    continue
                href = link["href"]
                url = urljoin("https://www.cbo.gov", href)
                title = link.get_text(strip=True)

                date_el = row.find("time") or row.find(class_=lambda c: c and "date" in c.lower() if c else False)
                date_text = date_el.get("datetime", "") or (date_el.get_text(strip=True) if date_el else "")
                pub_date = _parse_date_flexible(date_text)
                if not pub_date:
                    # try to find year in row text
                    pub_date = _parse_year_from_text(row.get_text(" ", strip=True), start, end)
                if not pub_date:
                    continue

                if pub_date > end:
                    continue
                if pub_date < start:
                    past_window = True
                    continue

                if not self._is_relevant(title):
                    continue

                if url in seen:
                    continue
                seen.add(url)

                body = _extract_body(url, min_words=50)
                if not body or len(body.split()) < 50:
                    continue

                yield _make_article(
                    source_id=self.source_id,
                    url=url,
                    published_at=pub_date.isoformat() + "T00:00:00Z",
                    title=title,
                    body=body,
                    author="CBO",
                    section="cbo_publication",
                    tier=1,
                    document_type="cbo_publication",
                )
                time.sleep(1.0)

            page += 1
            time.sleep(0.5)

    def _fetch_rss(
        self, start: date, end: date, seen: set[str]
    ) -> Iterator[Article]:
        for entry in _parse_rss(self._RSS_URL):
            pub_date = _entry_date(entry)
            if not pub_date or pub_date < start or pub_date > end:
                continue
            url = entry.get("link", "")
            if not url or url in seen:
                continue
            seen.add(url)
            title = entry.get("title", "CBO publication")
            if not self._is_relevant(title):
                continue
            body = _extract_body(url) or BeautifulSoup(entry.get("summary", ""), "lxml").get_text(strip=True)
            if not body or len(body.split()) < 50:
                continue
            yield _make_article(
                source_id=self.source_id,
                url=url,
                published_at=pub_date.isoformat() + "T00:00:00Z",
                title=title,
                body=body,
                author="CBO",
                section="cbo_publication",
                tier=1,
                document_type="cbo_publication",
            )
            time.sleep(0.5)

    def _is_relevant(self, title: str) -> bool:
        tl = title.lower()
        return any(kw in tl for kw in self._KEEP_KEYWORDS)


class TreasuryOFRIngestor(Ingestor):
    """Treasury Office of Financial Research and FSOC publications.

    OFR publishes Annual Reports, Working Papers, and Briefs.
    FSOC publishes Annual Reports.
    Both are static HTML/PDF with no RSS — we fetch known index pages.
    """

    source_id = "treasury_ofr"

    _OFR_WORKING_PAPERS = "https://www.financialresearch.gov/working-papers/"
    _OFR_BRIEFS = "https://www.financialresearch.gov/briefs/"
    _FSOC_REPORTS = "https://home.treasury.gov/policy-issues/financial-markets-financial-institutions-and-fiscal-service/fsoc/studies-and-reports"

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        yield from self._scrape_ofr_index(self._OFR_WORKING_PAPERS, "ofr_working_paper", start, end)
        yield from self._scrape_ofr_index(self._OFR_BRIEFS, "ofr_brief", start, end)
        yield from self._scrape_fsoc(start, end)

    def _scrape_ofr_index(
        self, index_url: str, doc_type: str, start: date, end: date
    ) -> Iterator[Article]:
        try:
            resp = _get(index_url)
        except Exception as exc:
            log.warning("OFR index fetch failed %s: %s", index_url, exc)
            return
        soup = BeautifulSoup(resp.text, "lxml")
        for entry in soup.select("li, article, .publication-entry, .views-row"):
            link = entry.find("a", href=True)
            if not link:
                continue
            href = link["href"]
            full_url = urljoin("https://www.financialresearch.gov", href)
            title = link.get_text(strip=True)
            # Try to extract year from title or nearby text
            text_context = entry.get_text(" ", strip=True)
            pub_date = _parse_year_from_text(text_context, start, end)
            if not pub_date:
                continue
            body = _extract_body(full_url, min_words=50)
            if not body:
                continue
            yield _make_article(
                source_id=self.source_id,
                url=full_url,
                published_at=pub_date.isoformat() + "T00:00:00Z",
                title=title or doc_type,
                body=body,
                author="OFR",
                section=doc_type,
                tier=1,
                document_type=doc_type,
            )
            time.sleep(1.0)

    def _scrape_fsoc(self, start: date, end: date) -> Iterator[Article]:
        try:
            resp = _get(self._FSOC_REPORTS)
        except Exception as exc:
            log.warning("FSOC reports fetch failed: %s", exc)
            return
        soup = BeautifulSoup(resp.text, "lxml")
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "annual" not in href.lower() and "annual" not in link.get_text().lower():
                continue
            full_url = urljoin("https://home.treasury.gov", href)
            title = link.get_text(strip=True)
            pub_date = _parse_year_from_text(title + " " + href, start, end)
            if not pub_date:
                continue
            body = _extract_body(full_url, min_words=50)
            if not body:
                continue
            yield _make_article(
                source_id=self.source_id,
                url=full_url,
                published_at=pub_date.isoformat() + "T00:00:00Z",
                title=title or "FSOC Annual Report",
                body=body,
                author="FSOC",
                section="fsoc_annual_report",
                tier=1,
                document_type="fsoc_annual_report",
            )
            time.sleep(1.0)


# ---------------------------------------------------------------------------
# Tier 2 — Academic analytical
# ---------------------------------------------------------------------------


class NBERIngestor(Ingestor):
    """NBER Working Papers: abstracts + introduction section.

    Timestamp = paper posting date (when it enters public discourse).
    Filter to JEL codes E (Macro/Monetary), F (International), G (Financial).

    Uses the NBER Drupal API (paginated, newest-first) instead of the RSS feed
    which 404s since the 2024 site redesign. Individual paper pages are fetched
    only for macro-relevant papers (to get exact date and full abstract).
    """

    source_id = "nber"

    _API_URL = "https://www.nber.org/api/v1/working_page_listing/contentType/working_paper/_/_/search"
    _PAPER_BASE = "https://www.nber.org"
    _JEL_PREFIXES = _NBER_JEL_PREFIXES
    _PER_PAGE = 100

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        start_year, end_year = start.year, end.year

        # Estimate starting page to avoid scanning years we don't need.
        # ~600 NBER papers/year on average; API returns newest-first.
        from datetime import date as _date
        current_year = _date.today().year
        years_back_from_now = max(0, current_year - end_year)
        start_page = max(1, int(years_back_from_now * 600 / self._PER_PAGE) - 2)
        log.debug("NBER: starting at page %d (end_year=%d)", start_page, end_year)

        page = start_page
        passed_window = False  # True once we've seen a record with year < start_year

        while True:
            try:
                resp = requests.get(
                    self._API_URL,
                    params={"page": page, "perPage": self._PER_PAGE},
                    headers=_HEADERS,
                    timeout=30.0,
                )
                resp.raise_for_status()
            except Exception as exc:
                log.warning("NBER API page %d failed: %s", page, exc)
                break

            data = resp.json()
            results = data.get("results", [])
            if not results:
                break  # exhausted corpus

            for record in results:
                display_date = record.get("displaydate", "") or ""
                try:
                    record_month = datetime.strptime(display_date, "%B %Y")
                    record_year = record_month.year
                except ValueError:
                    continue

                if record_year > end_year:
                    continue  # still approaching our window (newest-first)
                if record_year < start_year:
                    passed_window = True
                    continue  # finish this page, then stop

                url_path = record.get("url", "")
                if not url_path:
                    continue
                url = self._PAPER_BASE + url_path if url_path.startswith("/") else url_path

                title = record.get("title", "NBER working paper")
                api_abstract = BeautifulSoup(record.get("abstract", ""), "lxml").get_text(" ", strip=True)

                # Quick relevance pre-filter on title + truncated API abstract
                if not self._is_macro_relevant([], title, api_abstract):
                    continue

                # Fetch individual page for exact date, full abstract, JEL codes
                try:
                    exact_date, full_abstract, jel_codes, authors = self._fetch_paper_page(url)
                except Exception as exc:
                    log.debug("NBER page fetch failed %s: %s", url, exc)
                    exact_date, full_abstract, jel_codes = None, api_abstract, []
                    authors = self._parse_authors(record.get("authors", ""))

                # Re-check with JEL codes now that we have them
                if jel_codes and not self._is_macro_relevant(jel_codes, title, full_abstract):
                    continue

                pub_date = exact_date if exact_date else record_month.date().replace(day=1)
                if pub_date < start or pub_date > end:
                    continue

                body = full_abstract or api_abstract
                if not body or len(body.split()) < 30:
                    continue

                yield _make_article(
                    source_id=self.source_id,
                    url=url,
                    published_at=pub_date.isoformat() + "T00:00:00Z",
                    title=title,
                    body=body,
                    author=", ".join(authors) if authors else None,
                    section="working_paper",
                    tier=2,
                    document_type="nber_working_paper",
                    extra_meta={"jel_codes": jel_codes},
                )
                time.sleep(0.3)

            if passed_window:
                break  # all subsequent pages are older than start_year

            page += 1
            time.sleep(0.5)

    def _fetch_paper_page(self, url: str) -> tuple[date | None, str, list[str], list[str]]:
        """Return (exact_date, abstract_text, jel_codes, authors) from an NBER paper page."""
        import re

        resp = requests.get(url, headers=_HEADERS, timeout=30.0)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # Exact publication date from citation meta tag: "YYYY/MM/DD"
        exact_date: date | None = None
        meta_date = soup.find("meta", attrs={"name": "citation_publication_date"})
        if meta_date and meta_date.get("content"):
            try:
                exact_date = datetime.strptime(meta_date["content"], "%Y/%m/%d").date()
            except ValueError:
                pass

        # Full abstract from the page-header intro div
        abstract_el = soup.select_one("div.page-header__intro-inner")
        if not abstract_el:
            abstract_el = soup.find("div", class_=lambda c: c and "abstract" in c.lower())
        abstract_text = abstract_el.get_text(" ", strip=True) if abstract_el else ""

        # JEL codes: look for text matching capital letter + 2 digits
        jel_codes: list[str] = []
        for tag in soup.find_all(string=lambda t: t and "JEL" in t):
            code_text = tag.parent.get_text(" ", strip=True) if tag.parent else ""
            found = re.findall(r"\b[A-Z]\d{2}\b", code_text)
            if found:
                jel_codes = found
                break

        # Authors: strip HTML from <a> tags in the author list
        authors = self._parse_authors_from_soup(soup)

        return exact_date, abstract_text, jel_codes, authors

    def _parse_authors(self, authors_html: str) -> list[str]:
        """Extract plain author names from NBER API HTML author list."""
        if not authors_html:
            return []
        soup = BeautifulSoup(authors_html, "lxml")
        return [a.get_text(strip=True) for a in soup.find_all("a") if a.get_text(strip=True)]

    def _parse_authors_from_soup(self, soup: BeautifulSoup) -> list[str]:
        author_el = soup.select_one(".page-header__authors")
        if not author_el:
            return []
        return [a.get_text(strip=True) for a in author_el.find_all("a") if a.get_text(strip=True)]

    def _is_macro_relevant(self, jel_codes: list[str], title: str, abstract: str) -> bool:
        if jel_codes:
            return any(code.startswith(prefix) for code in jel_codes for prefix in self._JEL_PREFIXES)
        macro_terms = {
            "inflation", "monetary policy", "interest rate", "federal reserve",
            "exchange rate", "gdp", "recession", "unemployment", "credit",
            "financial stability", "central bank", "fiscal", "yield curve",
        }
        text_lower = (title + " " + abstract).lower()
        return any(term in text_lower for term in macro_terms)


class SSRNIngestor(Ingestor):
    """SSRN Financial Economics Network: abstract-only records via RSS.

    Full text is not consistently accessible. Abstracts provide sufficient
    semantic signal for macro-financial narrative clustering.

    Historical limitation: SSRN does not expose a public bulk API for historical
    papers. The RSS feeds carry only recent submissions (typically 30–90 days).
    SSRN contributes primarily to the live-update pipeline (Phase 6), not the
    historical corpus. This limitation is disclosed in the pre-registration.
    """

    source_id = "ssrn_finance"

    _FEEDS = [
        "https://papers.ssrn.com/sol3/Jrnls/jrnl.cfm?link=2",   # Financial Economics
        "https://papers.ssrn.com/sol3/jrnls/jrnl.cfm?link=30",  # Macroeconomics
    ]

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        seen: set[str] = set()
        for feed_url in self._FEEDS:
            for entry in _parse_rss(feed_url):
                pub_date = _entry_date(entry)
                if not pub_date or pub_date < start or pub_date > end:
                    continue
                url = entry.get("link", "")
                if not url or url in seen:
                    continue
                seen.add(url)
                title = entry.get("title", "SSRN paper")
                abstract = BeautifulSoup(entry.get("summary", ""), "lxml").get_text(strip=True)
                if not abstract or len(abstract.split()) < 20:
                    continue
                yield _make_article(
                    source_id=self.source_id,
                    url=url,
                    published_at=pub_date.isoformat() + "T00:00:00Z",
                    title=title,
                    body=abstract,
                    author=entry.get("author"),
                    section="working_paper",
                    tier=2,
                    document_type="ssrn_abstract",
                )
                time.sleep(0.2)


class VoxEUIngestor(Ingestor):
    """VoxEU / CEPR columns: date-filtered archive search.

    Uses the date-range filter on ``cepr.org/voxeu/search-all-columns``
    (``date[min]``/``date[max]`` GET params in YYYY-MM-DD format).  This gives
    access to the full archive from 2007 to present, not just the recent RSS
    window.  Each result page returns 12 articles; we paginate until all pages
    are consumed.
    """

    source_id = "voxeu"

    _SEARCH_URL = "https://cepr.org/voxeu/search-all-columns"
    _BASE = "https://cepr.org"

    # Macro-relevance terms for VoxEU pre-filter (loose — most VoxEU columns
    # are economics; this just excludes pure health/education posts)
    _MACRO_TERMS = {
        "inflation", "monetary", "interest rate", "federal reserve", "central bank",
        "exchange rate", "gdp", "recession", "unemployment", "credit", "fiscal",
        "financial", "bank", "debt", "trade", "currency", "bond", "yield",
        "growth", "economy", "economics", "market", "policy", "capital",
        "covid", "pandemic", "crisis", "shock", "risk", "investment",
    }

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        seen: set[str] = set()
        page = 0
        while True:
            params = {
                "date[min]": start.isoformat(),
                "date[max]": end.isoformat(),
                "page": page,
            }
            try:
                resp = requests.get(self._SEARCH_URL, params=params, headers=_HEADERS, timeout=30.0)
                resp.raise_for_status()
            except Exception as exc:
                log.warning("VoxEU search page %d: %s", page, exc)
                break

            soup = BeautifulSoup(resp.text, "lxml")
            articles = soup.select("article.c-card")
            if not articles:
                break

            for art in articles:
                link = art.find("a", href=True)
                if not link:
                    continue
                href = link["href"]
                url = urljoin(self._BASE, href) if href.startswith("/") else href
                if url in seen:
                    continue
                seen.add(url)

                date_el = art.select_one("time")
                if not date_el:
                    continue
                date_text = date_el.get("datetime", "") or date_el.get_text(strip=True)
                pub_date = _parse_date_flexible(date_text)
                if not pub_date or pub_date < start or pub_date > end:
                    continue

                title_el = art.select_one("h3, h2, .c-card__title")
                title = title_el.get_text(strip=True) if title_el else ""

                if not self._is_macro_relevant(title):
                    continue

                body, fetched_title, author, _ = _fetch_page_full(url, min_words=50)
                if not body or len(body.split()) < 50:
                    continue
                if fetched_title and not title:
                    title = fetched_title

                yield _make_article(
                    source_id=self.source_id,
                    url=url,
                    published_at=pub_date.isoformat() + "T00:00:00Z",
                    title=title or "VoxEU column",
                    body=body,
                    author=author,
                    section="voxeu_column",
                    tier=2,
                    document_type="voxeu_column",
                )
                time.sleep(1.0)

            # Check if there are more pages
            last_link = soup.select_one("a[title='Go to last page'], .pager__item--last a")
            if last_link:
                m = re.search(r"page=(\d+)", last_link.get("href", ""))
                if m and page >= int(m.group(1)):
                    break
            elif len(articles) < 12:
                break  # incomplete page = last page

            page += 1
            time.sleep(1.0)

    def _is_macro_relevant(self, title: str) -> bool:
        tl = title.lower()
        return any(term in tl for term in self._MACRO_TERMS)


# ---------------------------------------------------------------------------
# Tier 3 — Policy-journalism bridge
# ---------------------------------------------------------------------------


class BrookingsIngestor(Ingestor):
    """Brookings Institution: WordPress REST API (``article`` post type).

    The ``article`` custom type contains all research publications. 53k+ total
    articles accessible via date-range filter. Individual article pages are
    fetched for full body text.

    Macro-relevance pre-filter avoids fetching pages for health, education,
    and governance content that is out of scope.
    """

    source_id = "brookings"

    _API_BASE = "https://www.brookings.edu"

    _MACRO_TERMS = {
        "inflation", "monetary", "interest rate", "federal reserve", "central bank",
        "exchange rate", "gdp", "recession", "unemployment", "credit", "fiscal",
        "financial", "bank", "debt", "trade", "currency", "bond", "yield",
        "growth", "economy", "economics", "market", "policy", "budget", "tax",
        "covid", "pandemic", "crisis", "labor market", "housing", "investment",
    }

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        seen: set[str] = set()
        for post in _wp_rest_fetch(self._API_BASE, "article", start, end):
            url = post.get("link", "")
            if not url or url in seen:
                continue

            title_raw = post.get("title", {})
            title = BeautifulSoup(
                title_raw.get("rendered", "") if isinstance(title_raw, dict) else str(title_raw),
                "lxml",
            ).get_text(strip=True)

            if not self._is_macro_relevant(title):
                continue

            seen.add(url)
            article = _wp_post_to_article(
                post,
                source_id=self.source_id,
                section="brookings_economic_studies",
                tier=3,
                document_type="brookings_post",
                start=start,
                end=end,
                fetch_full_body=True,
            )
            if article:
                yield article
                time.sleep(1.0)

    def _is_macro_relevant(self, title: str) -> bool:
        tl = title.lower()
        return any(term in tl for term in self._MACRO_TERMS)


class PIIEIngestor(Ingestor):
    """Peterson Institute for International Economics: listing page scraper.

    PIIE's individual article pages return HTTP 403 from residential IPs
    (Cloudflare protection). The listing pages are accessible and contain
    title, date, author, and URL. Full article body is attempted but falls
    back to title-only if the page is blocked.

    From university IPs (RCC Midway3) the full body fetch succeeds. The
    listing covers policy-briefs, working-papers, piie-briefings, and
    key research blogs.

    Note: PIIE URLs encode the publication year, enabling reliable date
    filtering without fetching each article.
    """

    source_id = "piie"

    _LISTING_PATHS = [
        ("/publications/policy-briefs", "policy_brief"),
        ("/publications/working-papers", "working_paper"),
        ("/publications/piie-briefings", "piie_briefing"),
        ("/blogs/realtime-economic-issues-watch", "blog_post"),
        ("/blogs/trade-investment-policy-watch", "blog_post"),
    ]

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        seen: set[str] = set()
        for path, doc_type in self._LISTING_PATHS:
            yield from self._fetch_listing(path, doc_type, start, end, seen)

    def _fetch_listing(
        self,
        path: str,
        doc_type: str,
        start: date,
        end: date,
        seen: set[str],
    ) -> Iterator[Article]:
        base = "https://www.piie.com"
        page = 0
        past_window = False

        while not past_window:
            try:
                resp = requests.get(
                    base + path,
                    params={"page": page} if page > 0 else {},
                    headers=_HEADERS,
                    timeout=30.0,
                )
                if resp.status_code in (403, 404):
                    log.debug("PIIE %s page %d: HTTP %d", path, page, resp.status_code)
                    return
                resp.raise_for_status()
            except Exception as exc:
                log.warning("PIIE %s page %d: %s", path, page, exc)
                return

            soup = BeautifulSoup(resp.text, "lxml")
            items = soup.select("article.teaser")
            if not items:
                break

            for item in items:
                date_el = item.select_one("time")
                if not date_el:
                    continue
                dt_str = date_el.get("datetime", "")
                try:
                    pub_date = datetime.fromisoformat(dt_str.replace("Z", "+00:00")).date()
                except (ValueError, AttributeError):
                    pub_date = _parse_date_flexible(date_el.get_text(strip=True))
                if not pub_date:
                    continue

                if pub_date > end:
                    continue
                if pub_date < start:
                    past_window = True
                    continue

                link = item.select_one(".teaser__title a")
                if not link:
                    continue
                href = link.get("href", "")
                url = urljoin(base, href) if href.startswith("/") else href
                if url in seen:
                    continue
                seen.add(url)

                title = link.get_text(strip=True)
                author_el = item.select_one(".author-list")
                author = author_el.get_text(" ", strip=True) if author_el else None

                # Try to fetch full body; fall back to title on 403
                body, fetched_title, _, _pd = _fetch_page_full(url, min_words=30)
                if not body or len(body.split()) < 20:
                    body = title  # minimal fallback — will be filtered by corpus min_words
                    log.debug("PIIE body unavailable for %s (likely residential IP block)", url)
                if fetched_title and not title:
                    title = fetched_title

                if not body or len(body.split()) < 10:
                    continue

                yield _make_article(
                    source_id=self.source_id,
                    url=url,
                    published_at=pub_date.isoformat() + "T00:00:00Z",
                    title=title,
                    body=body,
                    author=author,
                    section="piie_publication",
                    tier=3,
                    document_type=f"piie_{doc_type}",
                    extra_meta={"listing_only": len(body.split()) < 50},
                )
                time.sleep(1.0)

            page += 1
            time.sleep(0.5)


# ---------------------------------------------------------------------------
# Composite ingestor
# ---------------------------------------------------------------------------


class InstitutionalIngestor(Ingestor):
    """Composite: runs all institutional, academic, and policy-journalism ingestors.

    Also delegates to FederalReserveIngestor for Board communications (FOMC,
    speeches, Beige Book). Use this as the single entry point for the full
    Phase 2 semantic corpus ingestion.

    Checkpoint/resume: if checkpoint_path is given, a JSON file is written after
    each sub-ingestor completes. On restart, completed sub-ingestors are skipped
    and the JSONL output is opened in append mode by the caller (run_pipeline.py).
    Partial sub-ingestor runs may produce duplicate records; the filter/dedup
    stage handles them.
    """

    source_id = "institutional"

    def __init__(self, checkpoint_path: Path | None = None) -> None:
        self._checkpoint_path = checkpoint_path
        self._sub_ingestors: list[Ingestor] = [
            FederalReserveIngestor(),
            FedRegionalIngestor(),
            IMFIngestor(),
            BISIngestor(),
            CBOIngestor(),
            TreasuryOFRIngestor(),
            NBERIngestor(),
            SSRNIngestor(),
            VoxEUIngestor(),
            BrookingsIngestor(),
            PIIEIngestor(),
        ]

    def _load_checkpoint(self) -> dict:
        if self._checkpoint_path and self._checkpoint_path.exists():
            try:
                return json.loads(self._checkpoint_path.read_text())
            except Exception as exc:
                log.warning("Could not load checkpoint %s: %s — starting fresh", self._checkpoint_path, exc)
        return {}

    def _save_checkpoint(self, data: dict) -> None:
        if self._checkpoint_path:
            self._checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            self._checkpoint_path.write_text(json.dumps(data, indent=2))

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        checkpoint = self._load_checkpoint()
        for ingestor in self._sub_ingestors:
            sid = ingestor.source_id
            if checkpoint.get(sid, {}).get("status") == "completed":
                log.info("Checkpoint: skipping %s (already completed, %d articles)",
                         sid, checkpoint[sid].get("count", 0))
                continue
            log.info("InstitutionalIngestor: running %s", sid)
            count = 0
            try:
                for article in ingestor.fetch(start, end):
                    yield article
                    count += 1
                checkpoint[sid] = {"status": "completed", "count": count}
                self._save_checkpoint(checkpoint)
                log.info("Checkpoint: %s completed (%d articles)", sid, count)
            except Exception as exc:
                log.error("Sub-ingestor %s failed: %s", sid, exc)
                checkpoint[sid] = {"status": "failed", "error": str(exc)}
                self._save_checkpoint(checkpoint)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _parse_year_from_text(text: str, start: date, end: date) -> date | None:
    """Extract a 4-digit year from text and return a date if in [start, end]."""
    years = re.findall(r"\b(20\d{2}|19\d{2})\b", text)
    for year_str in years:
        year = int(year_str)
        if start.year <= year <= end.year:
            return date(year, 1, 1)
    return None
