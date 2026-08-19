"""RAG response cache for AtlasIQ V1.

Caches successful ``PipelineResult`` values (answers + abstentions) keyed by
question + pipeline settings. Entries expire after ``CacheConfig.ttl_seconds``
so repeated queries are cheap without serving forever-stale answers.

Eval / benchmarks should call ``answer_query(..., use_cache=False)``.
Re-indexing the corpus invalidates the entire cache.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from atlas.config import REPO_ROOT, AtlasConfig, config as default_config
from atlas.telemetry import StageTimings

CACHE_DIR = REPO_ROOT / ".cache"
CACHE_FILE = CACHE_DIR / "rag_response_cache.json"


def _normalize_question(question: str) -> str:
    return " ".join((question or "").strip().lower().split())


def cache_key(
    question: str,
    *,
    mode: str,
    threshold: float,
    rerank: bool,
    model_id: str,
    prompt_version: str,
) -> str:
    raw = "|".join(
        [
            _normalize_question(question),
            (mode or "").strip().lower(),
            f"{float(threshold):.4f}",
            "1" if rerank else "0",
            (model_id or "").strip(),
            (prompt_version or "").strip(),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load() -> Dict[str, Any]:
    if not CACHE_FILE.is_file():
        return {"version": 2, "entries": {}}
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"version": 2, "entries": {}}
        data.setdefault("entries", {})
        return data
    except Exception:  # noqa: BLE001
        return {"version": 2, "entries": {}}


def _save(data: Dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CACHE_FILE)


def purge_expired(*, ttl_seconds: float, now: Optional[float] = None) -> int:
    """Remove expired entries. Returns number removed."""
    now = time.time() if now is None else now
    data = _load()
    entries = data.get("entries") or {}
    keep: Dict[str, Any] = {}
    removed = 0
    for key, entry in entries.items():
        saved_at = float((entry or {}).get("saved_at") or 0)
        if ttl_seconds > 0 and (now - saved_at) > ttl_seconds:
            removed += 1
            continue
        keep[key] = entry
    if removed:
        data["entries"] = keep
        _save(data)
    return removed


def invalidate_all() -> None:
    """Drop the full response cache (e.g. after corpus re-index)."""
    data = {"version": 2, "entries": {}}
    _save(data)


def _serialize_result(result: Any) -> Dict[str, Any]:
    return {
        "answer": result.answer,
        "abstained": result.abstained,
        "citations": list(result.citations),
        "prompt_version": result.prompt_version,
        "model_id": result.model_id,
        "mode": result.mode,
        "prompt_name": result.prompt_name,
        "max_combined_score": result.max_combined_score,
        "similarity_threshold": result.similarity_threshold,
        "generation_called": result.generation_called,
        "error": result.error,
        "abstention_reason": result.abstention_reason,
        "abstention_kind": result.abstention_kind,
        "timings": result.timings.as_dict() if result.timings else {},
        "chunks": [
            {
                "chunk_id": c.chunk_id,
                "text": c.text,
                "source": c.source,
                "domain": c.domain,
                "chunk_index": c.chunk_index,
                "doc_id": c.doc_id,
                "similarity_score": c.similarity_score,
                "keyword_score": c.keyword_score,
                "combined_score": c.combined_score,
                "chroma_distance": c.chroma_distance,
                "accessed": c.accessed,
                "used": c.used,
                "rerank_score": c.rerank_score,
            }
            for c in (result.chunks or [])
        ],
    }


def _deserialize_result(payload: Dict[str, Any], *, age_seconds: float) -> Any:
    # Late import avoids circular dependency at module load.
    from atlas.pipeline import EvidenceChunk, PipelineResult

    timings_raw = payload.get("timings") or {}
    timings = StageTimings(
        retrieve_ms=float(timings_raw.get("retrieve_ms") or 0.0),
        rerank_ms=float(timings_raw.get("rerank_ms") or 0.0),
        generate_ms=float(timings_raw.get("generate_ms") or 0.0),
        total_ms=float(timings_raw.get("total_ms") or 0.0),
    )
    chunks: List[EvidenceChunk] = []
    for c in payload.get("chunks") or []:
        chunks.append(
            EvidenceChunk(
                chunk_id=c.get("chunk_id") or "",
                text=c.get("text") or "",
                source=c.get("source") or "",
                domain=c.get("domain") or "",
                chunk_index=int(c.get("chunk_index") or 0),
                doc_id=c.get("doc_id") or "",
                similarity_score=float(c.get("similarity_score") or 0.0),
                keyword_score=int(c.get("keyword_score") or 0),
                combined_score=float(c.get("combined_score") or 0.0),
                chroma_distance=float(c.get("chroma_distance") or 0.0),
                accessed=bool(c.get("accessed")),
                used=bool(c.get("used")),
                rerank_score=(
                    float(c["rerank_score"]) if c.get("rerank_score") is not None else None
                ),
            )
        )
    return PipelineResult(
        answer=payload.get("answer") or "",
        abstained=bool(payload.get("abstained")),
        chunks=chunks,
        citations=list(payload.get("citations") or []),
        timings=timings,
        prompt_version=payload.get("prompt_version") or "",
        model_id=payload.get("model_id") or "",
        mode=payload.get("mode") or "",
        prompt_name=payload.get("prompt_name") or "",
        max_combined_score=payload.get("max_combined_score"),
        similarity_threshold=payload.get("similarity_threshold"),
        generation_called=bool(payload.get("generation_called")),
        error=payload.get("error"),
        abstention_reason=payload.get("abstention_reason"),
        abstention_kind=payload.get("abstention_kind"),
        cache_hit=True,
        cache_age_seconds=age_seconds,
    )


def get_cached_result(
    question: str,
    *,
    mode: str,
    threshold: float,
    rerank: bool,
    cfg: Optional[AtlasConfig] = None,
) -> Optional[Any]:
    """Return a fresh cached ``PipelineResult``, or None if missing/expired/disabled."""
    cfg = cfg or default_config
    cache_cfg = cfg.cache
    if not cache_cfg.enabled:
        return None

    purge_expired(ttl_seconds=float(cache_cfg.ttl_seconds))

    key = cache_key(
        question,
        mode=mode,
        threshold=threshold,
        rerank=rerank,
        model_id=cfg.generation.model_id,
        prompt_version=cfg.prompts.version,
    )
    entry = (_load().get("entries") or {}).get(key)
    if not isinstance(entry, dict):
        return None
    saved_at = float(entry.get("saved_at") or 0)
    age = time.time() - saved_at
    if cache_cfg.ttl_seconds > 0 and age > float(cache_cfg.ttl_seconds):
        return None
    payload = entry.get("payload")
    if not isinstance(payload, dict) or payload.get("error"):
        return None
    return _deserialize_result(payload, age_seconds=age)


def put_cached_result(
    question: str,
    result: Any,
    *,
    mode: str,
    threshold: float,
    rerank: bool,
    cfg: Optional[AtlasConfig] = None,
) -> None:
    """Store a successful pipeline result. Never caches errors."""
    if result is None or getattr(result, "error", None):
        return
    cfg = cfg or default_config
    cache_cfg = cfg.cache
    if not cache_cfg.enabled:
        return

    key = cache_key(
        question,
        mode=mode,
        threshold=threshold,
        rerank=rerank,
        model_id=cfg.generation.model_id,
        prompt_version=cfg.prompts.version,
    )
    data = _load()
    entries = data.setdefault("entries", {})
    entries[key] = {
        "question": question,
        "saved_at": time.time(),
        "ttl_seconds": float(cache_cfg.ttl_seconds),
        "payload": _serialize_result(result),
    }
    max_entries = int(cache_cfg.max_entries)
    if max_entries > 0 and len(entries) > max_entries:
        oldest = sorted(entries.items(), key=lambda kv: kv[1].get("saved_at") or 0)
        for drop_key, _ in oldest[: len(entries) - max_entries]:
            entries.pop(drop_key, None)
    _save(data)


# Back-compat aliases used by earlier UI wiring / tests
def get_cached_payload(*args: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
    result = get_cached_result(*args, **kwargs)
    if result is None:
        return None
    return _serialize_result(result)


def put_cached_payload(
    question: str,
    payload: Dict[str, Any],
    *,
    mode: str,
    threshold: float,
    rerank: bool,
    cfg: Optional[AtlasConfig] = None,
) -> None:
    if not payload or payload.get("error"):
        return
    from atlas.pipeline import EvidenceChunk, PipelineResult

    chunks = []
    for i, c in enumerate(payload.get("chunks") or []):
        chunks.append(
            EvidenceChunk(
                chunk_id=c.get("chunk_id") or "",
                text=c.get("text") or "",
                source=c.get("source") or "",
                domain=c.get("domain") or "",
                chunk_index=int(c.get("chunk_index") or i),
                doc_id=c.get("doc_id") or "",
                similarity_score=float(c.get("similarity_score") or 0.0),
                keyword_score=int(c.get("keyword_score") or 0),
                combined_score=float(c.get("combined_score") or 0.0),
                chroma_distance=float(c.get("chroma_distance") or 0.0),
                accessed=bool(c.get("accessed", True)),
                used=bool(c.get("used")),
                rerank_score=None,
            )
        )
    timings_raw = payload.get("timings") or {}
    result = PipelineResult(
        answer=payload.get("answer") or "",
        abstained=bool(payload.get("abstained")),
        chunks=chunks,
        citations=list(payload.get("citations") or []),
        timings=StageTimings(
            retrieve_ms=float(timings_raw.get("retrieve_ms") or 0.0),
            rerank_ms=float(timings_raw.get("rerank_ms") or 0.0),
            generate_ms=float(timings_raw.get("generate_ms") or 0.0),
            total_ms=float(timings_raw.get("total_ms") or 0.0),
        ),
        prompt_version=payload.get("prompt_version") or "v1",
        model_id=payload.get("model_id") or "",
        mode=payload.get("mode") or mode,
        prompt_name=payload.get("prompt_name") or "",
        max_combined_score=payload.get("max_combined_score"),
        similarity_threshold=payload.get("similarity_threshold"),
        generation_called=bool(payload.get("generation_called")),
        abstention_reason=payload.get("abstention_reason"),
        abstention_kind=payload.get("abstention_kind"),
    )
    put_cached_result(
        question, result, mode=mode, threshold=threshold, rerank=rerank, cfg=cfg
    )
