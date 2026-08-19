# AtlasIQ — Evaluation Specification

**Version:** V1  
**Status:** Engineering contract (pre-implementation)  
**Golden dataset:** `evaluation_dataset.json` (repository root)

---

## Purpose

Evaluation is a **first-class product capability**, not an afterthought. AtlasIQ must demonstrate that knowledge quality is **measured**, **reproducible**, and **regression-gated**—matching enterprise expectations for AI systems in revenue, legal, and policy domains.

This document defines metrics, workflow, and regression strategy for AtlasIQ V1.

---

## Golden Dataset Strategy

### Current state

| Property | Value |
|----------|-------|
| File | `evaluation_dataset.json` |
| Items | 30 Q&A pairs |
| Corpus coverage | 10 of 50 files (~20%) |
| Schema | `id`, `question`, `expected_context`, `source` |
| Origin | LLM-generated via Gemini scripts (`generate_all_eval_gemini.py`) |
| Known issues | Duplicate `id` values (`test_case_028` × 3) — fix before baseline lock |

### Schema (V1 canonical)

```json
{
  "id": "test_case_001",
  "question": "Natural language enterprise question",
  "expected_context": "Ground-truth passage from source document",
  "source": "corpus/skus/product_tier_08.md"
}
```

| Field | Role |
|-------|------|
| `question` | User query input to pipeline |
| `expected_context` | Reference passage for overlap metrics (not necessarily exact answer string) |
| `source` | Ground-truth file path for retrieval metrics |

### Golden set tiers

| Tier | Scope | V1 usage |
|------|-------|----------|
| **Smoke** | 5 fixed questions (subset of golden set) | CI fast gate |
| **Core** | Full 30 items | Demo baseline, local dev |
| **Extended** | 3 Q&A × 50 files = 150 items | P1/P2; generate via `generate_all_eval_gemini.py` |

### Golden set quality rules

1. Questions must be answerable **only** from the cited `source` file.
2. `expected_context` must contain the factual tokens being tested (numbers, percentages, dollar amounts).
3. Each `id` must be unique before baseline lock.
4. Human spot-check recommended for demo-critical cases (minimum: 5 smoke questions).
5. Dataset is **committed**; eval **reports** are gitignored in `eval_results/`.

### Expansion workflow

```
corpus/ updated
    → run generate_all_eval_gemini.py (checkpoint/resume)
    → human review sample
    → commit evaluation_dataset.json
    → run run_eval.py → new baseline
```

---

## Retrieval Metrics

Measured per eval case against pipeline retrieval output (before or after rerank — **document choice in report**; V1 default: after rerank, before generation).

| Metric | Definition | V1 target (core set) |
|--------|------------|----------------------|
| **Source Recall@1** | Golden `source` equals rank-1 chunk's source path | Report |
| **Source Recall@3** | Golden `source` in top-3 chunk sources | ≥ **0.80** |
| **Source Recall@5** | Golden `source` in top-5 | Report |
| **Context Token F1** | Token F1 between top-1 chunk text and `expected_context` | Mean ≥ **0.50** |
| **MRR** | Mean reciprocal rank of golden source | Report |

### Token F1 computation

- Lowercase, alphanumeric tokenization
- F1 on token sets between strings
- Used for `expected_context` vs retrieved chunk (retrieval quality) and vs answer (generation quality)

### Notes

- Path matching is normalized (forward slashes, relative to repo root).
- Multiple chunks from same source file count as hit if path matches.

---

## Generation Metrics

| Metric | Definition | V1 target |
|--------|------------|-----------|
| **Answer Token F1** | Token F1 between generated answer and `expected_context` | Mean ≥ **0.40** |
| **Key fact presence** | Binary: all numeric tokens in `expected_context` appear in answer | Report per case |
| **Abstention correctness** | For negative cases (P1): should abstain | P1 |

Generation metrics run only when pipeline does **not** abstain.

---

## Citation Metrics

AtlasIQ V1 requires explicit citations in grounded mode. Citations are evaluated deterministically before judge review.

| Metric | Definition | V1 target |
|--------|------------|-----------|
| **Citation present** | Answer contains at least one citation marker (`[C#]` or `[source: ...]`) | ≥ **0.90** grounded cases |
| **Citation accuracy** | At least one cited source path matches golden `source` | ≥ **0.70** |
| **Citation-to-retrieval consistency** | Every `[C#]` maps to a chunk in retrieval set | ≥ **0.95** |

### Citation format (V1 contract)

- Inline chunk refs: `[C1]`, `[C2]`, … matching context block IDs in prompt
- Source paths: `corpus/policies/discount_matrix_policy_10.md` in citation footer or inline

Judge evaluates citation **quality**; metrics evaluate citation **presence and correctness**.

---

## Groundedness and Faithfulness

### Deterministic (fast, CI-friendly)

- Answer Token F1 vs `expected_context`
- Numeric token overlap (discount %, dollar amounts, uptime %)
- Citation accuracy

### LLM-as-judge (offline, Groq)

See [PROMPTS.md](./PROMPTS.md) — `prompts/v1/judge_faithfulness.txt`

Judge returns structured JSON per case:

| Score | Scale | Question |
|-------|-------|----------|
| `faithfulness` | 1–5 | Is every claim supported by retrieved context? |
| `completeness` | 1–5 | Does answer cover key facts in expected_context? |
| `citation_quality` | 1–5 | Do citations align with sources used? |

**V1 target:** Mean `faithfulness` ≥ **4.0** on core set.

### Judge rules

- Judge receives: question, retrieved chunks, generated answer, **not** expected_context (avoids leakage) OR expected_context in separate "reference" field for completeness only — **V1 choice: give expected_context only to completeness sub-score prompt variant, or separate judge call**
- Recommended V1: two judge calls or one structured prompt with blind faithfulness section
- Judge model: same Groq stack (`llama-3.3-70b-versatile`), temperature 0
- Judge failures recorded as `null` score, not silently skipped

---

## Abstention Evaluation

### V1 (core set)

Current golden set contains **no negative abstention cases**. Abstention is demonstrated live in [DEMO.md](./DEMO.md), not scored in core eval.

### P1 — Abstention golden cases

Add items with `"expect_abstention": true`:

```json
{
  "id": "test_case_neg_001",
  "question": "What is our HIPAA breach notification timeline?",
  "expected_context": null,
  "source": null,
  "expect_abstention": true
}
```

| Metric | Definition |
|--------|------------|
| **Abstention precision** | Fraction of `expect_abstention` cases where pipeline abstained |
| **False abstention rate** | Abstained on answerable core questions |

---

## Latency Metrics

Recorded per eval case and aggregated in report.

| Metric | Description |
|--------|-------------|
| `retrieve_ms` | Retrieval + optional rerank |
| `generate_ms` | LLM completion |
| `total_ms` | End-to-end |
| `p50`, `p95`, `p99` | Aggregates across run |

**V1 demo target:** P50 total < 2000 ms local (hardware-dependent; report hardware in eval metadata).

Latency does **not** gate CI in V1 unless extreme regression (> 2× baseline).

---

## LLM-as-Judge Workflow

```
For each eval case:
    1. Run pipeline → answer + chunks
    2. If abstained → skip generation metrics; record abstention
    3. Run eval/metrics.py (deterministic)
    4. Run eval/judge.py with prompts/v1/judge_faithfulness.txt
    5. Append to case result
Aggregate → eval_results/run_{timestamp}.json
```

### Eval report metadata (required fields)

```json
{
  "run_id": "uuid",
  "timestamp": "ISO-8601",
  "git_commit": "short sha",
  "prompt_version": "v1",
  "model_id": "llama-3.3-70b-versatile",
  "embedding_model": "all-MiniLM-L6-v2",
  "corpus_files": 50,
  "similarity_threshold": 0.75,
  "rerank_enabled": false,
  "aggregate": { ... },
  "cases": [ ... ]
}
```

---

## Evaluation Workflow

### Local development

```bash
# 1. Ensure index exists (after implementation)
python scripts/index_corpus.py

# 2. Full eval
python run_eval.py

# 3. Smoke subset
python run_eval.py --smoke 5

# 4. Compare to baseline
python run_eval.py --compare eval_results/baseline.json
```

### Pre-demo checklist

1. Reindex corpus from committed `corpus/`
2. Run full eval; verify Recall@3 and judge faithfulness meet targets
3. Archive report as demo baseline with timestamp
4. Confirm UI telemetry matches eval environment (same threshold, prompt version)

### CI smoke (P1)

`.github/workflows/eval-smoke.yml`:

- Trigger: PR to `atlasiq-v1` / `main`
- Steps: install deps → index corpus → `run_eval.py --smoke 5`
- Gate: Recall@3 ≥ 0.60 on smoke (lower bar due to small n) or fixed 4/5 source hits

---

## Regression Prevention

| Mechanism | Description |
|-----------|-------------|
| **Committed golden set** | Same questions every run |
| **Baseline report** | Checked in to `eval_results/baseline.json` optionally, or documented in README with expected numbers |
| **Prompt version in report** | Behavior change visible when prompts change |
| **CI smoke** | Blocks merge on retrieval regression |
| **CHANGELOG** | Behavior-affecting changes documented |
| **Threshold discipline** | Similarity threshold changes require re-eval and CHANGELOG entry |

### Regression triage order

1. Check index health (chunk count, corpus hash)
2. Check prompt_version and model_id in report
3. Compare per-case failures (retrieval miss vs generation miss)
4. Inspect Evidence Inspector for failed cases manually

---

## What Evaluation Does NOT Cover (V1)

- Conflict detection accuracy
- Multi-turn conversation coherence
- User satisfaction / thumbs feedback
- Cross-lingual retrieval
- PDF ingestion quality
- Cost optimization

---

## Related Documents

- [PROMPTS.md](./PROMPTS.md) — Judge and generation prompt versions
- [ARCHITECTURE.md](./ARCHITECTURE.md) — Pipeline and eval layer separation
- [PRODUCT_PRINCIPLES.md](./PRODUCT_PRINCIPLES.md) — Evaluation-driven development
- [DEMO.md](./DEMO.md) — Live eval demonstration step
