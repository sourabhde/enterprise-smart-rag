"""Regression: customer-specific commercial facts hard-abstain; supported Qs still answer."""

from __future__ import annotations

from atlas.pipeline import (
    _customer_specific_evidence_missing,
    answer_query,
)
from atlas.retrieval import RetrievedChunk


def _chunk(text: str, source: str = "corpus/skus/product_tier_12.md") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=f"{source}:0",
        text=text,
        source=source,
        domain="skus",
        chunk_index=0,
        doc_id="product_tier_12",
        similarity_score=0.9,
        keyword_score=2,
        combined_score=1.2,
        chroma_distance=0.1,
    )


def test_customer_specific_detector_true_for_acme():
    chunks = [
        _chunk(
            "Module 12 base platform subscription is $53,000 per year. Includes 25 seats."
        )
    ]
    q = "What is Acme Corporation’s privately negotiated Module 12 price for FY2024?"
    assert _customer_specific_evidence_missing(q, chunks) is True


def test_customer_specific_detector_false_for_list_price():
    chunks = [
        _chunk(
            "Module 12 base platform subscription is $53,000 per year. Includes 25 seats."
        )
    ]
    q = "What is the annual base subscription for Module 12, and how many seats are included?"
    assert _customer_specific_evidence_missing(q, chunks) is False


def test_customer_specific_detector_false_for_policy():
    chunks = [
        _chunk(
            "Under Framework 10, an Account Executive may approve up to 9% off list.",
            source="corpus/policies/discount_matrix_policy_10.md",
        )
    ]
    q = "What is the maximum discretionary discount an Account Executive can approve under Framework 10?"
    assert _customer_specific_evidence_missing(q, chunks) is False


def test_live_pipeline_acme_hard_abstains():
    """Real retrieve path — no Groq call on customer-specific miss."""
    q = "What is Acme Corporation’s privately negotiated Module 12 price for FY2024?"
    r = answer_query(q, mode="grounded")
    assert r.error is None
    assert r.abstained is True
    assert r.generation_called is False
    assert "customer-specific" in r.answer.lower() or "negotiated" in r.answer.lower()


def test_live_pipeline_unsupported_entity_hard_abstains():
    q = "What discount can an Account Executive approve under Framework 99?"
    r = answer_query(q, mode="grounded")
    assert r.error is None
    assert r.abstained is True
    assert r.generation_called is False


def test_live_pipeline_supported_module_price_still_gates_open():
    """Gate must open for supported Module 12 list price (generation may still need API)."""
    from atlas.pipeline import _customer_specific_evidence_missing, _entity_evidence_missing
    from atlas.retrieval import retrieve
    from atlas.rerank import rerank

    q = "What is the annual base subscription for Module 12?"
    chunks = list(rerank(q, retrieve(q), enabled=False))
    assert _customer_specific_evidence_missing(q, chunks) is False
    assert _entity_evidence_missing(q, chunks) is False
