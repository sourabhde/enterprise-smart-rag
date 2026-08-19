#!/usr/bin/env python3
"""CLI: index AtlasIQ V1 markdown corpus into Chroma collection atlasiq_v1.

Reuses atlas.ingest / atlas.embeddings / atlas.store. Safe to re-run (upsert).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Allow running as ``python scripts/index_corpus.py`` from repo root
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from atlas.config import config
from atlas.embeddings import get_embedding_model
from atlas.ingest import discover_markdown_files, ingest_corpus
from atlas.store import (
    collection_count,
    get_client,
    get_or_create_collection,
    index_chunks,
    list_collection_names,
)


def main() -> int:
    started = time.perf_counter()

    model = get_embedding_model()
    if model is None:
        print("ERROR: embedding model failed to load.", file=sys.stderr)
        return 1

    files = discover_markdown_files()
    documents_discovered = len(files)

    result = ingest_corpus(model=model)
    chunks_produced = result.chunk_count

    client = get_client()
    collection = get_or_create_collection(client)
    upserted = index_chunks(result.chunks, collection=collection, model=model)
    final_count = collection_count(collection)

    elapsed_s = time.perf_counter() - started

    print("AtlasIQ corpus index")
    print(f"  corpus:              {config.paths.corpus_dir}")
    print(f"  collection:          {config.chroma.collection_name}")
    print(f"  documents discovered:{documents_discovered:5d}")
    print(f"  chunks produced:     {chunks_produced:5d}")
    print(f"  chunks upserted:     {upserted:5d}")
    print(f"  collection count:    {final_count:5d}")
    print(f"  elapsed:             {elapsed_s:.2f}s")
    if result.zero_chunk_documents:
        print(f"  zero-chunk docs:     {len(result.zero_chunk_documents)}")

    # Non-fatal visibility into other collections (do not modify them)
    others = [n for n in list_collection_names(client) if n != config.chroma.collection_name]
    if others:
        print(f"  other collections:   {', '.join(others)} (untouched)")

    if documents_discovered == 0:
        print("ERROR: no markdown files found under corpus/.", file=sys.stderr)
        return 1
    if final_count != chunks_produced:
        print(
            f"WARNING: collection count ({final_count}) != chunks produced ({chunks_produced})",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
