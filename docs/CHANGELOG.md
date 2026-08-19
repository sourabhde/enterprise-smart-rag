# AtlasIQ Changelog

All notable product and engineering changes for AtlasIQ are recorded here.

Behavior-affecting changes **must** be documented, including changes to:

- Prompts under `prompts/`
- Generation or embedding models
- Retrieval parameters (top-k, keyword weight, hybrid formula)
- Similarity / abstention thresholds
- Reranking defaults
- Golden dataset schema or contents
- Evaluation methodology (metrics, judge prompts, scoring rules)
- Pipeline contracts that alter answers or eval scores

Format follows a lightweight Keep-a-Changelog style.

---

## [Unreleased]

### Planned (AtlasIQ V1 implementation)

- Wire modular `atlas/` pipeline to corpus ingestion and ChromaDB (`atlasiq_v1` collection)
- Evidence-grounded generation with versioned prompts (`prompts/v1/`)
- Score-gated abstention and Evidence Inspector on real retrieval
- `run_eval.py` with retrieval, generation, citation metrics and LLM-as-judge
- Redesigned enterprise Streamlit surfaces (Knowledge, Evidence, Evaluation, Observability, Settings)
- Remove prototype mock answers and fake telemetry from `app.py`

---

## [0.1.0] — 2026-08-16 — Contract phase (pre-implementation)

### Added

- Product and engineering contract documentation:
  - `docs/PRODUCT.md`
  - `docs/PRODUCT_PRINCIPLES.md`
  - `docs/ARCHITECTURE.md`
  - `docs/EVALUATION.md`
  - `docs/PROMPTS.md`
  - `docs/DEMO.md`
  - `docs/CHANGELOG.md`
- Versioned prompt set for V1 (files only; not yet loaded by application code):
  - `prompts/v1/answer_grounded.txt`
  - `prompts/v1/answer_general.txt`
  - `prompts/v1/abstention.txt`
  - `prompts/v1/judge_faithfulness.txt`

### Current repository state (honest baseline)

- Branch `atlasiq-v1` includes synthetic enterprise corpus (`corpus/`, 50 markdown files) and partial golden set (`evaluation_dataset.json`, 30 items).
- Eval generation scripts exist (`generate_corpus.py`, `generate_all_eval_gemini.py`, etc.).
- Current `app.py` is a **prototype UI shell** with mock indexing and mock answers—not the target AtlasIQ runtime.
- Proven RAG logic remains available in Git history (`8d28058`) but is not connected to the current UI or corpus index path.
- Local `chroma_db/` may contain legacy indexes; it is gitignored and not the contracted `atlasiq_v1` collection until implementation.

### Notes

- This entry marks the **contract lock for documentation and prompts**, not a production runtime release.
- After the first locked eval baseline, treat `prompts/v1/` as immutable; introduce `prompts/v2/` for prompt changes (see `docs/PROMPTS.md`).
