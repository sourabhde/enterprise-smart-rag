# AtlasIQ — Architecture

**Version:** V1 target specification  
**Status:** Contract document (pre-implementation)  
**Baseline branch:** `atlasiq-v1`

---

## Purpose

This document defines the **current** repository architecture, the **target** AtlasIQ V1 architecture, and the boundaries between UI, pipeline, retrieval, storage, and evaluation. Implementation must evolve from proven components in Git history—not greenfield rewrite.

---

## Current Architecture (As of Repository Audit)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  app.py (atlasiq-v1, ~140 lines)                                        │
│  Prototype UI shell — mock indexing, mock retrieval, fake telemetry    │
└─────────────────────────────────────────────────────────────────────────┘
                                    ✕ not connected
┌─────────────────────────────────────────────────────────────────────────┐
│  app.py @ 8d28058 (~520 lines) — proven but disconnected                │
│  Upload → semantic chunk → in-memory pandas store → hybrid retrieve     │
│  → Groq Llama-3.3-70b → Vector Inspector + pillar dashboard             │
└─────────────────────────────────────────────────────────────────────────┘

┌──────────────────────┐  ┌──────────────────────┐  ┌────────────────────┐
│  corpus/ (50 md)     │  │  evaluation_dataset  │  │  chroma_db/ (local)│
│  skus/legal/policies │  │  .json (30 items)    │  │  18 legacy chunks  │
└──────────────────────┘  └──────────────────────┘  └────────────────────┘
         committed                 committed              gitignored, unused
```

### Current component truth table

| Component | Status |
|-----------|--------|
| Semantic chunking | Implemented in `8d28058`, not in current `app.py` |
| Embeddings (all-MiniLM-L6-v2) | Implemented in `8d28058` |
| Vector storage | In-memory DataFrame in `8d28058`; Chroma on disk unused |
| Hybrid retrieval | Implemented in `8d28058` |
| Cross-encoder rerank | Claimed in prototype UI; not implemented |
| Groq generation | Implemented in `8d28058` |
| Citations | Partial (context in prompt; inspector shows chunks) |
| Abstention | Prompt-only in Private mode; no score gate |
| Evaluation runner | Not implemented |
| LLM-as-judge | Hardcoded score in `8d28058`; fake in prototype |
| Corpus ingestion | Generator exists; app does not index corpus |

---

## Target Architecture (AtlasIQ V1)

AtlasIQ V1 introduces a **layered Python package** (`atlas/`) with a thin Streamlit UI (`app.py`) and a standalone eval CLI (`run_eval.py`). Both call the same pipeline.

```
                         ┌─────────────────────────────────┐
                         │         Streamlit UI            │
                         │  (Knowledge / Evidence / Eval   │
                         │   / Observability / Settings)   │
                         └───────────────┬─────────────────┘
                                         │
                         ┌───────────────▼─────────────────┐
                         │      atlas/pipeline.py          │
                         │   answer_query() orchestrator   │
                         └───────────────┬─────────────────┘
           ┌─────────────────────────────┼─────────────────────────────┐
           │                             │                             │
┌──────────▼──────────┐    ┌─────────────▼────────────┐    ┌──────────▼──────────┐
│  atlas/ingest.py    │    │   atlas/retrieval.py     │    │  atlas/generation.py│
│  atlas/chunking.py  │    │   atlas/rerank.py        │    │  + prompts/ files   │
│  atlas/embeddings.py│    │                          │    │                     │
└──────────┬──────────┘    └─────────────┬────────────┘    └──────────┬──────────┘
           │                             │                             │
           └─────────────────────────────┼─────────────────────────────┘
                                         │
                         ┌───────────────▼─────────────────┐
                         │       atlas/store.py            │
                         │   ChromaDB persistent client    │
                         │   collection: atlasiq_v1        │
                         └─────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│  run_eval.py  ──►  atlas/pipeline.py  +  eval/metrics.py  + eval/judge.py│
│  (offline, reproducible, records prompt_version + model_id)              │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Major Components

### UI Layer (`app.py` + optional `pages/`)

**Responsibility:** Presentation, user input, rendering pipeline results. No retrieval math, no prompt strings, no direct Chroma calls.

**Surfaces (target):**

| Surface | Function |
|---------|----------|
| Knowledge Workspace | Chat Q&A, citation display |
| Evidence Inspector | Chunk list, scores, source paths |
| Evaluation | Last eval run summary |
| Observability | Index stats, latency, stage health |
| Settings | Thresholds, modes, rerank toggle |

**Rule:** UI reads structured `PipelineResult` objects only.

---

### Pipeline Layer (`atlas/pipeline.py`)

**Responsibility:** Orchestrate retrieve → rerank → abstention check → generate → assemble telemetry.

**Inputs:** `question`, `PipelineSettings` (mode, thresholds, prompt version, rerank flag)  
**Outputs:** `PipelineResult` — answer text, abstained flag, chunks used, citations, timing, token usage

**Rule:** Single code path shared by UI and `run_eval.py`.

---

### Ingestion & Indexing (`atlas/ingest.py`, `atlas/chunking.py`, `atlas/embeddings.py`, `scripts/index_corpus.py`)

**Responsibility:** Load documents, semantic chunk, embed, upsert to store.

| Stage | Implementation source |
|-------|----------------------|
| Parse md/txt | New ingest module; PDF optional from baseline |
| Semantic chunk | Port `semantic_chunk_text()` from `8d28058` |
| Embed | `all-MiniLM-L6-v2` via `atlas/embeddings.py` |
| Metadata | `source`, `domain` (skus/legal/policies), `chunk_index`, `doc_id` |

**Trigger:** Sidebar “Index / Sync Corpus” and CLI `scripts/index_corpus.py`.

---

### Storage Layer (`atlas/store.py`)

**Responsibility:** Persistent vector index via ChromaDB.

| Property | Value |
|----------|-------|
| Path | `./chroma_db/` (gitignored, rebuilt locally) |
| Collection | `atlasiq_v1` (single active collection V1) |
| Distance | Cosine |
| Dimension | 384 |

**Rule:** Full reindex replaces collection contents; no silent drift between demo machines (document rebuild in README).

---

### Retrieval Layer (`atlas/retrieval.py`, `atlas/rerank.py`)

**Responsibility:** Candidate generation and ranking.

**Hybrid retrieval (default):**

1. Vector query against Chroma (top-N candidates)
2. Keyword overlap rescore on candidate text
3. Combined score: `vector_score + keyword_hits * KEYWORD_WEIGHT` (baseline weight: 0.15 from `8d28058`)

**Optional rerank (`atlas/rerank.py`):**

- Cross-encoder: `cross-encoder/ms-marco-MiniLM-L-6-v2`
- Reranks top-N before final top-K selection
- Disabled by default if latency-critical

**Abstention gate (in pipeline):**

- If max combined score < `similarity_threshold` → abstain
- If zero candidates → abstain

---

### Generation Layer (`atlas/generation.py` + `prompts/`)

**Responsibility:** LLM call, prompt assembly, output cleanup.

| Property | Value |
|----------|-------|
| Provider | Groq |
| Model | `llama-3.3-70b-versatile` |
| Temperature | 0.1 |
| Max tokens | 500 (V1) |

Prompts loaded from versioned files under `prompts/` — not embedded in Python except loader glue.

---

### Evaluation Layer (`run_eval.py`, `eval/metrics.py`, `eval/judge.py`)

**Responsibility:** Offline quality measurement, regression detection.

- Does not import Streamlit
- Calls same `pipeline.answer_query()` as UI
- Writes JSON reports to `eval_results/` (gitignored)

See [EVALUATION.md](./EVALUATION.md).

---

### Configuration (`atlas/config.py`)

**Responsibility:** Environment variables, defaults, model IDs, paths.

Loaded from `.env` via `python-dotenv`. Example keys: `GROQ_API_KEY`.

---

## Data Flow

### Indexing flow

```
corpus/**/*.md
    → ingest (read + metadata)
    → chunking (semantic_chunk_text)
    → embeddings (encode batch)
    → store.upsert(chunks + vectors + metadata)
    → UI/Observability: {files, chunks, collection_name}
```

Optional: legacy root `.txt` files indexed with `domain=legacy` for conflict demos (P1).

### Query flow (runtime)

```
user question
    → embeddings.encode(query)
    → store.query + retrieval.hybrid_rescore
    → [optional] rerank.cross_encoder
    → pipeline.abstention_check
    → generation (prompt + context + question)
    → PipelineResult → UI render
```

---

## Retrieval Flow (Detailed)

```
Query text
    │
    ▼
┌─────────────────┐
│ Embed query     │  all-MiniLM-L6-v2
└────────┬────────┘
         ▼
┌─────────────────┐
│ Chroma query    │  top-N by vector distance (N ≥ final K)
└────────┬────────┘
         ▼
┌─────────────────┐
│ Keyword rescore │  term overlap per chunk
└────────┬────────┘
         ▼
┌─────────────────┐
│ Combined rank   │  vector + α·keyword
└────────┬────────┘
         ▼
┌─────────────────┐     disabled
│ Cross-encoder   │◄──── rerank toggle
└────────┬────────┘
         ▼
┌─────────────────┐
│ Top-K select    │  K=3 default
└────────┬────────┘
         ▼
┌─────────────────┐
│ Threshold gate  │  → abstain if below
└─────────────────┘
```

---

## Generation Flow (Detailed)

```
Top-K chunks + question + mode + prompt_version
    │
    ▼
┌─────────────────────────────┐
│ Load prompts/{version}/     │
│   answer_grounded.txt       │
│   abstention.txt (if gate)  │
└────────┬────────────────────┘
         ▼
┌─────────────────────────────┐
│ Build context block         │
│ [C1] source=... text=...    │
│ [C2] ...                    │
└────────┬────────────────────┘
         ▼
┌─────────────────────────────┐
│ Groq chat completion        │
└────────┬────────────────────┘
         ▼
┌─────────────────────────────┐
│ clean_llm_output()          │
│ Parse citation markers      │
└────────┬────────────────────┘
         ▼
    Answer + cited chunk IDs
```

**Grounded mode instruction (conceptual):** Answer only from `[C1]…[Cn]`; cite as `[C#]` and source path; if insufficient, use abstention template.

---

## Evaluation Flow

```
evaluation_dataset.json
    │
    ▼
For each case:
    pipeline.answer_query(question)
    │
    ├── metrics: recall@k, context F1, answer F1, citation check
    └── judge: faithfulness, completeness (Groq, JSON output)
    │
    ▼
Aggregate report → eval_results/run_{timestamp}.json
    │
    ▼
CI smoke: compare recall@3 vs baseline threshold
```

---

## Observability

### Runtime (live demo)

| Signal | Source | Surface |
|--------|--------|---------|
| Total latency ms | `telemetry.py` wall clock | Observability |
| Retrieve ms | Pipeline span | Observability |
| Rerank ms | Pipeline span | Observability |
| Generate ms | Pipeline span | Observability |
| Chunks retrieved / used | PipelineResult | Evidence Inspector |
| Per-chunk score | Retrieval result | Evidence Inspector |
| Index file count | Store metadata | Observability |
| Abstained flag | PipelineResult | Knowledge Workspace |

### Offline (eval)

| Signal | Source |
|--------|--------|
| Recall@1, Recall@3 | `eval/metrics.py` |
| Context / answer F1 | `eval/metrics.py` |
| Citation accuracy | `eval/metrics.py` |
| Judge scores | `eval/judge.py` |
| Prompt version | Recorded in eval report |

**Prohibited in V1:** Hardcoded faithfulness percentages, simulated chunk paths, sleep-based “processing.”

---

## Separation of Concerns

| Layer | May depend on | Must not depend on |
|-------|---------------|-------------------|
| UI (`app.py`) | `pipeline`, `config` | Chroma directly, prompt strings, sklearn |
| Pipeline | retrieval, generation, store, telemetry | Streamlit |
| Retrieval | store, embeddings | Groq, Streamlit |
| Generation | prompts/, config | Streamlit, Chroma |
| Store | chromadb, config | Streamlit, Groq |
| Evaluation | pipeline, metrics, judge | Streamlit |

---

## Repository Layout (Target)

```
glass-box-rag/
├── app.py                      # Thin Streamlit shell (to be rewired)
├── run_eval.py                 # Eval CLI entrypoint
├── atlas/
│   ├── config.py
│   ├── ingest.py
│   ├── chunking.py
│   ├── embeddings.py
│   ├── store.py
│   ├── retrieval.py
│   ├── rerank.py
│   ├── generation.py
│   ├── pipeline.py
│   └── telemetry.py
├── eval/
│   ├── metrics.py
│   └── judge.py
├── prompts/
│   └── v1/
│       ├── answer_grounded.txt
│       ├── answer_general.txt
│       ├── abstention.txt
│       └── judge_faithfulness.txt
├── scripts/
│   └── index_corpus.py
├── corpus/                     # Committed knowledge base
├── evaluation_dataset.json     # Golden set
├── docs/                       # Product & engineering contract
└── chroma_db/                  # Gitignored, local index
```

---

## Migration Strategy (No Greenfield Rewrite)

1. **Extract** `semantic_chunk_text`, hybrid retrieval, `clean_llm_output`, Groq call from `8d28058` into `atlas/` modules unchanged in algorithm.
2. **Replace** in-memory DataFrame with `atlas/store.py` (Chroma).
3. **Point** ingestion at committed `corpus/` instead of upload-only.
4. **Rewire** `app.py` to call `pipeline.answer_query()` — preserve useful UX patterns (inspector, modes) but replace prototype mock logic and visual design direction per [PRODUCT.md](./PRODUCT.md).
5. **Add** `run_eval.py` sharing pipeline — no duplicate retrieval logic.

---

## Related Documents

- [PRODUCT.md](./PRODUCT.md)
- [EVALUATION.md](./EVALUATION.md)
- [PROMPTS.md](./PROMPTS.md)
- [DEMO.md](./DEMO.md)
