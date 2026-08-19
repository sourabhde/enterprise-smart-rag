"""Embedding model layer extracted from proven 8d28058:app.py.

Preserves SentenceTransformer('all-MiniLM-L6-v2') loading and try/except → None
fallback. Replaces @st.cache_resource with functools.lru_cache.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, List, Optional, Sequence, Union

import numpy as np
from sentence_transformers import SentenceTransformer

from atlas.config import config

EmbeddingArray = np.ndarray

# Set when load fails — surfaced in UI/readiness (never includes secrets).
_last_load_error: Optional[str] = None


def embedding_load_error() -> Optional[str]:
    """Return the last embedding load failure message, if any."""
    return _last_load_error


@lru_cache(maxsize=1)
def get_embedding_model() -> Optional[SentenceTransformer]:
    """Load and cache the V1 embedding model (all-MiniLM-L6-v2).

    Tries a normal load first, then ``local_files_only=True`` so a cached
    model works offline after ``scripts/warm_models.py`` has run once.
    """
    global _last_load_error
    model_id = config.embedding.model_id
    _last_load_error = None
    for local_only in (False, True):
        try:
            return SentenceTransformer(model_id, local_files_only=local_only)
        except Exception as exc:  # noqa: BLE001
            _last_load_error = str(exc)
    return None


# Backward-compatible alias for the proven name
load_embedding_model = get_embedding_model


def encode_texts(texts: Sequence[str], model: Optional[Any] = None) -> EmbeddingArray:
    """Encode one or more texts into a 2D array of shape (n, 384)."""
    if model is None:
        model = get_embedding_model()
    if model is None:
        raise RuntimeError("Embedding model is unavailable (failed to load).")
    if not texts:
        return np.zeros((0, config.embedding.dimension), dtype=np.float32)
    vectors = model.encode(list(texts))
    return np.asarray(vectors)


def encode_query(text: str, model: Optional[Any] = None) -> EmbeddingArray:
    """Encode a single query string into a 1D vector of length 384."""
    vectors = encode_texts([text], model=model)
    return vectors[0]
