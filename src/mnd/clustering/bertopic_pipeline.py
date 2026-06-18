"""BERTopic clustering pipeline.

Wraps BERTopic with UMAP + HDBSCAN parameters from config and adds:
  - Class-based TF-IDF (c-TF-IDF) for cluster representation
  - Bootstrap stability evaluation: NMI + ARI across replicates

Every UMAP / HDBSCAN / c-TF-IDF parameter is the BERTopic v0.16.4 library
default (Grootendorst 2022, arXiv:2203.05794). Single granularity is the field
convention (Bybee et al. 2024 JF; Hansen et al. 2018 QJE; Larsen & Thorsrud
2019 JoE); stability is a reported diagnostic, not a gate.

All random seeds flow from config.reproducibility.global_random_seed.
"""
from __future__ import annotations

from typing import Any

import numpy as np

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
        reduce_frequent_words=cc.get("reduce_frequent_words", False),
        bm25_weighting=cc.get("bm25_weighting", False),
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
    """Manages BERTopic fitting and bootstrap stability evaluation.

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
        """Fit BERTopic and return single-granularity cluster assignments.

        Returns:
            topics      list[int] — topic per document (-1 = noise)
            topic_info  DataFrame — labels and representative terms
            n_topics    int       — topics found (excluding noise)
        """
        log.info("Fitting BERTopic on %d documents", len(documents))
        self._model = _build_model(self._cfg, self._seed)
        topics, _ = self._model.fit_transform(documents, embeddings)
        topics = list(topics)

        topic_info = self._model.get_topic_info()
        n_topics = int((topic_info["Topic"] >= 0).sum())
        log.info("Found %d topics (%d noise docs)", n_topics, topics.count(-1))

        return {
            "topics": topics,
            "topic_info": topic_info,
            "n_topics": n_topics,
        }

    # ------------------------------------------------------------------
    # Bootstrap stability (diagnostic, not a gate)
    # ------------------------------------------------------------------

    def evaluate_stability(
        self,
        documents: list[str],
        embeddings: np.ndarray,
        n_replicates: int | None = None,
    ) -> dict[str, Any]:
        """NMI + ARI across bootstrap replicates vs. a baseline fit.

        Seeds: config.validation.bootstrap_random_seed through +n_replicates.
        Replicate count: config.validation.bootstrap_replicates (Efron &
        Tibshirani 1993 recommend B >= 500-1000 for confidence intervals).
        Reported as a diagnostic, not a pass/fail gate.
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

        mean_nmi = float(np.mean(nmi_scores)) if nmi_scores else 0.0
        log.info("Stability: mean NMI=%.3f over %d replicates", mean_nmi, len(nmi_scores))
        return {
            "mean_nmi": mean_nmi,
            "std_nmi": float(np.std(nmi_scores)) if nmi_scores else 0.0,
            "mean_ari": float(np.mean(ari_scores)) if ari_scores else 0.0,
            "std_ari": float(np.std(ari_scores)) if ari_scores else 0.0,
            "all_nmi": nmi_scores,
            "all_ari": ari_scores,
            "n_replicates": len(nmi_scores),
        }
