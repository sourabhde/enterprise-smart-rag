#!/usr/bin/env python3
"""Download/cache embedding (and optional rerank) models for offline demos."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.config import config  # noqa: E402
from atlas.embeddings import get_embedding_model  # noqa: E402


def main() -> None:
    get_embedding_model.cache_clear()
    model = get_embedding_model()
    if model is None:
        print("Failed to load embedding model.", file=sys.stderr)
        raise SystemExit(1)
    probe = model.encode(["warmup probe"])
    print(
        f"Embedding model ready: {config.embedding.model_id} "
        f"(dim={len(probe[0])})"
    )


if __name__ == "__main__":
    main()
