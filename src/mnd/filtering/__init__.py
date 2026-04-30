"""Filtering stage: topic filter and near-duplicate detection."""

from mnd.filtering.dedup import Deduplicator
from mnd.filtering.topic_filter import TopicFilter

__all__ = ["TopicFilter", "Deduplicator"]
