"""Per-source coverage tests for ingestion methodology lock-in.

Network-dependent. Marked ``integration``; not run by default. Invoke with::

    pytest tests/integration/test_source_coverage.py -m integration -v

For every (source, window) pair we assert FOUR contracts. Each contract
maps to a methodology requirement; a failure means a basis-set source is
silently undercovering and the corpus would be biased. Fix the ingestor —
do NOT loosen the assertion.

Contract A — **Floor count** (basis-set coverage).
    At least N records emerge within the iterator's ``max_records`` cap.
    Catches silent-zero failures (e.g. Cloudflare 403 swallowed by an
    ``except: return``) and partial-undercount regressions (e.g. a
    regex that only matches the most recent month).

Contract B — **Authoritative date per record** (methodology principle 1).
    Every record's ``published_at`` parses as an ISO date and lies in
    ``[window_start, window_end]``. Catches the "fabricated mid-year
    date" failure mode and the "Wayback snapshot timestamp masquerading
    as publication date" failure mode.

Contract C — **Real body per record** (full-content embedding requirement).
    Every record has ``word_count`` ≥ the source-specific minimum. Catches
    title-only / teaser-only emission where the listing summary leaked
    through as the body field.

Contract D — **Section diversity & date span** (basis-set series breadth).
    The expected sections are all present, distinct sections match the
    multi-series rule when applicable, and the observed dates span
    ``min_date_span_days`` — guarding against "ingestor returns the same
    week of records over and over."

Mandatory dependencies. ``curl_cffi`` (TLS impersonation for IMF, Atlanta,
VoxEU) and ``pypdf`` (PDF extraction for CEA, Congressional Path B) are
**required** for the ingest to function. We do not skip tests when they
are missing — we let pytest surface the ImportError so the developer
installs them. Run ``pip install -r requirements.txt`` first.

Network errors (DNS failure, connection refused, read timeout) DO skip
gracefully — those are environmental, not code defects. Any other
exception fails the test loudly.
"""
from __future__ import annotations

import itertools
import socket
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date

import pytest
import requests

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
# Contract definition
# ---------------------------------------------------------------------------


@dataclass
class CoverageCase:
    """A single coverage contract for one (sub-ingestor, window) pair.

    Floors are basis-set-justified, not heuristic:

    - Fed (board, regional, FEDS Notes, Beige Book): institutional cadence
      sets a known minimum (FOMC = 8/yr, MPR = 2/yr, Beige Book = 8/yr,
      speeches = ~80/yr, FEDS Notes = ~70/yr).
    - BIS: ~70 working papers + ~20 QR articles + ~15 bulletins + speeches
      per year (post-ADR-017 expansion).
    - IMF: WEO 2x/yr + GFSR 2x/yr + ~70 working papers + ~25 F&D + blog.
    - Brookings: ~1k publications/yr via WP REST.
    - PIIE: ~300 publications/yr.
    - VoxEU: ~250 columns/yr.
    - NBER: ~1500 working papers/yr.
    - CEA: 1 ERP/yr, ~20 chapters.
    - Congressional: ~6-12 hearings/yr (Treasury Sec testimony).
    - Treasury OFR: ~10 working papers + briefs/yr.
    - Atlanta Fed: ~30-50 working-papers/macroblog items/yr (post-2019).
    - CBO: ~700-1200 publications/yr.

    Floor is ~25-35% of expected to leave headroom for window edge effects
    while still catching silent-zero / 80%-undercount regressions.
    """

    name: str
    iterator_factory: Callable[[date, date], Iterator[Article]]
    window_start: date
    window_end: date
    floor_count: int
    max_records: int = 400
    section_filter: str | None = None
    expected_sections: set[str] = field(default_factory=set)
    min_date_span_days: int = 0
    min_body_word_count: int = 50

    @property
    def id(self) -> str:
        return self.name


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------


def _fed_method(method_name: str) -> Callable[[date, date], Iterator[Article]]:
    """Build an iterator factory for one private method on FederalReserveIngestor."""
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
        # Beige Books are long-form (~13k words) so a 200 floor catches
        # any extraction-truncation regression.
        min_body_word_count=200,
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
        floor_count=20,
        max_records=200,
        min_date_span_days=90,
    ),
    CoverageCase(
        name="fed_atlanta_2023_listing_api",
        iterator_factory=lambda s, e: FedRegionalIngestor()._fetch_atlanta(s, e, set()),
        window_start=date(2023, 1, 1),
        window_end=date(2023, 12, 31),
        # Pre-ADR-017 fed_atlanta = 0 records; ADR-021 switched to the
        # per-series JSON listing API. Floor enforces non-trivial yield.
        floor_count=10,
        max_records=80,
        min_date_span_days=60,
    ),
    # -----------------------------------------------------------------
    # Institutional sources
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
        # CHRG transcripts are long; testimony press releases shorter.
        # 80 is a conservative floor across both registers.
        min_body_word_count=80,
    ),
    CoverageCase(
        name="imf_2023_multi_series",
        iterator_factory=lambda s, e: IMFIngestor().fetch(s, e),
        window_start=date(2023, 1, 1),
        window_end=date(2023, 12, 31),
        floor_count=30,
        max_records=300,
        expected_sections=set(),  # diversity asserted via multi-section rule
        min_date_span_days=120,
    ),
    CoverageCase(
        name="bis_2023_multi_section",
        iterator_factory=lambda s, e: BISIngestor().fetch(s, e),
        window_start=date(2023, 1, 1),
        window_end=date(2023, 12, 31),
        floor_count=40,
        max_records=400,
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
        name="cbo_2023_wayback",
        iterator_factory=lambda s, e: CBOIngestor().fetch(s, e),
        window_start=date(2023, 6, 1),
        window_end=date(2023, 7, 31),
        # CBO publishes ~700-1200 items/year so a 2-month window has
        # ~120-200 expected. Floor at 5 is a sanity check; the empirical
        # yield is the CBO methodology question still pending resolution.
        floor_count=5,
        max_records=30,
        expected_sections={"cbo_publication"},
        min_date_span_days=14,
    ),
    # -----------------------------------------------------------------
    # Academic / policy
    # -----------------------------------------------------------------
    CoverageCase(
        name="voxeu_2012_historical_window",
        iterator_factory=lambda s, e: VoxEUIngestor().fetch(s, e),
        window_start=date(2012, 1, 1),
        window_end=date(2012, 12, 31),
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
        floor_count=15,
        max_records=120,
        expected_sections={"piie_publication"},
        min_date_span_days=90,
    ),
    # -----------------------------------------------------------------
    # ADR-020 additions: NBER + CEA
    # -----------------------------------------------------------------
    CoverageCase(
        name="nber_2023h2_direct_url_enum",
        iterator_factory=lambda s, e: NBERIngestor().fetch(s, e),
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
        window_start=date(2023, 1, 1),
        window_end=date(2023, 12, 31),
        floor_count=10,
        max_records=60,
        expected_sections={"cea_erp_chapter"},
        # All ERP chapters share the volume's dateIssued, so date span
        # is irrelevant — the floor + section check are the assertions
        # that matter.
        min_date_span_days=0,
        # ERP chapters are PDF-extracted; full chapter is thousands of
        # words. A 500-word floor catches partial-page-only extraction.
        min_body_word_count=500,
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
        min_body_word_count=500,
    ),
    # -----------------------------------------------------------------
    # Historical-edge cross-checks at the 2010 corpus floor
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
# Exception classes that count as "true network failures" — these skip
# the test gracefully (the network is the problem, not the code). Any other
# exception fails loudly.
# ---------------------------------------------------------------------------

_NETWORK_EXCEPTIONS: tuple[type[BaseException], ...] = (
    requests.ConnectionError,
    requests.Timeout,
    socket.gaierror,
    ConnectionResetError,
)


# ---------------------------------------------------------------------------
# Test driver
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_source_coverage(case: CoverageCase) -> None:
    """Run one coverage contract — four assertions, one code path.

    See the module docstring for the contracts (A floor count, B
    authoritative date per record, C real body per record, D section
    diversity + date span).
    """
    iterator = case.iterator_factory(case.window_start, case.window_end)

    # Collect up to max_records, filtering by section if requested.
    # Network errors skip; everything else propagates as test failure.
    collected: list[Article] = []
    try:
        for art in itertools.islice(iterator, case.max_records):
            if case.section_filter and art.section != case.section_filter:
                continue
            collected.append(art)
    except _NETWORK_EXCEPTIONS as exc:  # pragma: no cover
        pytest.skip(
            f"{case.name}: network error ({type(exc).__name__}: {exc}). "
            "Treated as transient connectivity issue, not a code defect."
        )

    # ---- Contract A: floor count ----
    assert len(collected) >= case.floor_count, (
        f"{case.name}: only {len(collected)} records collected, "
        f"expected at least {case.floor_count} within "
        f"{case.window_start.isoformat()}..{case.window_end.isoformat()} "
        f"(max_records={case.max_records}, section_filter={case.section_filter!r}). "
        "Likely a silent coverage failure — fix the ingestor, don't lower the floor."
    )

    # ---- Contract B: authoritative date per record ----
    # Every record must carry a real publication date inside the requested
    # window. Methodology principle 1 (anchored or removed) — fabricated
    # or fallback-derived dates are forbidden.
    invalid_dates: list[tuple[str, str]] = []
    out_of_window: list[tuple[str, date]] = []
    parsed_dates: list[date] = []
    for art in collected:
        try:
            pub = date.fromisoformat(art.published_at[:10])
        except (ValueError, TypeError):
            invalid_dates.append((art.url, art.published_at))
            continue
        if pub < case.window_start or pub > case.window_end:
            out_of_window.append((art.url, pub))
            continue
        parsed_dates.append(pub)
    assert not invalid_dates, (
        f"{case.name}: {len(invalid_dates)} records have unparseable "
        f"published_at values. Examples: {invalid_dates[:3]}. "
        "Every emitted record must carry a valid ISO date — fix the ingestor "
        "to drop records without authoritative dates rather than fabricating one."
    )
    assert not out_of_window, (
        f"{case.name}: {len(out_of_window)} records have dates outside the "
        f"requested window {case.window_start}..{case.window_end}. Examples: "
        f"{out_of_window[:3]}. The ingestor's window filter is broken."
    )

    # ---- Contract C: real body per record ----
    # Every record must carry a body whose word count meets the source's
    # minimum. Catches title-only / teaser-only / abstract-only emission.
    short_bodies = [
        (art.url, art.word_count)
        for art in collected
        if art.word_count < case.min_body_word_count
    ]
    assert not short_bodies, (
        f"{case.name}: {len(short_bodies)} records have body word_count "
        f"below {case.min_body_word_count}. Examples: {short_bodies[:3]}. "
        "Either body extraction is truncated, or the ingestor is emitting "
        "title/teaser fallbacks — fix the ingestor."
    )

    # ---- Contract D1: section diversity ----
    seen_sections = {a.section for a in collected if a.section}

    if case.name in _MULTI_SECTION_MIN_SECTIONS:
        min_n, universe = _MULTI_SECTION_MIN_SECTIONS[case.name]
        relevant_seen = seen_sections & universe
        assert len(relevant_seen) >= min_n, (
            f"{case.name}: only {len(relevant_seen)} distinct sections out of "
            f"{universe} seen (got {relevant_seen}); expected at least {min_n}. "
            "Likely indicates only one series is being captured."
        )

    if case.expected_sections:
        missing = case.expected_sections - seen_sections
        assert not missing, (
            f"{case.name}: expected sections missing: {missing}. "
            f"Seen sections: {seen_sections}. Indicates partial series coverage."
        )

    # ---- Contract D2: date span ----
    # Date-span asserts the ingestor is not silently returning only the
    # most-recent records from a much larger pool. The check is only
    # meaningful when the iterator has been exhausted — if max_records
    # cut us off mid-iteration, a newest-first source will appear to
    # cluster in the latest part of the window simply because we didn't
    # read enough records to reach the earliest part. We use a heuristic:
    # if len(collected) >= 0.95 * max_records, assume the iterator was
    # capped and skip the strict span assertion. The floor count + date
    # validation (Contract B) already prove that records are real and
    # in-window; clustering with cap-hit is a test-read artifact, not
    # an ingestor defect.
    if case.min_date_span_days > 0 and parsed_dates:
        cap_likely_hit = len(collected) >= int(0.95 * case.max_records)
        if cap_likely_hit:
            # We collected enough records to suggest the iterator was
            # capped, not exhausted. Skip the span check.
            pass
        else:
            span_days = (max(parsed_dates) - min(parsed_dates)).days
            assert span_days >= case.min_date_span_days, (
                f"{case.name}: records clustered within {span_days} days "
                f"({min(parsed_dates).isoformat()}..{max(parsed_dates).isoformat()}); "
                f"expected span ≥ {case.min_date_span_days} days; iterator "
                f"yielded {len(collected)} of {case.max_records} max_records "
                "(below the 95% cap heuristic, so the iterator is treated as "
                "exhausted). Indicates the ingestor is silently ignoring its "
                "date range and only returning recent records."
            )
