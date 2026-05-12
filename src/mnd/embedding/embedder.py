"""Article embedding.

Single-model strategy per ADR-010: all-mpnet-base-v2 (768-d, training cutoff ~2020-2021).
The two-model Qwen3/mpnet strategy from ADR-001 has been superseded.

Look-ahead sensitivity check: compare NMI across pre-2021 and post-2021 sub-periods
using this single model — no second model needed.

The interface returns numpy arrays for downstream BERTopic compatibility.
"""
from __future__ import annotations

from typing import Literal

import numpy as np

from mnd.utils.config import load_config
from mnd.utils.logging import get_logger

log = get_logger(__name__)

ModelRole = Literal["primary"]


class Embedder:
    """Embedder for all-mpnet-base-v2 (single model per ADR-010).

    Use ``Embedder.from_config("primary")`` for all pipeline runs.
    """

    def __init__(
        self,
        model_name: str,
        *,
        revision: str = "main",
        instruction_aware: bool = False,
        instruction_prefix: str = "",
        max_seq_len: int = 512,
        device: str = "auto",
        fp16: bool = True,
        batch_size: int = 32,
    ) -> None:
        self.model_name = model_name
        self.revision = revision
        self.instruction_aware = instruction_aware
        self.instruction_prefix = instruction_prefix
        self.max_seq_len = max_seq_len
        self.device = device
        self.fp16 = fp16
        self.batch_size = batch_size
        self._model = None  # lazy

    @classmethod
    def from_config(cls, role: ModelRole = "primary") -> "Embedder":
        import os
        cfg = load_config()
        emb_cfg = cfg["embedding"][role]
        compute_cfg = cfg.get("compute", {})
        # MND_MAX_SEQ_LEN env var lets local MPS runs override the config value
        # (config.yaml defaults to 32768 for RCC; set to 512 in .env for MacBook Air)
        env_seq_len = os.environ.get("MND_MAX_SEQ_LEN")
        max_seq_len = int(env_seq_len) if env_seq_len else emb_cfg.get("max_seq_len", 32768)
        return cls(
            model_name=emb_cfg["model"],
            revision=emb_cfg.get("revision", "main"),
            instruction_aware=emb_cfg.get("instruction_aware", False),
            instruction_prefix=emb_cfg.get("instruction_prefix", ""),
            max_seq_len=max_seq_len,
            device=compute_cfg.get("embedding_device", "auto"),
            fp16=compute_cfg.get("embedding_fp16", True),
            batch_size=compute_cfg.get("embedding_batch_size", 32),
        )

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "sentence-transformers is required. `pip install sentence-transformers`."
            ) from exc

        log.info("Loading embedding model: %s @ %s", self.model_name, self.revision)
        device = self._resolve_device(self.device)
        kwargs: dict = {"revision": self.revision} if self.revision != "main" else {}
        self._model = SentenceTransformer(
            self.model_name,
            device=device,
            model_kwargs=kwargs,
        )
        self._model.max_seq_length = self.max_seq_len
        if self.fp16 and device.startswith("cuda"):
            self._model.half()

    @staticmethod
    def _resolve_device(device: str = "auto") -> str:
        """Resolve the embedding device, respecting the config/env value."""
        import os
        env_device = os.environ.get("MND_EMBEDDING_DEVICE", device)
        if env_device != "auto":
            return env_device
        try:
            import torch
        except ImportError:  # pragma: no cover
            return "cpu"
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    def encode(self, texts: list[str], *, show_progress: bool = True) -> np.ndarray:
        """Encode a batch of texts to embeddings.

        Applies the instruction prefix automatically when ``instruction_aware=True``.
        Returns float32 array of shape (N, D).
        """
        self._load()
        prepared = (
            [self.instruction_prefix + t for t in texts] if self.instruction_aware else texts
        )
        embeddings = self._model.encode(
            prepared,
            batch_size=self.batch_size,
            show_progress_bar=show_progress,
            convert_to_numpy=True,
            normalize_embeddings=True,  # cosine via inner product downstream
        )
        return embeddings.astype(np.float32, copy=False)


def prepare_text_for_embedding(title: str, body: str, max_tokens: int = 600) -> str:
    """Combine headline + truncated body. Token-counted truncation is
    handled by the model's tokenizer; we use a conservative whitespace-token
    approximation here so we don't have to load the tokenizer to chunk.
    """
    text = title.strip()
    if body:
        words = body.split()
        approx_body_words = max(0, max_tokens - len(text.split()))
        text = f"{text}. {' '.join(words[:approx_body_words])}"
    return text
