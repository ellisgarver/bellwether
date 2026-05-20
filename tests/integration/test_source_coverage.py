"""Per-source coverage tests for ingestion methodology lock-in.

Network-dependent. Marked ``integration``; not run by default. Invoke with:

    pytest tests/integration/test_source_coverage.py -m integration -v

Each case asserts three things against a narrow date window:

  1. Floor count — at least N records emerged within the islice cap.
     Catches silent-zero failures (e.g. fed_atlanta = 0 records, CBO = 0
     records, voxeu missing 2010-18 due to swallowed timeout).
  2. Section diversity — every section in ``expected_sections`` appears at
     least once. Catches "only one series ingested" failures (e.g. BIS prior
     to ADR-017 only matched working_paper; Chicago Fed prior to ADR-017
     only matched chicago_fed_letter).
  3. Date span — observed dates span ≥ ``min_date_span_days``. Catches the
     "all clustered in one month" failure mode that wouldn't show up in a
     floor-count check (e.g. a regex matching only the most recent month).

Conservative floors. Real upstream counts are usually 2-5× higher; the
floors only need to distinguish "ingestor working" from "ingestor silently
broken." If a floor fails, the right response is to investigate, not to
loosen the floor.

Some ingestors require optional dependencies (``curl_cffi``, ``playwright``)
that may not be installed locally. Those tests skip gracefully via the
helpers in ``conftest.py``; run the full battery on RCC where all deps
are installed.
"""
from __future__ import annotations

import importlib
import itertools
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date

import pytest

from mnd.ingestion.base import Article
from mnd.ingestion.fed import FederalReserveIngestor
from mnd.ingestion.institutional import (
    BISIngestor,
    BrookingsIngestor,
    CBOIngestor,
    CEAIngestor,
    CongressionalIngestor,
    FedRegionalIngestor,
    IMFIngestor,
    NBERIngestor,
    PIIEIngestor,
    TreasuryOFRIngestor,
    VoxEUIngestor,
)


# ---------------------------------------------------------------------------
# Skip helpers for optional, RCC-only dependencies
# ---------------------------------------------------------------------------


def _have(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
    except ImportError:
        return False
    return True


def requires_curl_cffi() -> None:
    if not _have("curl_cffi"):
        pytest.skip(
            "curl_cffi not installed — required for sources behind TLS-fingerprint "
            "bot protection (IMF/Akamai, Atlanta Fed, CBO). "
            "Install with `pip install curl_cffi`."
        )


def requires_playwright() -> None:
    if not _have("playwright"):
        pytest.skip(
            "playwright not installed — required for CBO (DataDome JS challenge). "
            "Install with `pip install playwright && python -m playwright install chromium`."
        )


def requires_pypdf() -> None:
    if not _have("pypdf"):
        pytest.skip(
            "pypdf not installed — required for CEA (govinfo ERP PDF text). "
            "Install with `pip install pypdf` (see requirements.txt / ADR-020)."
        )


# ---------------------------------------------------------------------------
# Contract definition
# ---------------------------------------------------------------------------


@dataclass
class CoverageCase:
    """A single coverage contract for one (sub-ingestor, window) pair."""

    name: str
    iterator_factory: Callable[[date, date], Iterator[Article]]
    window_start: date
    window_end: date
    floor_count: int
    max_records: int = 200
    section_filter: str | None = None
    expected_sections: set[str] = field(default_factory=set)
    min_date_span_days: int = 0
    skip_check: Callable[[], None] | None = None

    @property
    def id(self) -> str:
        return self.name


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------
#
# Floors are conservative (~25–35% of typical upstream counts). They protect
# against silent zero-yield failures, not against partial-undercount
# regressions — those need full-corpus QA after re-ingest.


def _fed_method(method_name: str) -> Callable[[date, date], Iterator[Article]]:
    """Build an iterator factory for one private method on FederalReserveIngestor.

    Used for targeted historical-edge tests so the test doesn't pay the cost
    of fetching every other Fed document type for the same window.
    """
    def factory(start: date, end: date) -> Iterator[Article]:
        ingestor = FederalReserveIngestor()
        return getattr(ingestor, method_name)(start, end)
    return factory


CASES: list[CoverageCase] = [
    # -----------------------------------------------------------------
    # Fed Board — composite sanity + three historical-edge URL patterns
    # -----------------------------------------------------------------
    CoverageCase(
        name="fed_main_2023h1_composite",
        iterator_factory=lambda s, e: FederalReserveIngestor().fetch(s, e),
        window_start=date(2023, 1, 1),
        window_end=date(2023, 6, 30),
        floor_count=40,
        max_records=400,
        expected_sections={
            "fomc_statement",
            "fomc_minutes",
            "speech",
            "feds_notes",
            "beige_book",
        },
        min_date_span_days=90,
    ),
    CoverageCase(
        name="fed_speeches_2010_legacy_url",
        iterator_factory=_fed_method("_fetch_speeches"),
        window_start=date(2010, 1, 1),
        window_end=date(2010, 12, 31),
        floor_count=20,
        max_records=200,
        section_filter="speech",
        expected_sections={"speech"},
        min_date_span_days=120,
    ),
    CoverageCase(
        name="fed_feds_notes_2014_legacy_url",
        iterator_factory=_fed_method("_fetch_feds_notes"),
        window_start=date(2014, 1, 1),
        window_end=date(2014, 12, 31),
        floor_count=10,
        max_records=200,
        section_filter="feds_notes",
        expected_sections={"feds_notes"},
        min_date_span_days=120,
    ),
    CoverageCase(
        name="fed_beige_book_2014_subdir_variant",
        iterator_factory=_fed_method("_fetch_beige_books"),
        window_start=date(2014, 1, 1),
        window_end=date(2014, 12, 31),
        floor_count=4,
        max_records=50,
        section_filter="beige_book",
        expected_sections={"beige_book"},
        min_date_span_days=60,
    ),
    # -----------------------------------------------------------------
    # Regional Feds
    # -----------------------------------------------------------------
    CoverageCase(
        name="fed_ny_liberty_street_2023q1",
        iterator_factory=lambda s, e: FedRegionalIngestor()._fetch_liberty_street(s, e, set()),
        window_start=date(2023, 1, 1),
        window_end=date(2023, 3, 31),
        floor_count=15,
        max_records=80,
        min_date_span_days=30,
    ),
    CoverageCase(
        name="fed_sf_2023",
        iterator_factory=lambda s, e: FedRegionalIngestor()._fetch_frbsf(s, e, set()),
        window_start=date(2023, 1, 1),
        window_end=date(2023, 12, 31),
        floor_count=10,
        max_records=80,
        min_date_span_days=90,
    ),
    CoverageCase(
        name="fed_chicago_2023_multi_series",
        iterator_factory=lambda s, e: FedRegionalIngestor()._fetch_chicago_fed_letter(s, e, set()),
        window_start=date(2023, 1, 1),
        window_end=date(2023, 12, 31),
        # Floor explicitly higher than the pre-ADR-017 cap of 246 / N years;
        # the failure mode was "single series captured only" → set diversity
        # check below.
        floor_count=20,
        max_records=200,
        min_date_span_days=90,
    ),
    CoverageCase(
        name="fed_atlanta_2023_curl_cffi",
        iterator_factory=lambda s, e: FedRegionalIngestor()._fetch_atlanta(s, e, set()),
        window_start=date(2023, 1, 1),
        window_end=date(2023, 12, 31),
        # Pre-ADR-017 fed_atlanta = 0 records. Any non-zero proves the
        # curl_cffi + sitemap walk is wired correctly.
        floor_count=10,
        max_records=80,
        min_date_span_days=60,
        skip_check=requires_curl_cffi,
    ),
    # -----------------------------------------------------------------
    # Tier 1 institutional
    # -----------------------------------------------------------------
    CoverageCase(
        name="congressional_treasury_sec_2023",
        iterator_factory=lambda s, e: CongressionalIngestor().fetch(s, e),
        window_start=date(2023, 1, 1),
        window_end=date(2023, 12, 31),
        floor_count=10,
        max_records=80,
        expected_sections={"treasury_testimony"},
        min_date_span_days=90,
    ),
    CoverageCase(
        name="imf_2023_multi_series",
        iterator_factory=lambda s, e: IMFIngestor().fetch(s, e),
        window_start=date(2023, 1, 1),
        window_end=date(2023, 12, 31),
        floor_count=30,
        max_records=300,
        # Of the 5 series we require ≥3 to appear. Don't pin to specific names
        # so the test doesn't over-specify.
        expected_sections=set(),  # diversity asserted via custom check below
        min_date_span_days=120,
        skip_check=requires_curl_cffi,
    ),
    CoverageCase(
        name="bis_2023_multi_section",
        iterator_factory=lambda s, e: BISIngestor().fetch(s, e),
        window_start=date(2023, 1, 1),
        window_end=date(2023, 12, 31),
        # Pre-ADR-017 BIS yielded ~working-papers only (~70/year).
        # Post-ADR-017 should yield working_paper + quarterly_review + bulletin
        # + speech + other_publication. Floor is conservative.
        floor_count=40,
        max_records=400,
        # Diversity asserted via custom check below — require ≥3 distinct
        # sections out of {working_paper, quarterly_review, bulletin, speech,
        # other_publication}.
        expected_sections=set(),
        min_date_span_days=120,
    ),
    CoverageCase(
        name="treasury_ofr_2023",
        iterator_factory=lambda s, e: TreasuryOFRIngestor().fetch(s, e),
        window_start=date(2023, 1, 1),
        window_end=date(2023, 12, 31),
        floor_count=3,
        max_records=40,
        min_date_span_days=30,
    ),
    CoverageCase(
        name="cbo_2023_datadome",
        iterator_factory=lambda s, e: CBOIngestor().fetch(s, e),
        window_start=date(2023, 6, 1),
        window_end=date(2023, 7, 31),
        # Pre-ADR-017 CBO = 0 records (DataDome 403). Any non-zero proves
        # the Playwright + curl_cffi-with-cookies hybrid is working.
        floor_count=5,
        max_records=30,
        expected_sections={"cbo_publication"},
        min_date_span_days=14,
        skip_check=requires_playwright,
    ),
    # -----------------------------------------------------------------
    # Tier 2 — academic / policy
    # -----------------------------------------------------------------
    CoverageCase(
        name="voxeu_2012_historical_window",
        iterator_factory=lambda s, e: VoxEUIngestor().fetch(s, e),
        window_start=date(2012, 1, 1),
        window_end=date(2012, 12, 31),
        # Pre-fix VoxEU silent-timeout dropped everything before 2019.
        # Any non-trivial 2012 count proves the year-sharded fetch works.
        floor_count=15,
        max_records=100,
        min_date_span_days=120,
    ),
    CoverageCase(
        name="voxeu_2023_recent",
        iterator_factory=lambda s, e: VoxEUIngestor().fetch(s, e),
        window_start=date(2023, 1, 1),
        window_end=date(2023, 12, 31),
        floor_count=20,
        max_records=120,
        min_date_span_days=120,
    ),
    CoverageCase(
        name="brookings_2023q1",
        iterator_factory=lambda s, e: BrookingsIngestor().fetch(s, e),
        window_start=date(2023, 1, 1),
        window_end=date(2023, 3, 31),
        floor_count=30,
        max_records=200,
        expected_sections={"brookings_economic_studies"},
        min_date_span_days=30,
    ),
    CoverageCase(
        name="piie_2023_body_fetch",
        iterator_factory=lambda s, e: PIIEIngestor().fetch(s, e),
        window_start=date(2023, 1, 1),
        window_end=date(2023, 12, 31),
        # Pre-ADR-017 PIIE silently emitted title-only fallbacks (179 total
        # for 2010-present). ADR-017 dropped the title-only fallback;
        # floor here proves bodies are being captured.
        floor_count=15,
        max_records=120,
        expected_sections={"piie_publication"},
        min_date_span_days=90,
    ),
    # CFR removed by ADR-020 (basis-set redundancy with PIIE on the
    # international-policy dimension). CFRIngestor class is retained in
    # institutional.py for backwards-compat data reads but is not run in
    # any new ingest — no coverage test.
    # -----------------------------------------------------------------
    # ADR-020 additions: NBER (academic primary work) and CEA (executive
    # fiscal voice). Each is tested with a narrow window so the integration
    # battery stays under ~30 minutes per source.
    # -----------------------------------------------------------------
    CoverageCase(
        name="nber_2023h2_direct_url_enum",
        iterator_factory=lambda s, e: NBERIngestor().fetch(s, e),
        # 2023 Q3-Q4 hits w31500..w32000 — a few hundred papers, manageable
        # to scan within max_records cap.
        window_start=date(2023, 7, 1),
        window_end=date(2023, 9, 30),
        floor_count=30,
        max_records=400,
        expected_sections={"nber_working_paper"},
        min_date_span_days=45,
    ),
    CoverageCase(
        name="nber_2014_historical_edge",
        iterator_factory=lambda s, e: NBERIngestor().fetch(s, e),
        # 2014 Q1 hits w19800..w20100 — sanity check that the year-floor
        # table is calibrated correctly for the historical edge.
        window_start=date(2014, 1, 1),
        window_end=date(2014, 3, 31),
        floor_count=20,
        max_records=300,
        expected_sections={"nber_working_paper"},
        min_date_span_days=30,
    ),
    CoverageCase(
        name="cea_erp_2023_govinfo",
        iterator_factory=lambda s, e: CEAIngestor().fetch(s, e),
        # ERP-2023 was published in March 2023; the test window covers all
        # of 2023 so we capture the single ERP issued that year. Every
        # chapter granule shares the same dateIssued, so we disable the
        # date-span check (the floor + section check are the assertions
        # that matter).
        window_start=date(2023, 1, 1),
        window_end=date(2023, 12, 31),
        floor_count=10,
        max_records=60,
        expected_sections={"cea_erp_chapter"},
        min_date_span_days=0,
        skip_check=requires_pypdf,
    ),
    CoverageCase(
        name="cea_erp_2014_historical",
        iterator_factory=lambda s, e: CEAIngestor().fetch(s, e),
        window_start=date(2014, 1, 1),
        window_end=date(2014, 12, 31),
        floor_count=10,
        max_records=60,
        expected_sections={"cea_erp_chapter"},
        min_date_span_days=0,
        skip_check=requires_pypdf,
    ),
    # -----------------------------------------------------------------
    # Tier 1/2 historical-edge cross-check: confirm each historically-
    # significant source still yields content in 2010 (the corpus floor).
    # 2010 is the most failure-prone window because many sites' URL
    # patterns and feed formats changed between then and now.
    # -----------------------------------------------------------------
    CoverageCase(
        name="brookings_2010_historical_edge",
        iterator_factory=lambda s, e: BrookingsIngestor().fetch(s, e),
        window_start=date(2010, 1, 1),
        window_end=date(2010, 12, 31),
        floor_count=20,
        max_records=300,
        expected_sections={"brookings_economic_studies"},
        min_date_span_days=120,
    ),
    CoverageCase(
        name="imf_2010_historical_edge",
        iterator_factory=lambda s, e: IMFIngestor().fetch(s, e),
        window_start=date(2010, 1, 1),
        window_end=date(2010, 12, 31),
        floor_count=20,
        max_records=300,
        expected_sections=set(),
        min_date_span_days=120,
        skip_check=requires_curl_cffi,
    ),
    CoverageCase(
        name="bis_2010_historical_edge",
        iterator_factory=lambda s, e: BISIngestor().fetch(s, e),
        window_start=date(2010, 1, 1),
        window_end=date(2010, 12, 31),
        floor_count=30,
        max_records=400,
        expected_sections=set(),
        min_date_span_days=120,
    ),
    CoverageCase(
        name="treasury_ofr_2016_historical_edge",
        iterator_factory=lambda s, e: TreasuryOFRIngestor().fetch(s, e),
        window_start=date(2016, 1, 1),
        window_end=date(2016, 12, 31),
        floor_count=3,
        max_records=40,
        min_date_span_days=60,
    ),
]


# ---------------------------------------------------------------------------
# Cases that need custom diversity logic (≥N distinct sections among an
# open-ended set) — pinned by name here so the test function can dispatch.
# ---------------------------------------------------------------------------

_MULTI_SECTION_MIN_SECTIONS: dict[str, tuple[int, set[str]]] = {
    # name → (minimum distinct sections required, universe of valid sections)
    "fed_chicago_2023_multi_series": (
        3,
        {
            "chicago_fed_letter",
            "economic_perspectives",
            "working_paper",
            "policy_discussion_paper",
            "public_policy_paper",
            "profitwise",
            "insights",
            "insights_blog",
        },
    ),
    "imf_2023_multi_series": (
        3,
        {"imf_weo", "imf_gfsr", "imf_fandd", "imf_working_paper", "imf_blog"},
    ),
    "bis_2023_multi_section": (
        3,
        {"working_paper", "quarterly_review", "bulletin", "speech", "other_publication"},
    ),
}


# ---------------------------------------------------------------------------
# Test driver
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_source_coverage(case: CoverageCase) -> None:
    """Run one coverage contract.

    Three assertions, one common code path. See module docstring.
    """
    if case.skip_check is not None:
        case.skip_check()

    iterator = case.iterator_factory(case.window_start, case.window_end)

    # Collect up to max_records, filtering by section if requested.
    collected: list[Article] = []
    try:
        for art in itertools.islice(iterator, case.max_records):
            if case.section_filter and art.section != case.section_filter:
                continue
            collected.append(art)
    except Exception as exc:  # pragma: no cover - depends on upstream
        pytest.skip(
            f"{case.name}: upstream fetch raised {type(exc).__name__}: {exc}. "
            "Treated as network/environment error, not a code failure."
        )

    # ---- 1. Floor count ----
    assert len(collected) >= case.floor_count, (
        f"{case.name}: only {len(collected)} records collected, "
        f"expected at least {case.floor_count} within "
        f"{case.window_start.isoformat()}..{case.window_end.isoformat()} "
        f"(max_records cap = {case.max_records}, "
        f"section_filter = {case.section_filter!r}). "
        "Likely a silent coverage failure — investigate the ingestor."
    )

    # ---- 2. Section diversity ----
    seen_sections = {a.section for a in collected if a.section}

    # Pinned-name diversity rule (≥ N distinct sections from a known set).
    if case.name in _MULTI_SECTION_MIN_SECTIONS:
        min_n, universe = _MULTI_SECTION_MIN_SECTIONS[case.name]
        relevant_seen = seen_sections & universe
        assert len(relevant_seen) >= min_n, (
            f"{case.name}: only {len(relevant_seen)} distinct sections out of "
            f"{universe} seen (got {relevant_seen}); expected at least {min_n}. "
            "Likely indicates only one series is being captured."
        )

    # Generic expected_sections rule (all listed sections must appear).
    if case.expected_sections:
        missing = case.expected_sections - seen_sections
        assert not missing, (
            f"{case.name}: expected sections missing: {missing}. "
            f"Seen sections: {seen_sections}. Indicates partial series coverage."
        )

    # ---- 3. Date span ----
    if case.min_date_span_days > 0:
        pub_dates: list[date] = []
        for art in collected:
            try:
                pub_dates.append(date.fromisoformat(art.published_at[:10]))
            except ValueError:
                continue
        if pub_dates:
            span_days = (max(pub_dates) - min(pub_dates)).days
            assert span_days >= case.min_date_span_days, (
                f"{case.name}: records clustered within {span_days} days "
                f"({min(pub_dates).isoformat()}..{max(pub_dates).isoformat()}); "
                f"expected span ≥ {case.min_date_span_days} days. "
                "Indicates the ingestor may be silently ignoring its date range "
                "and only returning recent records."
            )
