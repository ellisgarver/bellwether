"""Filtering stage: date range, near-duplicate removal, and boilerplate stripping.

There is no pre-clustering topic filter. The basis-set source selection is the
only macro-content scope constraint at ingest time; topic relevance is decided
post-clustering by ``mnd.clustering.jel_classifier`` over BERTopic cluster
representatives, not by a keyword gate over individual articles.

The ``filter`` stage in run_pipeline.py performs date-range filtering, MinHash
whole-document near-duplicate removal (``Deduplicator``, ADR-019), and
sub-document cross-document boilerplate stripping (``BoilerplateStripper``,
ADR-054). All three are content/repetition operations; none inspects topic.
"""

from mnd.filtering.boilerplate import BoilerplateReport, BoilerplateStripper
from mnd.filtering.dedup import Deduplicator

__all__ = ["Deduplicator", "BoilerplateStripper", "BoilerplateReport"]
