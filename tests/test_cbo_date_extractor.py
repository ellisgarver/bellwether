"""Regression tests for the CBO publication-date extractor.

CBO's 2025 site redesign dropped the Drupal ``dcterms.*`` meta tags the
extractor originally keyed on, moving the date to a ``book:release_date`` meta
and a ``<time datetime>`` element. That silently dropped every in-window pid in
ingest job 50724243 (5879 pids walked, 0 kept). These pin the three accepted
sources + their precedence so the drift can't recur unnoticed.
"""
from __future__ import annotations

from datetime import date

from mnd.ingestion.institutional import _cbo_publication_date_from_html


def test_post_2025_book_release_date_meta():
    html = '<meta property="book:release_date" content="Thu, 06/20/2024 - 12:00">'
    assert _cbo_publication_date_from_html(html) == date(2024, 6, 20)


def test_time_datetime_iso_fallback():
    # No book:release_date meta — fall back to the <time datetime> ISO stamp.
    html = '<time datetime="2024-06-20T12:00:00Z">June 20, 2024</time>'
    assert _cbo_publication_date_from_html(html) == date(2024, 6, 20)


def test_legacy_dcterms_still_supported():
    # Pre-redesign earliest-ts captures still carry Dublin Core tags.
    html = '<meta name="dcterms.created" content="2013-05-22">'
    assert _cbo_publication_date_from_html(html) == date(2013, 5, 22)


def test_release_meta_wins_over_time_and_dcterms():
    html = (
        '<meta property="book:release_date" content="Tue, 12/01/2009 - 12:00">'
        '<meta name="dcterms.created" content="2011-12-01">'
        '<time datetime="2011-12-01T12:00:00Z">December 1, 2011</time>'
    )
    # book:release_date is authoritative — not the 2011 migration stamp.
    assert _cbo_publication_date_from_html(html) == date(2009, 12, 1)


def test_none_when_no_date_markup():
    assert _cbo_publication_date_from_html("<html><body>no date</body></html>") is None
    assert _cbo_publication_date_from_html("") is None
