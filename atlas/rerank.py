"""Optional cross-encoder reranking for AtlasIQ V1.

Default is OFF (``config.rerank.enabled``). When disabled, candidates are
returned unchanged and the cross-encoder is never loaded.

When enabled, scores query/document pairs with
``cross-encoder/ms-marco-MiniLM-L-6-v2`` and sorts descending by that score.
Hybrid retrieval scores on each candidate are preserved.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import List, Optional, Sequence, Union

from atlas.config import AtlasConfig, config
from atlas.retrieval import RetrievedChunk

# Module-level load flag for verification (lazy — remains False until enabled path runs)
_cross_encoder_load_attempted: bool = False


@dataclass(frozen=True)
class RerankedChunk:
    """Retrieved candidate plus optional cross-encoder score."""

    chunk_id: str
    text: str
    source: str
    domain: str
    chunk_index: int
    doc_id: str
    similarity_score: float
    keyword_score: int
    combined_score: float
    chroma_distance: float
    rerank_score: Optional[float] = None


Candidate = Union[RetrievedChunk, RerankedChunk]


def is_cross_encoder_loaded() -> bool:
    """True only after a successful lazy load of the cross-encoder."""
    return get_cross_encoder.cache_info().currsize > 0


def cross_encoder_load_attempted() -> bool:
    """True if ``get_cross_encoder`` was invoked (even if load failed)."""
    return _cross_encoder_load_attempted


@lru_cache(maxsize=1)
def get_cross_encoder(model_id: Optional[str] = None):
    """Lazily load and cache the configured cross-encoder model."""
    global _cross_encoder_load_attempted
    _cross_encoder_load_attempted = True
    from sentence_transformers import CrossEncoder

    mid = model_id or config.rerank.model_id
    return CrossEncoder(mid)


def _as_reranked(chunk: Candidate, rerank_score: Optional[float] = None) -> RerankedChunk:
    return RerankedChunk(
        chunk_id=chunk.chunk_id,
        text=chunk.text,
        source=chunk.source,
        domain=chunk.domain,
        chunk_index=chunk.chunk_index,
        doc_id=chunk.doc_id,
        similarity_score=chunk.similarity_score,
        keyword_score=chunk.keyword_score,
        combined_score=chunk.combined_score,
        chroma_distance=chunk.chroma_distance,
        rerank_score=rerank_score,
    )


def rerank(
    query: str,
    candidates: Sequence[Candidate],
    *,
    enabled: Optional[bool] = None,
    cfg: Optional[AtlasConfig] = None,
) -> List[Candidate]:
    """Optionally rerank retrieval candidates with a cross-encoder.

    When ``enabled`` is False (default from config), returns ``candidates``
    unchanged (same objects, same order) and does not load any model.

    When enabled, returns ``RerankedChunk`` instances sorted by
    ``rerank_score`` descending. Original hybrid fields are preserved.
    """
    cfg = cfg or config
    use_rerank = cfg.rerank.enabled if enabled is None else bool(enabled)

    if not use_rerank:
        # Passthrough: identical content and ordering; no model load
        return list(candidates)

    if not candidates:
        return []

    encoder = get_cross_encoder(cfg.rerank.model_id)
    pairs = [(query, c.text) for c in candidates]
    scores = encoder.predict(pairs)

    ranked = [
        _as_reranked(chunk, rerank_score=float(score))
        for chunk, score in zip(candidates, scores)
    ]
    ranked.sort(key=lambda c: c.rerank_score if c.rerank_score is not None else float("-inf"), reverse=True)
    return ranked
