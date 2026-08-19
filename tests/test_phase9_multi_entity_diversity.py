"""Regression: multi-entity queries keep one chunk per named entity in top_k."""

from __future__ import annotations

from atlas.pipeline import answer_query
from atlas.retrieval import diversify_by_query_entities, retrieve
from atlas.rerank import rerank
from atlas.routing import QueryEntity, extract_query_entities


def test_diversify_keeps_one_chunk_per_entity():
    q = (
        "State Module 12’s base subscription, Framework 10’s Vice President of "
        "Global Sales discount ceiling, and Region 01’s committed monthly uptime."
    )
    entities = extract_query_entities(q)
    assert len(entities) == 3
    ranked = list(rerank(q, retrieve(q, top_k=5), enabled=False))
    # Simulate pre-diversify ranking by fetching a wider pool then diversifying
    wide = list(retrieve(q, top_k=5))
    top3 = diversify_by_query_entities(wide, entities, 3)
    sources = {c.source for c in top3}
    assert any("product_tier_12" in s for s in sources)
    assert any("discount_matrix_policy_10" in s for s in sources)
    assert any("sla_agreement_region_01" in s for s in sources)


def test_retrieve_top3_includes_all_three_domains():
    q = (
        "State Module 12’s base subscription, Framework 10’s Vice President of "
        "Global Sales discount ceiling, and Region 01’s committed monthly uptime."
    )
    hits = list(retrieve(q, top_k=3))
    sources = {h.source for h in hits}
    assert any("product_tier_12" in s for s in sources)
    assert any("discount_matrix_policy_10" in s for s in sources)
    assert any("sla_agreement_region_01" in s for s in sources)


def test_p8_case_024_answers_all_three_key_facts():
    q = (
        "State Module 12’s base subscription, Framework 10’s Vice President of "
        "Global Sales discount ceiling, and Region 01’s committed monthly uptime."
    )
    r = answer_query(q, mode="grounded")
    assert r.error is None
    assert r.abstained is False
    assert r.generation_called is True
    ans = (r.answer or "").replace(",", "").replace("\u202f", " ").replace(" ", "")
    assert "53000" in ans or "53,000" in (r.answer or "").replace("\u202f", "")
    assert "29%" in (r.answer or "").replace("\u202f", " ") or "29" in ans
    assert "99.10" in (r.answer or "").replace("\u202f", "")


def test_single_entity_still_returns_module12():
    hits = list(retrieve("What is the base subscription for Module 12?", top_k=3))
    assert hits
    assert any("product_tier_12" in h.source for h in hits)
