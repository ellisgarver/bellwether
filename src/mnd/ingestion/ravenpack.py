"""DEPRECATED (ADR-016, 2026-05-18): RavenPack via WRDS is no longer the
dynamics layer. The Layer 1B dynamics signal is now sourced from Media Cloud
Premium Press via `src/mnd/detection/mediacloud.py`. Same Media Cloud API as
Layer 2; different outlet collection scope. No WRDS subscription needed.

This module is retained as reference code for the historical ADR-010/ADR-008
design. Do not import or invoke. Do not pass WRDS_* environment variables;
they are obsolete.

---

ORIGINAL DOCSTRING (for reference):

RavenPack RPA 1.0 Global Macro, Dow Jones Edition — dynamics layer ingestion.

This module provides the DYNAMICS LAYER for the project: weekly article volume
counts per narrative cluster, normalized before SIR/logistic fitting (ADR-008).

It does NOT produce Article records for embedding or clustering. Output is a
weekly time series DataFrame with columns:
    week_start      date (Monday of each ISO week)
    source_id       outlet identifier (e.g. 'wsj', 'djn', 'marketwatch')
    article_count   number of articles in that week matching the macro filter

RavenPack is accessed via WRDS (Wharton Research Data Services) using either:
  - WRDS Python API (wrds library):  pip install wrds
  - Direct psycopg2 connection to WRDS PostgreSQL

Authentication: WRDS_USERNAME and WRDS_PASSWORD environment variables (or
~/.pgpass / wrds.Connection interactive prompt as fallback).

The macro filter uses RavenPack's event_relevance_score (>= 75) and
event_sentiment_score presence to limit to macro-relevant news items.
No entity filter is applied — we want broad macro topic coverage.

Relevant WRDS tables:
    ravenpack.rpa_dj_pub          — main article/event table
    ravenpack.rpa_dj_pub_ent      — entity mapping (for optional entity filter)

Column reference (ravenpack.rpa_dj_pub):
    rp_story_id       unique story identifier
    rp_document_id    unique document (article) identifier
    timestamp_utc     publication timestamp UTC
    source_id         RavenPack source identifier (maps to outlet names)
    event_relevance   0–100 relevance score for the event within the article
    css               composite sentiment score (-1 to 1); NULL for non-scored
    rpa_source_id     abbreviation (e.g. WSJ, DJN, MKW)

Typical usage:

    from mnd.ingestion.ravenpack import RavenPackIngestor
    ingestor = RavenPackIngestor()
    df = ingestor.fetch_volume_series(date(2010, 1, 1), date(2025, 12, 31))
    df.to_parquet("data/raw/dynamics/ravenpack_weekly.parquet")
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from typing import TYPE_CHECKING

import pandas as pd

from mnd.utils.logging import get_logger

if TYPE_CHECKING:
    pass

log = get_logger(__name__)

# Minimum event relevance score to include in volume counts.
# RavenPack's own documentation recommends >= 75 for "clearly about" the event.
_MIN_RELEVANCE = 75

# RPA source IDs that map to macro-financial outlets in the Dow Jones edition.
# This is a safelist to exclude pure PR Newswire releases (source_type='PRS')
# and non-financial wire traffic. An empty set means no source filter.
_MACRO_SOURCE_TYPES: set[str] = {
    "WSJ",   # Wall Street Journal
    "DJN",   # Dow Jones Newswires
    "MKW",   # MarketWatch
    "BAR",   # Barron's
    # PR Newswire omitted: primarily corporate announcements, low narrative signal
}

# SQL query template for weekly volume by source
_VOLUME_QUERY = """
SELECT
    DATE_TRUNC('week', timestamp_utc::date)::date AS week_start,
    rpa_source_id AS source_id,
    COUNT(DISTINCT rp_document_id) AS article_count
FROM ravenpack.rpa_dj_pub
WHERE
    timestamp_utc >= %(start_dt)s
    AND timestamp_utc < %(end_dt)s
    AND event_relevance >= %(min_relevance)s
    {source_filter}
GROUP BY 1, 2
ORDER BY 1, 2
"""

_SOURCE_FILTER_SQL = "AND rpa_source_id = ANY(%(source_ids)s)"


class RavenPackIngestor:
    """Fetch weekly article volume time series from RavenPack via WRDS.

    This is NOT a subclass of Ingestor — it does not produce Article records.
    It produces a pandas DataFrame for the dynamics normalization pipeline.
    """

    def __init__(
        self,
        *,
        wrds_username: str | None = None,
        wrds_password: str | None = None,
        source_filter: set[str] | None = _MACRO_SOURCE_TYPES,
        min_relevance: int = _MIN_RELEVANCE,
    ) -> None:
        self._username = wrds_username or os.environ.get("WRDS_USERNAME")
        self._password = wrds_password or os.environ.get("WRDS_PASSWORD")
        self._source_filter = source_filter
        self._min_relevance = min_relevance

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def fetch_volume_series(self, start: date, end: date) -> pd.DataFrame:
        """Return weekly article volume time series for [start, end].

        Columns:
            week_start (date)  — Monday of the ISO week
            source_id  (str)   — RavenPack rpa_source_id (e.g. 'WSJ')
            article_count (int)

        Raises RuntimeError if WRDS connection fails.
        """
        log.info(
            "RavenPack: fetching volume series %s → %s (min_relevance=%d)",
            start, end, self._min_relevance,
        )
        conn = self._connect()
        try:
            df = self._query_volume(conn, start, end)
        finally:
            conn.close()
        log.info("RavenPack: %d rows fetched", len(df))
        return df

    def fetch_article_metadata(
        self, start: date, end: date, limit: int = 100_000
    ) -> pd.DataFrame:
        """Return article-level metadata records for [start, end].

        Columns:
            rp_document_id, timestamp_utc, rpa_source_id, event_relevance, css

        Primarily useful for diagnostic spot-checks and source composition QA.
        """
        conn = self._connect()
        try:
            df = self._query_metadata(conn, start, end, limit)
        finally:
            conn.close()
        return df

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _connect(self):
        """Return an open database connection (wrds or psycopg2 fallback)."""
        # Try the WRDS Python library first (preferred: handles auth, SSL, etc.)
        try:
            import wrds  # type: ignore[import-untyped]
            kwargs: dict = {}
            if self._username:
                kwargs["wrds_username"] = self._username
            db = wrds.Connection(**kwargs)
            log.info("RavenPack: connected via wrds library")
            return _WRDSConnectionAdapter(db)
        except ImportError:
            log.debug("wrds library not installed; falling back to psycopg2")
        except Exception as exc:
            log.debug("wrds.Connection failed: %s; trying psycopg2", exc)

        # Fallback: direct psycopg2 connection to WRDS PostgreSQL
        try:
            import psycopg2  # type: ignore[import-untyped]
            if not self._username or not self._password:
                raise RuntimeError(
                    "WRDS_USERNAME and WRDS_PASSWORD environment variables are required "
                    "when the wrds Python library is not installed."
                )
            conn = psycopg2.connect(
                host="wrds-pgdata.wharton.upenn.edu",
                port=9737,
                dbname="wrds",
                user=self._username,
                password=self._password,
                sslmode="require",
            )
            log.info("RavenPack: connected via psycopg2")
            return _PsycopgConnectionAdapter(conn)
        except ImportError as exc:
            raise RuntimeError(
                "Neither the 'wrds' nor 'psycopg2' package is installed. "
                "Install one: pip install wrds  OR  pip install psycopg2-binary"
            ) from exc

    def _query_volume(self, conn, start: date, end: date) -> pd.DataFrame:
        end_exclusive = end + timedelta(days=1)
        params: dict = {
            "start_dt": start.isoformat(),
            "end_dt": end_exclusive.isoformat(),
            "min_relevance": self._min_relevance,
        }
        if self._source_filter:
            sql = _VOLUME_QUERY.format(source_filter=_SOURCE_FILTER_SQL)
            params["source_ids"] = list(self._source_filter)
        else:
            sql = _VOLUME_QUERY.format(source_filter="")
        return conn.query(sql, params)

    def _query_metadata(self, conn, start: date, end: date, limit: int) -> pd.DataFrame:
        end_exclusive = end + timedelta(days=1)
        sql = """
        SELECT
            rp_document_id,
            timestamp_utc,
            rpa_source_id,
            event_relevance,
            css
        FROM ravenpack.rpa_dj_pub
        WHERE
            timestamp_utc >= %(start_dt)s
            AND timestamp_utc < %(end_dt)s
            AND event_relevance >= %(min_relevance)s
        ORDER BY timestamp_utc
        LIMIT %(limit)s
        """
        params = {
            "start_dt": start.isoformat(),
            "end_dt": end_exclusive.isoformat(),
            "min_relevance": self._min_relevance,
            "limit": limit,
        }
        return conn.query(sql, params)


# ---------------------------------------------------------------------------
# Connection adapters — normalize wrds.Connection and psycopg2 interfaces
# ---------------------------------------------------------------------------


class _WRDSConnectionAdapter:
    """Thin adapter over wrds.Connection."""

    def __init__(self, db) -> None:
        self._db = db

    def query(self, sql: str, params: dict) -> pd.DataFrame:
        return self._db.raw_sql(sql, params=params)

    def close(self) -> None:
        try:
            self._db.close()
        except Exception:
            pass


class _PsycopgConnectionAdapter:
    """Thin adapter over a raw psycopg2 connection."""

    def __init__(self, conn) -> None:
        self._conn = conn

    def query(self, sql: str, params: dict) -> pd.DataFrame:
        import psycopg2.extras  # type: ignore[import-untyped]

        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return pd.DataFrame(rows)

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass
