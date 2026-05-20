"""Clustering stage: single-granularity BERTopic pipeline with stability diagnostic (ADR-019)."""

from mnd.clustering.bertopic_pipeline import BertopicPipeline
from mnd.clustering.similar_narratives import (
    compute_similar_narratives,
    lexical_similarity,
    morphological_similarity,
    semantic_similarity,
)

__all__ = [
    "BertopicPipeline",
    "compute_similar_narratives",
    "semantic_similarity",
    "lexical_similarity",
    "morphological_similarity",
]
