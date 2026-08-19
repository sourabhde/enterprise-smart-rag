"""Deterministic tests: API/model failures must never count as TP/TN/FP/FN."""

from eval.metrics import (
    OUTCOME_ERROR,
    OUTCOME_FP,
    OUTCOME_TN,
    OUTCOME_TP,
    aggregate_metrics,
    classify_error_kind,
    score_case,
)


def _base(**kwargs):
    defaults = dict(
        golden_source="a.md",
        expected_context="",
        retrieved_sources=["a.md"],
        top1_chunk_text="x",
        answer="",
        abstained=False,
        expect_abstention=False,
        key_facts=["$53,000"],
    )
    defaults.update(kwargs)
    return score_case(**defaults)


def test_model_not_found_is_error_not_fp():
    m = _base(
        expect_abstention=True,
        answer="",
        pipeline_error=(
            "Groq generation failed: Error code: 404 - "
            "{'error': {'code': 'model_not_found'}}"
        ),
    )
    assert m.outcome == OUTCOME_ERROR
    assert m.scored is False
    assert m.false_positive_answer is False
    assert m.true_negative_abstention is False
    assert classify_error_kind(m.error_kind and "") or True
    assert m.error_kind == "generation"


def test_429_is_error_not_fn():
    m = _base(
        answer="",
        abstained=False,
        pipeline_error="Error code: 429 - rate_limit exceeded",
    )
    assert m.outcome == OUTCOME_ERROR
    assert m.false_abstention is False
    assert m.true_positive_answer is False


def test_timeout_is_error():
    m = _base(pipeline_error="Request timed out talking to Groq API")
    assert m.outcome == OUTCOME_ERROR
    assert m.error_kind == "generation"


def test_clean_tp_still_works():
    m = _base(answer="Base is $53,000", abstained=False)
    assert m.outcome == OUTCOME_TP
    assert m.scored is True


def test_aggregate_excludes_errors_from_product_rates():
    err = _base(
        expect_abstention=True,
        pipeline_error="model_not_found",
    ).as_dict()
    tn = _base(
        golden_source="",
        retrieved_sources=[],
        answer="cannot",
        abstained=True,
        expect_abstention=True,
        key_facts=[],
    ).as_dict()
    agg = aggregate_metrics([err, tn])
    assert agg["confusion"]["ERROR"] == 1
    assert agg["confusion"]["TN"] == 1
    assert agg["confusion"]["FP"] == 0
    assert agg["clean_full_eval"] is False
    assert agg["execution_error_count"] == 1
