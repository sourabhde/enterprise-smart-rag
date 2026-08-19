"""RAG response cache — no LLM required."""

from dataclasses import replace

from atlas.answer_cache import (
    cache_key,
    get_cached_result,
    invalidate_all,
    put_cached_result,
)
from atlas.config import AtlasConfig, CacheConfig
from atlas.pipeline import PipelineResult
from atlas.telemetry import StageTimings


def _cfg(ttl: int = 3600, enabled: bool = True) -> AtlasConfig:
    return AtlasConfig(cache=CacheConfig(enabled=enabled, ttl_seconds=ttl, max_entries=50))


def _result(answer: str = "ok") -> PipelineResult:
    return PipelineResult(
        answer=answer,
        abstained=False,
        chunks=[],
        citations=["C1"],
        timings=StageTimings(),
        prompt_version="v1",
        model_id="test-model",
        mode="grounded",
        prompt_name="answer_grounded",
        generation_called=True,
    )


def test_cache_roundtrip(tmp_path, monkeypatch):
    import atlas.answer_cache as ac

    monkeypatch.setattr(ac, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(ac, "CACHE_FILE", tmp_path / "rag_response_cache.json")
    cfg = _cfg()

    q = "What is the annual base subscription for Module 12?"
    put_cached_result(
        q, _result("$53,000 and 25 seats"), mode="grounded", threshold=0.75, rerank=False, cfg=cfg
    )
    hit = get_cached_result(q, mode="grounded", threshold=0.75, rerank=False, cfg=cfg)
    assert hit is not None
    assert hit.cache_hit is True
    assert hit.answer == "$53,000 and 25 seats"

    # Errors must not be cached
    put_cached_result(
        "other",
        replace(_result(""), error="429", generation_called=False),
        mode="grounded",
        threshold=0.75,
        rerank=False,
        cfg=cfg,
    )
    assert get_cached_result("other", mode="grounded", threshold=0.75, rerank=False, cfg=cfg) is None


def test_cache_ttl_expires(tmp_path, monkeypatch):
    import atlas.answer_cache as ac
    import time

    monkeypatch.setattr(ac, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(ac, "CACHE_FILE", tmp_path / "rag_response_cache.json")
    cfg = _cfg(ttl=1)

    put_cached_result(
        "ttl q", _result("fresh"), mode="grounded", threshold=0.75, rerank=False, cfg=cfg
    )
    assert get_cached_result("ttl q", mode="grounded", threshold=0.75, rerank=False, cfg=cfg)

    # Force age past TTL
    data = ac._load()
    key = next(iter(data["entries"]))
    data["entries"][key]["saved_at"] = time.time() - 5
    ac._save(data)

    assert get_cached_result("ttl q", mode="grounded", threshold=0.75, rerank=False, cfg=cfg) is None


def test_invalidate_all(tmp_path, monkeypatch):
    import atlas.answer_cache as ac

    monkeypatch.setattr(ac, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(ac, "CACHE_FILE", tmp_path / "rag_response_cache.json")
    cfg = _cfg()
    put_cached_result("q", _result(), mode="grounded", threshold=0.75, rerank=False, cfg=cfg)
    invalidate_all()
    assert get_cached_result("q", mode="grounded", threshold=0.75, rerank=False, cfg=cfg) is None


def test_cache_key_normalizes_whitespace():
    a = cache_key(
        "Hello   World",
        mode="grounded",
        threshold=0.75,
        rerank=False,
        model_id="m",
        prompt_version="v1",
    )
    b = cache_key(
        "hello world",
        mode="grounded",
        threshold=0.75,
        rerank=False,
        model_id="m",
        prompt_version="v1",
    )
    assert a == b
