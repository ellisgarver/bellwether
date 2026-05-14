"""Institutional, academic, and policy-analytical ingestors.

Covers the semantic corpus tiers defined in ADR-012 / MND_PROJECT_SPEC (1).md rev3
and config/whitelist.yaml:

  Tier 1 — Institutional policy
    FederalReserveIngestor  fed.py — FOMC, speeches, Beige Book, FEDS Notes
                            NOTE: Fed Chair Jackson Hole speeches are published on
                            federalreserve.gov and captured here — no separate ingestor needed.
    FedRegionalIngestor     Regional Fed blogs and Economic Letters
    CongressionalIngestor   Treasury Secretary testimony (Senate Banking, HFSC)
    IMFIngestor             imf.org — WEO/GFSR/Blog/Working Papers (RCC only)
    BISIngestor             bis.org — Quarterly Review + Working Papers
    TreasuryOFRIngestor     OFR Working Papers and Briefs, FSOC Annual Reports
    CBOIngestor             cbo.gov — Budget/Economic Outlook (may 403 from residential IPs)

  Tier 2 — Academic-analytical
    NBERIngestor            nber.org — WP abstracts (Phase 6 live RSS only; historical blocked)
    VoxEUIngestor           cepr.org/voxeu — full posts
    SSRNIngestor            ssrn.com — abstracts (Phase 6 live RSS only; no historical archive)
    BrookingsIngestor       brookings.edu — macro-filtered articles
    PIIEIngestor            piie.com — policy briefs, working papers, blog posts
    CFRIngestor             cfr.org — reports, backgrounders, expert briefs (macro-filtered)

  InstitutionalIngestor   Composite: runs all active ingestors and merges output.
                          NBER and SSRN are EXCLUDED from historical corpus runs
                          (historical_corpus=false in whitelist.yaml). They run in
                          Phase 6 live RSS updates only.

Removed (ADR-012 / MND_PROJECT_SPEC rev3):
  JacksonHoleIngestor — redundant; Jackson Hole speeches are on federalreserve.gov
                        and captured by FederalReserveIngestor. Separate ingestor
                        created duplicates.
  ArxivIngestor       — cut from scope: 2017-only coverage, low macro volume.
                        Archived at scripts/archive/arxiv_ingestor.py.

Journalism tier (AP News, Reuters, MarketWatch) removed in ADR-010.
Ingestors archived in scripts/archive/.

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
from urllib.parse import urljoin
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
    extra_fields: str = "link,date,title,excerpt,content",
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


def _wp_html_to_text(rendered: str) -> str:
    """Strip HTML tags from a WP REST rendered field. Avoids BS4 filename warning on plain text."""
    if not rendered:
        return ""
    if "<" not in rendered:
        return rendered.strip()
    return BeautifulSoup(rendered, "lxml").get_text(strip=True)


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
    title = _wp_html_to_text(
        title_raw.get("rendered", "") if isinstance(title_raw, dict) else str(title_raw)
    )

    excerpt_raw = post.get("excerpt", {})
    excerpt = _wp_html_to_text(
        excerpt_raw.get("rendered", "") if isinstance(excerpt_raw, dict) else ""
    )

    # Use content.rendered from API if present (avoids per-article page fetch)
    content_raw = post.get("content", {})
    api_content = _wp_html_to_text(
        content_raw.get("rendered", "") if isinstance(content_raw, dict) else ""
    )

    author: str | None = None
    if api_content and len(api_content.split()) >= 50:
        body = api_content
    elif fetch_full_body:
        body, fetched_title, author, _ = _fetch_page_full(url, min_words=50)
        if not body or len(body.split()) < 50:
            body = excerpt
        if fetched_title and not title:
            title = fetched_title
    else:
        body = excerpt

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
    """IMF WEO and GFSR flagship overview pages (2010-present).

    STATUS (2026-05-14): TEMPORARILY DISABLED FOR HISTORICAL CORPUS RUNS.

    All previously-verified IMF URL paths (the hardcoded WEO/GFSR/F&D slugs
    in `_WEO_PATHS` / `_GFSR_PATHS` / `_FANDD_PATHS` below) now 302-redirect
    to the IMF's `/en/errors/404` page — slug IDs have been rotated. The
    publications API endpoint `/api/v1/en/publications` and the RSS endpoints
    (`/en/Blogs/rss`, `/en/feed`, `/external/np/rss/news.aspx`) all return
    the SPA 404 HTML body even with HTTP 200.

    Confirmed 2026-05-14 by direct curl probes from RCC and residential IPs:
    both the hardcoded URLs and the JSON API land on
    `https://www.imf.org/en/errors/404`. The site is fully Next.js SSR and
    there is no static index that links to current publications.

    Until a working retrieval path is identified (likely options:
    Next.js `_next/data/<buildId>/...` SSG endpoint, the homepage
    `__NEXT_DATA__` payload, or accepting Phase-6-only live RSS coverage),
    `InstitutionalIngestor` skips IMF in the historical composite. The class
    is retained so reinstating only requires uncommenting it from the
    sub-ingestors list once a fix lands.

    This is documented as a corpus limitation in the methodology section.
    The lost Tier-1 coverage is partially absorbed by BIS, Fed (FOMC + FEDS
    Notes), and Treasury/OFR, which together provide the bulk of the
    macro-financial institutional discourse signal.
    """

    source_id = "imf"
    # Set to True to opt out of historical runs via composite._sub_ingestors.
    _HISTORICAL_DISABLED = True

    # IMF blocks "MacroNarrativeDynamics/..." UA; plain requests UA returns 200.
    _IMF_HEADERS: dict = {}

    # Verified WEO issue URLs (2010-2024). Older editions use 2016-12-31 as
    # URL date; actual pub date is parsed from the slug title.
    _WEO_PATHS = [
        ("/en/Publications/WEO/Issues/2024/10/22/world-economic-outlook-october-2024-policy-pivot-rising-threats-55033", "2024-10-22"),
        ("/en/Publications/WEO/Issues/2024/04/16/world-economic-outlook-april-2024-steady-but-slow-resilience-amid-divergence-54030", "2024-04-16"),
        ("/en/Publications/WEO/Issues/2023/10/10/world-economic-outlook-october-2023-navigating-global-divergences-53197", "2023-10-10"),
        ("/en/Publications/WEO/Issues/2023/04/11/world-economic-outlook-april-2023-a-rocky-recovery-52317", "2023-04-11"),
        ("/en/Publications/WEO/Issues/2022/10/11/world-economic-outlook-october-2022-countering-the-cost-of-living-crisis-50372", "2022-10-11"),
        ("/en/Publications/WEO/Issues/2022/04/19/world-economic-outlook-april-2022-war-sets-back-the-global-recovery-50501", "2022-04-19"),
        ("/en/Publications/WEO/Issues/2021/10/12/world-economic-outlook-october-2021-recovery-during-a-pandemic-50570", "2021-10-12"),
        ("/en/Publications/WEO/Issues/2021/04/06/world-economic-outlook-april-2021-managing-divergent-recoveries-50219", "2021-04-06"),
        ("/en/Publications/WEO/Issues/2020/10/13/world-economic-outlook-october-2020-a-long-and-difficult-ascent-49722", "2020-10-13"),
        ("/en/Publications/WEO/Issues/2020/04/14/world-economic-outlook-april-2020-the-great-lockdown-49306", "2020-04-14"),
        ("/en/Publications/WEO/Issues/2019/10/15/world-economic-outlook-october-2019-global-manufacturing-downturn-rising-trade-barriers-48306", "2019-10-15"),
        ("/en/Publications/WEO/Issues/2019/04/02/world-economic-outlook-april-2019-growth-slowdown-precarious-recovery-46809", "2019-04-02"),
        ("/en/Publications/WEO/Issues/2018/09/24/world-economic-outlook-october-2018-challenges-to-steady-growth-45540", "2018-09-24"),
        ("/en/Publications/WEO/Issues/2018/04/02/world-economic-outlook-april-2018-cyclical-upswing-structural-change-45119", "2018-04-02"),
        ("/en/Publications/WEO/Issues/2017/09/19/world-economic-outlook-october-2017-seeking-sustainable-growth-short-term-recovery-44594", "2017-09-19"),
        ("/en/Publications/WEO/Issues/2017/04/07/world-economic-outlook-april-2017-gaining-momentum-44464", "2017-04-07"),
        ("/en/Publications/WEO/Issues/2016/10/04/world-economic-outlook-october-2016-subdued-demand-symptoms-and-remedies-44084", "2016-10-04"),
        ("/en/Publications/WEO/Issues/2016/04/06/world-economic-outlook-april-2016-too-slow-for-too-long-43693", "2016-04-06"),
        ("/en/Publications/WEO/Issues/2016/12/31/World-Economic-Outlook-October-2015-Adjusting-to-Lower-Commodity-Prices-43234", "2015-10-01"),
        ("/en/Publications/WEO/Issues/2016/12/31/World-Economic-Outlook-April-2015-Uneven-Growth-Short-and-Long-Term-Factors-43011", "2015-04-01"),
        ("/en/Publications/WEO/Issues/2016/12/31/World-Economic-Outlook-October-2014-Legacies-Clouds-Uncertainties-42082", "2014-10-01"),
        ("/en/Publications/WEO/Issues/2016/12/31/World-Economic-Outlook-April-2014-Recovery-Strengthens-Remains-Uneven-41631", "2014-04-01"),
        ("/en/Publications/WEO/Issues/2016/12/31/World-Economic-Outlook-October-2013-Transitions-and-Tensions-41218", "2013-10-01"),
        ("/en/Publications/WEO/Issues/2016/12/31/World-Economic-Outlook-April-2013-Hopes-Realities-Risks-40834", "2013-04-01"),
        ("/en/Publications/WEO/Issues/2016/12/31/World-Economic-Outlook-October-2012-Coping-with-High-Debt-and-Sluggish-Growth-40557", "2012-10-01"),
        ("/en/Publications/WEO/Issues/2016/12/31/World-Economic-Outlook-April-2012-Growth-Resuming-Dangers-Remain-40210", "2012-04-01"),
        ("/en/Publications/WEO/Issues/2016/12/31/World-Economic-Outlook-September-2011-Slowing-Growth-Rising-Risks-39839", "2011-09-01"),
        ("/en/Publications/WEO/Issues/2016/12/31/World-Economic-Outlook-April-2011-Tensions-from-the-Two-Speed-Recovery-39562", "2011-04-01"),
        ("/en/Publications/WEO/Issues/2016/12/31/World-Economic-Outlook-October-2010-Recovery-Risk-and-Rebalancing-39113", "2010-10-01"),
        ("/en/Publications/WEO/Issues/2016/12/31/World-Economic-Outlook-April-2010-Rebalancing-Growth-40086", "2010-04-01"),
    ]

    # Verified GFSR issue URLs (2010-2024).
    _GFSR_PATHS = [
        ("/en/Publications/GFSR/Issues/2024/10/22/global-financial-stability-report-october-2024-the-great-funding-transformation-55092", "2024-10-22"),
        ("/en/Publications/GFSR/Issues/2024/04/17/global-financial-stability-report-april-2024-the-last-mile-financial-vulnerabilities-54174", "2024-04-17"),
        ("/en/Publications/GFSR/Issues/2023/10/11/global-financial-stability-report-october-2023-financial-and-climate-policies-for-a-high-53510", "2023-10-11"),
        ("/en/Publications/GFSR/Issues/2023/04/05/global-financial-stability-report-april-2023-vulnerabilities-in-a-higher-for-longer-52502", "2023-04-05"),
        ("/en/Publications/GFSR/Issues/2022/10/11/global-financial-stability-report-october-2022-navigating-the-high-inflation-environment-51318", "2022-10-11"),
        ("/en/Publications/GFSR/Issues/2022/04/19/global-financial-stability-report-april-2022-shockwaves-from-the-war-in-ukraine-test-the-50786", "2022-04-19"),
        ("/en/Publications/GFSR/Issues/2021/10/13/global-financial-stability-report-october-2021-covid-19-crypto-and-climate-navigating-50823", "2021-10-13"),
        ("/en/Publications/GFSR/Issues/2021/04/06/global-financial-stability-report-april-2021-preempting-a-legacy-of-vulnerabilities-50057", "2021-04-06"),
        ("/en/Publications/GFSR/Issues/2020/10/13/global-financial-stability-report-october-2020-bridge-to-recovery-49753", "2020-10-13"),
        ("/en/Publications/GFSR/Issues/2020/04/14/global-financial-stability-report-april-2020-markets-in-the-time-of-covid-19-49020", "2020-04-14"),
        ("/en/Publications/GFSR/Issues/2019/10/16/global-financial-stability-report-october-2019-lower-for-longer-48763", "2019-10-16"),
        ("/en/Publications/GFSR/Issues/2019/04/01/global-financial-stability-report-april-2019-vulnerabilities-in-a-maturing-credit-cycle-46843", "2019-04-01"),
        ("/en/Publications/GFSR/Issues/2018/09/26/global-financial-stability-report-october-2018-a-decade-after-the-global-financial-crisis-45710", "2018-09-26"),
        ("/en/Publications/GFSR/Issues/2018/04/02/global-financial-stability-report-april-2018-a-bumpy-road-ahead-45843", "2018-04-02"),
        ("/en/Publications/GFSR/Issues/2017/09/27/global-financial-stability-report-october-2017-is-growth-at-risk-44419", "2017-09-27"),
        ("/en/Publications/GFSR/Issues/2017/04/07/global-financial-stability-report-april-2017-getting-the-policy-mix-right-44501", "2017-04-07"),
        ("/en/Publications/GFSR/Issues/2016/10/05/global-financial-stability-report-october-2016-fostering-stability-in-a-low-growth-low-44018", "2016-10-05"),
        ("/en/Publications/GFSR/Issues/2016/04/11/global-financial-stability-report-april-2016-potent-policies-for-a-successful-43839", "2016-04-11"),
        ("/en/Publications/GFSR/Issues/2016/12/31/Global-Financial-Stability-Report-October-2015-Vulnerabilities-Legacies-and-Policy-43350", "2015-10-01"),
        ("/en/Publications/GFSR/Issues/2016/12/31/Global-Financial-Stability-Report-April-2015-Navigating-Monetary-Policy-Challenges-42120", "2015-04-01"),
        ("/en/Publications/GFSR/Issues/2016/12/31/Global-Financial-Stability-Report-October-2014-Risk-Taking-Liquidity-and-Shadow-Banking-Curbing-Excess-While-Promoting-Growth-41718", "2014-10-01"),
        ("/en/Publications/GFSR/Issues/2016/12/31/Global-Financial-Stability-Report-April-2014-Moving-from-Liquidity-to-Growth-Driven-Markets-41244", "2014-04-01"),
        ("/en/Publications/GFSR/Issues/2016/12/31/Global-Financial-Stability-Report-October-2013-Transitions-Challenges-to-Growth-41167", "2013-10-01"),
        ("/en/Publications/GFSR/Issues/2016/12/31/Global-Financial-Stability-Report-April-2013-Old-Risks-New-Challenges-40768", "2013-04-01"),
        ("/en/Publications/GFSR/Issues/2016/12/31/Global-Financial-Stability-Report-October-2012-Restoring-Confidence-and-Progressing-on-Reforms-40567", "2012-10-01"),
        ("/en/Publications/GFSR/Issues/2016/12/31/Global-Financial-Stability-Report-April-2012-The-Quest-for-Lasting-Stability-40583", "2012-04-01"),
        ("/en/Publications/GFSR/Issues/2016/12/31/Global-Financial-Stability-Report-September-2011-Grappling-with-Crisis-Legacies-39857", "2011-09-01"),
        ("/en/Publications/GFSR/Issues/2016/12/31/Global-Financial-Stability-Report-April-2011-Durable-Financial-Stability-39567", "2011-04-01"),
        ("/en/Publications/GFSR/Issues/2016/12/31/Global-Financial-Stability-Report-October-2010-Sovereigns-Funding-and-Systemic-Liquidity-39107", "2010-10-01"),
        ("/en/Publications/GFSR/Issues/2016/12/31/Global-Financial-Stability-Report-April-2010-Meeting-New-Challenges-to-Stability-and-Building-a-Safer-System-40082", "2010-04-01"),
    ]

    # Finance & Development quarterly magazine (2010–2024).
    # Published March, June, September, December. Paths verified 2026-05-08.
    _FANDD_PATHS = [
        ("/en/Publications/fandd/Issues/2024/12/TABLE-OF-CONTENTS-E1224", "2024-12-01"),
        ("/en/Publications/fandd/Issues/2024/09/TABLE-OF-CONTENTS-E924", "2024-09-01"),
        ("/en/Publications/fandd/Issues/2024/06/TABLE-OF-CONTENTS-E624", "2024-06-01"),
        ("/en/Publications/fandd/Issues/2024/03/TABLE-OF-CONTENTS-E324", "2024-03-01"),
        ("/en/Publications/fandd/Issues/2023/12/TABLE-OF-CONTENTS-E1223", "2023-12-01"),
        ("/en/Publications/fandd/Issues/2023/09/TABLE-OF-CONTENTS-E923", "2023-09-01"),
        ("/en/Publications/fandd/Issues/2023/06/TABLE-OF-CONTENTS-E623", "2023-06-01"),
        ("/en/Publications/fandd/Issues/2023/03/TABLE-OF-CONTENTS-E323", "2023-03-01"),
        ("/en/Publications/fandd/Issues/2022/12/TABLE-OF-CONTENTS-E1222", "2022-12-01"),
        ("/en/Publications/fandd/Issues/2022/09/TABLE-OF-CONTENTS-E922", "2022-09-01"),
        ("/en/Publications/fandd/Issues/2022/06/TABLE-OF-CONTENTS-E622", "2022-06-01"),
        ("/en/Publications/fandd/Issues/2022/03/TABLE-OF-CONTENTS-E322", "2022-03-01"),
        ("/en/Publications/fandd/Issues/2021/12/TABLE-OF-CONTENTS-E1221", "2021-12-01"),
        ("/en/Publications/fandd/Issues/2021/09/TABLE-OF-CONTENTS-E921", "2021-09-01"),
        ("/en/Publications/fandd/Issues/2021/06/TABLE-OF-CONTENTS-E621", "2021-06-01"),
        ("/en/Publications/fandd/Issues/2021/03/TABLE-OF-CONTENTS-E321", "2021-03-01"),
        ("/en/Publications/fandd/Issues/2020/12/TABLE-OF-CONTENTS-E1220", "2020-12-01"),
        ("/en/Publications/fandd/Issues/2020/09/TABLE-OF-CONTENTS-E920", "2020-09-01"),
        ("/en/Publications/fandd/Issues/2020/06/TABLE-OF-CONTENTS-E620", "2020-06-01"),
        ("/en/Publications/fandd/Issues/2020/03/TABLE-OF-CONTENTS-E320", "2020-03-01"),
        ("/en/Publications/fandd/Issues/2019/12/TABLE-OF-CONTENTS-E1219", "2019-12-01"),
        ("/en/Publications/fandd/Issues/2019/09/TABLE-OF-CONTENTS-E919", "2019-09-01"),
        ("/en/Publications/fandd/Issues/2019/06/TABLE-OF-CONTENTS-E619", "2019-06-01"),
        ("/en/Publications/fandd/Issues/2019/03/TABLE-OF-CONTENTS-E319", "2019-03-01"),
        ("/en/Publications/fandd/Issues/2018/12/TABLE-OF-CONTENTS-E1218", "2018-12-01"),
        ("/en/Publications/fandd/Issues/2018/09/TABLE-OF-CONTENTS-E918", "2018-09-01"),
        ("/en/Publications/fandd/Issues/2018/06/TABLE-OF-CONTENTS-E618", "2018-06-01"),
        ("/en/Publications/fandd/Issues/2018/03/TABLE-OF-CONTENTS-E318", "2018-03-01"),
        ("/en/Publications/fandd/Issues/2017/12/TABLE-OF-CONTENTS-E1217", "2017-12-01"),
        ("/en/Publications/fandd/Issues/2017/09/TABLE-OF-CONTENTS-E917", "2017-09-01"),
        ("/en/Publications/fandd/Issues/2017/06/TABLE-OF-CONTENTS-E617", "2017-06-01"),
        ("/en/Publications/fandd/Issues/2017/03/TABLE-OF-CONTENTS-E317", "2017-03-01"),
        ("/en/Publications/fandd/Issues/2016/12/TABLE-OF-CONTENTS-E1216", "2016-12-01"),
        ("/en/Publications/fandd/Issues/2016/09/TABLE-OF-CONTENTS-E916", "2016-09-01"),
        ("/en/Publications/fandd/Issues/2016/06/TABLE-OF-CONTENTS-E616", "2016-06-01"),
        ("/en/Publications/fandd/Issues/2016/03/TABLE-OF-CONTENTS-E316", "2016-03-01"),
        ("/en/Publications/fandd/Issues/2015/12/TABLE-OF-CONTENTS-E1215", "2015-12-01"),
        ("/en/Publications/fandd/Issues/2015/09/TABLE-OF-CONTENTS-E915", "2015-09-01"),
        ("/en/Publications/fandd/Issues/2015/06/TABLE-OF-CONTENTS-E615", "2015-06-01"),
        ("/en/Publications/fandd/Issues/2015/03/TABLE-OF-CONTENTS-E315", "2015-03-01"),
        ("/en/Publications/fandd/Issues/2014/12/TABLE-OF-CONTENTS-E1214", "2014-12-01"),
        ("/en/Publications/fandd/Issues/2014/09/TABLE-OF-CONTENTS-E914", "2014-09-01"),
        ("/en/Publications/fandd/Issues/2014/06/TABLE-OF-CONTENTS-E614", "2014-06-01"),
        ("/en/Publications/fandd/Issues/2014/03/TABLE-OF-CONTENTS-E314", "2014-03-01"),
        ("/en/Publications/fandd/Issues/2013/12/TABLE-OF-CONTENTS-E1213", "2013-12-01"),
        ("/en/Publications/fandd/Issues/2013/09/TABLE-OF-CONTENTS-E913", "2013-09-01"),
        ("/en/Publications/fandd/Issues/2013/06/TABLE-OF-CONTENTS-E613", "2013-06-01"),
        ("/en/Publications/fandd/Issues/2013/03/TABLE-OF-CONTENTS-E313", "2013-03-01"),
        ("/en/Publications/fandd/Issues/2012/12/TABLE-OF-CONTENTS-E1212", "2012-12-01"),
        ("/en/Publications/fandd/Issues/2012/09/TABLE-OF-CONTENTS-E912", "2012-09-01"),
        ("/en/Publications/fandd/Issues/2012/06/TABLE-OF-CONTENTS-E612", "2012-06-01"),
        ("/en/Publications/fandd/Issues/2012/03/TABLE-OF-CONTENTS-E312", "2012-03-01"),
        ("/en/Publications/fandd/Issues/2011/12/TABLE-OF-CONTENTS-E1211", "2011-12-01"),
        ("/en/Publications/fandd/Issues/2011/09/TABLE-OF-CONTENTS-E911", "2011-09-01"),
        ("/en/Publications/fandd/Issues/2011/06/TABLE-OF-CONTENTS-E611", "2011-06-01"),
        ("/en/Publications/fandd/Issues/2011/03/TABLE-OF-CONTENTS-E311", "2011-03-01"),
        ("/en/Publications/fandd/Issues/2010/12/TABLE-OF-CONTENTS-E1210", "2010-12-01"),
        ("/en/Publications/fandd/Issues/2010/09/TABLE-OF-CONTENTS-E910", "2010-09-01"),
        ("/en/Publications/fandd/Issues/2010/06/TABLE-OF-CONTENTS-E610", "2010-06-01"),
        ("/en/Publications/fandd/Issues/2010/03/TABLE-OF-CONTENTS-E310", "2010-03-01"),
    ]

    # IMF Working Papers API endpoint (requires university IP — blocked from residential).
    # Pagination: offset-based, 25 per page, sorted by date descending.
    _WP_API = "https://www.imf.org/api/v1/en/publications"

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        yield from self._fetch_flagships(start, end, self._WEO_PATHS, "weo")
        yield from self._fetch_flagships(start, end, self._GFSR_PATHS, "gfsr")
        yield from self._fetch_flagships(start, end, self._FANDD_PATHS, "fandd")
        yield from self._fetch_working_papers(start, end)

    def _fetch_working_papers(self, start: date, end: date) -> Iterator[Article]:
        """Fetch IMF Working Papers via the publications JSON API.

        Requires university IP (RCC Midway3). Blocked from residential IPs with 403.
        API returns paginated JSON with title, url, date, abstract fields.
        """
        base = "https://www.imf.org"
        offset = 0
        page_size = 25
        seen: set[str] = set()

        while True:
            try:
                resp = requests.get(
                    self._WP_API,
                    params={
                        "type": "WP",
                        "from": start.isoformat(),
                        "to": end.isoformat(),
                        "offset": offset,
                        "limit": page_size,
                        "sort": "date",
                    },
                    headers=self._IMF_HEADERS,
                    timeout=30.0,
                )
                if resp.status_code == 403:
                    log.info(
                        "IMF WP API blocked (HTTP 403) — requires university IP. "
                        "Skipping working papers (will succeed on RCC)."
                    )
                    return
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                log.warning("IMF WP API offset=%d: %s", offset, exc)
                return

            items = data.get("items", data.get("results", data if isinstance(data, list) else []))
            if not items:
                break

            for item in items:
                url_path = item.get("url", "") or item.get("link", "")
                if not url_path:
                    continue
                url = base + url_path if url_path.startswith("/") else url_path
                if url in seen:
                    continue
                seen.add(url)

                title = item.get("title", "IMF Working Paper")
                pub_date_str = item.get("date", item.get("publishedDate", ""))
                try:
                    pub_date = _parse_date_flexible(pub_date_str) or start
                except Exception:
                    pub_date = start
                if pub_date < start or pub_date > end:
                    continue

                # Use abstract from API if present; otherwise fetch page body
                abstract = item.get("abstract", item.get("summary", ""))
                if abstract and len(abstract.split()) >= 50:
                    body = abstract
                else:
                    body = _extract_body(url, min_words=50) or abstract
                if not body or len(body.split()) < 30:
                    continue

                yield _make_article(
                    source_id=self.source_id,
                    url=url,
                    published_at=pub_date.isoformat() + "T00:00:00Z",
                    title=title,
                    body=body,
                    author="IMF",
                    section="working_paper",
                    tier=1,
                    document_type="imf_working_paper",
                )
                time.sleep(0.5)

            offset += page_size
            if len(items) < page_size:
                break
            time.sleep(1.0)

    def _fetch_flagships(
        self, start: date, end: date, path_table: list, doc_type: str
    ) -> Iterator[Article]:
        base = "https://www.imf.org"
        seen: set[str] = set()
        for path, pub_date_str in path_table:
            try:
                pub_date = date.fromisoformat(pub_date_str)
            except ValueError:
                continue
            if pub_date < start or pub_date > end:
                continue
            url = base + path
            if url in seen:
                continue
            seen.add(url)
            try:
                resp = requests.get(url, headers=self._IMF_HEADERS, timeout=20.0)
                resp.raise_for_status()
            except Exception as exc:
                log.debug("IMF %s fetch failed %s: %s", doc_type.upper(), url, exc)
                continue
            body = trafilatura.extract(resp.text, include_comments=False, include_tables=False)
            meta = trafilatura.extract_metadata(resp.text)
            title = (meta.title or "") if meta else ""
            # IMF returns 200+404 HTML for rate-limited or non-existent pages
            if title == "404" or not title:
                log.debug("IMF %s skipping 404 response: %s", doc_type.upper(), url)
                continue
            if not body or len(body.split()) < 50:
                log.debug("IMF %s body too short (%d words): %s", doc_type, len(body.split()) if body else 0, url)
                continue
            yield _make_article(
                source_id=self.source_id,
                url=url,
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

    # OFR publication URL pattern: /working-papers/YYYY/MM/DD/slug or /briefs/YYYY/MM/DD/slug
    _OFR_DATE_RE = re.compile(r"/(?:working-papers|briefs)/(\d{4})/(\d{2})/(\d{2})/")

    def _scrape_ofr_index(
        self, index_url: str, doc_type: str, start: date, end: date
    ) -> Iterator[Article]:
        try:
            resp = _get(index_url)
        except Exception as exc:
            log.warning("OFR index fetch failed %s: %s", index_url, exc)
            return
        soup = BeautifulSoup(resp.text, "lxml")
        seen: set[str] = set()
        for link in soup.find_all("a", href=True):
            href = link["href"]
            m = self._OFR_DATE_RE.search(href)
            if not m:
                continue
            try:
                pub_date = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue
            if pub_date < start or pub_date > end:
                continue
            full_url = urljoin("https://www.financialresearch.gov", href)
            if full_url in seen:
                continue
            seen.add(full_url)
            title = link.get_text(strip=True)
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
        # FSOC Annual Reports are PDF-only — no extractable HTML body.
        # Skip silently; they are documented as a corpus limitation.
        log.debug("FSOC Annual Reports are PDF-only; skipping for text corpus")
        return
        yield  # make this a generator


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
        consecutive_failures = 0

        while True:
            # On timeout, retry up to 3 times then skip the page (do not abort pagination).
            # Non-transient errors (4xx, connection errors beyond retries) abort pagination.
            skip_page = False
            for _attempt in range(3):
                try:
                    resp = requests.get(
                        self._API_URL,
                        params={"page": page, "perPage": self._PER_PAGE},
                        headers=_HEADERS,
                        timeout=60.0,
                    )
                    resp.raise_for_status()
                    consecutive_failures = 0
                    break
                except requests.exceptions.Timeout:
                    log.warning("NBER API page %d timeout (attempt %d/3)", page, _attempt + 1)
                    if _attempt < 2:
                        time.sleep(2 ** _attempt)
                    else:
                        log.warning("NBER API page %d: timed out 3 times, skipping", page)
                        skip_page = True
                except Exception as exc:
                    log.warning("NBER API page %d failed: %s", page, exc)
                    consecutive_failures += 1
                    if consecutive_failures >= 3:
                        log.error("NBER: %d consecutive failures, stopping pagination", consecutive_failures)
                        return
                    break
            if skip_page:
                page += 1
                time.sleep(0.5)
                continue

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

        resp = requests.get(url, headers=_HEADERS, timeout=60.0)
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
                time.sleep(0.5)

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

    Macro-relevance pre-filter uses compound phrases and high-confidence single
    terms. Single words (policy, market, growth, bond, crisis) are excluded
    because they match Brookings content on education, health, and governance.
    """

    source_id = "brookings"

    _API_BASE = "https://www.brookings.edu"

    # Compound phrases and high-signal single terms only.
    # Single words like "policy", "market", "growth", "bond", "crisis",
    # "investment", "trade", "covid", "pandemic" are excluded — too broad for
    # Brookings which covers education, health, governance, and foreign policy.
    _MACRO_TERMS = {
        # High-signal single words
        "inflation", "monetary", "gdp", "recession", "unemployment", "stagflation",
        "macroeconomic", "macrofinancial", "deficit", "surplus",
        # Compound phrases (require exact substring)
        "central bank", "interest rate", "federal reserve", "exchange rate",
        "bond yield", "yield curve", "credit risk", "financial stability",
        "monetary policy", "fiscal policy", "fiscal stimulus", "fiscal cliff",
        "trade deficit", "trade surplus", "current account", "balance of payments",
        "quantitative easing", "forward guidance", "tapering", "taper tantrum",
        "treasury market", "treasury yield", "sovereign debt", "public debt",
        "credit spread", "systemic risk", "financial regulation", "bank capital",
        "stress test", "economic growth", "economic outlook", "economic forecast",
        "labor market", "wage growth", "productivity growth",
        "housing market", "mortgage rate",
        "stock market crash", "equity market", "bond market",
        "global economy", "world economy", "emerging market",
        "financial crisis", "banking crisis", "debt crisis",
        "hutchins center", "hamilton project",
    }

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        seen: set[str] = set()
        for post in _wp_rest_fetch(self._API_BASE, "article", start, end):
            url = post.get("link", "")
            if not url or url in seen:
                continue

            title_raw = post.get("title", {})
            title = _wp_html_to_text(
                title_raw.get("rendered", "") if isinstance(title_raw, dict) else str(title_raw)
            )

            if not self._is_macro_relevant(title):
                continue

            seen.add(url)
            article = _wp_post_to_article(
                post,
                source_id=self.source_id,
                section="brookings_economic_studies",
                tier=2,
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
                    tier=2,
                    document_type=f"piie_{doc_type}",
                    extra_meta={"listing_only": len(body.split()) < 50},
                )
                time.sleep(1.0)

            page += 1
            time.sleep(0.5)


class CFRIngestor(Ingestor):
    """Council on Foreign Relations: RSS-based retrieval.

    CFR publishes reports, backgrounders, and expert briefs on global macro-
    financial topics: dollar dynamics, sovereign debt, global monetary policy,
    trade, and geopolitical-financial intersections. Tier 2 per ADR-010.

    Retrieval: RSS feed (cfr.org/feed) with macro-relevance title filter.
    Historical archive depth is limited by what the feed exposes; the RSS
    practically covers recent items only and will produce thin coverage
    for years before the current rolling window. This is documented in
    methodology as a known coverage asymmetry for CFR specifically.
    """

    source_id = "cfr"

    # Was https://www.cfr.org/rss/all — 404 as of 2026-05-13.
    # CFR consolidated their feeds at /feed.
    _RSS_URL = "https://www.cfr.org/feed"

    _MACRO_TERMS = {
        "inflation", "monetary", "interest rate", "federal reserve", "central bank",
        "exchange rate", "gdp", "recession", "unemployment", "credit", "fiscal",
        "financial", "dollar", "debt", "trade", "currency", "bond", "yield",
        "growth", "economy", "economics", "market", "policy", "capital",
        "banking", "banking crisis", "treasury", "fed", "global economy",
        "emerging market", "imf", "world bank", "g20", "g7",
    }

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        seen: set[str] = set()
        for entry in _parse_rss(self._RSS_URL):
            pub_date = _entry_date(entry)
            if not pub_date or pub_date < start or pub_date > end:
                continue
            url = entry.get("link", "")
            if not url or url in seen:
                continue
            title = entry.get("title", "")
            if not self._is_macro_relevant(title):
                continue
            seen.add(url)

            body = _extract_body(url) or BeautifulSoup(
                entry.get("summary", ""), "lxml"
            ).get_text(strip=True)
            if not body or len(body.split()) < 50:
                continue

            yield _make_article(
                source_id=self.source_id,
                url=url,
                published_at=pub_date.isoformat() + "T00:00:00Z",
                title=title,
                body=body,
                author=entry.get("author"),
                section="cfr_publication",
                tier=2,
                document_type="cfr_brief",
            )
            time.sleep(1.0)

    def _is_macro_relevant(self, title: str) -> bool:
        tl = title.lower()
        return any(term in tl for term in self._MACRO_TERMS)


# ---------------------------------------------------------------------------
# Tier 1 — Congressional testimony
# ---------------------------------------------------------------------------


class CongressionalIngestor(Ingestor):
    """Fed Chair and Treasury Secretary testimony before Congress.

    Scope: Senate Banking Committee and House Financial Services Committee only.
    Approximately 6–10 hearings per year. Fed Chair testimony is available via
    the Federal Reserve's own website (supplementing fed.py which covers FOMC).
    Treasury Secretary testimony is retrieved from the Treasury press release page.

    Note: fed.py's FederalReserveIngestor already ingests Fed Chair testimony
    from federalreserve.gov/testimony. This ingestor fetches Treasury Secretary
    testimony from Treasury.gov, which is not covered elsewhere.

    To avoid duplicating Fed Chair testimony, this ingestor only fetches
    Treasury Secretary testimony. Fed Chair testimony from fed.py's ingestor
    is sufficient for that source.
    """

    source_id = "congressional"

    # Secretary Statements & Remarks listing (Drupal, date-range filterable).
    # Treasury.gov links follow /news/press-releases/sb#### pattern.
    _LISTING_URL = "https://home.treasury.gov/news/press-releases"
    _TREASURY_BASE = "https://home.treasury.gov"

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        seen: set[str] = set()
        yield from self._fetch_treasury_testimony(start, end, seen)

    # Maximum number of listing pages to scan when paginating backward to a
    # historical window. Treasury press releases run ~5–10 per day; 2010-2025
    # covers ~50,000 releases at ~20 per listing page, so 2500 pages is the
    # theoretical worst case. We cap at 600 (≈12,000 releases ≈ 3-4 years of
    # Sec-Statements traffic) to avoid runaway loops on misconfigured calls.
    # Restricting to category=Secretary Statements & Remarks reduces traffic
    # by ~80%, so 600 pages covers well over a decade of testimony.
    _MAX_LISTING_PAGES = 600
    _LISTING_ROW_DATE_RE = re.compile(
        r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
        r"\s+\d{1,2},\s+\d{4}\b"
    )

    def _fetch_treasury_testimony(
        self, start: date, end: date, seen: set[str]
    ) -> Iterator[Article]:
        """Scrape Treasury Secretary Statements & Remarks for testimony items.

        Treasury's Drupal listing IGNORES `date_filter[min]/[max]` query params
        on the server side as of 2026-05 — supplying them returns the standard
        newest-first ordering. To reach a historical window we therefore must
        paginate backward until the rows on a page are older than `start`.

        Per-row dates are present in the listing HTML next to each release
        title (e.g. "May 11, 2026 Economic Fury Ramps Up..."), so we filter
        on those before fetching individual article pages — avoiding one HTTP
        request per out-of-window release.
        """
        consecutive_no_match_pages = 0
        for page in range(self._MAX_LISTING_PAGES):
            params: dict = {"category": "Secretary Statements & Remarks"}
            # The date filter params don't filter server-side, but submitting
            # them is harmless and preserves the intent in the URL.
            params["date_filter[min]"] = start.isoformat()
            params["date_filter[max]"] = end.isoformat()
            if page > 0:
                params["page"] = page
            try:
                resp = requests.get(
                    self._LISTING_URL,
                    params=params,
                    headers=_HEADERS,
                    timeout=30.0,
                )
                if resp.status_code in (403, 404):
                    log.debug("Treasury listing page %d: HTTP %d", page, resp.status_code)
                    return
                resp.raise_for_status()
            except Exception as exc:
                log.warning("Treasury listing page %d: %s", page, exc)
                return

            soup = BeautifulSoup(resp.text, "lxml")
            release_links = [
                a for a in soup.find_all("a", href=True)
                if re.match(r"^/news/press-releases/[a-zA-Z]{2}\d+", a["href"])
                and len(a.get_text(strip=True)) > 15
            ]

            if not release_links:
                log.debug("Treasury listing page %d: no release links — stopping", page)
                break

            # Resolve each link's date from the surrounding listing row.
            rows = [self._extract_row_date(link) for link in release_links]
            valid_dates = [d for d in rows if d is not None]
            oldest = min(valid_dates) if valid_dates else None
            newest = max(valid_dates) if valid_dates else None

            page_matches = 0
            for link, row_date in zip(release_links, rows):
                if row_date is None:
                    continue
                if row_date < start or row_date > end:
                    continue
                href = link["href"]
                url = self._TREASURY_BASE + href
                if url in seen:
                    continue
                title = link.get_text(strip=True)
                if not self._is_relevant(title):
                    continue

                seen.add(url)
                body, fetched_title, author, page_date = _fetch_page_full(url, min_words=30)
                if not body or len(body.split()) < 20:
                    continue
                # Prefer the article-page date (more precise) but fall back to
                # the listing-row date when the page omits it.
                published = page_date or row_date
                if published < start or published > end:
                    continue
                page_matches += 1

                yield _make_article(
                    source_id=self.source_id,
                    url=url,
                    published_at=published.isoformat() + "T00:00:00Z",
                    title=fetched_title or title or "Treasury Secretary Testimony",
                    body=body,
                    author=author,
                    section="treasury_testimony",
                    tier=1,
                    document_type="congressional_testimony",
                )
                time.sleep(1.0)

            # Stop once we've paginated past the requested window.
            if oldest is not None and oldest < start:
                log.info("Treasury listing: reached page %d with oldest date %s < start %s — stopping",
                         page, oldest, start)
                break

            # Safety: if we drift far past the window without finding anything
            # for many pages in a row, bail out instead of grinding to MAX_PAGES.
            if page_matches == 0:
                consecutive_no_match_pages += 1
                # When we're still future-of-window (newest > end), keep paging
                # back. When we're past-of-window (oldest < start) we would
                # have already broken above. The remaining case is "fully
                # inside window but nothing matched relevance filter" — give
                # it 50 pages of slack before giving up.
                if (newest is not None and newest <= end
                        and consecutive_no_match_pages >= 50):
                    log.info("Treasury listing: 50 consecutive in-window pages with no "
                             "relevant matches at page %d — stopping early", page)
                    break
            else:
                consecutive_no_match_pages = 0

            # Defer to Drupal's own "next page" link as the canonical stop
            # signal if present.
            next_link = soup.select_one("a[title='Next page'], .pager__item--next a")
            if not next_link:
                log.debug("Treasury listing page %d: no next page — stopping", page)
                break
            time.sleep(0.5)
        else:
            log.warning("Treasury listing: hit MAX_LISTING_PAGES=%d before crossing start=%s",
                        self._MAX_LISTING_PAGES, start)

    def _extract_row_date(self, link) -> date | None:
        """Find the date string nearest to a release link in the listing HTML.

        Listing rows look like:
            <some container>
              <time/date span> May 11, 2026 </>
              <a href="/news/press-releases/sb0498"> Title... </a>
            </>
        We walk up at most 4 ancestors looking for a Month D, YYYY string,
        which is the per-row date Treasury renders.
        """
        node = link
        for _ in range(4):
            node = node.parent if node else None
            if node is None:
                break
            text = node.get_text(" ", strip=True)
            m = self._LISTING_ROW_DATE_RE.search(text)
            if m:
                parsed = _parse_date_flexible(m.group(0))
                if parsed:
                    return parsed
        return None

    def _is_relevant(self, title: str) -> bool:
        """Keep Secretary-level testimony, congressional statements, and the
        broader macro-relevant secretary remarks (FOMC events, fiscal/debt,
        confirmation hearings, Treasury-led economic conferences).

        Treasury's Secretary Statements & Remarks category mixes congressional
        testimony with conference remarks. We previously matched only the
        narrow testimony vocabulary; the broader filter below keeps the
        narrative-relevant content while still excluding pure sanctions
        announcements and lower-level official press releases.
        """
        tl = title.lower()
        # Exclude lower-level officials — Tier-1 ingestion is Secretary-level
        if re.search(r"\bunder ?secretary\b|\bassistant secretary\b|\bdeputy\b", tl):
            return False
        # Exclude pure sanctions announcements ("Treasury Sanctions...")
        # which are policy actions, not narrative-formation discourse.
        if re.search(r"\btreasury sanctions\b|\beconomic fury\b", tl):
            return False
        relevant_terms = (
            # Testimony / congressional appearances
            "testimony", "before the", "subcommittee", "senate banking",
            "house financial services", "appropriations", "ways and means",
            "joint economic committee", "committee on finance",
            # Secretary remarks of macro relevance
            "remarks by", "statement by", "secretary",
            "monetary policy", "inflation", "fiscal", "debt", "economy",
            "economic outlook", "treasury market", "financial stability",
        )
        return any(term in tl for term in relevant_terms)


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
            CongressionalIngestor(),
            # IMFIngestor disabled for historical runs as of 2026-05-14:
            # all hardcoded URLs and API endpoints land on /en/errors/404.
            # See IMFIngestor docstring for diagnostic notes. Reinstate once
            # a working retrieval path (Next.js _next/data SSG or homepage
            # __NEXT_DATA__ scrape) is implemented.
            # IMFIngestor(),
            BISIngestor(),
            TreasuryOFRIngestor(),
            CBOIngestor(),
            # NBER and SSRN excluded from historical corpus runs (historical_corpus=false).
            # Uncomment for Phase 6 live RSS updates only:
            # NBERIngestor(),
            # SSRNIngestor(),
            VoxEUIngestor(),
            BrookingsIngestor(),
            PIIEIngestor(),
            CFRIngestor(),
        ]

    def _load_checkpoint(self) -> dict:
        if self._checkpoint_path and self._checkpoint_path.exists():
            try:
                data = json.loads(self._checkpoint_path.read_text())
            except Exception as exc:
                log.warning("Could not load checkpoint %s: %s — starting fresh", self._checkpoint_path, exc)
                return {}
            # Detect false-completed entries (status=completed, count=0) written by
            # the pre-fix bug that treated 0-article fetches as successful completions.
            false_completions = [
                sid for sid, v in data.items()
                if v.get("status") == "completed" and v.get("count", 0) == 0
            ]
            if false_completions:
                genuine_completions = [
                    sid for sid, v in data.items()
                    if v.get("status") == "completed" and v.get("count", 0) > 0
                ]
                if not genuine_completions:
                    # Entire checkpoint is zero-article completions — nothing was ever
                    # successfully fetched. Delete and start completely fresh.
                    log.warning(
                        "Checkpoint %s has no successful fetches (all count=0); deleting and starting fresh",
                        self._checkpoint_path,
                    )
                    self._checkpoint_path.unlink()
                    return {}
                # Some sources genuinely completed; only reset the false ones.
                log.warning(
                    "Checkpoint has %d false-completed sources (count=0): %s — marking failed for retry",
                    len(false_completions), ", ".join(false_completions),
                )
                for sid in false_completions:
                    data[sid] = {"status": "failed", "error": "0 articles on previous run (false completion)"}
                self._save_checkpoint(data)
            return data
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
                if count > 0:
                    checkpoint[sid] = {"status": "completed", "count": count}
                    self._save_checkpoint(checkpoint)
                    log.info("Checkpoint: %s completed (%d articles)", sid, count)
                else:
                    checkpoint[sid] = {"status": "failed", "error": "returned 0 articles"}
                    self._save_checkpoint(checkpoint)
                    log.warning("Checkpoint: %s returned 0 articles; marked failed for retry", sid)
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
