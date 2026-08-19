# AtlasIQ V1 Engineering Handoff

**Document ID:** H0  
**Audience:** Future Cursor agents and engineers continuing AtlasIQ V1  
**Rule:** Read this file before starting work. Prefer this document plus repo contracts over chat history.

---

## 1. Project Identity

| Field | Value |
|-------|--------|
| **Project** | AtlasIQ V1 |
| **Purpose** | Enterprise RAG / knowledge workspace — evidence-first Q&A over an indexed corpus, with inspectable retrieval, score-gated abstention, and offline evaluation |
| **Current branch** | `atlasiq-v1` |
| **Proven legacy reference** | Git commit `8d28058`, file `app.py` (working hybrid RAG: semantic chunking, MiniLM, hybrid score, Groq) |
| **Checkpoint before AtlasIQ rebuild** | `c74144f` (corpus + evaluation foundation; prototype UI shell) |
| **Current state** | Real modular `atlas/` pipeline + enterprise Streamlit UI + evaluation stack (`run_eval.py`, `eval/`) |
| **Current phase** | V1 readiness / packaging (post T15 audit) |
| **Retrieval baseline** | **T14B** (do not start another retrieval optimization by default) |

AtlasIQ is **not** a generic chatbot demo. Wrong SKU prices, discount authorities, or SLA figures are product failures. Answers must be traceable, inspectable, and evaluable.

---

## 2. V1 Architecture

### 2.1 Online query path (production)

```
corpus/**/*.md
  → ingest (atlas/ingest.py)
  → semantic chunking (atlas/chunking.py; proven 8d28058 behavior)
  → MiniLM embeddings (atlas/embeddings.py; all-MiniLM-L6-v2, 384-d)
  → Chroma collection atlasiq_v1 (atlas/store.py; deterministic chunk_id upsert)
  → retrieval (atlas/retrieval.py; hybrid scoring)
  → T14B entity-aware routing (atlas/routing.py; ranking boost when IDs present)
  → optional cross-encoder rerank (atlas/rerank.py; DEFAULT OFF)
  → combined_score abstention gate (atlas/pipeline.py; threshold 0.75)
  → prompt loader (atlas/generation.py ← prompts/v1/*.txt)
  → Groq generation (llama-3.3-70b-versatile)  OR  deterministic abstention (no Groq)
  → citation parsing ([C#])
  → PipelineResult (answer, chunks, citations, timings, prompt/model metadata)
  → Streamlit UI (app.py; thin layer over answer_query())
```

### 2.2 Evaluation path (offline)

```
evaluation_dataset.json  (30 unique cases)
  → shared retrieve() / answer_query()  (same implementation as UI)
  → deterministic metrics (eval/metrics.py)
  → optional Groq LLM-as-judge (eval/judge.py; prompts/v1/judge_faithfulness.txt)
  → eval_results/run_*.json  (gitignored)
```

Comparison / analysis artifacts also live under `eval_results/` (e.g. T14A failure analysis, T14B comparison). They are **not** live UI claims.

### 2.3 Shared pipeline contract

- **Single entrypoint for Q&A:** `atlas.pipeline.answer_query()`
- **UI and eval both call this path** for answers (eval additionally snapshots `retrieve(top_k=5)` for Recall@k / MRR).
- **Modes:**
  - **Grounded** (UI) / **Private** (alias): always RAG; abstention gate applies; does **not** bypass threshold.
  - **General:** no corpus retrieval; `answer_general.txt`; no evidence citations from corpus.
  - **Auto:** RAG when `atlasiq_v1` has chunks; otherwise general.

---

## 3. Modules and Responsibilities

| Module | Responsibility |
|--------|----------------|
| `atlas/config.py` | Paths, Chroma/embedding/generation/retrieval/rerank/prompt settings; loads `.env` if `python-dotenv` present; `GROQ_API_KEY` |
| `atlas/chunking.py` | Semantic chunking (embedding-shift / cosine between sentences); uses sklearn cosine |
| `atlas/embeddings.py` | Load/cache `SentenceTransformer(all-MiniLM-L6-v2)`; `encode_texts` / `encode_query` |
| `atlas/ingest.py` | Discover `corpus/**/*.md`; produce `ChunkRecord`s with `chunk_id`, `doc_id`, `source`, `domain`, `chunk_index` |
| `atlas/store.py` | Persistent Chroma client; get/create `atlasiq_v1`; upsert by deterministic IDs; list collections (does not delete legacy) |
| `atlas/retrieval.py` | Hybrid retrieve; T14B wiring (entity pool expand, seed match, rank with boost); returns `RetrievedChunk` |
| `atlas/routing.py` | Extract Module/Region/Framework entities; source hints; metadata boost; `apply_metadata_routing` |
| `atlas/rerank.py` | Optional cross-encoder rerank; lazy load; default disabled |
| `atlas/generation.py` | Load prompts from disk; grounded/general generation; abstention **render** (no gate decision); citation parse; blocks judge prompt for generation |
| `atlas/telemetry.py` | Real wall-clock stage timings (retrieve / rerank / generate / total); no floors |
| `atlas/pipeline.py` | `answer_query()` orchestration; gate on max `combined_score`; assemble `PipelineResult` / `EvidenceChunk` |
| `eval/metrics.py` | Deterministic Recall@k, MRR, token F1, citation metrics, false abstention, aggregates |
| `eval/judge.py` | Offline judge using `judge_faithfulness.txt` + Groq; not used for live answers |
| `run_eval.py` | CLI: run golden set, write `eval_results/run_*.json`, optional `--skip-judge`, `--compare` |
| `scripts/index_corpus.py` | CLI index: ingest → upsert `atlasiq_v1`; safe re-run; reports other collections untouched |
| `app.py` | Streamlit UI only: Workspace, Evidence, Observability, Settings, Evaluation (**still a stub as of T15**); calls `answer_query()` |

**Prompts (not Python):** `prompts/v1/answer_grounded.txt`, `answer_general.txt`, `abstention.txt`, `judge_faithfulness.txt`.

**Contracts (docs):** `PRODUCT.md`, `PRODUCT_PRINCIPLES.md`, `ARCHITECTURE.md`, `EVALUATION.md`, `PROMPTS.md`, `DEMO.md`, `CHANGELOG.md` — some sections are stale vs shipped code (see §8); reconcile before portfolio freeze.

**Tests:** `tests/test_t14b_routing.py` (T14B routing verification). Broader gate/mode/index tests are mostly manual via `run_eval.py`.

---

## 4. LOCKED V1 DECISIONS

Treat the following as **LOCKED** unless a future experiment proves a correctness/regression problem with measured evidence:

| Decision | Locked value |
|----------|----------------|
| Embedding model | `all-MiniLM-L6-v2` |
| Embedding dimension | 384 |
| Generation model | `llama-3.3-70b-versatile` (Groq) |
| Temperature | 0.1 |
| max_tokens | 500 |
| Hybrid formula | `combined = similarity + keyword_count * 0.15` |
| Chroma distance → similarity | `similarity = 1 - chroma_distance` (cosine space) |
| top_n (normal) | 10 |
| top_n (T14B with identifiers) | expanded to ≥ 40 candidate pool |
| top_k (answer context) | 3 |
| Abstention threshold | **0.75** |
| Abstention gate score | **max `combined_score`** among retrieved candidates |
| T14B metadata boost | Affects **ranking only**; does **not** enter the abstention gate |
| Metadata match boost value | `5.0` |
| Reranking | Implemented; **default OFF** |
| Cross-encoder model | `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| Prompt version | `v1` |
| Prompt storage | Files under `prompts/v1/`, **not** inline in Python |
| Grounded context labels | `[C1]`, `[C2]`, … |
| General mode | No corpus evidence / no corpus citations |
| Auto mode | RAG when V1 index populated |
| Grounded / Private | **Does not** bypass abstention threshold |
| Chroma collection | `atlasiq_v1` |
| Corpus default | Markdown under `corpus/` |
| Indexing | Deterministic `chunk_id`s; idempotent upsert |
| Legacy Chroma collections | **Must not be deleted** by V1 tooling |
| Metrics in production UI | **No fake metrics**, no fake judge scores, no theatrical “guardrails passed” |
| LLM-as-judge | **Offline evaluation only**, not live answer generation |
| Terminology | Do **not** call simple top-k selection “reranking” |

---

## 5. T0–T15 Execution Ledger

| Task | Outcome | Status |
|------|---------|--------|
| **T0** | Contract docs + eval ID cleanup (`test_case_001`–`030` unique) | **DONE** |
| **T1** | `atlas/config.py` | **DONE** |
| **T2** | `atlas/chunking.py` (proven semantic chunking) | **DONE** |
| **T3** | `atlas/embeddings.py` | **DONE** |
| **T4** | `atlas/ingest.py` (50 md → structured chunks) | **DONE** |
| **T5** | `atlas/store.py` (Chroma `atlasiq_v1`) | **DONE** |
| **T6** | `scripts/index_corpus.py` | **DONE** |
| **T7** | Hybrid retrieval | **DONE** |
| **T8** | Optional cross-encoder rerank (default off) | **DONE** |
| **T9** | Generation + citations from `prompts/v1/` | **DONE** |
| **T10** | Pipeline + abstention + telemetry | **DONE** |
| **T11** | Real UI wiring over `answer_query()` | **DONE** |
| **T12** | Enterprise UI surfaces | **DONE** |
| **T13** | Evaluation CLI + metrics + judge | **DONE** |
| **T14A** | Retrieval failure analysis (sibling ambiguity; CE offline no lift) | **DONE** |
| **T14B** | Identifier-aware metadata routing / ranking | **DONE** |
| **T15** | V1 readiness audit (read-only) | **DONE** |
| **H0** | This handoff document | **DONE** (this file) |

### T14B measured deltas (vs T13 baseline)

Source: T13 `eval_results/run_20260816T190948Z.json` vs T14B `eval_results/run_20260817T043505Z.json` + `eval_results/t14b_comparison_20260817T044056Z.*`.

| Metric | T13 → T14B |
|--------|------------|
| Recall@3 | 0.367 → **0.633** |
| Recall@1 | 0.233 → **0.533** |
| Recall@5 | 0.533 → **0.700** |
| Recall@10 | 0.767 → **0.833** |
| MRR | 0.333 → **0.591** |
| answer F1 | 0.466 → **0.576** |
| citation accuracy | 0.367 → **0.633** |
| retrieve p50 | 13.3 ms → **15.4 ms** |
| Cases improved @3 | **8** |
| Cases regressed @3 | **0** |
| Explicit-ID subset R@3 | 0.467 → **1.000** |
| Identifier-free subset R@3 | 0.267 → **0.267** (unchanged) |

T14B eval run used `--skip-judge` (retrieval-focused). Do not invent T14B judge means.

---

## 6. T14B Retrieval Design

**Problem (T14A):** Dominant failure mode is sibling-document ambiguity in a near-duplicate corpus (Module N / Region N / Framework N), not threshold calibration. Offline cross-encoder rerank produced **zero** Recall@3 lift. Recommendation was improve retrieval disambiguation; keep threshold 0.75 and rerank off.

**When Module / Region / Framework identifiers are present in the query:**

1. Extract entities via `atlas.routing.extract_query_entities`
2. Expand semantic candidate pool to **≥ 40**
3. Seed chunks whose `source` exactly matches entity filename hints (corpus naming)
4. Score seeds with **real cosine similarity** from stored Chroma embeddings (no fake distance=0)
5. Rank using `combined_score + metadata_boost`
6. `METADATA_MATCH_BOOST = 5.0`
7. Return `top_k` (default 3 for answers; eval recall snapshot uses top_k=5)
8. Retain original hybrid **`combined_score`** for the abstention gate

**Explicit non-changes:**

- Hybrid formula was **NOT** changed
- Threshold was **NOT** changed (still 0.75)
- Rerank was **NOT** enabled by default
- Metadata boost is a **ranking** mechanism, **not** an abstention mechanism

**Identifier-free queries:** Pure hybrid behavior; `metadata_boost = 0`.

---

## 7. T13 Baseline

Full judge-on run: `eval_results/run_20260816T190948Z.json`.

| Metric | Value |
|--------|-------|
| Recall@3 | 0.367 |
| Recall@1 | 0.233 |
| MRR | 0.333 |
| context F1 | 0.569 |
| answer F1 | 0.466 |
| citation present | 1.0 |
| citation accuracy | 0.367 |
| judge faithfulness mean | 5.0 |
| false abstention | 0.0 |
| threshold | 0.75 |
| rerank | off |

These are the **T13** numbers. T14B improved retrieval/answer F1/citations under `--skip-judge`; **do not claim** T14B judge faithfulness unless a new judge-on run is produced.

---

## 8. T15 Readiness Audit

**Status:** `READY WITH BLOCKERS`

### Blockers

1. `requirements.txt` missing hard deps used in code: `numpy`, `scikit-learn`; `python-dotenv` used optionally but not listed
2. `README.md` obsolete/misleading (old product name, in-memory index narrative, etc.)
3. Docs stale vs shipped behavior (`CHANGELOG` still “Planned”; PRODUCT/DEMO claim Evaluation UI + Recall@3 ≥ 0.80)
4. Evaluation UI is still a stub (CLI eval works; UI does not load `eval_results`)
5. Intentional V1 source trees are largely **untracked** (`atlas/`, `docs/`, `eval/`, …)
6. Documented Recall@3 ≥ **0.80** gate is **not** met; measured T14B Recall@3 = **0.633**

### Risks

- Cold-start HuggingFace / sentence-transformers model download (works here via cache)
- P50 end-to-end latency ~3.5–4.5s (vs aspirational &lt;2s demo target)
- UI evidence-threshold slider can diverge from default 0.75 mid-session
- `token_usage` absent from `PipelineResult` (mentioned in ARCHITECTURE)
- Metadata boost not visible in Evidence Inspector
- Tracked Chroma binaries create dirty working tree despite ignore intent
- Obsolete root generators / sample files can confuse portfolio narrative
- “Private” (docs) vs “Grounded” (UI) terminology

**T15 did not modify code.** Packaging/docs/UI wiring remain the next work.

---

## 9. Remaining Work

Remaining work is **intentionally limited** to:

| Track | Scope |
|-------|--------|
| **A** | Durable documentation / handoff (this file; keep updated) |
| **B** | Reproducibility packaging (`requirements`, `.env.example`) |
| **C** | Documentation reconciliation (README, CHANGELOG, PRODUCT/DEMO targets) |
| **D** | Evaluation UI decision/implementation (wire real artifacts **or** demote DEMO claims) |
| **E** | Final verification (index + smoke + eval) |
| **F** | V1 freeze |
| **G** | Portfolio packaging |

### Explicit prohibition

**DO NOT start another retrieval optimization by default.**  
**T14B is the current retrieval baseline.**

Only reconsider retrieval if a measured correctness/regression issue appears, and then: establish baseline → one controlled change → re-eval.

---

## 10. V1 Quality Claims

**Do not claim Recall@3 ≥ 0.80.**

The measured **T14B Recall@3 is 0.633**.

Honest portfolio narrative should emphasize:

- Measurable improvement **0.367 → 0.633** Recall@3 after failure-driven work
- T14A failure analysis drove the intervention (sibling ambiguity, not threshold/CE)
- **No** Recall@3 regressions vs T13
- Explicit-ID subset reached **1.000** R@3; identifier-free subset unchanged (still hard)
- Hybrid scoring formula remained unchanged
- Improvement came from **identifier-aware routing / metadata ranking**, not gate gaming

---

## 11. Git State

Snapshot aligned with **T15** (and still accurate at H0 creation unless noted):

### Intentional / untracked (should eventually be committed)

```
atlas/
docs/          # including this V1_HANDOFF.md once created
eval/
prompts/
run_eval.py
scripts/
tests/
```

### Modified (working tree)

```
app.py
.gitignore
evaluation_dataset.json
```

### Generated / ignored

```
eval_results/     # gitignored; holds run_*.json, T14A/T14B reports
.venv/
.env              # secrets; never commit
```

### Pre-existing / working Chroma dirty files

```
chroma_db/*       # local persistent index; historically tracked files may still show as modified
```

Other collections may exist alongside `atlasiq_v1` (e.g. legacy vault names). **Do not delete them.**

Do not claim exact individual Chroma binary filenames in process docs unless freshly inspected.

---

## 12. Rules for Future Cursor Agents

1. Read **`docs/V1_HANDOFF.md`** before starting work.
2. Treat **LOCKED** decisions (§4) as constraints.
3. Do not redo completed ledger tasks without measured evidence of need.
4. Before changing retrieval, establish a measured baseline (and compare to T14B).
5. One controlled retrieval change at a time.
6. Never introduce hardcoded evaluation/quality scores in production UI.
7. Never fabricate telemetry (no latency floors, no fake health).
8. Never put prompts back into Python source.
9. Never bypass the abstention gate for Grounded / Private mode.
10. Never treat top-k selection as cross-encoder reranking.
11. Do not delete legacy Chroma collections.
12. Do not commit secrets.
13. Do not commit `.env`.
14. Do not commit local Chroma binaries unless explicitly decided.
15. Keep `eval_results/` ignored unless a deliberate anonymized baseline artifact is selected for commit.
16. Every implementation task must include a verification step.
17. Stop after the requested task and report git status.
18. Do not silently expand task scope.

---

## 13. Next Task

**NEXT:** V1 packaging / readiness fixes.

**Expected order:**

1. `requirements.txt` + `.env.example`
2. README refresh
3. Documentation reconciliation (CHANGELOG / PRODUCT / DEMO / ARCHITECTURE vs shipped + T14B metrics)
4. Evaluation UI wiring (or explicit DEMO demotion to CLI-only)
5. Final verification
6. V1 freeze
7. Portfolio packaging

---

## Appendix — Key artifact paths

| Artifact | Path |
|----------|------|
| Golden set | `evaluation_dataset.json` |
| T13 baseline report | `eval_results/run_20260816T190948Z.json` |
| T14B eval report (skip-judge) | `eval_results/run_20260817T043505Z.json` |
| T14A analysis | `eval_results/t14a_failure_analysis_20260817T041840Z.{json,md}` |
| T14B comparison | `eval_results/t14b_comparison_20260817T044056Z.{json,md}` |
| Index CLI | `python scripts/index_corpus.py` |
| Eval CLI | `python run_eval.py` / `--skip-judge` / `--compare <baseline.json>` |
| UI | `streamlit run app.py` |

**Index expectations:** ~50 markdown docs under `corpus/`; ~134 chunks in `atlasiq_v1` after successful index.
