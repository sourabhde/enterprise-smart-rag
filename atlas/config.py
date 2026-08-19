"""AtlasIQ V1 configuration.

Single importable configuration layer. No retrieval, UI, or pipeline logic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    # python-dotenv is optional at import time; env vars may already be set.
    pass

# Repository root: atlas/config.py → atlas/ → repo root
REPO_ROOT = Path(__file__).resolve().parent.parent


class ExecutionMode(str, Enum):
    """Documented V1 mode semantics (behavior implemented later in pipeline)."""

    GROUNDED = "grounded"  # aka private: retrieval + evidence-only answers
    GENERAL = "general"  # non-grounded general knowledge
    AUTO = "auto"  # use grounded retrieval when index/evidence applicable


@dataclass(frozen=True)
class PathConfig:
    repo_root: Path = REPO_ROOT
    corpus_dir: Path = field(default_factory=lambda: REPO_ROOT / "corpus")
    chroma_dir: Path = field(default_factory=lambda: REPO_ROOT / "chroma_db")
    evaluation_dataset: Path = field(
        default_factory=lambda: REPO_ROOT / "evaluation_dataset.json"
    )
    prompts_dir: Path = field(default_factory=lambda: REPO_ROOT / "prompts")
    eval_results_dir: Path = field(default_factory=lambda: REPO_ROOT / "eval_results")


@dataclass(frozen=True)
class ChromaConfig:
    """Persistent vector store settings.

    Distance semantics: collection uses cosine space. Chroma typically returns
    cosine *distance* (lower is nearer). Callers must convert to similarity
    when gating against ``RetrievalConfig.similarity_threshold``
    (e.g. similarity ≈ 1 - distance for cosine, depending on Chroma version).
    This config does not perform that conversion.
    """

    collection_name: str = "atlasiq_v1"
    distance_metric: str = "cosine"
    # Explicit: threshold and hybrid scores in V1 are expressed as similarity
    # in [0, 1] (higher = more similar), not raw Chroma distance.
    score_semantics: str = "cosine_similarity"


@dataclass(frozen=True)
class EmbeddingConfig:
    model_id: str = "all-MiniLM-L6-v2"
    dimension: int = 384


@dataclass(frozen=True)
class GenerationConfig:
    provider: str = "groq"
    # Verified available via Groq models.list for this API key (2026-08-17).
    # Override with env GROQ_MODEL if needed; do not use xAI/Grok here.
    model_id: str = "openai/gpt-oss-120b"
    temperature: float = 0.1
    max_tokens: int = 700


@dataclass(frozen=True)
class RetrievalConfig:
    keyword_weight: float = 0.15
    top_k: int = 3
    # Candidate pool for hybrid rescore / optional rerank; must be >= top_k
    top_n: int = 10
    # V1 contract default from EVALUATION.md metadata example — not yet calibrated
    similarity_threshold: float = 0.75


@dataclass(frozen=True)
class RerankConfig:
    enabled: bool = False
    model_id: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"


@dataclass(frozen=True)
class PromptConfig:
    version: str = "v1"

    @property
    def version_dir(self) -> Path:
        return REPO_ROOT / "prompts" / self.version


@dataclass(frozen=True)
class CacheConfig:
    """RAG response cache (answers + abstentions).

    ``ttl_seconds`` is the refresh window — after this age a miss forces a live
    pipeline run so answers do not stay stale forever.
    Override with ``ATLASIQ_CACHE_ENABLED`` / ``ATLASIQ_CACHE_TTL_SECONDS``.
    """

    enabled: bool = True
    ttl_seconds: int = 3600  # 1 hour default refresh
    max_entries: int = 500


@dataclass(frozen=True)
class AtlasConfig:
    """Immutable AtlasIQ V1 configuration bundle."""

    paths: PathConfig = field(default_factory=PathConfig)
    chroma: ChromaConfig = field(default_factory=ChromaConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    rerank: RerankConfig = field(default_factory=RerankConfig)
    prompts: PromptConfig = field(default_factory=PromptConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    default_execution_mode: ExecutionMode = ExecutionMode.GROUNDED

    def __post_init__(self) -> None:
        if self.retrieval.top_n < self.retrieval.top_k:
            raise ValueError(
                f"retrieval.top_n ({self.retrieval.top_n}) must be >= "
                f"retrieval.top_k ({self.retrieval.top_k})"
            )

    @property
    def groq_api_key(self) -> Optional[str]:
        """Return GROQ_API_KEY from the environment, or None if unset.

        Never log or print this value.
        """
        key = os.getenv("GROQ_API_KEY")
        if key is None or key.strip() == "":
            return None
        return key

    @property
    def has_groq_api_key(self) -> bool:
        return self.groq_api_key is not None


def get_config() -> AtlasConfig:
    """Return the default V1 configuration instance.

    ``GROQ_MODEL`` (optional) overrides ``generation.model_id`` when set.
    ``GROQ_API_KEY`` is read at call time via ``AtlasConfig.groq_api_key``.
    Cache: ``ATLASIQ_CACHE_ENABLED``, ``ATLASIQ_CACHE_TTL_SECONDS``.
    """
    model_override = (os.getenv("GROQ_MODEL") or "").strip()
    cache_enabled_raw = (os.getenv("ATLASIQ_CACHE_ENABLED") or "1").strip().lower()
    cache_enabled = cache_enabled_raw not in {"0", "false", "no", "off"}
    ttl_raw = (os.getenv("ATLASIQ_CACHE_TTL_SECONDS") or "").strip()
    try:
        ttl = int(ttl_raw) if ttl_raw else 3600
    except ValueError:
        ttl = 3600
    ttl = max(0, ttl)
    cache = CacheConfig(enabled=cache_enabled, ttl_seconds=ttl)
    if model_override:
        return AtlasConfig(
            generation=GenerationConfig(model_id=model_override),
            cache=cache,
        )
    return AtlasConfig(cache=cache)


# Module-level default for convenient ``from atlas.config import config``
config = get_config()
