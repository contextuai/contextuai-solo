"""
Internal embedding service using all-MiniLM-L6-v2 (ONNX).

Bundled with the installer and loaded lazily on first use.
No API endpoints — intended for future RAG features.
"""

import logging
import os
import sys
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

try:
    import onnxruntime as ort

    _ORT_AVAILABLE = True
except ImportError:
    ort = None
    _ORT_AVAILABLE = False
    logger.warning(
        "onnxruntime is not installed — embedding service will be unavailable"
    )

try:
    from tokenizers import Tokenizer

    _TOKENIZERS_AVAILABLE = True
except ImportError:
    Tokenizer = None
    _TOKENIZERS_AVAILABLE = False
    logger.warning(
        "tokenizers is not installed — embedding service will be unavailable"
    )


_MODEL_SUBPATH = os.path.join("embedding", "all-MiniLM-L6-v2")
_MAX_LENGTH = 256
_EMBEDDING_DIM = 384


def _resolve_model_dir() -> Path:
    """Resolve model directory from PyInstaller bundle or dev-mode env var."""
    # PyInstaller frozen bundle
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / "models" / _MODEL_SUBPATH

    # Dev mode: MODELS_DIR env var, default ~/.contextuai-solo/models
    base = os.environ.get("MODELS_DIR", os.path.join(Path.home(), ".contextuai-solo", "models"))
    return Path(base) / _MODEL_SUBPATH


class EmbeddingService:
    """Lazy-loaded ONNX embedding service (all-MiniLM-L6-v2, 384-dim)."""

    def __init__(self) -> None:
        self._session: "ort.InferenceSession | None" = None
        self._tokenizer: "Tokenizer | None" = None
        self._loaded = False

    # ------------------------------------------------------------------
    # Lazy loading
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return

        if not _ORT_AVAILABLE or not _TOKENIZERS_AVAILABLE:
            raise RuntimeError(
                "onnxruntime and tokenizers must both be installed to use the embedding service"
            )

        model_dir = _resolve_model_dir()
        onnx_path = model_dir / "model.onnx"
        tokenizer_path = model_dir / "tokenizer.json"

        if not onnx_path.exists():
            raise FileNotFoundError(f"ONNX model not found at {onnx_path}")
        if not tokenizer_path.exists():
            raise FileNotFoundError(f"Tokenizer not found at {tokenizer_path}")

        logger.info("Loading embedding model from %s", model_dir)

        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self._session = ort.InferenceSession(str(onnx_path), opts, providers=["CPUExecutionProvider"])

        self._tokenizer = Tokenizer.from_file(str(tokenizer_path))
        self._tokenizer.enable_truncation(max_length=_MAX_LENGTH)
        self._tokenizer.enable_padding(length=_MAX_LENGTH, pad_id=0, pad_token="[PAD]")

        self._loaded = True
        logger.info("Embedding model loaded successfully")

    # ------------------------------------------------------------------
    # Inference helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _mean_pool(token_embeddings: np.ndarray, attention_mask: np.ndarray) -> np.ndarray:
        """Mean pooling: average token embeddings weighted by attention mask."""
        mask_expanded = np.expand_dims(attention_mask, axis=-1)  # (B, T, 1)
        summed = np.sum(token_embeddings * mask_expanded, axis=1)  # (B, D)
        counts = np.clip(mask_expanded.sum(axis=1), a_min=1e-9, a_max=None)  # (B, 1)
        return summed / counts

    @staticmethod
    def _normalize(vectors: np.ndarray) -> np.ndarray:
        """L2-normalize each row to unit length."""
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms = np.clip(norms, a_min=1e-12, a_max=None)
        return vectors / norms

    def _run(self, texts: list[str]) -> np.ndarray:
        """Tokenize, run ONNX inference, pool, and normalize."""
        self._ensure_loaded()

        encodings = self._tokenizer.encode_batch(texts)

        input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
        attention_mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
        token_type_ids = np.zeros_like(input_ids, dtype=np.int64)

        outputs = self._session.run(
            None,
            {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "token_type_ids": token_type_ids,
            },
        )

        token_embeddings = outputs[0]  # (B, T, 384)
        pooled = self._mean_pool(token_embeddings, attention_mask)
        return self._normalize(pooled)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def embed(self, text: str) -> list[float]:
        """Return a 384-dim unit-length embedding for a single text."""
        vector = self._run([text])[0]
        return vector.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return 384-dim unit-length embeddings for a batch of texts."""
        if not texts:
            return []
        vectors = self._run(texts)
        return vectors.tolist()


# Singleton instance
embedding_service = EmbeddingService()
