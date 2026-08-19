#!/usr/bin/env python3
"""AtlasIQ V1 evaluation CLI (docs/EVALUATION.md).

Runs the golden set through atlas.pipeline.answer_query, computes deterministic
metrics, optionally runs LLM-as-judge, and writes eval_results/run_{timestamp}.json.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dataclasses import replace

from atlas.config import config
from atlas.ingest import discover_markdown_files
from atlas.pipeline import answer_query
from atlas.rerank import rerank
from atlas.retrieval import retrieve
from atlas.store import collection_count
from eval.judge import judge_answer
from eval.metrics import aggregate_metrics, percentile, score_case


def _git_commit() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_REPO_ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except Exception:
        return "unknown"


def load_dataset(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("evaluation_dataset.json must be a JSON array")
    ids = [c.get("id") for c in data]
    if len(ids) != len(set(ids)):
        raise ValueError("evaluation_dataset.json contains duplicate IDs")
    return data


def _retrieval_snapshot(question: str, *, top_k: int, rerank_enabled: bool, cfg):
    """Hybrid retrieve (+ optional rerank) for Recall@k / MRR (k up to 5)."""
    hits = retrieve(question, top_k=top_k, cfg=cfg)
    hits = rerank(question, hits, enabled=rerank_enabled, cfg=cfg)
    return hits


def evaluate_case(
    case: Dict[str, Any],
    *,
    cfg,
    rerank_enabled: bool,
    skip_judge: bool,
) -> Dict[str, Any]:
    question = case["question"]
    golden_source = case.get("source") or ""
    expected_context = case.get("expected_context") or ""
    expected_answer = case.get("expected_answer")
    acceptable_sources = case.get("acceptable_sources") or (
        [golden_source] if golden_source else []
    )
    key_facts = case.get("key_facts") or []
    expect_abstention = bool(case.get("expect_abstention"))
    case_types = list(case.get("type") or [])

    retrieval_error: Optional[str] = None
    retrieval_hits = []
    retrieved_sources: List[str] = []
    top1_text = None
    try:
        # Retrieval metrics use up to 5 candidates (EVALUATION.md Recall@5)
        retrieval_hits = _retrieval_snapshot(
            question, top_k=5, rerank_enabled=rerank_enabled, cfg=cfg
        )
        retrieved_sources = [h.source for h in retrieval_hits]
        top1_text = retrieval_hits[0].text if retrieval_hits else None
    except Exception as exc:  # noqa: BLE001 — surface as retrieval ERROR
        retrieval_error = f"retrieval_failed: {exc}"

    # Answer path: real grounded pipeline (threshold unchanged)
    result = answer_query(
        question,
        mode="grounded",
        cfg=cfg,
        rerank_enabled=rerank_enabled,
        use_cache=False,
    )

    answer_sources = [c.source for c in result.chunks]
    metrics = score_case(
        golden_source=golden_source,
        expected_context=expected_context,
        retrieved_sources=retrieved_sources,
        top1_chunk_text=top1_text,
        answer=result.answer,
        abstained=result.abstained,
        answer_context_sources=answer_sources,
        acceptable_sources=acceptable_sources,
        key_facts=key_facts,
        expect_abstention=expect_abstention,
        expected_answer=expected_answer,
        pipeline_error=result.error,
        retrieval_error=retrieval_error,
    )
    metrics_dict = metrics.as_dict()

    judge_payload: Dict[str, Any]
    if skip_judge or expect_abstention:
        judge_payload = {
            "judge_called": False,
            "error": (
                "Judge skipped (expected abstention)."
                if expect_abstention and not skip_judge
                else "Judge skipped (--skip-judge)."
            ),
            "faithfulness": None,
            "completeness": None,
            "citation_quality": None,
        }
    elif result.error or retrieval_error or not metrics.scored:
        judge_payload = {
            "judge_called": False,
            "error": (
                "Pipeline/retrieval error; judge not called: "
                f"{result.error or retrieval_error}"
            ),
            "faithfulness": None,
            "completeness": None,
            "citation_quality": None,
        }
    elif result.abstained:
        judge_payload = {
            "judge_called": False,
            "error": "Pipeline abstained; judge not called.",
            "faithfulness": None,
            "completeness": None,
            "citation_quality": None,
        }
    else:
        judge_payload = judge_answer(
            question=question,
            answer=result.answer,
            chunks=result.chunks,
            expected_context=expected_context
            or (expected_answer if isinstance(expected_answer, str) else ""),
            cfg=cfg,
        ).as_dict()
        # Judge API failures: count separately; do not flip product outcome to ERROR
        if judge_payload.get("judge_called") and judge_payload.get("error"):
            metrics_dict["judge_error"] = True
            if not metrics_dict.get("error_kind"):
                metrics_dict["error_kind"] = "judge"

    acceptable_norm = [s.replace("\\", "/") for s in acceptable_sources]
    return {
        "id": case["id"],
        "question": question,
        "type": case_types,
        "expect_abstention": expect_abstention,
        "expected_behavior": case.get("expected_behavior"),
        "golden_source": golden_source,
        "acceptable_sources": acceptable_sources,
        "key_facts": key_facts,
        "expected_context": expected_context,
        "expected_answer": expected_answer,
        "abstained": result.abstained,
        "generation_called": result.generation_called,
        "answer": result.answer,
        "citations": list(result.citations),
        "prompt_version": result.prompt_version,
        "model_id": result.model_id,
        "prompt_name": result.prompt_name,
        "max_combined_score": result.max_combined_score,
        "similarity_threshold": result.similarity_threshold,
        "error": result.error,
        "retrieval_error": retrieval_error,
        "timings": result.timings.as_dict(),
        "retrieval": {
            "top_k": 5,
            "rerank_enabled": rerank_enabled,
            "sources": retrieved_sources,
            "chunk_ids": [h.chunk_id for h in retrieval_hits],
            "ranks": list(range(1, len(retrieval_hits) + 1)),
            "similarity_scores": [h.similarity_score for h in retrieval_hits],
            "combined_scores": [h.combined_score for h in retrieval_hits],
            "golden_source_retrieved": any(
                s.replace("\\", "/") in acceptable_norm
                or s.replace("\\", "/") == golden_source.replace("\\", "/")
                for s in retrieved_sources
            ),
        },
        "answer_context_chunks": [
            {
                "rank": i + 1,
                "chunk_id": c.chunk_id,
                "source": c.source,
                "domain": c.domain,
                "similarity_score": c.similarity_score,
                "combined_score": c.combined_score,
                "accessed": c.accessed,
                "used": c.used,
            }
            for i, c in enumerate(result.chunks)
        ],
        "answer_context_sources": answer_sources,
        "metrics": metrics_dict,
        "judge": judge_payload,
    }



def build_report(
    cases_out: List[Dict[str, Any]],
    *,
    cfg,
    rerank_enabled: bool,
    dataset_path: Path,
    smoke: Optional[int],
) -> Dict[str, Any]:
    metrics_list = [c["metrics"] for c in cases_out]
    aggregate = aggregate_metrics(metrics_list)

    judge_faith = [
        c["judge"].get("faithfulness")
        for c in cases_out
        if c.get("judge") and c["judge"].get("judge_called") and c["judge"].get("error") is None
    ]
    judge_comp = [
        c["judge"].get("completeness")
        for c in cases_out
        if c.get("judge") and c["judge"].get("judge_called") and c["judge"].get("error") is None
    ]
    judge_cite = [
        c["judge"].get("citation_quality")
        for c in cases_out
        if c.get("judge") and c["judge"].get("judge_called") and c["judge"].get("error") is None
    ]
    judge_errors = sum(
        1
        for c in cases_out
        if c.get("judge") and c["judge"].get("judge_called") and c["judge"].get("error")
    )
    judge_calls = sum(
        1 for c in cases_out if c.get("judge") and c["judge"].get("judge_called")
    )
    # Prefer explicit judge_error_count from metrics; fall back to judge payload count
    if aggregate.get("judge_error_count", 0) == 0 and judge_errors:
        aggregate["judge_error_count"] = judge_errors

    # Enrich rate-limit / timeout counts from raw case errors (metrics dict may lack text)
    rate_limit_count = sum(
        1
        for c in cases_out
        if c.get("error")
        and any(
            x in str(c.get("error")).lower()
            for x in ("429", "rate_limit", "rate limit")
        )
    )
    timeout_count = sum(
        1
        for c in cases_out
        if c.get("error")
        and any(x in str(c.get("error")).lower() for x in ("timeout", "timed out"))
    )
    aggregate["rate_limit_count"] = max(
        int(aggregate.get("rate_limit_count") or 0), rate_limit_count
    )
    aggregate["timeout_count"] = max(
        int(aggregate.get("timeout_count") or 0), timeout_count
    )

    totals = [c["timings"]["total_ms"] for c in cases_out if c.get("timings")]
    retrieve_ms = [
        c["timings"]["retrieve_ms"] + c["timings"].get("rerank_ms", 0)
        for c in cases_out
        if c.get("timings")
    ]
    generate_ms = [c["timings"]["generate_ms"] for c in cases_out if c.get("timings")]

    aggregate.update(
        {
            "judge_faithfulness_mean": (
                sum(judge_faith) / len(judge_faith) if judge_faith else None
            ),
            "judge_completeness_mean": (
                sum(judge_comp) / len(judge_comp) if judge_comp else None
            ),
            "judge_citation_quality_mean": (
                sum(judge_cite) / len(judge_cite) if judge_cite else None
            ),
            "judge_calls": judge_calls,
            "judge_parse_or_api_errors": judge_errors,
            "latency_ms": {
                "retrieve_p50": percentile(retrieve_ms, 50),
                "generate_p50": percentile(generate_ms, 50),
                "total_p50": percentile(totals, 50),
                "total_p95": percentile(totals, 95),
                "total_p99": percentile(totals, 99),
            },
        }
    )

    # Category slices (by first matching type tag)
    slice_tags = [
        "identifier_specific",
        "identifier_free",
        "abstention",
        "multi_document",
        "adversarial_premise",
        "sibling_discrimination",
        "ambiguous",
    ]
    by_category: Dict[str, Any] = {}
    for tag in slice_tags:
        subset = [c for c in cases_out if tag in (c.get("type") or [])]
        if not subset:
            continue
        by_category[tag] = aggregate_metrics([c["metrics"] for c in subset])

    try:
        corpus_files = len(discover_markdown_files())
    except Exception:
        corpus_files = None

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return {
        "run_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_commit(),
        "prompt_version": cfg.prompts.version,
        "model_id": cfg.generation.model_id,
        "embedding_model": cfg.embedding.model_id,
        "judge_prompt": f"prompts/{cfg.prompts.version}/judge_faithfulness.txt",
        "corpus_files": corpus_files,
        "collection_count": collection_count(cfg=cfg),
        "similarity_threshold": cfg.retrieval.similarity_threshold,
        "rerank_enabled": rerank_enabled,
        "dataset_path": str(dataset_path),
        "case_count": len(cases_out),
        "smoke": smoke,
        "benchmark_status": "atlasiq_v1_gold_frozen",
        "clean_full_eval": bool(aggregate.get("clean_full_eval")),
        "retrieval_metric_note": (
            "Recall@k/MRR use acceptable_sources when present (else source); "
            "retrieve top_k=5; answers use answer_query top_k=3, gate 0.75, rerank default off. "
            "API/pipeline failures are OUTCOME=ERROR and excluded from TP/TN/FP/FN/WRONG."
        ),
        "aggregate": aggregate,
        "by_category": by_category,
        "cases": cases_out,
        "report_filename_hint": f"run_{ts}.json",
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="AtlasIQ V1 evaluation runner")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=config.paths.evaluation_dataset,
        help="Path to evaluation_dataset.json",
    )
    parser.add_argument(
        "--smoke",
        type=int,
        default=None,
        help="Run only the first N cases (CI smoke)",
    )
    parser.add_argument(
        "--skip-judge",
        action="store_true",
        help="Skip LLM-as-judge calls (deterministic metrics only)",
    )
    parser.add_argument(
        "--rerank",
        action="store_true",
        help="Enable cross-encoder rerank (default: off)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output report path (default: eval_results/run_<timestamp>.json)",
    )
    parser.add_argument(
        "--compare",
        type=Path,
        default=None,
        help="Optional baseline report to print recall_at_3 delta against",
    )
    args = parser.parse_args(argv)

    dataset = load_dataset(args.dataset)
    if args.smoke is not None:
        dataset = dataset[: max(0, args.smoke)]

    rerank_enabled = bool(args.rerank)
    # Keep threshold at config default (0.75); do not calibrate in T13
    cfg = replace(
        config,
        rerank=replace(config.rerank, enabled=rerank_enabled),
    )

    print(
        f"AtlasIQ eval | cases={len(dataset)} | threshold={cfg.retrieval.similarity_threshold} "
        f"| rerank={rerank_enabled} | judge={'off' if args.skip_judge else 'on'}"
    )
    print(f"collection_count={collection_count(cfg=cfg)}")

    cases_out: List[Dict[str, Any]] = []
    for i, case in enumerate(dataset, start=1):
        print(f"[{i}/{len(dataset)}] {case['id']} …", flush=True)
        row = evaluate_case(
            case,
            cfg=cfg,
            rerank_enabled=rerank_enabled,
            skip_judge=bool(args.skip_judge),
        )
        cases_out.append(row)
        m = row["metrics"]
        j = row.get("judge") or {}
        print(
            f"    outcome={m.get('outcome')} abstained={row['abstained']} "
            f"recall@3={m['recall_at_3']} err={row.get('error') or row.get('retrieval_error')} "
            f"judge_faithfulness={j.get('faithfulness')}"
        )

    report = build_report(
        cases_out,
        cfg=cfg,
        rerank_enabled=rerank_enabled,
        dataset_path=args.dataset,
        smoke=args.smoke,
    )

    out_dir = config.paths.eval_results_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.output:
        out_path = args.output
    else:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = out_dir / f"run_{ts}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    agg = report["aggregate"]
    conf = agg.get("confusion") or {}
    print("\n=== Aggregate ===")
    print(f"clean_full_eval:          {agg.get('clean_full_eval')}")
    print(
        f"outcomes TP/TN/FP/FN/WRONG/ERROR: "
        f"{conf.get('TP')}/{conf.get('TN')}/{conf.get('FP')}/"
        f"{conf.get('FN')}/{conf.get('WRONG')}/{conf.get('ERROR')}"
    )
    print(
        f"errors gen/ret/judge/exec: "
        f"{agg.get('generation_error_count')}/{agg.get('retrieval_error_count')}/"
        f"{agg.get('judge_error_count')}/{agg.get('pipeline_execution_error_count')}"
    )
    print(f"recall_at_3:              {agg.get('recall_at_3')}")
    print(f"recall_at_1:              {agg.get('recall_at_1')}")
    print(f"mrr:                      {agg.get('mrr')}")
    print(f"answer_correct_rate:      {agg.get('answer_correct_rate')}")
    print(f"key_fact_hit_rate_mean:   {agg.get('key_fact_hit_rate_mean')}")
    print(f"key_fact_presence_rate:   {agg.get('key_fact_presence_rate')}")
    print(f"citation_accuracy_mean:   {agg.get('citation_accuracy_mean')}")
    print(f"false_abstention_rate:    {agg.get('false_abstention_rate')}")
    print(f"false_positive_answer_rate:{agg.get('false_positive_answer_rate')}")
    print(f"true_negative_abstention: {agg.get('true_negative_abstention_rate')}")
    print(f"abstention_precision:     {agg.get('abstention_precision')}")
    print(f"abstention_recall:        {agg.get('abstention_recall')}")
    print(f"judge_faithfulness_mean:  {agg.get('judge_faithfulness_mean')}")
    print(
        f"latency total p50/p95:    {agg.get('latency_ms', {}).get('total_p50')} / "
        f"{agg.get('latency_ms', {}).get('total_p95')}"
    )
    print(f"report: {out_path}")
    if not agg.get("clean_full_eval"):
        print(
            "CLEAN_FULL_EVAL_BLOCKED: execution errors present; "
            "do not treat product rates as authoritative."
        )

    if args.compare and args.compare.is_file():
        baseline = json.loads(args.compare.read_text(encoding="utf-8"))
        base_r3 = (baseline.get("aggregate") or {}).get("recall_at_3")
        cur_r3 = agg.get("recall_at_3")
        if base_r3 is not None and cur_r3 is not None:
            print(f"compare recall_at_3 delta: {cur_r3 - base_r3:+.4f} (baseline={base_r3})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
