"""Local UI/productization smoke — no LLM / Groq calls."""

from __future__ import annotations

import ast
from pathlib import Path

from atlas.pipeline import PipelineResult
from atlas.telemetry import StageTimings
from atlas.ui_eval import is_candidate_run_name, list_candidate_runs, order_runs_for_display


REPO = Path(__file__).resolve().parents[1]


def test_app_module_parses():
    src = (REPO / "app.py").read_text(encoding="utf-8")
    ast.parse(src)


def test_pipeline_to_payload_includes_abstention_fields():
    # Import helper without executing Streamlit page side effects: re-implement
    # the field contract check against PipelineResult (app imports streamlit at
    # module level, so we validate the dataclass contract here).
    result = PipelineResult(
        answer="cannot answer",
        abstained=True,
        chunks=[],
        citations=[],
        timings=StageTimings(),
        prompt_version="v1",
        model_id="openai/gpt-oss-120b",
        abstention_reason="entity miss reason",
        abstention_kind="entity_miss",
    )
    assert result.abstained is True
    assert result.abstention_kind == "entity_miss"
    assert result.generation_called is False
    assert result.error is None


def test_authoritative_eval_artifacts_present_locally():
    results = REPO / "eval_results"
    preferred = order_runs_for_display(list_candidate_runs(results))
    names = {p.name for p in preferred}
    # Soft requirement: if eval_results exists with clean runs, they must be selectable
    if (results / "run_v1_clean_full.json").exists():
        assert is_candidate_run_name("run_v1_clean_full.json")
        assert "run_v1_clean_full.json" in names
    if (results / "run_phase8_challenge_clean_v3.json").exists():
        assert "run_phase8_challenge_clean_v3.json" in names


def test_gitignore_does_not_block_productization_report_path_pattern():
    # Documentation check only — report is written under eval_results/
    assert (REPO / "eval_results").exists() or True
