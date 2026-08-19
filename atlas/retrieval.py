"""Hybrid retrieval over Chroma collection ``atlasiq_v1``.

Proven scoring from ``8d28058:app.py``:
    combined = cosine_similarity + keyword_count * 0.15

Chroma returns cosine *distance*; V1 converts with:
    similarity = 1 - distance

T14B adds metadata-aware routing on top of hybrid scores when the query
contains explicit Module / Region / Framework identifiers. Hybrid
``combined_score`` is unchanged; ranking uses
``combined_score + metadata_boost``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set

import numpy as np
from chromadb.api.models.Collection import Collection

from atlas.config import AtlasConfig, config
from atlas.embeddings import encode_query, get_embedding_model
from atlas.routing import (
    QueryEntity,
    apply_metadata_routing,
    entity_source_hints,
    extract_query_entities,
    metadata_boost_for,
    ranking_score,
)
from atlas.store import collection_count, get_or_create_collection

# When identifiers are present, pull a wider semantic pool so sibling docs
# that would otherwise sit outside top_n can still be re-ranked.
ENTITY_CANDIDATE_FLOOR = 40


def diversify_by_query_entities(
    ranked: Sequence[RetrievedChunk],
    entities: Sequence[QueryEntity],
    top_k: int,
) -> List[RetrievedChunk]:
    """Ensure multi-entity queries keep at least one chunk per named entity.

    When a question names Module + Framework + Region, naive top_k can be
    dominated by two chunks from one sibling document and drop another
    required domain. Single-entity / no-entity queries are unchanged.
    """
    if top_k < 1:
        return []
    if len(entities) <= 1 or len(ranked) <= top_k:
        return list(ranked[:top_k])

    selected: List[RetrievedChunk] = []
    used: Set[str] = set()
    for ent in entities:
        if len(selected) >= top_k:
            break
        for c in ranked:
            if c.chunk_id in used:
                continue
            if metadata_boost_for(c.source, c.doc_id or "", [ent]) > 0:
                selected.append(c)
                used.add(c.chunk_id)
                break
    for c in ranked:
        if len(selected) >= top_k:
            break
        if c.chunk_id not in used:
            selected.append(c)
            used.add(c.chunk_id)
    return selected


@dataclass(frozen=True)
class RetrievedChunk:
    """One ranked retrieval hit for pipeline / Evidence Inspector."""

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
    metadata_boost: float = 0.0

    @property
    def ranking_score(self) -> float:
        return ranking_score(self.combined_score, self.metadata_boost)


def cosine_distance_to_similarity(distance: float) -> float:
    """Convert Chroma cosine distance to cosine similarity.

    For cosine space, Chroma reports distance where nearer neighbors have
    smaller distance. V1 uses::

        similarity = 1 - distance
    """
    return 1.0 - float(distance)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two 1D vectors (matches Chroma cosine space)."""
    a = np.asarray(a, dtype=np.float64).reshape(-1)
    b = np.asarray(b, dtype=np.float64).reshape(-1)
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def keyword_term_count(query: str, text: str) -> int:
    """Count query terms (len > 2) that appear in ``text`` (case-insensitive).

    Matches proven ``8d28058`` hybrid keyword behavior.
    """
    query_terms = [t.lower() for t in query.split() if len(t) > 2]
    lowered = text.lower()
    return sum(1 for term in query_terms if term in lowered)


def _chunk_from_parts(
    *,
    chunk_id: str,
    text: str,
    meta: Dict[str, Any],
    similarity: float,
    query: str,
    keyword_weight: float,
    entities: Sequence[QueryEntity],
) -> RetrievedChunk:
    kw = keyword_term_count(query, text)
    combined = float(similarity) + (kw * keyword_weight)
    source = str(meta.get("source", ""))
    doc_id = str(meta.get("doc_id", ""))
    boost = metadata_boost_for(source, doc_id, entities)
    return RetrievedChunk(
        chunk_id=str(chunk_id),
        text=text,
        source=source,
        domain=str(meta.get("domain", "")),
        chunk_index=int(meta.get("chunk_index", 0)),
        doc_id=doc_id,
        similarity_score=float(similarity),
        keyword_score=int(kw),
        combined_score=float(combined),
        chroma_distance=float(1.0 - float(similarity)),
        metadata_boost=float(boost),
    )


def _fetch_entity_seed_chunks(
    collection: Collection,
    entities: Sequence[QueryEntity],
    *,
    query: str,
    query_vec: np.ndarray,
    keyword_weight: float,
) -> List[RetrievedChunk]:
    """Load chunks whose ``source`` matches entity hints; score with real cosine.

    Uses stored Chroma embeddings so ``combined_score`` stays honest for the
    evidence gate (no fake distance=0 similarity).
    """
    seeds: List[RetrievedChunk] = []
    seen: Set[str] = set()
    for entity in entities:
        for source_path in entity_source_hints(entity):
            try:
                got = collection.get(
                    where={"source": {"$eq": source_path}},
                    include=["documents", "metadatas", "embeddings"],
                )
            except Exception:
                continue
            ids = got.get("ids") or []
            documents = got.get("documents") or []
            metadatas = got.get("metadatas") or []
            embeddings = got.get("embeddings")
            if embeddings is None:
                embeddings = []
            for i, cid in enumerate(ids):
                if cid in seen:
                    continue
                seen.add(cid)
                text = documents[i] or ""
                meta = metadatas[i] or {}
                if i >= len(embeddings):
                    continue
                emb = np.asarray(embeddings[i])
                if emb.size == 0:
                    continue
                sim = cosine_similarity(query_vec, emb)
                seeds.append(
                    _chunk_from_parts(
                        chunk_id=str(cid),
                        text=text,
                        meta=meta,
                        similarity=sim,
                        query=query,
                        keyword_weight=keyword_weight,
                        entities=entities,
                    )
                )
    return seeds


def retrieve(
    query: str,
    *,
    top_k: Optional[int] = None,
    top_n: Optional[int] = None,
    collection: Optional[Collection] = None,
    model: Optional[Any] = None,
    cfg: Optional[AtlasConfig] = None,
) -> List[RetrievedChunk]:
    """Retrieve and hybrid-rank chunks for ``query``.

    1. Encode query
    2. Fetch ``top_n`` Chroma candidates (cosine distance); expand pool when
       query entities are present
    3. Convert distance → similarity (``1 - distance``)
    4. Keyword count (terms len > 2)
    5. ``combined = similarity + keyword_count * keyword_weight``  (unchanged)
    6. Optional metadata boost for Module/Region/Framework matches
    7. Sort by ``combined + metadata_boost`` descending; return ``top_k``
    """
    cfg = cfg or config
    k = cfg.retrieval.top_k if top_k is None else int(top_k)
    n = cfg.retrieval.top_n if top_n is None else int(top_n)
    if n < k:
        raise ValueError(f"top_n ({n}) must be >= top_k ({k})")
    if k < 1:
        return []

    entities = extract_query_entities(query)
    if entities:
        n = max(n, ENTITY_CANDIDATE_FLOOR)

    collection = collection or get_or_create_collection(cfg=cfg)
    if model is None:
        model = get_embedding_model()
    if model is None:
        raise RuntimeError("Embedding model is unavailable; cannot retrieve.")

    query_vec = encode_query(query, model=model)
    n_results = min(n, max(collection_count(collection), 1))
    weight = float(cfg.retrieval.keyword_weight)

    raw = collection.query(
        query_embeddings=[query_vec.tolist()],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )

    ids = (raw.get("ids") or [[]])[0]
    documents = (raw.get("documents") or [[]])[0]
    metadatas = (raw.get("metadatas") or [[]])[0]
    distances = (raw.get("distances") or [[]])[0]

    by_id: Dict[str, RetrievedChunk] = {}
    for i, chunk_id in enumerate(ids):
        cid = str(chunk_id)
        sim = cosine_distance_to_similarity(float(distances[i]))
        by_id[cid] = _chunk_from_parts(
            chunk_id=cid,
            text=documents[i] or "",
            meta=metadatas[i] or {},
            similarity=sim,
            query=query,
            keyword_weight=weight,
            entities=entities,
        )

    # Inject exact metadata matches so sibling docs outside the semantic
    # neighborhood still enter the candidate pool (with real cosine scores).
    if entities:
        for seed in _fetch_entity_seed_chunks(
            collection,
            entities,
            query=query,
            query_vec=query_vec,
            keyword_weight=weight,
        ):
            existing = by_id.get(seed.chunk_id)
            if existing is None:
                by_id[seed.chunk_id] = seed
            elif seed.ranking_score > existing.ranking_score:
                by_id[seed.chunk_id] = seed

    candidates = list(by_id.values())

    def _rebuild(c: RetrievedChunk, boost: float, _rank: float) -> RetrievedChunk:
        return RetrievedChunk(
            chunk_id=c.chunk_id,
            text=c.text,
            source=c.source,
            domain=c.domain,
            chunk_index=c.chunk_index,
            doc_id=c.doc_id,
            similarity_score=c.similarity_score,
            keyword_score=c.keyword_score,
            combined_score=c.combined_score,
            chroma_distance=c.chroma_distance,
            metadata_boost=float(boost),
        )

    ranked = apply_metadata_routing(
        candidates,
        entities,
        rebuild=_rebuild,
    )
    ranked.sort(key=lambda c: (-c.ranking_score, c.source, c.chunk_id))
    return diversify_by_query_entities(ranked, entities, k)
