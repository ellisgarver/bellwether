"""Canonical topic filter (ADR-016 / ADR-018 / ADR-019).

Single-stage keyword gate over the JEL-anchored canonical keyword list
(`config/topic_filter_keywords.yaml`, schema 2.1.0). An article passes when its
title+body contains at least ``keyword_min_matches`` distinct keywords from the
list.

The prior embedding-similarity Gate 2 (cosine similarity to a seed-article
centroid, threshold 0.55) was removed by ADR-019 — there is no field-accepted
literature anchor for a fixed cosine cutoff in dense-retrieval filtering
(Reimers & Gurevych 2019 SBERT report task-tuned operating points, not a
universal value). Keyword-only filtering at Stage 2 + downstream clustering
is the cleaner pre-registration story.

Parameters come from ``config.filtering.topic.*``. Do not hand-tune to match
anchor recovery.
"""
from __future__ import annotations

from typing import Any

from mnd.ingestion.base import Article
from mnd.utils.config import load_config, load_yaml
from mnd.utils.logging import get_logger

log = get_logger(__name__)


def _load_keywords(keywords_yaml: dict[str, Any]) -> list[str]:
    """Flatten every category's keyword list into a single lowercased list.

    Supports both YAML schema shapes for backwards compatibility:
      - schema_version 1.x: ``categories: {name: [kw, ...]}``
      - schema_version 2.x: ``categories: {name: {jel: [...], keywords: [kw, ...]}}``
    """
    keywords: list[str] = []
    for category in keywords_yaml.get("categories", {}).values():
        if isinstance(category, list):
            keywords.extend(category)
        elif isinstance(category, dict):
            keywords.extend(category.get("keywords", []))
    return [kw.lower() for kw in keywords]


def _keyword_gate(text: str, keywords: list[str], min_matches: int) -> tuple[bool, int]:
    text_lower = text.lower()
    count = sum(1 for kw in keywords if kw in text_lower)
    return count >= min_matches, count


class TopicFilter:
    """Single-gate keyword filter (ADR-019).

    Instantiate once per pipeline run; keyword list is cached. Call
    ``filter(articles)`` to annotate and return the list.
    """

    def __init__(self, keyword_min_matches: int | None = None) -> None:
        cfg = load_config()
        topic_cfg = cfg["filtering"]["topic"]
        self.keyword_min_matches = (
            keyword_min_matches
            if keyword_min_matches is not None
            else topic_cfg["keyword_min_matches"]
        )
        keywords_yaml = load_yaml("config/topic_filter_keywords.yaml")
        self._keywords = _load_keywords(keywords_yaml)

    def filter(self, articles: list[Article]) -> list[Article]:
        """Annotate each article with filter metadata; return the same list.

        Sets ``article.raw_metadata["passed_filter"]`` (bool) and
        ``article.raw_metadata["filter_detail"]`` (dict). Callers that want
        only passing articles should apply:

            [a for a in articles if a.raw_metadata["passed_filter"]]
        """
        for article in articles:
            full_text = f"{article.title} {article.body}"
            kw_pass, kw_count = _keyword_gate(full_text, self._keywords, self.keyword_min_matches)

            article.raw_metadata["passed_filter"] = kw_pass
            article.raw_metadata["filter_detail"] = {
                "keyword_matches": kw_count,
                "keyword_pass": kw_pass,
            }

        n_pass = sum(1 for a in articles if a.raw_metadata.get("passed_filter"))
        log.info(
            "Topic filter: %d/%d passed (keyword_min=%d)",
            n_pass, len(articles), self.keyword_min_matches,
        )
        return articles
