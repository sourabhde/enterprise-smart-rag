"""Prompt loading and Groq generation for AtlasIQ V1.

Prompts are loaded from ``prompts/<version>/`` files. No inline prompt text.
Abstention *score gating* is owned by T10; this module can render
``abstention.txt`` but does not decide when to abstain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from groq import Groq

from atlas.config import AtlasConfig, config
from atlas.rerank import RerankedChunk
from atlas.retrieval import RetrievedChunk

Candidate = Union[RetrievedChunk, RerankedChunk]

PROMPT_FILES = {
    "answer_grounded": "answer_grounded.txt",
    "answer_general": "answer_general.txt",
    "abstention": "abstention.txt",
}


class PromptNotFoundError(FileNotFoundError):
    """Raised when a requested prompt file is missing."""


class GenerationError(RuntimeError):
    """Raised when Groq generation fails or configuration is incomplete."""


@dataclass(frozen=True)
class GenerationResult:
    """Structured generation output for later PipelineResult assembly."""

    answer: str
    prompt_version: str
    model_id: str
    citations: List[str] = field(default_factory=list)
    used_chunk_ids: List[str] = field(default_factory=list)
    context: str = ""
    prompt_name: str = ""
    mode: str = ""


def clean_llm_output(text: Optional[str]) -> Optional[str]:
    """Port of proven ``8d28058:app.py`` L73–80 output sanitization."""
    if not text:
        return text
    # Normalize unicode spaces (e.g. U+202F narrow no-break) used by some Groq models
    text = re.sub(r"[\u00a0\u202f\u2007\u2009\u200a]", " ", text)
    # Fix corrupted artifacts such as stray letters attached to percentages or currency
    text = re.sub(r'a(\d+)', r'\1%', text)
    # Fix spacing issues in large numbers like "1, 000" -> "1,000"
    text = re.sub(r'(\d),\s+(\d)', r'\1,\2', text)
    # Collapse "9 %" / "9  %" → "9%" for stable citation/key-fact matching
    text = re.sub(r"(\d)\s+%", r"\1%", text)
    return text


def parse_citations(text: str) -> List[str]:
    """Extract citation markers like ``C1`` from ``[C1]``, ``[C2]``, … in order.

    Also accepts fullwidth brackets ``【C1】`` used by some Groq chat models.
    Does not invent citations that are not present in ``text``.
    """
    if not text:
        return []
    # Preserve order of first occurrence; allow C10+ via digits
    seen = set()
    ordered: List[str] = []
    for match in re.finditer(r"(?:\[|【)(C\d+)(?:\]|】)", text):
        label = match.group(1)
        if label not in seen:
            seen.add(label)
            ordered.append(label)
    return ordered


@lru_cache(maxsize=32)
def load_prompt(name: str, version: Optional[str] = None) -> str:
    """Load a prompt file from ``prompts/<version>/``.

    ``name`` is a logical key (``answer_grounded``, ``answer_general``,
    ``abstention``) or a bare filename ending in ``.txt``.
    """
    ver = version or config.prompts.version
    filename = PROMPT_FILES.get(name, name)
    if not filename.endswith(".txt"):
        filename = f"{filename}.txt"
    if filename == "judge_faithfulness.txt":
        raise PromptNotFoundError(
            "judge_faithfulness.txt is reserved for evaluation (T13), "
            "not generation."
        )

    path = config.paths.prompts_dir / ver / filename
    if not path.is_file():
        raise PromptNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


def render_prompt(template: str, values: Dict[str, str]) -> str:
    """Substitute ``{{PLACEHOLDER}}`` tokens from the prompt contract.

    Only replaces placeholders present in ``values``. Unknown placeholders
    in the template are left unchanged so missing fields are visible.
    """
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered


def build_context_blocks(chunks: Sequence[Candidate]) -> str:
    """Build numbered evidence blocks in ranked order.

    Format::

        [C1] source=<source>
        <chunk text>

        [C2] source=<source>
        <chunk text>
    """
    blocks: List[str] = []
    for i, chunk in enumerate(chunks, start=1):
        source = getattr(chunk, "source", "") or ""
        text = (getattr(chunk, "text", "") or "").strip()
        blocks.append(f"[C{i}] source={source}\n{text}")
    return "\n\n".join(blocks)


def _get_groq_client(cfg: Optional[AtlasConfig] = None) -> Groq:
    cfg = cfg or config
    key = cfg.groq_api_key
    if not key:
        raise GenerationError(
            "GROQ_API_KEY is not set; cannot call the generation model."
        )
    return Groq(api_key=key)


def _chat_complete(system_or_user_prompt: str, *, cfg: Optional[AtlasConfig] = None) -> str:
    """Call Groq with configured model parameters. Raises GenerationError on failure."""
    cfg = cfg or config
    client = _get_groq_client(cfg)
    try:
        completion = client.chat.completions.create(
            model=cfg.generation.model_id,
            messages=[{"role": "user", "content": system_or_user_prompt}],
            temperature=cfg.generation.temperature,
            max_tokens=cfg.generation.max_tokens,
        )
    except Exception as exc:  # noqa: BLE001 — surface as GenerationError for T10
        msg = str(exc)
        lowered = msg.lower()
        if (
            "429" in msg
            or "rate limit" in lowered
            or "tokens per day" in lowered
            or "too many requests" in lowered
        ):
            raise GenerationError(
                "Groq rate limit / TPD exhausted (HTTP 429). "
                "Retry after quota reset; do not treat this as an evidence abstention. "
                f"Provider detail: {msg}"
            ) from exc
        raise GenerationError(f"Groq generation failed: {exc}") from exc

    try:
        raw = completion.choices[0].message.content
    except (IndexError, AttributeError) as exc:
        raise GenerationError("Groq response missing message content.") from exc

    cleaned = clean_llm_output(raw or "")
    return cleaned or ""


def generate_grounded(
    question: str,
    chunks: Sequence[Candidate],
    *,
    prompt_version: Optional[str] = None,
    cfg: Optional[AtlasConfig] = None,
) -> GenerationResult:
    """Generate an evidence-grounded answer with ``[C#]`` citations."""
    cfg = cfg or config
    version = prompt_version or cfg.prompts.version
    context = build_context_blocks(chunks)
    template = load_prompt("answer_grounded", version=version)
    prompt = render_prompt(
        template,
        {"CONTEXT": context, "QUESTION": question},
    )
    answer = _chat_complete(prompt, cfg=cfg)
    return GenerationResult(
        answer=answer,
        prompt_version=version,
        model_id=cfg.generation.model_id,
        citations=parse_citations(answer),
        used_chunk_ids=[c.chunk_id for c in chunks],
        context=context,
        prompt_name="answer_grounded",
        mode="grounded",
    )


def generate_general(
    question: str,
    *,
    prompt_version: Optional[str] = None,
    cfg: Optional[AtlasConfig] = None,
) -> GenerationResult:
    """Generate a non-grounded general-mode answer (no corpus context)."""
    cfg = cfg or config
    version = prompt_version or cfg.prompts.version
    template = load_prompt("answer_general", version=version)
    prompt = render_prompt(template, {"QUESTION": question})
    answer = _chat_complete(prompt, cfg=cfg)
    return GenerationResult(
        answer=answer,
        prompt_version=version,
        model_id=cfg.generation.model_id,
        citations=parse_citations(answer),
        used_chunk_ids=[],
        context="",
        prompt_name="answer_general",
        mode="general",
    )


def render_abstention_prompt(
    question: str,
    *,
    reason: str = "",
    threshold: str = "",
    prompt_version: Optional[str] = None,
    cfg: Optional[AtlasConfig] = None,
) -> str:
    """Render ``abstention.txt`` (no LLM call; score gate is T10)."""
    cfg = cfg or config
    version = prompt_version or cfg.prompts.version
    template = load_prompt("abstention", version=version)
    return render_prompt(
        template,
        {
            "QUESTION": question,
            "REASON": reason,
            "THRESHOLD": threshold,
        },
    )
