"""Media Cloud press-volume overlay.

Media Cloud provides free daily *story counts over time* for a keyword query
across large news collections — aggregate counts only, no article text. Its role
here is a display/validation overlay: for a given narrative, broad/premium
press volume is plotted against the institutional discourse volume to make the
"narratives form upstream in institutional/academic discourse, surface later in
the press" dynamic visible.

This layer is display/validation only. It must never feed embedding,
clustering, or dynamics fitting — Media Cloud text is not in the ADR-020 basis
set and these counts are a post-hoc overlay (ADR-042, ADR-020). Press counts may
serve as a *secondary* cross-check of the institutional fit; the SIR/logistic
fit target stays institutional volume (ADR-019 §E).

Coverage caveat: the Online News Archive thins before ~2017, so pre-2017
narratives may have sparse or absent counts. Callers should degrade gracefully
("press coverage data unavailable before ~2017") rather than show a misleading
flat line.

This module uses the `mediacloud` PyPI package (`SearchApi.story_count_over_time`).
The legacy `api.mediacloud.org/api/v2` REST API was retired in December 2023.
The separate Media Cloud "Wayback Machine" title-search API is a different
product and is not used here.

Output schema (one record per query per day):
    {
        "query": "...",
        "date": "YYYY-MM-DD",
        "story_count": 123,
        "total_count": 98765,        # all stories that day in the collection
        "ratio": 0.00124,            # story_count / total_count (attention share)
        "collection_ids": [34412234],
        "retrieved_at": "ISO8601"
    }

API key required: MEDIACLOUD_API_KEY in .env (free signup at search.mediacloud.org).
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Iterator

from tenacity import retry, stop_after_attempt, wait_random_exponential

from mnd.utils.logging import get_logger

log = get_logger(__name__)

# US National collection — the broad US news proxy for macro discourse (ADR-042).
US_NATIONAL_COLLECTION = 34412234

# Premium-press outlet collection(s) — the Layer-1B financial-press proxy (ADR-016:
# WSJ, Bloomberg, FT, Reuters, NYT, Barron's, Dow Jones, MarketWatch, AP Business …).
# Media Cloud has no single canonical "premium press" id, so this is left to config
# (``detection.mediacloud.premium_collection_ids``); the operator supplies the
# collection id(s) for their premium-press outlets. Empty -> the premium overlay is
# simply absent and callers fall back to the broad collection (ADR-064).
PREMIUM_PRESS_COLLECTION_IDS: list[int] = []

# Counts are unreliable before roughly this year; surfaced so callers can caption.
RELIABLE_SINCE_YEAR = 2017


class MediaCloudDetector:
    """Query Media Cloud for daily story counts by keyword query (ADR-042).

    Usage:
        detector = MediaCloudDetector.from_env()
        records = list(detector.fetch_story_counts(
            query="inflation OR \\"monetary policy\\"",
            start=date(2023, 1, 1),
            end=date(2023, 3, 31),
        ))

    Output is a list of daily story-count dicts (see module docstring). This
    class only retrieves; the press overlay and any anomaly flagging are done
    downstream.
    """

    def __init__(self, api_key: str, output_dir: Path | None = None) -> None:
        self.api_key = api_key
        self.output_dir = output_dir

    @classmethod
    def from_env(cls, output_dir: Path | None = None) -> "MediaCloudDetector":
        api_key = os.environ.get("MEDIACLOUD_API_KEY", "")
        if not api_key:
            raise EnvironmentError(
                "MEDIACLOUD_API_KEY not set in environment. "
                "Add it to .env — see .env.example."
            )
        return cls(api_key=api_key, output_dir=output_dir)

    def _search_api(self):
        """Lazily build the SearchApi so importing this module needs no package."""
        try:
            import mediacloud.api
        except ImportError as exc:  # pragma: no cover - environment guard
            raise ImportError(
                "The 'mediacloud' package is required for the press overlay "
                "(ADR-042). Install it: pip install mediacloud"
            ) from exc
        return mediacloud.api.SearchApi(self.api_key)

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_random_exponential(multiplier=1, max=30),
        reraise=True,
    )
    def _story_count_over_time(
        self, query: str, start: date, end: date, collection_ids: list[int]
    ) -> list[dict]:
        return self._search_api().story_count_over_time(
            query, start, end, collection_ids=collection_ids
        )

    def fetch_story_counts(
        self,
        query: str,
        start: date,
        end: date,
        *,
        collections: list[int] | None = None,
    ) -> Iterator[dict]:
        """Yield daily story-count records for the given keyword query.

        Parameters
        ----------
        query:
            Media Cloud query string, e.g. ``inflation OR "monetary policy"``.
        start, end:
            Date range (inclusive). The new API returns the full daily series in
            one call, so no chunking is needed.
        collections:
            Media Cloud collection IDs to scope the outlets. Defaults to the US
            National collection (broad US news proxy for macro discourse).
        """
        collection_ids = collections or [US_NATIONAL_COLLECTION]
        if start.year < RELIABLE_SINCE_YEAR:
            log.warning(
                "MediaCloud: range starts %s — coverage thins before ~%d; "
                "early counts may be sparse or absent.",
                start.isoformat(), RELIABLE_SINCE_YEAR,
            )
        try:
            rows = self._story_count_over_time(query, start, end, collection_ids)
        except Exception as exc:
            log.warning(
                "MediaCloud query failed for %s→%s: %s",
                start.isoformat(), end.isoformat(), exc,
            )
            return

        for row in rows:
            record_date = _coerce_date(row.get("date"))
            if record_date is None or not (start <= record_date <= end):
                continue
            total = int(row.get("total_count", 0) or 0)
            count = int(row.get("count", 0) or 0)
            ratio = row.get("ratio")
            if ratio is None:
                ratio = (count / total) if total else 0.0
            yield {
                "query": query,
                "date": record_date.isoformat(),
                "story_count": count,
                "total_count": total,
                "ratio": float(ratio),
                "collection_ids": collection_ids,
                "retrieved_at": _now_utc_iso(),
            }

    def fetch_and_save(
        self,
        query: str,
        start: date,
        end: date,
        *,
        query_slug: str | None = None,
        collections: list[int] | None = None,
    ) -> Path:
        """Fetch story counts and write JSONL to output_dir. Returns output path."""
        if self.output_dir is None:
            raise ValueError("output_dir must be set to use fetch_and_save")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        slug = query_slug or _slugify(query)
        filename = f"mediacloud_{slug}_{start.isoformat()}_{end.isoformat()}.jsonl"
        output_path = self.output_dir / filename

        count = 0
        with open(output_path, "w") as f:
            for record in self.fetch_story_counts(
                query, start, end, collections=collections
            ):
                f.write(json.dumps(record) + "\n")
                count += 1

        log.info("MediaCloud: wrote %d records to %s", count, output_path)
        return output_path

    def detect_anomalies(
        self,
        records: list[dict],
        *,
        baseline_days: int = 90,
        threshold_sigma: float = 2.0,
    ) -> list[dict]:
        """Flag records where story_count exceeds baseline mean + threshold_sigma * std.

        A simple z-score detector over a leading baseline window. Returns every
        record with 'is_anomaly' and 'z_score' added. This is a convenience for
        the overlay (highlighting press spikes); it is not part of the core
        analysis and never feeds clustering (ADR-042).
        """
        import statistics

        if len(records) < baseline_days:
            log.debug(
                "Too few records for anomaly detection (%d < %d)",
                len(records), baseline_days,
            )
            return [{**r, "is_anomaly": False, "z_score": 0.0} for r in records]

        counts = [r["story_count"] for r in records]
        mean = statistics.mean(counts[:baseline_days])
        stdev = statistics.stdev(counts[:baseline_days]) or 1.0

        result = []
        for r in records:
            z = (r["story_count"] - mean) / stdev
            result.append({**r, "is_anomaly": z > threshold_sigma, "z_score": round(z, 3)})
        return result


def press_heating(
    records: list[dict],
    *,
    recent_weeks: int = 4,
    baseline_weeks: int = 52,
    k: float = 2.0,
    reliable_since_year: int = RELIABLE_SINCE_YEAR,
) -> dict | None:
    """Press-heating signal for one narrative (ADR-064 / ADR-057 §2).

    Fires when a narrative's most-recent ``recent_weeks`` of press *attention share*
    (``story_count / total_count``, robust to overall press-volume drift) sits
    ``>= k`` standard deviations above its own trailing ``baseline_weeks`` baseline.
    This is a display-only "the press is spiking on a story we already track" flag,
    kept separate from the institutional recency flag; it never feeds embedding,
    clustering, or scope (ADR-010/020/046).

    Operates on the ``ratio`` field of the daily records (see ``fetch_story_counts``).
    Records are resampled to weekly means so the window matches the institutional
    emerging horizon and the baseline carries a year of seasonality. Returns ``None``
    when there is too little reliable history to judge (fewer than
    ``recent_weeks + baseline_weeks`` reliable weeks, or all-zero baseline).

    The returned dict is display-ready:
        {is_heating, z, recent_mean, baseline_mean, k, recent_weeks,
         baseline_weeks, caption}
    """
    import pandas as pd

    if not records:
        return None
    rows = [
        (d, float(r.get("ratio", 0.0) or 0.0))
        for r in records
        if (d := _coerce_date(r.get("date"))) is not None
        and d.year >= reliable_since_year
    ]
    if not rows:
        return None
    s = pd.Series(
        [v for _, v in rows], index=pd.DatetimeIndex([d for d, _ in rows])
    ).sort_index()
    weekly = s.resample("W").mean().dropna()
    if len(weekly) < recent_weeks + baseline_weeks:
        return None

    recent = weekly.iloc[-recent_weeks:]
    baseline = weekly.iloc[-(recent_weeks + baseline_weeks):-recent_weeks]
    base_mean = float(baseline.mean())
    base_std = float(baseline.std(ddof=1))
    if base_std <= 0.0:
        return None
    recent_mean = float(recent.mean())
    z = (recent_mean - base_mean) / base_std
    return {
        "is_heating": bool(z >= k),
        "z": round(z, 3),
        "recent_mean": recent_mean,
        "baseline_mean": base_mean,
        "k": k,
        "recent_weeks": recent_weeks,
        "baseline_weeks": baseline_weeks,
        "caption": (
            f"press attention {z:.1f}σ above its {baseline_weeks}-week baseline"
            if z >= k
            else f"press attention within {k:.0f}σ of its {baseline_weeks}-week baseline"
        ),
    }


def _coerce_date(value) -> date | None:
    """Accept a datetime.date, datetime, or ISO string from the API."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _now_utc_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _slugify(text: str) -> str:
    import re
    return re.sub(r"[^a-z0-9_]+", "_", text.lower().strip())[:60]
