"""Executable verification for T14B metadata-aware retrieval."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from atlas.retrieval import retrieve
from atlas.routing import extract_query_entities


def _sources(hits):
    return [h.source for h in hits]


def test_extract_entities():
    ents = extract_query_entities("What is the annual list price for Module 12?")
    assert any(e.kind == "module" and e.value == "12" for e in ents)
    ents = extract_query_entities("uptime for Region 01")
    assert any(e.kind == "region" and e.value == "01" for e in ents)
    ents = extract_query_entities("discount under Framework 03")
    assert any(e.kind == "framework" and e.value == "03" for e in ents)
    assert extract_query_entities("What are Tier 2 Volume API limits?") == []
    extract_query_entities("??? arbitrary !!! natural language 🚀")  # no crash


def test_module_12_ranks_product_tier_12():
    hits = retrieve("What is the annual list price for Module 12?", top_k=5)
    assert hits, "expected retrieval hits"
    assert hits[0].source.endswith("product_tier_12.md"), _sources(hits)
    assert hits[0].metadata_boost > 0


def test_region_favors_matching_doc():
    hits = retrieve(
        "What is the committed monthly uptime availability percentage "
        "for production workloads deployed in Region 01?",
        top_k=5,
    )
    assert hits
    assert "region_01" in hits[0].source, _sources(hits)


def test_framework_favors_matching_doc():
    # Explicit Framework N identifier (general routing, not eval-hardcoded).
    hits = retrieve(
        "What discount bands apply under Framework 03?",
        top_k=5,
    )
    assert hits
    assert "discount_matrix_policy_03" in hits[0].source, _sources(hits)


def test_no_identifier_keeps_hybrid_order_stable():
    q = "What are the rate limits and pricing for Tier 2 Volume API usage?"
    assert extract_query_entities(q) == []
    a = retrieve(q, top_k=5)
    b = retrieve(q, top_k=5)
    assert _sources(a) == _sources(b)
    assert all(h.metadata_boost == 0.0 for h in a)


def test_deterministic_ordering():
    q = "What is the annual base subscription fee for Module 12?"
    a = _sources(retrieve(q, top_k=5))
    b = _sources(retrieve(q, top_k=5))
    assert a == b


def main() -> int:
    tests = [
        test_extract_entities,
        test_module_12_ranks_product_tier_12,
        test_region_favors_matching_doc,
        test_framework_favors_matching_doc,
        test_no_identifier_keeps_hybrid_order_stable,
        test_deterministic_ordering,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as exc:
            failed += 1
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
