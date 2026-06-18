"""Filtering stage: near-duplicate detection only.

There is no pre-clustering topic filter. The basis-set source selection is the
only macro-content scope constraint at ingest time; topic relevance is decided
post-clustering by ``mnd.clustering.jel_classifier`` over BERTopic cluster
representatives, not by a keyword gate over individual articles.

The ``filter`` stage in run_pipeline.py performs date-range filtering and
MinHash near-duplicate removal — nothing else.
"""

from mnd.filtering.dedup import Deduplicator

__all__ = ["Deduplicator"]
