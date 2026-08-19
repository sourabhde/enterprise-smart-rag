"""Deterministic evaluation metrics for AtlasIQ V1.

Supports legacy fields (source, expected_context) and frozen V1 gold fields
(acceptable_sources, key_facts, expect_abstention, expected_answer).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set


def normalize_source_path(path: Optional[str]) -> str:
    if not path:
        return ""
    return path.replace("\\", "/").strip().lstrip("./")


def tokenize(text: str) -> Set[str]:
    if not text:
        return set()
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def numeric_tokens(text: str) -> Set[str]:
    if not text:
        return set()
    return set(re.findall(r"\d[\d,]*(?:\.\d+)?%?", text.lower()))


def normalize_fact(fact: str) -> str:
    """Normalize a key fact for substring matching ($1,600 == $1600; 9 % == 9%)."""
    f = (fact or "").lower().strip()
    f = re.sub(r"[\u00a0\u202f\u2007\u2009\u200a]", " ", f)
    f = f.replace("‑", "-").replace("–", "-").replace("—", "-")
    f = f.replace(",", "")
    f = re.sub(r"\s+", " ", f)
    f = re.sub(r"(\d)\s+%", r"\1%", f)
    f = re.sub(r"(\d+)\s*-?\s*hours?\b", r"\1hr", f)
    f = re.sub(r"(\d+)\s*-?\s*hour\b", r"\1hr", f)
    f = re.sub(r"(\d+)\s*million\b", r"\1m", f)
    f = re.sub(r"(\d+)\s*m\b", r"\1m", f)
    f = re.sub(r"forfeiture\b", "forfeit", f)
    f = re.sub(r"forfeited\b", "forfeit", f)
    # Remove remaining spaces/hyphens so compact forms match
    f = re.sub(r"[\s\-]+", "", f)
    return f


def token_f1(predicted: str, reference: str) -> float:
    pred = tokenize(predicted)
    ref = tokenize(reference)
    if not pred and not ref:
        return 1.0
    if not pred or not ref:
        return 0.0
    overlap = pred & ref
    precision = len(overlap) / len(pred)
    recall = len(overlap) / len(ref)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _acceptable_list(
    golden_source: str,
    acceptable_sources: Optional[Sequence[str]],
) -> List[str]:
    if acceptable_sources:
        return [normalize_source_path(s) for s in acceptable_sources if s]
    if golden_source:
        return [normalize_source_path(golden_source)]
    return []


def source_rank_any(
    retrieved_sources: Sequence[str],
    acceptable: Sequence[str],
) -> Optional[int]:
    targets = set(acceptable)
    if not targets:
        return None
    for i, src in enumerate(retrieved_sources):
        if normalize_source_path(src) in targets:
            return i + 1
    return None


def recall_at_k_any(
    retrieved_sources: Sequence[str],
    acceptable: Sequence[str],
    k: int,
) -> float:
    rank = source_rank_any(retrieved_sources, acceptable)
    if rank is None:
        return 0.0
    return 1.0 if rank <= k else 0.0


def mrr_any(retrieved_sources: Sequence[str], acceptable: Sequence[str]) -> float:
    rank = source_rank_any(retrieved_sources, acceptable)
    if rank is None:
        return 0.0
    return 1.0 / float(rank)


# Backward-compatible aliases
def source_rank(retrieved_sources: Sequence[str], golden_source: str) -> Optional[int]:
    return source_rank_any(retrieved_sources, _acceptable_list(golden_source, None))


def recall_at_k(retrieved_sources: Sequence[str], golden_source: str, k: int) -> float:
    return recall_at_k_any(
        retrieved_sources, _acceptable_list(golden_source, None), k
    )


def mrr_score(retrieved_sources: Sequence[str], golden_source: str) -> float:
    return mrr_any(retrieved_sources, _acceptable_list(golden_source, None))


def citation_present(answer: str) -> bool:
    if not answer:
        return False
    if re.search(r"(?:\[|【)C\d+(?:\]|】)", answer):
        return True
    if re.search(r"\[source:\s*[^\]]+\]", answer, flags=re.IGNORECASE):
        return True
    return False


def parse_citation_labels(answer: str) -> List[str]:
    return re.findall(r"(?:\[|【)(C\d+)(?:\]|】)", answer or "")


def citation_to_retrieval_consistency(
    answer: str, retrieved_count: int
) -> Optional[float]:
    labels = parse_citation_labels(answer)
    if not labels:
        return None
    ok = 0
    for label in labels:
        idx = int(label[1:]) - 1
        if 0 <= idx < retrieved_count:
            ok += 1
    return ok / len(labels)


def citation_accuracy(
    answer: str,
    retrieved_sources: Sequence[str],
    golden_source: str,
    acceptable_sources: Optional[Sequence[str]] = None,
) -> Optional[float]:
    labels = parse_citation_labels(answer)
    if not labels:
        return None
    targets = set(_acceptable_list(golden_source, acceptable_sources))
    for label in labels:
        idx = int(label[1:]) - 1
        if 0 <= idx < len(retrieved_sources):
            if normalize_source_path(retrieved_sources[idx]) in targets:
                return 1.0
    for match in re.finditer(r"\[source:\s*([^\]]+)\]", answer or "", flags=re.IGNORECASE):
        if normalize_source_path(match.group(1)) in targets:
            return 1.0
    return 0.0


def key_fact_presence(answer: str, expected_context: str) -> Optional[bool]:
    """Legacy: all numeric tokens from expected_context appear in answer."""
    nums = numeric_tokens(expected_context)
    if not nums:
        return None
    answer_l = (answer or "").lower().replace(",", "")
    return all(n.replace(",", "") in answer_l for n in nums)


def key_facts_hit_rate(answer: str, key_facts: Sequence[str]) -> Optional[float]:
    """Fraction of structured key_facts found in the answer (normalized)."""
    facts = [normalize_fact(f) for f in key_facts if f and str(f).strip()]
    if not facts:
        return None
    answer_l = normalize_fact(answer or "")
    hits = sum(1 for f in facts if f in answer_l)
    return hits / len(facts)


def key_facts_all_present(answer: str, key_facts: Sequence[str]) -> Optional[bool]:
    rate = key_facts_hit_rate(answer, key_facts)
    if rate is None:
        return None
    return rate >= 1.0


# Product outcomes. ERROR is exclusive of TP/TN/FP/FN/WRONG.
OUTCOME_TP = "TP"
OUTCOME_TN = "TN"
OUTCOME_FP = "FP"
OUTCOME_FN = "FN"
OUTCOME_WRONG = "WRONG"
OUTCOME_ERROR = "ERROR"


def classify_error_kind(
    pipeline_error: Optional[str],
    *,
    retrieval_error: Optional[str] = None,
    judge_error: Optional[str] = None,
) -> Optional[str]:
    """Return generation|retrieval|judge|execution or None if no error."""
    if retrieval_error:
        return "retrieval"
    if not pipeline_error and not judge_error:
        return None
    msg = (pipeline_error or "").lower()
    if any(
        x in msg
        for x in (
            "429",
            "rate limit",
            "rate_limit",
            "timeout",
            "timed out",
            "generation",
            "groq",
            "api",
            "http",
            "model_not_found",
            "does not exist",
            "not found",
            "404",
        )
    ):
        return "generation"
    if pipeline_error:
        return "execution"
    if judge_error:
        return "judge"
    return None


@dataclass
class CaseMetrics:
    recall_at_1: float
    recall_at_3: float
    recall_at_5: float
    mrr: float
    context_token_f1: Optional[float]
    answer_token_f1: Optional[float]
    key_fact_presence: Optional[bool]
    key_fact_hit_rate: Optional[float]
    citation_present: Optional[bool]
    citation_accuracy: Optional[float]
    citation_to_retrieval_consistency: Optional[float]
    abstained: bool
    expect_abstention: bool
    false_abstention: bool
    false_positive_answer: bool
    true_negative_abstention: bool
    true_positive_answer: bool
    answer_correct: Optional[bool] = None
    outcome: str = OUTCOME_ERROR
    error_kind: Optional[str] = None
    scored: bool = True  # False when execution failed; exclude from product rates

    def as_dict(self) -> Dict[str, Any]:
        return {
            "recall_at_1": self.recall_at_1,
            "recall_at_3": self.recall_at_3,
            "recall_at_5": self.recall_at_5,
            "mrr": self.mrr,
            "context_token_f1": self.context_token_f1,
            "answer_token_f1": self.answer_token_f1,
            "key_fact_presence": self.key_fact_presence,
            "key_fact_hit_rate": self.key_fact_hit_rate,
            "citation_present": self.citation_present,
            "citation_accuracy": self.citation_accuracy,
            "citation_to_retrieval_consistency": self.citation_to_retrieval_consistency,
            "abstained": self.abstained,
            "expect_abstention": self.expect_abstention,
            "false_abstention": self.false_abstention,
            "false_positive_answer": self.false_positive_answer,
            "true_negative_abstention": self.true_negative_abstention,
            "true_positive_answer": self.true_positive_answer,
            "answer_correct": self.answer_correct,
            "outcome": self.outcome,
            "error_kind": self.error_kind,
            "scored": self.scored,
        }


def score_case(
    *,
    golden_source: str,
    expected_context: str,
    retrieved_sources: Sequence[str],
    top1_chunk_text: Optional[str],
    answer: str,
    abstained: bool,
    answer_context_sources: Optional[Sequence[str]] = None,
    acceptable_sources: Optional[Sequence[str]] = None,
    key_facts: Optional[Sequence[str]] = None,
    expect_abstention: bool = False,
    expected_answer: Optional[str] = None,
    pipeline_error: Optional[str] = None,
    retrieval_error: Optional[str] = None,
) -> CaseMetrics:
    """Score one case across retrieval, answer, citation, and abstention axes.

    Pipeline/API failures (429, timeout, generation crash) are OUTCOME_ERROR and
    never count as TP/TN/FP/FN/WRONG.
    """
    sources = list(retrieved_sources)
    cite_sources = (
        list(answer_context_sources)
        if answer_context_sources is not None
        else list(retrieved_sources)
    )
    acceptable = _acceptable_list(golden_source, acceptable_sources)
    facts = list(key_facts or [])
    err_kind = classify_error_kind(pipeline_error, retrieval_error=retrieval_error)

    # Retrieval: abstention cases with no acceptable sources → N/A as 0 / skip
    if expect_abstention and not acceptable:
        r1 = r3 = r5 = mrr = 0.0
    else:
        r1 = recall_at_k_any(sources, acceptable, 1)
        r3 = recall_at_k_any(sources, acceptable, 3)
        r5 = recall_at_k_any(sources, acceptable, 5)
        mrr = mrr_any(sources, acceptable)

    ref_text = expected_answer or expected_context or ""
    context_f1 = (
        token_f1(top1_chunk_text or "", expected_context or ref_text)
        if top1_chunk_text is not None and (expected_context or ref_text)
        else None
    )

    # --- ERROR path: do not invent product outcomes ---
    if err_kind or pipeline_error or retrieval_error:
        return CaseMetrics(
            recall_at_1=r1,
            recall_at_3=r3,
            recall_at_5=r5,
            mrr=mrr,
            context_token_f1=context_f1,
            answer_token_f1=None,
            key_fact_presence=None,
            key_fact_hit_rate=None,
            citation_present=None,
            citation_accuracy=None,
            citation_to_retrieval_consistency=None,
            abstained=bool(abstained),
            expect_abstention=expect_abstention,
            false_abstention=False,
            false_positive_answer=False,
            true_negative_abstention=False,
            true_positive_answer=False,
            answer_correct=None,
            outcome=OUTCOME_ERROR,
            error_kind=err_kind or "execution",
            scored=False,
        )

    if abstained:
        if expect_abstention:
            outcome = OUTCOME_TN
            false_abs = False
            false_pos = False
            true_neg = True
            true_pos = False
            ans_ok: Optional[bool] = True
        else:
            outcome = OUTCOME_FN
            false_abs = True
            false_pos = False
            true_neg = False
            true_pos = False
            ans_ok = False
        return CaseMetrics(
            recall_at_1=r1,
            recall_at_3=r3,
            recall_at_5=r5,
            mrr=mrr,
            context_token_f1=context_f1,
            answer_token_f1=None,
            key_fact_presence=None,
            key_fact_hit_rate=None,
            citation_present=None,
            citation_accuracy=None,
            citation_to_retrieval_consistency=None,
            abstained=True,
            expect_abstention=expect_abstention,
            false_abstention=false_abs,
            false_positive_answer=false_pos,
            true_negative_abstention=true_neg,
            true_positive_answer=true_pos,
            answer_correct=ans_ok,
            outcome=outcome,
            error_kind=None,
            scored=True,
        )

    # Answered path
    hit_rate = key_facts_hit_rate(answer, facts) if facts else None
    legacy_presence = (
        key_facts_all_present(answer, facts)
        if facts
        else key_fact_presence(answer, expected_context or ref_text)
    )
    ans_f1 = token_f1(answer, ref_text) if ref_text else None
    if facts:
        answer_correct = bool(legacy_presence)
    elif ref_text:
        answer_correct = (ans_f1 or 0.0) >= 0.35
    else:
        answer_correct = None

    if expect_abstention:
        outcome = OUTCOME_FP
        false_pos = True
        false_abs = False
        true_neg = False
        true_pos = False
        answer_correct = False
    elif answer_correct is True:
        outcome = OUTCOME_TP
        false_pos = False
        false_abs = False
        true_neg = False
        true_pos = True
    elif answer_correct is False:
        outcome = OUTCOME_WRONG
        false_pos = False
        false_abs = False
        true_neg = False
        true_pos = False
    else:
        # Answered answerable case with no gold facts/text → treat as TP on answerability only
        outcome = OUTCOME_TP
        false_pos = False
        false_abs = False
        true_neg = False
        true_pos = True

    return CaseMetrics(
        recall_at_1=r1,
        recall_at_3=r3,
        recall_at_5=r5,
        mrr=mrr,
        context_token_f1=context_f1,
        answer_token_f1=ans_f1,
        key_fact_presence=legacy_presence,
        key_fact_hit_rate=hit_rate,
        citation_present=citation_present(answer),
        citation_accuracy=citation_accuracy(
            answer, cite_sources, golden_source, acceptable_sources=acceptable
        ),
        citation_to_retrieval_consistency=citation_to_retrieval_consistency(
            answer, len(cite_sources)
        ),
        abstained=False,
        expect_abstention=expect_abstention,
        false_abstention=false_abs,
        false_positive_answer=false_pos,
        true_negative_abstention=true_neg,
        true_positive_answer=true_pos,
        answer_correct=answer_correct,
        outcome=outcome,
        error_kind=None,
        scored=True,
    )


def _mean(values: Iterable[Optional[float]]) -> Optional[float]:
    nums = [float(v) for v in values if v is not None]
    if not nums:
        return None
    return sum(nums) / len(nums)


def aggregate_metrics(case_metrics: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(case_metrics)
    if n == 0:
        return {}

    def col(key: str) -> List[Optional[float]]:
        return [m.get(key) for m in case_metrics]

    # Product rates use only successfully executed cases (scored=True).
    scored = [m for m in case_metrics if m.get("scored", True)]
    errors = [m for m in case_metrics if m.get("outcome") == OUTCOME_ERROR or m.get("scored") is False]

    def _count_outcome(label: str) -> int:
        return sum(1 for m in case_metrics if m.get("outcome") == label)

    tp = _count_outcome(OUTCOME_TP)
    tn = _count_outcome(OUTCOME_TN)
    fp = _count_outcome(OUTCOME_FP)
    fn = _count_outcome(OUTCOME_FN)
    wrong = _count_outcome(OUTCOME_WRONG)
    err_n = _count_outcome(OUTCOME_ERROR)

    gen_err = sum(1 for m in case_metrics if m.get("error_kind") == "generation")
    ret_err = sum(1 for m in case_metrics if m.get("error_kind") == "retrieval")
    judge_err = sum(
        1
        for m in case_metrics
        if m.get("error_kind") == "judge" or m.get("judge_error")
    )
    exec_err = sum(1 for m in case_metrics if m.get("error_kind") == "execution")

    def _error_msg(m: Dict[str, Any]) -> str:
        return str(m.get("pipeline_error") or m.get("error") or m.get("error_kind") or "").lower()

    # Prefer explicit error text when present on the case metrics dict
    rate_limit_count = sum(
        1
        for m in case_metrics
        if m.get("outcome") == OUTCOME_ERROR
        and any(x in str(m.get("error_kind", "")).lower() + _error_msg(m) for x in ("429", "rate_limit", "rate limit"))
    )
    timeout_count = sum(
        1
        for m in case_metrics
        if m.get("outcome") == OUTCOME_ERROR
        and any(x in _error_msg(m) for x in ("timeout", "timed out"))
    )

    abstained = sum(1 for m in scored if m.get("abstained"))
    answered = len(scored) - abstained
    expect_abs = [m for m in scored if m.get("expect_abstention")]
    expect_ans = [m for m in scored if not m.get("expect_abstention")]

    false_abs = sum(1 for m in scored if m.get("false_abstention"))
    false_pos = sum(1 for m in scored if m.get("false_positive_answer"))
    true_neg = sum(1 for m in scored if m.get("true_negative_abstention"))
    true_pos = sum(1 for m in scored if m.get("true_positive_answer"))

    answered_metrics = [m for m in scored if not m.get("abstained")]
    # Retrieval means: all expect-answer cases (incl. ERROR) still report R@k
    # for diagnostics, but product rates use scored-only expect_ans.
    retrieval_pool = [m for m in case_metrics if not m.get("expect_abstention")]
    retrieval_pool_scored = expect_ans

    def mean_answered(key: str) -> Optional[float]:
        return _mean(m.get(key) for m in answered_metrics)

    def mean_pool(pool: Sequence[Dict[str, Any]], key: str) -> Optional[float]:
        return _mean(m.get(key) for m in pool)

    scored_n = len(scored)
    # Abstention precision = among abstentions, share that should abstain = TN/(TN+FN)
    # Abstention recall = among should-abstain, share that did = TN/(TN+FP)
    abstention_precision = (tn / (tn + fn)) if (tn + fn) > 0 else None
    abstention_recall = (tn / (tn + fp)) if (tn + fp) > 0 else None
    clean_full_eval = err_n == 0

    return {
        "case_count": n,
        "scored_case_count": scored_n,
        "answered_count": answered,
        "abstained_count": abstained,
        "expect_abstention_count": len(expect_abs),
        "expect_answer_count": len(expect_ans),
        "false_abstention_rate": (false_abs / len(expect_ans)) if expect_ans else None,
        "false_positive_answer_rate": (false_pos / len(expect_abs)) if expect_abs else None,
        "true_negative_abstention_rate": (true_neg / len(expect_abs)) if expect_abs else None,
        "true_positive_answer_rate": (true_pos / len(expect_ans)) if expect_ans else None,
        "answer_correct_rate": _mean(
            m.get("answer_correct") for m in scored if m.get("answer_correct") is not None
        ),
        "key_fact_hit_rate_mean": mean_answered("key_fact_hit_rate"),
        "recall_at_1": mean_pool(retrieval_pool_scored or retrieval_pool, "recall_at_1"),
        "recall_at_3": mean_pool(retrieval_pool_scored or retrieval_pool, "recall_at_3"),
        "recall_at_5": mean_pool(retrieval_pool_scored or retrieval_pool, "recall_at_5"),
        "mrr": mean_pool(retrieval_pool_scored or retrieval_pool, "mrr"),
        "context_token_f1_mean": _mean(col("context_token_f1")),
        "answer_token_f1_mean": mean_answered("answer_token_f1"),
        "citation_present_rate": mean_answered("citation_present"),
        "citation_accuracy_mean": mean_answered("citation_accuracy"),
        "citation_to_retrieval_consistency_mean": mean_answered(
            "citation_to_retrieval_consistency"
        ),
        "key_fact_presence_rate": mean_answered("key_fact_presence"),
        "abstention_precision": abstention_precision,
        "abstention_recall": abstention_recall,
        "confusion": {
            "TP": tp,
            "TN": tn,
            "FP": fp,
            "FN": fn,
            "WRONG": wrong,
            "ERROR": err_n,
            # legacy aliases
            "true_positive_answers": true_pos,
            "true_negative_abstentions": true_neg,
            "false_positive_answers": false_pos,
            "false_negative_abstentions": false_abs,
            "wrong_answers": wrong,
            "execution_errors": err_n,
        },
        "execution_error_count": err_n,
        "generation_error_count": gen_err,
        "retrieval_error_count": ret_err,
        "judge_error_count": judge_err,
        "pipeline_execution_error_count": exec_err,
        "rate_limit_count": rate_limit_count,
        "timeout_count": timeout_count,
        "clean_full_eval": clean_full_eval,
        "unscored_case_count": len(errors),
    }


def percentile(values: Sequence[float], p: float) -> Optional[float]:
    if not values:
        return None
    xs = sorted(float(v) for v in values)
    if len(xs) == 1:
        return xs[0]
    k = (len(xs) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    if f == c:
        return xs[f]
    return xs[f] + (xs[c] - xs[f]) * (k - f)
