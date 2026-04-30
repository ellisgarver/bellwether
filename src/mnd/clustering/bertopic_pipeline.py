"""BERTopic clustering pipeline (plan §6).

Wraps BERTopic with UMAP + HDBSCAN parameters from config and adds:
  - Three-level hierarchical merging (fine ≈ 200 / medium ≈ 60 / coarse ≈ 15 topics)
  - Class-based TF-IDF (c-TF-IDF) for cluster representation
  - Bootstrap stability evaluation: NMI + ARI across 20 random-seed replicates
    against a baseline fit — kill criterion 1 (min_bootstrap_nmi from config)

All random seeds flow from config.reproducibility.global_random_seed.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from mnd.utils.config import load_config
from mnd.utils.logging import get_logger

log = get_logger(__name__)


def _build_model(cfg: dict[str, Any], seed: int):
    from bertopic import BERTopic
    from bertopic.vectorizers import ClassTfidfTransformer
    from hdbscan import HDBSCAN
    from sklearn.feature_extraction.text import CountVectorizer
    from umap import UMAP

    uc = cfg["clustering"]["umap"]
    hc = cfg["clustering"]["hdbscan"]
    cc = cfg["clustering"].get("ctfidf", {})

    umap_model = UMAP(
        n_neighbors=uc["n_neighbors"],
        min_dist=uc["min_dist"],
        n_components=uc["n_components"],
        metric=uc["metric"],
        random_state=seed,
    )
    hdbscan_model = HDBSCAN(
        min_cluster_size=hc["min_cluster_size"],
        min_samples=hc.get("min_samples"),
        cluster_selection_method=hc["cluster_selection_method"],
        metric=hc["metric"],
        prediction_data=True,
    )
    vectorizer = CountVectorizer(stop_words="english", ngram_range=(1, 2))
    ctfidf = ClassTfidfTransformer(
        reduce_frequent_words=cc.get("reduce_frequent_words", True),
        bm25_weighting=cc.get("bm25_weighting", True),
    )
    return BERTopic(
        umap_model=umap_model,
        hdbscan_model=hdbscan_model,
        vectorizer_model=vectorizer,
        ctfidf_model=ctfidf,
        calculate_probabilities=False,
        verbose=False,
    )


class BertopicPipeline:
    """Manages BERTopic fitting, hierarchical merging, and stability evaluation.

    Usage:
        pipeline = BertopicPipeline.from_config()
        results  = pipeline.fit_transform(documents, embeddings)
        stability = pipeline.evaluate_stability(documents, embeddings)
    """

    def __init__(self, cfg: dict[str, Any] | None = None) -> None:
        self._cfg = cfg or load_config()
        self._seed = self._cfg["reproducibility"]["global_random_seed"]
        self._model = None

    @classmethod
    def from_config(cls) -> "BertopicPipeline":
        return cls(load_config())

    # ------------------------------------------------------------------
    # Main fit
    # ------------------------------------------------------------------

    def fit_transform(
        self, documents: list[str], embeddings: np.ndarray
    ) -> dict[str, Any]:
        """Fit BERTopic and return hierarchical cluster assignments.

        Returns:
            topics      list[int] — fine-grained topic per document (-1 = noise)
            topic_info  DataFrame — labels and representative terms
            hierarchical dict    — {fine, medium, coarse} topic lists
            n_topics    int      — topics found at fine level (excluding noise)
        """
        log.info("Fitting BERTopic on %d documents", len(documents))
        self._model = _build_model(self._cfg, self._seed)
        topics, _ = self._model.fit_transform(documents, embeddings)
        topics = list(topics)

        topic_info = self._model.get_topic_info()
        n_topics = int((topic_info["Topic"] >= 0).sum())
        log.info("Found %d topics (%d noise docs)", n_topics, topics.count(-1))

        hierarchical = self._build_hierarchy(documents, topics)

        return {
            "topics": topics,
            "topic_info": topic_info,
            "hierarchical": hierarchical,
            "n_topics": n_topics,
        }

    # ------------------------------------------------------------------
    # Hierarchical merging
    # ------------------------------------------------------------------

    def _build_hierarchy(
        self,
        documents: list[str],
        fine_topics: list[int],
    ) -> dict[str, list[int]]:
        gran = self._cfg["clustering"]["granularity"]
        result: dict[str, list[int]] = {"fine": fine_topics}

        current_topics = fine_topics
        for level, target_key in [("medium", "medium_target"), ("coarse", "coarse_target")]:
            target = gran[target_key]
            n_current = len({t for t in current_topics if t >= 0})
            if n_current <= target:
                log.info(
                    "%s merge: already at/below target (%d ≤ %d), skipping",
                    level, n_current, target,
                )
                result[level] = current_topics
                continue
            try:
                merged = self._model.reduce_topics(documents, nr_topics=target)
                result[level] = list(merged.topics_)
                n_merged = len({t for t in result[level] if t >= 0})
                log.info("Merged to %s level: %d → %d topics", level, n_current, n_merged)
                current_topics = result[level]
            except Exception as exc:
                log.warning("Hierarchy merge at %s level failed: %s", level, exc)
                result[level] = current_topics

        return result

    # ------------------------------------------------------------------
    # Bootstrap stability (kill criterion 1)
    # ------------------------------------------------------------------

    def evaluate_stability(
        self,
        documents: list[str],
        embeddings: np.ndarray,
        n_replicates: int | None = None,
    ) -> dict[str, Any]:
        """NMI + ARI across bootstrap replicates vs. a baseline fit.

        Seeds: config.validation.bootstrap_random_seed through +n_replicates.
        Kill criterion 1: mean NMI ≥ config.validation.min_bootstrap_nmi.
        """
        from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

        val_cfg = self._cfg["validation"]
        if n_replicates is None:
            n_replicates = val_cfg["bootstrap_replicates"]

        base_seed = val_cfg["bootstrap_random_seed"]
        seeds = list(range(base_seed, base_seed + n_replicates))

        log.info("Stability eval: fitting baseline (seed=%d)", seeds[0])
        baseline_model = _build_model(self._cfg, seeds[0])
        baseline_topics, _ = baseline_model.fit_transform(documents, embeddings)
        baseline = np.array(baseline_topics)

        nmi_scores, ari_scores = [], []
        for i, seed in enumerate(seeds[1:], 1):
            log.info("Replicate %d/%d (seed=%d)", i, n_replicates - 1, seed)
            try:
                rep_model = _build_model(self._cfg, seed)
                rep_topics, _ = rep_model.fit_transform(documents, embeddings)
                rep = np.array(rep_topics)
                nmi_scores.append(normalized_mutual_info_score(baseline, rep))
                ari_scores.append(adjusted_rand_score(baseline, rep))
                log.info("  NMI=%.3f  ARI=%.3f", nmi_scores[-1], ari_scores[-1])
            except Exception as exc:
                log.warning("Replicate %d failed: %s", i, exc)

        threshold = val_cfg["min_bootstrap_nmi"]
        mean_nmi = float(np.mean(nmi_scores)) if nmi_scores else 0.0
        passed = mean_nmi >= threshold

        log.info(
            "Stability: mean NMI=%.3f (threshold=%.2f) → %s",
            mean_nmi, threshold, "PASS" if passed else "FAIL",
        )
        return {
            "mean_nmi": mean_nmi,
            "std_nmi": float(np.std(nmi_scores)) if nmi_scores else 0.0,
            "mean_ari": float(np.mean(ari_scores)) if ari_scores else 0.0,
            "std_ari": float(np.std(ari_scores)) if ari_scores else 0.0,
            "all_nmi": nmi_scores,
            "all_ari": ari_scores,
            "n_replicates": len(nmi_scores),
            "min_nmi_threshold": threshold,
            "passed": passed,
        }
