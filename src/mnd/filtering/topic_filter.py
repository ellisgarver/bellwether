"""Hybrid topic filter (plan §5.1).

Two gates in series — BOTH must pass:
  Gate 1 (keyword): at least ``keyword_min_matches`` topic keywords present in article text.
  Gate 2 (embedding): cosine similarity to the centroid of embedded seed articles ≥ threshold.

The embedding gate is disabled (pass-through) when no seed articles exist so that
the pipeline can still run during data preparation; a warning is logged.

Parameters come from config.filtering.topic.*. Thresholds are locked — do not tune
to match anchor recovery.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from mnd.embedding.embedder import Embedder, prepare_text_for_embedding
from mnd.ingestion.base import Article
from mnd.utils.config import load_config, load_yaml, project_root
from mnd.utils.logging import get_logger

log = get_logger(__name__)


def _load_keywords(keywords_yaml: dict[str, Any]) -> list[str]:
    """Flatten every category's keyword list into a single lowercased list.

    Supports two YAML shapes:
      - schema_version 1.x (legacy): ``categories: {name: [kw, ...]}``
      - schema_version 2.x (ADR-015): ``categories: {name: {jel: [...],
        keywords: [kw, ...]}}`` — JEL annotations are metadata only and
        are not included in the keyword list.
    """
    keywords: list[str] = []
    for category in keywords_yaml.get("categories", {}).values():
        if isinstance(category, list):
            keywords.extend(category)
        elif isinstance(category, dict):
            keywords.extend(category.get("keywords", []))
    return [kw.lower() for kw in keywords]


def _load_seed_articles(seed_path: Path) -> list[dict[str, Any]]:
    if not seed_path.exists():
        return []
    seeds = []
    with seed_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                seeds.append(json.loads(line))
    return seeds


def _keyword_gate(text: str, keywords: list[str], min_matches: int) -> tuple[bool, int]:
    text_lower = text.lower()
    count = sum(1 for kw in keywords if kw in text_lower)
    return count >= min_matches, count


class TopicFilter:
    """Two-gate hybrid topic filter.

    Instantiate once per pipeline run; keyword list and seed centroid are cached.
    Call ``filter(articles)`` to annotate and return the list.
    """

    def __init__(
        self,
        keyword_min_matches: int | None = None,
        embedding_threshold: float | None = None,
        embedder: Embedder | None = None,
    ) -> None:
        cfg = load_config()
        topic_cfg = cfg["filtering"]["topic"]
        root = project_root()

        self.keyword_min_matches = (
            keyword_min_matches
            if keyword_min_matches is not None
            else topic_cfg["keyword_min_matches"]
        )
        self.embedding_threshold = (
            embedding_threshold
            if embedding_threshold is not None
            else topic_cfg["embedding_similarity_threshold"]
        )

        keywords_yaml = load_yaml("config/topic_filter_keywords.yaml")
        self._keywords = _load_keywords(keywords_yaml)

        seed_path = root / topic_cfg["seed_articles_path"]
        self._seed_articles = _load_seed_articles(seed_path)

        self._embedder = embedder
        self._seed_centroid: np.ndarray | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_embedder(self) -> Embedder:
        if self._embedder is None:
            self._embedder = Embedder.from_config("primary")
        return self._embedder

    def _get_seed_centroid(self) -> np.ndarray | None:
        if self._seed_centroid is not None:
            return self._seed_centroid
        if not self._seed_articles:
            log.warning(
                "No seed articles found at configured path — embedding gate disabled. "
                "Curate data/anchors/topic_seed_articles.jsonl to at least 30 articles."
            )
            return None
        texts = [
            prepare_text_for_embedding(s.get("title", ""), s.get("body", ""))
            for s in self._seed_articles
        ]
        log.info("Embedding %d seed articles to build topic centroid", len(texts))
        embeddings = self._get_embedder().encode(texts, show_progress=False)
        centroid = embeddings.mean(axis=0).astype(np.float32)
        norm = float(np.linalg.norm(centroid))
        if norm > 0:
            centroid /= norm
        self._seed_centroid = centroid
        return self._seed_centroid

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def filter(self, articles: list[Article]) -> list[Article]:
        """Annotate each article with filter metadata; return the same list.

        Sets ``article.raw_metadata["passed_filter"]`` (bool) and
        ``article.raw_metadata["filter_detail"]`` (dict). Callers that want
        only passing articles should apply:
            [a for a in articles if a.raw_metadata["passed_filter"]]
        """
        centroid = self._get_seed_centroid()

        if centroid is not None:
            texts = [prepare_text_for_embedding(a.title, a.body) for a in articles]
            article_embs = self._get_embedder().encode(texts)
        else:
            article_embs = None

        for i, article in enumerate(articles):
            full_text = f"{article.title} {article.body}"
            kw_pass, kw_count = _keyword_gate(full_text, self._keywords, self.keyword_min_matches)

            if centroid is not None and article_embs is not None:
                sim = float(np.dot(article_embs[i], centroid))
                emb_pass = sim >= self.embedding_threshold
            else:
                sim = None
                emb_pass = True  # gate disabled when no seeds

            passed = kw_pass and emb_pass
            article.raw_metadata["passed_filter"] = passed
            article.raw_metadata["filter_detail"] = {
                "keyword_matches": kw_count,
                "keyword_pass": kw_pass,
                "embedding_similarity": sim,
                "embedding_pass": emb_pass,
            }

        n_pass = sum(1 for a in articles if a.raw_metadata.get("passed_filter"))
        log.info(
            "Topic filter: %d/%d passed (keyword_min=%d, emb_threshold=%.2f)",
            n_pass,
            len(articles),
            self.keyword_min_matches,
            self.embedding_threshold,
        )
        return articles
