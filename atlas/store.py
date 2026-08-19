"""Persistent Chroma vector store for AtlasIQ V1.

Isolates all Chroma I/O. Collection ``atlasiq_v1`` uses cosine space.
Embeddings are provided explicitly (no Chroma embedding function).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import chromadb
import numpy as np
from chromadb.api.models.Collection import Collection

from atlas.config import AtlasConfig, config
from atlas.embeddings import encode_texts, get_embedding_model
from atlas.ingest import ChunkRecord, ingest_corpus


def get_client(cfg: Optional[AtlasConfig] = None) -> chromadb.PersistentClient:
    """Return a PersistentClient rooted at the configured ``chroma_db`` path."""
    cfg = cfg or config
    path = Path(cfg.paths.chroma_dir)
    path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(path))


def get_or_create_collection(
    client: Optional[chromadb.PersistentClient] = None,
    cfg: Optional[AtlasConfig] = None,
) -> Collection:
    """Get or create the V1 collection with cosine distance semantics.

    Metadata ``hnsw:space=cosine`` applies when the collection is first created.
    Existing collections keep their original configuration (Chroma ignores
    metadata on get_or_create for an existing name).
    """
    cfg = cfg or config
    client = client or get_client(cfg)
    return client.get_or_create_collection(
        name=cfg.chroma.collection_name,
        metadata={"hnsw:space": cfg.chroma.distance_metric},
        embedding_function=None,
    )


def collection_count(
    collection: Optional[Collection] = None,
    cfg: Optional[AtlasConfig] = None,
) -> int:
    """Return the number of embeddings in the V1 collection."""
    collection = collection or get_or_create_collection(cfg=cfg)
    return int(collection.count())


def list_collection_names(client: Optional[chromadb.PersistentClient] = None) -> List[str]:
    """List all collection names in the persistent Chroma directory."""
    client = client or get_client()
    return sorted(c.name for c in client.list_collections())


def _metadata_for(record: ChunkRecord) -> Dict[str, Any]:
    return {
        "chunk_id": record.chunk_id,
        "doc_id": record.doc_id,
        "source": record.source,
        "domain": record.domain,
        "chunk_index": int(record.chunk_index),
    }


def index_chunks(
    chunks: Sequence[ChunkRecord],
    *,
    collection: Optional[Collection] = None,
    model: Optional[Any] = None,
    cfg: Optional[AtlasConfig] = None,
    batch_size: int = 64,
) -> int:
    """Upsert chunk records into ``atlasiq_v1``.

    Uses deterministic ``chunk_id`` values as Chroma IDs so re-indexing the
    same corpus does not create duplicates.

    Returns the number of records upserted in this call.
    """
    if not chunks:
        return 0

    cfg = cfg or config
    collection = collection or get_or_create_collection(cfg=cfg)
    if model is None:
        model = get_embedding_model()
    if model is None:
        raise RuntimeError("Embedding model is unavailable; cannot index.")

    texts = [c.text for c in chunks]
    embeddings = encode_texts(texts, model=model)
    if embeddings.ndim != 2 or embeddings.shape[1] != cfg.embedding.dimension:
        raise ValueError(
            f"Expected embeddings shape (n, {cfg.embedding.dimension}), "
            f"got {embeddings.shape}"
        )

    ids = [c.chunk_id for c in chunks]
    metadatas = [_metadata_for(c) for c in chunks]
    documents = texts

    # Upsert in batches for safer Chroma writes
    total = len(ids)
    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        collection.upsert(
            ids=ids[start:end],
            embeddings=embeddings[start:end].tolist(),
            documents=documents[start:end],
            metadatas=metadatas[start:end],
        )
    return total


def index_corpus(
    *,
    collection: Optional[Collection] = None,
    model: Optional[Any] = None,
    cfg: Optional[AtlasConfig] = None,
) -> Tuple[int, int]:
    """Ingest the markdown corpus and upsert all chunks into Chroma.

    Returns ``(chunk_count_upserted, collection_count_after)``.
    """
    cfg = cfg or config
    collection = collection or get_or_create_collection(cfg=cfg)
    if model is None:
        model = get_embedding_model()
    result = ingest_corpus(model=model)
    upserted = index_chunks(result.chunks, collection=collection, model=model, cfg=cfg)
    # Corpus changed — drop response cache so answers cannot stay stale.
    try:
        from atlas.answer_cache import invalidate_all

        invalidate_all()
    except Exception:  # noqa: BLE001
        pass
    return upserted, collection_count(collection)


def peek_sample(
    n: int = 1,
    *,
    collection: Optional[Collection] = None,
    cfg: Optional[AtlasConfig] = None,
) -> Dict[str, Any]:
    """Return a small sample from the V1 collection for verification."""
    collection = collection or get_or_create_collection(cfg=cfg)
    return collection.peek(limit=n)
