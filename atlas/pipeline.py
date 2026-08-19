"""Shared AtlasIQ V1 query pipeline (UI- and eval-independent).

Flow: mode → retrieve → optional rerank → score gate → generate | abstain.

Abstention uses ``prompts/v1/abstention.txt`` metadata and a deterministic
user-facing message. When the score gate fails, Groq is not called.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence, Union

from atlas.config import AtlasConfig, ExecutionMode, config
from atlas.generation import (
    GenerationError,
    generate_general,
    generate_grounded,
    parse_citations,
    render_abstention_prompt,
)
from atlas.rerank import RerankedChunk, rerank
from atlas.retrieval import RetrievedChunk, retrieve
from atlas.routing import extract_query_entities, metadata_boost_for
from atlas.store import collection_count
from atlas.telemetry import StageTimings, TelemetryClock

Candidate = Union[RetrievedChunk, RerankedChunk]


@dataclass(frozen=True)
class EvidenceChunk:
    """Evidence Inspector row: retrieval scores plus access/use flags."""

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
    accessed: bool
    used: bool
    rerank_score: Optional[float] = None


@dataclass
class PipelineResult:
    """Structured result shared by Streamlit UI and ``run_eval.py``."""

    answer: str
    abstained: bool
    chunks: List[EvidenceChunk]
    citations: List[str]
    timings: StageTimings
    prompt_version: str
    model_id: str
    mode: str = ""
    prompt_name: str = ""
    max_combined_score: Optional[float] = None
    similarity_threshold: Optional[float] = None
    generation_called: bool = False
    error: Optional[str] = None
    # Surfaced for UI only — same reasons already used in abstention copy; gate logic unchanged.
    abstention_reason: Optional[str] = None
    abstention_kind: Optional[str] = None
    cache_hit: bool = False
    cache_age_seconds: Optional[float] = None


def _normalize_mode(mode: Union[str, ExecutionMode, None]) -> ExecutionMode:
    if mode is None:
        return config.default_execution_mode
    if isinstance(mode, ExecutionMode):
        return mode
    key = str(mode).strip().lower()
    if key in ("grounded", "private"):
        return ExecutionMode.GROUNDED
    if key == "general":
        return ExecutionMode.GENERAL
    if key == "auto":
        return ExecutionMode.AUTO
    raise ValueError(f"Unknown execution mode: {mode!r}")


def _should_run_rag(mode: ExecutionMode, cfg: AtlasConfig) -> bool:
    if mode == ExecutionMode.GROUNDED:
        return True
    if mode == ExecutionMode.GENERAL:
        return False
    # AUTO: grounded retrieval when the index has content
    return collection_count(cfg=cfg) > 0


def _gate_score(chunks: Sequence[Candidate]) -> float:
    """Score used for the V1 abstention gate.

    Uses ``combined_score + metadata_boost`` (ranking score) so T14B entity
    routing can pass the gate when the correct Module/Region/Framework document
    is retrieved even if raw hybrid similarity is below the numeric threshold.
    Hybrid ``combined_score`` itself is unchanged.
    """
    if not chunks:
        return 0.0
    scores: List[float] = []
    for c in chunks:
        boost = float(getattr(c, "metadata_boost", 0.0) or 0.0)
        scores.append(float(c.combined_score) + boost)
    return max(scores)


def _passes_gate(chunks: Sequence[Candidate], threshold: float) -> bool:
    return _gate_score(chunks) >= threshold


def _entity_evidence_missing(question: str, chunks: Sequence[Candidate]) -> bool:
    """True when the query names Module/Region/Framework IDs but no ranked chunk matches.

    Prevents high-scoring sibling near-misses (e.g. Framework 99 → Framework 10)
    from passing the combined_score gate. Does not change the hybrid formula or
    the numeric threshold; it is an additional evidence-sufficiency check.
    """
    entities = extract_query_entities(question)
    if not entities:
        return False
    if not chunks:
        return True
    for c in chunks:
        if metadata_boost_for(c.source, getattr(c, "doc_id", "") or "", entities) > 0:
            return False
    return True


# Customer-specific commercial requests (negotiated deals, named accounts) are
# outside the V1 list-price / policy / SLA corpus. Hard-abstain before generation
# when the named party / negotiated fact is not present in retrieved evidence.
_CUSTOMER_COMMERCIAL_INTENT = re.compile(
    r"(?i)\b("
    r"privately\s+negotiated|"
    r"pre[- ]?negotiated|"
    r"negotiated\s+(?:price|discount|rate|fee|subscription|deal|contract|terms?)|"
    r"customer[- ]specific|"
    r"account[- ]specific|"
    r"privately\s+agreed|"
    r"signed\s+msa|"
    r"msa\s+(?:liability\s+)?carve[- ]?out|"
    r"partner\s+margin|"
    r"reseller\s+program|"
    r"professional[- ]services\s+day\s+rate|"
    r"soc\s*2|"
    r"japanese[- ]language"
    r")\b"
)
_NAMED_PARTY = re.compile(
    r"(?i)\b([A-Z][a-zA-Z]+(?:\s+(?:Corporation|Corp\.?|Inc\.?|Ltd\.?|LLC|Company))?)"
    r"(?:['’]s)?\b"
)
_NAMED_PARTY_SKIP = {
    "module",
    "region",
    "framework",
    "what",
    "which",
    "when",
    "where",
    "under",
    "account",
    "executive",
    "volume",
    "tier",
    "base",
    "platform",
    "annual",
    "list",
    "price",
    "discount",
    "regional",
    "sales",
    "director",
    "vice",
    "president",
    "global",
    "enterprise",
    "atlas",
    "atlasiq",
}


def _customer_specific_evidence_missing(
    question: str, chunks: Sequence[Candidate]
) -> bool:
    """True when the question asks for a customer-specific commercial fact absent from evidence.

    Does not fire on ordinary list-price / policy / SLA questions. Avoids soft
    LLM refusals after retrieving a related SKU (e.g. Module 12 for an Acme deal).
    """
    if not question or not _CUSTOMER_COMMERCIAL_INTENT.search(question):
        return False

    evidence_text = " ".join(
        f"{getattr(c, 'text', '') or ''} {getattr(c, 'source', '') or ''}"
        for c in chunks
    ).lower()

    parties: List[str] = []
    for match in _NAMED_PARTY.finditer(question):
        name = match.group(1).strip()
        first = name.split()[0].lower()
        if first in _NAMED_PARTY_SKIP:
            continue
        if extract_query_entities(name):
            continue
        parties.append(name)

    if parties:
        for party in parties:
            if party.lower() not in evidence_text:
                return True
        return False

    # Intent without a named party (e.g. pre-negotiated combo schedule): abstain
    # unless evidence itself discusses negotiation / customer-specific terms.
    if "negotiat" in evidence_text or "customer-specific" in evidence_text:
        return False
    return True


# Underspecified singular commercial asks with no Module/Region/Framework ID.
# These retrieve conflicting siblings and should hard-abstain in V1 grounded mode.
_UNDERSPECIFIED_PATTERNS = (
    re.compile(
        r"(?i)^what is the (?:cost of the )?base platform subscription\b"
    ),
    re.compile(
        r"(?i)^what is the maximum (?:ae|account executive)(?:'s)? "
        r"(?:discretionary )?discount\b"
    ),
    re.compile(r"(?i)^what discount can sales approve\??$"),
    re.compile(r"(?i)^what is the list price\??$"),
)


def _underspecified_without_entity(question: str) -> bool:
    q = (question or "").strip()
    if not q or extract_query_entities(q):
        return False
    return any(p.search(q) for p in _UNDERSPECIFIED_PATTERNS)


_UNSUPPORTED_TOPIC = re.compile(
    r"(?i)\b("
    r"renewal\s+uplift|"
    r"negotiat\w*.{0,60}uplift|"
    r"pre[- ]?approved\s+package|"
    r"package\s+sku|"
    r"\bsku\s+code\b|"
    r"fy\s*202[7-9]|"
    r"fy\s*20[3-9]\d|"
    r"future.{0,30}(?:list\s+)?price|"
    r"salesforce|"
    r"competitor|"
    r"side[- ]by[- ]side"
    r")\b"
)


def _unsupported_topic_request(question: str, chunks: Sequence[Candidate]) -> bool:
    """Hard-abstain on clearly out-of-corpus topics even if a Module/Region is named."""
    if not question or not _UNSUPPORTED_TOPIC.search(question):
        return False
    evidence = " ".join(
        (getattr(c, "text", "") or "") for c in chunks
    ).lower()
    # If evidence already contains the rare topic, allow generation
    markers = (
        "renewal uplift",
        "sku code",
        "salesforce",
        "fy2027",
        "fy2028",
        "pre-approved package",
        "preapproved package",
    )
    if any(m in evidence for m in markers):
        return False
    return True


def _format_abstention_answer(
    question: str,
    *,
    reason: str,
    threshold: float,
) -> str:
    """Deterministic user-facing abstention (no LLM). Aligns with abstention.txt."""
    return (
        "AtlasIQ cannot provide a reliable answer from the available evidence. "
        f"{reason} "
        f"Configured evidence threshold: {threshold}. "
        "Grounded answers require sufficient matching evidence from the indexed "
        "knowledge corpus. You may rephrase the question, specify a document domain "
        "(SKU, policy, or legal/SLA), or confirm that relevant documents have been indexed."
    )


def _to_evidence(
    chunks: Sequence[Candidate],
    *,
    accessed: bool,
    used_ids: Optional[set] = None,
) -> List[EvidenceChunk]:
    used_ids = used_ids or set()
    rows: List[EvidenceChunk] = []
    for c in chunks:
        rerank_score = getattr(c, "rerank_score", None)
        rows.append(
            EvidenceChunk(
                chunk_id=c.chunk_id,
                text=c.text,
                source=c.source,
                domain=c.domain,
                chunk_index=c.chunk_index,
                doc_id=c.doc_id,
                similarity_score=float(c.similarity_score),
                keyword_score=int(c.keyword_score),
                combined_score=float(c.combined_score),
                chroma_distance=float(c.chroma_distance),
                accessed=accessed,
                used=c.chunk_id in used_ids,
                rerank_score=float(rerank_score) if rerank_score is not None else None,
            )
        )
    return rows


def _citation_used_ids(citations: Sequence[str], chunks: Sequence[Candidate]) -> set:
    """Map ``[C1]`` → first chunk, etc., based on ranked context order."""
    used: set = set()
    for label in citations:
        if len(label) >= 2 and label[0] == "C" and label[1:].isdigit():
            idx = int(label[1:]) - 1
            if 0 <= idx < len(chunks):
                used.add(chunks[idx].chunk_id)
    return used


def answer_query(
    question: str,
    *,
    mode: Union[str, ExecutionMode, None] = None,
    cfg: Optional[AtlasConfig] = None,
    rerank_enabled: Optional[bool] = None,
    use_cache: Optional[bool] = None,
) -> PipelineResult:
    """Run the AtlasIQ V1 pipeline for a single question.

    Successful answers and abstentions are cached (TTL from ``cfg.cache``) unless
    ``use_cache=False`` (recommended for golden-set evaluation).
    """
    from atlas.answer_cache import get_cached_result, put_cached_result

    cfg = cfg or config
    exec_mode = _normalize_mode(mode)
    clock = TelemetryClock()
    threshold = float(cfg.retrieval.similarity_threshold)
    chunks: List[Candidate] = []
    do_cache = cfg.cache.enabled if use_cache is None else bool(use_cache)
    rerank_flag = (
        bool(cfg.rerank.enabled) if rerank_enabled is None else bool(rerank_enabled)
    )

    if do_cache:
        cached = get_cached_result(
            question,
            mode=exec_mode.value,
            threshold=threshold,
            rerank=rerank_flag,
            cfg=cfg,
        )
        if cached is not None:
            return cached

    try:
        if not _should_run_rag(exec_mode, cfg):
            with clock.span("generate"):
                gen = generate_general(question, cfg=cfg)
            timings = clock.finish()
            result = PipelineResult(
                answer=gen.answer,
                abstained=False,
                chunks=[],
                citations=gen.citations,
                timings=timings,
                prompt_version=gen.prompt_version,
                model_id=gen.model_id,
                mode=exec_mode.value,
                prompt_name=gen.prompt_name,
                max_combined_score=None,
                similarity_threshold=threshold,
                generation_called=True,
            )
            if do_cache:
                put_cached_result(
                    question,
                    result,
                    mode=exec_mode.value,
                    threshold=threshold,
                    rerank=rerank_flag,
                    cfg=cfg,
                )
            return result

        with clock.span("retrieve"):
            chunks = list(retrieve(question, cfg=cfg))

        with clock.span("rerank"):
            chunks = list(
                rerank(question, chunks, enabled=rerank_enabled, cfg=cfg)
            )

        max_combined = _gate_score(chunks)
        entity_miss = _entity_evidence_missing(question, chunks)
        customer_miss = _customer_specific_evidence_missing(question, chunks)
        underspec = _underspecified_without_entity(question)
        unsupported_topic = _unsupported_topic_request(question, chunks)
        if (
            entity_miss
            or customer_miss
            or underspec
            or unsupported_topic
            or not _passes_gate(chunks, threshold)
        ):
            if customer_miss:
                kind = "customer_specific"
                reason = (
                    "The question asks for a customer-specific or privately negotiated "
                    "commercial fact that is not present in the retrieved evidence."
                )
            elif unsupported_topic:
                kind = "unsupported_topic"
                reason = (
                    "The question requests information outside the indexed Sales/CPQ "
                    "corpus (for example future pricing, competitor comparisons, or "
                    "package codes that are not published in the evidence)."
                )
            elif underspec:
                kind = "underspecified"
                reason = (
                    "The question is underspecified (no Module/Region/Framework identifier) "
                    "and multiple catalog items could apply; AtlasIQ will not guess."
                )
            elif entity_miss:
                kind = "entity_miss"
                reason = (
                    "The question names a specific Module/Region/Framework identifier, "
                    "but none of the retrieved evidence matches that identifier."
                )
            elif not chunks:
                kind = "no_evidence"
                reason = "No retrieved chunks met the evidence threshold."
            else:
                kind = "score_gate"
                reason = (
                    f"Maximum combined retrieval score ({max_combined:.4f}) "
                    f"is below the configured threshold ({threshold})."
                )
            # Ensure abstention prompt file is loaded/rendered (contract), no LLM
            render_abstention_prompt(
                question,
                reason=reason,
                threshold=str(threshold),
                cfg=cfg,
            )
            answer = _format_abstention_answer(
                question, reason=reason, threshold=threshold
            )
            timings = clock.finish()
            result = PipelineResult(
                answer=answer,
                abstained=True,
                chunks=_to_evidence(chunks, accessed=True, used_ids=set()),
                citations=[],
                timings=timings,
                prompt_version=cfg.prompts.version,
                model_id=cfg.generation.model_id,
                mode=exec_mode.value,
                prompt_name="abstention",
                max_combined_score=max_combined,
                similarity_threshold=threshold,
                generation_called=False,
                abstention_reason=reason,
                abstention_kind=kind,
            )
            if do_cache:
                put_cached_result(
                    question,
                    result,
                    mode=exec_mode.value,
                    threshold=threshold,
                    rerank=rerank_flag,
                    cfg=cfg,
                )
            return result

        with clock.span("generate"):
            gen = generate_grounded(question, chunks, cfg=cfg)
        used_ids = _citation_used_ids(gen.citations, chunks)
        if not used_ids:
            used_ids = {c.chunk_id for c in chunks}
        timings = clock.finish()
        result = PipelineResult(
            answer=gen.answer,
            abstained=False,
            chunks=_to_evidence(chunks, accessed=True, used_ids=used_ids),
            citations=gen.citations,
            timings=timings,
            prompt_version=gen.prompt_version,
            model_id=gen.model_id,
            mode=exec_mode.value,
            prompt_name=gen.prompt_name,
            max_combined_score=max_combined,
            similarity_threshold=threshold,
            generation_called=True,
        )
        if do_cache:
            put_cached_result(
                question,
                result,
                mode=exec_mode.value,
                threshold=threshold,
                rerank=rerank_flag,
                cfg=cfg,
            )
        return result
    except (GenerationError, RuntimeError, ValueError) as exc:
        timings = clock.finish()
        return PipelineResult(
            answer="",
            abstained=False,
            chunks=_to_evidence(chunks, accessed=bool(chunks), used_ids=set()),
            citations=[],
            timings=timings,
            prompt_version=cfg.prompts.version,
            model_id=cfg.generation.model_id,
            mode=exec_mode.value,
            prompt_name="",
            max_combined_score=_gate_score(chunks) if chunks else None,
            similarity_threshold=threshold,
            generation_called=False,
            error=str(exc),
        )
