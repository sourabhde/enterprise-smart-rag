"""Evaluation-surface helpers for the Streamlit UI (no LLM calls)."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

# Preferred clean artifacts for public Evaluation surface (in display order).
PREFERRED_AUTHORITATIVE_RUNS: Tuple[str, ...] = (
    "run_v1_clean_full.json",
    "run_phase8_challenge_clean_v3.json",
)

DENY_NAME_FRAGMENTS: Tuple[str, ...] = (
    "archive_",
    "composed",
    "NON_AUTHORITATIVE",
    "patched",
    "partial_compose",
    "RATE_LIMITED",
)


def is_candidate_run_name(name: str) -> bool:
    if not name.startswith("run_") or not name.endswith(".json"):
        return False
    lowered = name.lower()
    return not any(frag.lower() in lowered for frag in DENY_NAME_FRAGMENTS)


def is_candidate_run(path: Path) -> bool:
    return is_candidate_run_name(path.name)


def run_authority(report: dict) -> Tuple[bool, str]:
    """Return (is_authoritative_display, status_label)."""
    if report.get("composed") or report.get("patched") or report.get("non_authoritative"):
        return False, "NON_AUTHORITATIVE"
    if report.get("clean_full_eval") is True or (report.get("aggregate") or {}).get(
        "clean_full_eval"
    ) is True:
        return True, "CLEAN"
    if report.get("clean_full_eval") is False or (report.get("aggregate") or {}).get(
        "clean_full_eval"
    ) is False:
        return False, "BLOCKED_OR_PARTIAL"
    return True, "UNVERIFIED_LEGACY"


def list_candidate_runs(results_dir: Path) -> List[Path]:
    if not results_dir.is_dir():
        return []
    return sorted(
        [p for p in results_dir.glob("run_*.json") if is_candidate_run(p)],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def order_runs_for_display(runs: Sequence[Path]) -> List[Path]:
    """Prefer known clean Phase 8/9 baselines, then remaining by mtime."""
    by_name = {p.name: p for p in runs}
    ordered: List[Path] = []
    for name in PREFERRED_AUTHORITATIVE_RUNS:
        if name in by_name:
            ordered.append(by_name[name])
    for p in runs:
        if p.name not in PREFERRED_AUTHORITATIVE_RUNS:
            ordered.append(p)
    return ordered


def deferred_phase9_note() -> str:
    """Deprecated: do not show internal phase notes in the product UI."""
    return ""
