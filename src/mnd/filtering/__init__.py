"""Filtering stage: near-duplicate detection only (ADR-020).

ADR-020 (2026-05-20) removed the pre-clustering JEL keyword filter entirely.
The basis-set source selection is now the only macro-content scope constraint
at ingest time; topic relevance is decided post-clustering by
``mnd.clustering.jel_classifier`` over BERTopic cluster representatives, not
by a keyword gate over individual articles.

The ``filter`` stage in run_pipeline.py performs date-range filtering and
MinHash near-duplicate removal — nothing else.
"""

from mnd.filtering.dedup import Deduplicator

__all__ = ["Deduplicator"]
