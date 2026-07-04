"""Tests for BERTopic model persistence (ADR-066 prereq for merge_models)."""
from __future__ import annotations

import numpy as np
import pytest

from mnd.clustering.bertopic_pipeline import BertopicPipeline
from mnd.utils.config import load_config


def test_save_model_without_fit_raises():
    """Guard: persisting before a fit is a clear error, not a silent no-op."""
    p = BertopicPipeline(load_config())
    with pytest.raises(RuntimeError, match="No fitted model"):
        p.save_model("/tmp/should_not_be_written")


@pytest.mark.integration
def test_fitted_model_round_trips(tmp_path):
    """Fit → save (safetensors) → reload yields the same topics (ADR-066)."""
    from bertopic import BERTopic

    cfg = load_config()
    cfg["clustering"]["umap"]["n_neighbors"] = 5
    cfg["clustering"]["hdbscan"]["min_cluster_size"] = 3
    rng = np.random.default_rng(0)
    emb = np.vstack([rng.normal(m, 0.05, (20, 32)) for m in (0.0, 3.0, 6.0)]).astype("float32")
    docs = [f"doc about topic {i // 20} number {i}" for i in range(60)]

    p = BertopicPipeline(cfg)
    result = p.fit_transform(docs, emb)
    model_dir = tmp_path / "topic_model"
    p.save_model(model_dir)

    assert (model_dir / "topics.json").exists()
    reloaded = BERTopic.load(str(model_dir))
    assert len(reloaded.get_topic_info()) == len(result["topic_info"])
