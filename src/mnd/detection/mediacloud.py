"""Media Cloud detection layer (Layer 2 per MND_PROJECT_SPEC.md Section 4).

Media Cloud provides daily story count time series by keyword/topic query
across thousands of outlets. Its sole role is to detect when a topic is
receiving anomalous volume attention before institutional sources have
characterized it in embeddable text.

Output schema (one record per query per day):
    {
        "query": "...",
        "date": "YYYY-MM-DD",
        "story_count": 123,
        "outlet_tier": "all | prestige_national | regional | trade",
        "retrieved_at": "ISO8601"
    }

API documentation: https://mediacloud.org/support/query-guide
API key required: MEDIACLOUD_API_KEY in .env
"""
from __future__ import annotations

import json
import os
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Iterator

import requests
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_random_exponential

from mnd.utils.logging import get_logger

log = get_logger(__name__)

_API_BASE = "https://api.mediacloud.org/api/v2"
_STORY_COUNT_ENDPOINT = f"{_API_BASE}/stories/count"

USER_AGENT = "MacroNarrativeDynamics/0.1 (academic research; contact via project repo)"


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, requests.exceptions.HTTPError):
        resp = getattr(exc, "response", None)
        return resp is not None and resp.status_code >= 500
    return True


@retry(
    stop=stop_after_attempt(4),
    wait=wait_random_exponential(multiplier=1, max=30),
    retry=retry_if_exception(_is_retryable),
)
def _get(url: str, params: dict, api_key: str, *, timeout: float = 30.0) -> dict:
    resp = requests.get(
        url,
        params={**params, "key": api_key},
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


class MediaCloudDetector:
    """Query Media Cloud for daily story counts by keyword query.

    Usage:
        detector = MediaCloudDetector.from_env()
        records = list(detector.fetch_story_counts(
            query="inflation OR 'monetary policy'",
            start=date(2023, 1, 1),
            end=date(2023, 3, 31),
        ))

    The output is a list of dicts with daily story counts. Anomaly detection
    is done downstream; this class only handles API retrieval.
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

    def fetch_story_counts(
        self,
        query: str,
        start: date,
        end: date,
        *,
        collections: list[int] | None = None,
        outlet_tier: str = "all",
        chunk_days: int = 30,
    ) -> Iterator[dict]:
        """Yield daily story count records for the given keyword query.

        Parameters
        ----------
        query:
            Media Cloud solr query string. E.g. "inflation OR 'monetary policy'".
        start, end:
            Date range (inclusive).
        collections:
            Optional list of Media Cloud collection IDs to restrict outlet scope.
            None = all indexed outlets.
        outlet_tier:
            Label for the outlet scope (for bookkeeping; not sent to API).
        chunk_days:
            Number of days per API request. Media Cloud aggregates by day within
            the requested range.
        """
        current = start
        while current <= end:
            chunk_end = min(current + timedelta(days=chunk_days - 1), end)
            try:
                params: dict = {
                    "q": query,
                    "fq": (
                        f"publish_date:[{current.isoformat()}T00:00:00Z "
                        f"TO {chunk_end.isoformat()}T23:59:59Z]"
                    ),
                    "split": "day",
                    "split_start_date": current.isoformat(),
                    "split_end_date": chunk_end.isoformat(),
                }
                if collections:
                    params["fq"] += f" AND tags_id_media:({' OR '.join(str(c) for c in collections)})"

                data = _get(_STORY_COUNT_ENDPOINT, params, self.api_key)
                split_counts: dict = data.get("split", {})

                for date_str, count in split_counts.items():
                    if date_str in ("gap", "start", "end"):
                        continue
                    try:
                        record_date = date.fromisoformat(date_str[:10])
                    except ValueError:
                        continue
                    if not (start <= record_date <= end):
                        continue
                    yield {
                        "query": query,
                        "date": record_date.isoformat(),
                        "story_count": int(count),
                        "outlet_tier": outlet_tier,
                        "retrieved_at": _now_utc_iso(),
                    }
            except Exception as exc:
                log.warning(
                    "MediaCloud query failed for chunk %s→%s: %s",
                    current.isoformat(), chunk_end.isoformat(), exc,
                )
            current = chunk_end + timedelta(days=1)
            time.sleep(0.5)

    def fetch_and_save(
        self,
        query: str,
        start: date,
        end: date,
        *,
        query_slug: str | None = None,
        outlet_tier: str = "all",
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
            for record in self.fetch_story_counts(query, start, end, outlet_tier=outlet_tier):
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

        Returns a list of anomalous records with 'is_anomaly' and 'z_score' added.
        This is a simple z-score detector; more sophisticated methods (e.g., ARIMA
        residuals) can be substituted without changing the upstream interface.
        """
        import statistics

        if len(records) < baseline_days:
            log.debug("Too few records for anomaly detection (%d < %d)", len(records), baseline_days)
            return [{**r, "is_anomaly": False, "z_score": 0.0} for r in records]

        counts = [r["story_count"] for r in records]
        mean = statistics.mean(counts[:baseline_days])
        stdev = statistics.stdev(counts[:baseline_days]) or 1.0

        result = []
        for r in records:
            z = (r["story_count"] - mean) / stdev
            result.append({**r, "is_anomaly": z > threshold_sigma, "z_score": round(z, 3)})
        return result


def _now_utc_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _slugify(text: str) -> str:
    import re
    return re.sub(r"[^a-z0-9_]+", "_", text.lower().strip())[:60]
