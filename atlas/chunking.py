"""Semantic chunking extracted from proven 8d28058:app.py (semantic_chunk_text).

Algorithm preserved: sentence split → embeddings → adjacent cosine distance →
85th-percentile threshold → chunk join. No Streamlit dependency.
"""

from __future__ import annotations

from typing import Any, List

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity


def semantic_chunk_text(file_text: str, model: Any) -> List[str]:
    """Split ``file_text`` into semantic chunks using embedding-distance boundaries.

    ``model`` must expose ``encode(list[str])`` (e.g. SentenceTransformer).
    """
    raw_sentences = [s.strip() for s in file_text.replace('\n', ' ').split('.') if s.strip()]
    if not raw_sentences:
        return [file_text]

    if len(raw_sentences) == 1:
        return raw_sentences

    sentence_embeddings = model.encode(raw_sentences)

    distances = []
    for i in range(len(sentence_embeddings) - 1):
        sim = cosine_similarity(
            sentence_embeddings[i].reshape(1, -1),
            sentence_embeddings[i+1].reshape(1, -1)
        )[0][0]
        distances.append(1.0 - sim)

    threshold = np.percentile(distances, 85) if distances else 0.5

    chunks = []
    current_chunk = [raw_sentences[0]]

    for i, dist in enumerate(distances):
        if dist > threshold:
            chunks.append(". ".join(current_chunk) + ".")
            current_chunk = [raw_sentences[i+1]]
        else:
            current_chunk.append(raw_sentences[i+1])

    if current_chunk:
        chunks.append(". ".join(current_chunk) + ".")

    return [c.strip() for c in chunks if c.strip()]
