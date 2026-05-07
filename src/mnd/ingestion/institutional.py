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
import time
from datetime import date, datetime
from pathlib import Path
from typing import Iterator
from urllib.parse import urljoin, urlparse

import feedparser
import requests
import trafilatura
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_random_exponential

from mnd.ingestion.base import Article, Ingestor, _now_utc_iso, _stable_article_id
from mnd.ingestion.fed import FederalReserveIngestor
from mnd.utils.logging import get_logger

log = get_logger(__name__)

USER_AGENT = "MacroNarrativeDynamics/0.1 (academic research; contact via project repo)"
_HEADERS = {"User-Agent": USER_AGENT}

# JEL codes that indicate macro/finance relevance for NBER filtering
_NBER_JEL_PREFIXES = ("E", "F", "G")


@retry(stop=stop_after_attempt(5), wait=wait_random_exponential(multiplier=1, max=30))
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
    """BIS: Quarterly Review, Annual Report, and Working Papers via RSS."""

    source_id = "bis"

    _RSS_URL = "https://www.bis.org/doclist/bis_rss.rss"

    # Document type keywords to keep; others (e.g. payment stats) are out of scope
    _KEEP_TYPES = {"speech", "working paper", "quarterly review", "annual report", "research"}

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        for entry in _parse_rss(self._RSS_URL):
            pub_date = _entry_date(entry)
            if not pub_date or pub_date < start or pub_date > end:
                continue
            url = entry.get("link", "")
            if not url:
                continue
            title = entry.get("title", "BIS publication")
            # BIS RSS tags document type in the <category> element
            tags = [t.get("term", "").lower() for t in getattr(entry, "tags", [])]
            doc_type_raw = " ".join(tags)
            if not any(kw in doc_type_raw for kw in self._KEEP_TYPES):
                # No matching category — be permissive for BIS (small volume)
                pass
            summary = entry.get("summary", "")
            body = _extract_body(url) or summary
            if not body or len(body.split()) < 50:
                continue
            yield _make_article(
                source_id=self.source_id,
                url=url,
                published_at=pub_date.isoformat() + "T00:00:00Z",
                title=title,
                body=body,
                author=entry.get("author"),
                section=doc_type_raw or "publication",
                tier=1,
                document_type=doc_type_raw or "publication",
            )
            time.sleep(0.5)


class FedRegionalIngestor(Ingestor):
    """Regional Fed publication blogs via RSS.

    Covers: Liberty Street Economics (NY Fed), FRBSF Economic Letter,
    Chicago Fed Letter, Atlanta Fed macroblog.

    The main FederalReserveIngestor (fed.py) covers Board communications.
    This ingestor captures the analytical research-blog content from regional banks.
    """

    source_id = "fed_regional"

    _FEEDS: list[tuple[str, str, str, str]] = [
        # (feed_url, sub_source_id, section, tier1_note)
        (
            "https://libertystreeteconomics.newyorkfed.org/feed/",
            "fed_ny",
            "liberty_street_economics",
            "New York Fed Liberty Street Economics",
        ),
        (
            "https://www.frbsf.org/economic-research/publications/economic-letter/feed/",
            "fed_sf",
            "frbsf_economic_letter",
            "San Francisco Fed Economic Letter",
        ),
        (
            "https://www.chicagofed.org/publications/chicago-fed-letter/rss",
            "fed_chicago",
            "chicago_fed_letter",
            "Chicago Fed Letter",
        ),
        (
            "https://www.atlantafed.org/blogs/macroblog/rss",
            "fed_atlanta",
            "macroblog",
            "Atlanta Fed macroblog",
        ),
    ]

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        for feed_url, sub_id, section, label in self._FEEDS:
            yield from self._fetch_one(feed_url, sub_id, section, label, start, end)

    def _fetch_one(
        self,
        feed_url: str,
        sub_id: str,
        section: str,
        label: str,
        start: date,
        end: date,
    ) -> Iterator[Article]:
        for entry in _parse_rss(feed_url):
            pub_date = _entry_date(entry)
            if not pub_date or pub_date < start or pub_date > end:
                continue
            url = entry.get("link", "")
            if not url:
                continue
            title = entry.get("title", label + " post")
            summary = entry.get("summary", "")
            body = _extract_body(url) or summary
            if not body or len(body.split()) < 50:
                continue
            yield _make_article(
                source_id=sub_id,
                url=url,
                published_at=pub_date.isoformat() + "T00:00:00Z",
                title=title,
                body=body,
                author=entry.get("author"),
                section=section,
                tier=1,
                document_type="fed_regional_research",
                extra_meta={"feed_label": label},
            )
            time.sleep(0.3)


class CBOIngestor(Ingestor):
    """Congressional Budget Office publications via RSS.

    Focuses on Budget Outlook, Economic Outlook, and Working Papers.
    """

    source_id = "cbo"

    _RSS_URL = "https://www.cbo.gov/publication/rss"

    _KEEP_TYPES = {
        "budget and economic outlook",
        "economic outlook",
        "working paper",
        "budget",
        "long-term budget",
        "monthly budget review",
    }

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        for entry in _parse_rss(self._RSS_URL):
            pub_date = _entry_date(entry)
            if not pub_date or pub_date < start or pub_date > end:
                continue
            url = entry.get("link", "")
            if not url:
                continue
            title = entry.get("title", "CBO publication")
            # Filter to macro-relevant document types
            tags = [t.get("term", "").lower() for t in getattr(entry, "tags", [])]
            if self._KEEP_TYPES and not any(
                any(kw in tag for kw in self._KEEP_TYPES) for tag in tags
            ):
                if not any(kw in title.lower() for kw in self._KEEP_TYPES):
                    continue
            summary = entry.get("summary", "")
            body = _extract_body(url) or summary
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
    """

    source_id = "ssrn_finance"

    # SSRN eJournal RSS for Financial Economics Network
    _FEEDS = [
        "https://papers.ssrn.com/sol3/Jrnls/jrnl.cfm?link=2",  # Financial Economics
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
    """VoxEU / CEPR full posts via RSS. Feed goes back to 2007.

    All VoxEU columns are open access. Full text extracted via trafilatura.
    """

    source_id = "voxeu"

    _RSS_URL = "https://cepr.org/voxeu/rss.xml"

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        for entry in _parse_rss(self._RSS_URL):
            pub_date = _entry_date(entry)
            if not pub_date or pub_date < start or pub_date > end:
                continue
            url = entry.get("link", "")
            if not url:
                continue
            title = entry.get("title", "VoxEU column")
            body = _extract_body(url) or BeautifulSoup(entry.get("summary", ""), "lxml").get_text(strip=True)
            if not body or len(body.split()) < 50:
                continue
            yield _make_article(
                source_id=self.source_id,
                url=url,
                published_at=pub_date.isoformat() + "T00:00:00Z",
                title=title,
                body=body,
                author=entry.get("author"),
                section="voxeu_column",
                tier=2,
                document_type="voxeu_column",
            )
            time.sleep(0.3)


# ---------------------------------------------------------------------------
# Tier 3 — Policy-journalism bridge
# ---------------------------------------------------------------------------


class BrookingsIngestor(Ingestor):
    """Brookings Institution Economic Studies posts via RSS."""

    source_id = "brookings"

    _FEEDS = [
        "https://www.brookings.edu/topic/economic-studies/feed/",
        "https://www.brookings.edu/topic/economy/feed/",
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
                title = entry.get("title", "Brookings post")
                body = _extract_body(url) or BeautifulSoup(entry.get("summary", ""), "lxml").get_text(strip=True)
                if not body or len(body.split()) < 50:
                    continue
                yield _make_article(
                    source_id=self.source_id,
                    url=url,
                    published_at=pub_date.isoformat() + "T00:00:00Z",
                    title=title,
                    body=body,
                    author=entry.get("author"),
                    section="brookings_economic_studies",
                    tier=3,
                    document_type="brookings_post",
                )
                time.sleep(0.3)


class PIIEIngestor(Ingestor):
    """Peterson Institute for International Economics full posts via RSS."""

    source_id = "piie"

    _RSS_URL = "https://www.piie.com/rss/all"

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        for entry in _parse_rss(self._RSS_URL):
            pub_date = _entry_date(entry)
            if not pub_date or pub_date < start or pub_date > end:
                continue
            url = entry.get("link", "")
            if not url:
                continue
            title = entry.get("title", "PIIE post")
            body = _extract_body(url) or BeautifulSoup(entry.get("summary", ""), "lxml").get_text(strip=True)
            if not body or len(body.split()) < 50:
                continue
            yield _make_article(
                source_id=self.source_id,
                url=url,
                published_at=pub_date.isoformat() + "T00:00:00Z",
                title=title,
                body=body,
                author=entry.get("author"),
                section="piie_publication",
                tier=3,
                document_type="piie_post",
            )
            time.sleep(0.3)


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
    import re
    years = re.findall(r"\b(20\d{2}|19\d{2})\b", text)
    for year_str in years:
        year = int(year_str)
        if start.year <= year <= end.year:
            return date(year, 1, 1)
    return None
