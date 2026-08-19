"""UI evaluation surface must not treat composed/archived runs as authoritative."""

from pathlib import Path

from atlas.ui_eval import (
    deferred_phase9_note,
    is_candidate_run_name,
    order_runs_for_display,
    run_authority,
)


def test_composed_archive_excluded_from_run_glob_logic():
    assert is_candidate_run_name("run_20260817T120000Z.json") is True
    assert is_candidate_run_name("run_v1_clean_full.json") is True
    assert (
        is_candidate_run_name("archive_composed_NON_AUTHORITATIVE_run_v1_frozen_final.json")
        is False
    )
    assert is_candidate_run_name("run_v1_frozen_final.json") is True
    assert is_candidate_run_name("run_RATE_LIMITED_partial.json") is False
    archived = Path(
        "eval_results/archive_composed_NON_AUTHORITATIVE_run_v1_frozen_final.json"
    )
    if archived.exists():
        assert is_candidate_run_name(archived.name) is False


def test_run_authority_clean_and_blocked():
    assert run_authority({"clean_full_eval": True, "aggregate": {}}) == (True, "CLEAN")
    assert run_authority({"aggregate": {"clean_full_eval": False}}) == (
        False,
        "BLOCKED_OR_PARTIAL",
    )
    assert run_authority({"non_authoritative": True}) == (False, "NON_AUTHORITATIVE")


def test_preferred_run_order():
    paths = [
        Path("run_other.json"),
        Path("run_phase8_challenge_clean_v3.json"),
        Path("run_v1_clean_full.json"),
    ]
    ordered = order_runs_for_display(paths)
    assert [p.name for p in ordered[:2]] == [
        "run_v1_clean_full.json",
        "run_phase8_challenge_clean_v3.json",
    ]


def test_deferred_note_disabled_for_product_ui():
    # Internal phase notes must not surface in the product UI.
    assert deferred_phase9_note() == ""
