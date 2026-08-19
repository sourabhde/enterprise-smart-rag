"""LLM-as-judge for AtlasIQ V1 using prompts/v1/judge_faithfulness.txt."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from groq import Groq

from atlas.config import AtlasConfig, config
from atlas.generation import render_prompt
from atlas.pipeline import EvidenceChunk


class JudgeError(RuntimeError):
    """Raised when judge prompt load, API call, or JSON parse fails."""


@dataclass
class JudgeResult:
    faithfulness: Optional[int]
    completeness: Optional[int]
    citation_quality: Optional[int]
    rationale: Optional[str]
    raw_response: Optional[str]
    judge_called: bool
    error: Optional[str] = None
    prompt_version: str = "v1"
    model_id: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "faithfulness": self.faithfulness,
            "completeness": self.completeness,
            "citation_quality": self.citation_quality,
            "rationale": self.rationale,
            "judge_called": self.judge_called,
            "error": self.error,
            "prompt_version": self.prompt_version,
            "model_id": self.model_id,
            "raw_response": self.raw_response,
        }


def load_judge_prompt(cfg: Optional[AtlasConfig] = None) -> str:
    cfg = cfg or config
    path = cfg.paths.prompts_dir / cfg.prompts.version / "judge_faithfulness.txt"
    if not path.is_file():
        raise JudgeError(f"Judge prompt not found: {path}")
    return path.read_text(encoding="utf-8")


def format_retrieved_chunks(chunks: Sequence[EvidenceChunk]) -> str:
    if not chunks:
        return "(no retrieved evidence)"
    blocks: List[str] = []
    for i, c in enumerate(chunks, start=1):
        blocks.append(
            f"[C{i}] source={c.source}\n{(c.text or '').strip()}"
        )
    return "\n\n".join(blocks)


def _extract_json_object(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise JudgeError("Empty judge response.")
    # Strip optional markdown fences
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise JudgeError(f"Judge response is not JSON: {text[:200]!r}")
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise JudgeError(f"Malformed judge JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise JudgeError("Judge JSON root must be an object.")
    return data


def _score_or_none(value: Any, field: str) -> Optional[int]:
    if value is None:
        return None
    try:
        n = int(value)
    except (TypeError, ValueError) as exc:
        raise JudgeError(f"Judge field {field!r} is not an integer: {value!r}") from exc
    if n < 1 or n > 5:
        raise JudgeError(f"Judge field {field!r} out of range 1–5: {n}")
    return n


def judge_answer(
    *,
    question: str,
    answer: str,
    chunks: Sequence[EvidenceChunk],
    expected_context: str,
    cfg: Optional[AtlasConfig] = None,
) -> JudgeResult:
    """Run LLM-as-judge. On failure, scores are null and error is set."""
    cfg = cfg or config
    model_id = cfg.generation.model_id
    prompt_version = cfg.prompts.version

    if not cfg.groq_api_key:
        return JudgeResult(
            faithfulness=None,
            completeness=None,
            citation_quality=None,
            rationale=None,
            raw_response=None,
            judge_called=False,
            error="GROQ_API_KEY is not set; judge not called.",
            prompt_version=prompt_version,
            model_id=model_id,
        )

    try:
        template = load_judge_prompt(cfg)
        prompt = render_prompt(
            template,
            {
                "QUESTION": question,
                "RETRIEVED_CHUNKS": format_retrieved_chunks(chunks),
                "ANSWER": answer or "",
                "EXPECTED_CONTEXT": expected_context or "",
            },
        )
        client = Groq(api_key=cfg.groq_api_key)
        completion = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=500,
        )
        raw = completion.choices[0].message.content or ""
        data = _extract_json_object(raw)
        return JudgeResult(
            faithfulness=_score_or_none(data.get("faithfulness"), "faithfulness"),
            completeness=_score_or_none(data.get("completeness"), "completeness"),
            citation_quality=_score_or_none(
                data.get("citation_quality"), "citation_quality"
            ),
            rationale=str(data.get("rationale")) if data.get("rationale") is not None else None,
            raw_response=raw,
            judge_called=True,
            error=None,
            prompt_version=prompt_version,
            model_id=model_id,
        )
    except JudgeError as exc:
        return JudgeResult(
            faithfulness=None,
            completeness=None,
            citation_quality=None,
            rationale=None,
            raw_response=None,
            judge_called=True,
            error=str(exc),
            prompt_version=prompt_version,
            model_id=model_id,
        )
    except Exception as exc:  # noqa: BLE001
        return JudgeResult(
            faithfulness=None,
            completeness=None,
            citation_quality=None,
            rationale=None,
            raw_response=None,
            judge_called=True,
            error=f"Judge API/runtime failure: {exc}",
            prompt_version=prompt_version,
            model_id=model_id,
        )
