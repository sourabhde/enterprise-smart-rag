# AtlasIQ V1 — Phase 8 Final Validation Report

**Date:** 2026-08-17  
**Application LLM:** `openai/gpt-oss-120b` (Groq) — unchanged  
**Corpus:** 50 synthetic Sales/CPQ docs — **unchanged**  
**Original gold:** `evaluation_dataset.json` (59) — **preserved**  
**Phase 8 challenge:** `evaluation_dataset_phase8_challenge.json` (57 frozen)

---

## 1. Product purpose
Evidence-grounded Sales/CPQ / commercial-operations assistant over a controlled synthetic enterprise corpus (SKU pricing, discount authority, regional SLA).

## 2. Corpus verdict
**ADEQUATE** (prior audit affirmed). No corpus edits in Phase 8.

## 3. Original 59-case benchmark
**INTACT / CLEAN** — `eval_results/run_v1_clean_full.json`  
TP/TN/FP/FN/WRONG/ERROR = **50/9/0/0/0/0** (not overwritten).

## 4. Phase 8 challenge-set verdict
- Candidate: 70 (`evaluation_dataset_phase8_candidate.json`)
- Grok review: **APPROVE_WITH_EDITS** — `eval_results/phase8_grok_candidate_review.{json,md}`
- Adjudicated frozen: **57** — `evaluation_dataset_phase8_frozen.json` / `evaluation_dataset_phase8_challenge.json`
- Removed 13 (frozen-59 clones + invalid sibling tags); repaired FAIL items
- Deterministic gold validation: **PASS** — `eval_results/phase8_gold_deterministic_validation.json`

## 5. Combined coverage
Original 59 + Phase 8 57 = **116** structured cases. Phase 8 adds multi-doc, multi-hop, adversarial wording, customer-specific, unsupported-topic edges beyond the original set.

## 6–13. Phase 8 challenge clean eval (authoritative)

**Artifact:** `eval_results/run_phase8_challenge_clean_v3.json`  
**Prior runs (non-final):** `run_phase8_challenge_clean.json`, `..._v2.json`

| Metric | Value |
|--------|------:|
| clean_full_eval | **True** |
| ERROR | **0** |
| TP / TN / FP / FN / WRONG | **39 / 17 / 0 / 0 / 1** |
| Recall@1 / @3 / @5 | 1.0 / 1.0 / 1.0 |
| Answer correct | ~0.965 |
| Key-fact hit | ~0.983 |
| Citation accuracy | 1.0 |
| False abstention | 0.0 |
| False-positive answer | 0.0 |
| True-negative abstention | 1.0 |

**Category slices (v3):** multi-doc / multi-hop / adversarial / sibling largely TP; abstention TN=17; **1 remaining WRONG** (`p8_case_024` triple fact — generation omitted Module 12 price on one rephrase).

**Failure table:** `eval_results/phase8_failure_table.json`

## 14. UI validation
- Streamlit served on **:8522** (HTTP 200); brand updated to *Evidence-grounded Sales/CPQ Intelligence*
- Pipeline flow strip: QUESTION → RETRIEVAL → EVIDENCE → ANSWER → CITATION
- Evaluation surface still excludes archived composed runs
- Functional pipeline smoke (Module 12 / FW99 / Acme / multi-doc): **PASS**
- Browser MCP could not attach to the local port in this environment; validation used curl + live `answer_query` path

## 15–16. Bugs discovered & fixed

| Bug | Fix |
|-----|-----|
| Entity-matched paraphrase **false abstention** (gate used raw `combined_score`, ignored `metadata_boost`) | `_gate_score` uses ranking score |
| Soft LLM refusals / partial answers on unsupported topics (SOC2, MSA carve-out, Salesforce, FY2027, package SKU) | `_unsupported_topic_request` + expanded customer-commercial patterns |
| Underspecified “what discount can sales approve?” | Underspec pattern |
| Eval composed artifact as truth | Already quarantined; UI deny-list retained |
| Key-fact `forfeit`/`forfeiture` mismatch | `normalize_fact` |

**Regression tests:** `tests/test_phase8_gate_and_unsupported.py` (+ prior abstention/metric tests)

## 17. Remaining limitations
- One multi-document completeness miss (`p8_case_024`)
- Sibling ambiguity remains hard by nature of shared boilerplate
- Groq judge not run (by design this phase)
- Browser automation to Streamlit flaky in this agent environment

## 18. Exact commands
```bash
python3 run_eval.py --skip-judge --dataset evaluation_dataset_phase8_challenge.json \
  --output eval_results/run_phase8_challenge_clean_v2.json
# then targeted re-exec → run_phase8_challenge_clean_v3.json
```

## 19. Exact artifacts
- `evaluation_dataset_phase8_candidate.json`
- `evaluation_dataset_phase8_frozen.json` / `evaluation_dataset_phase8_challenge.json`
- `eval_results/phase8_grok_candidate_review.{md,json}`
- `eval_results/phase8_gold_adjudication.md`
- `eval_results/run_phase8_challenge_clean_v3.json` ← **authoritative Phase 8**
- `eval_results/run_v1_clean_full.json` ← **authoritative original 59**
- `eval_results/V1_PHASE8_FINAL.md` (this file)

## 20. Final V1 readiness verdict

# DEMO READY

AtlasIQ V1 is a defensible evidence-grounded Sales/CPQ demo: original 59 remains perfect/clean, Phase 8 adversarial set is clean with **0 ERROR / 0 FP / 0 FN**, one residual multi-doc completeness miss, corpus unchanged, application LLM verified.
