"""Regression: entity-matched retrieval must pass the abstention gate via ranking score."""

from __future__ import annotations

from atlas.pipeline import _gate_score, answer_query
from atlas.retrieval import retrieve
from atlas.rerank import rerank


def test_gate_uses_metadata_boost_for_paraphrase():
    q = (
        "A prospect asks how many people can log in under Module 12 without "
        "buying extras — what do we tell them?"
    )
    hits = list(rerank(q, retrieve(q), enabled=False))
    assert hits
    assert hits[0].metadata_boost > 0
    assert hits[0].combined_score < 0.75  # raw hybrid may be low
    assert _gate_score(hits) >= 0.75  # ranking score must clear gate


def test_paraphrase_module12_seats_answers():
    q = (
        "A prospect asks how many people can log in under Module 12 without "
        "buying extras — what do we tell them?"
    )
    r = answer_query(q, mode="grounded")
    assert r.error is None
    assert r.abstained is False
    assert r.generation_called is True
    assert "25" in (r.answer or "")


def test_unsupported_soc2_hard_abstains():
    q = "What is the SOC 2 Type II report ID for the Region 01 control environment?"
    r = answer_query(q, mode="grounded")
    assert r.error is None
    assert r.abstained is True
    assert r.generation_called is False


def test_initech_msa_hard_abstains():
    q = "What is Initech’s signed MSA liability carve-out for Region 01?"
    r = answer_query(q, mode="grounded")
    assert r.error is None
    assert r.abstained is True
    assert r.generation_called is False
