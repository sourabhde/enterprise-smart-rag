# AtlasIQ — Product Principles

These principles govern product decisions, implementation tradeoffs, and demo behavior for AtlasIQ V1 and beyond. When two options compete, the higher-listed principle wins unless explicitly documented otherwise.

---

## 1. Evidence Before Fluency

**A correct, cited, partial answer is better than a fluent, uncited, complete-sounding answer.**

- Generation prompts require grounding in retrieved chunks only (in grounded mode).
- The UI prioritizes showing **what evidence was used** alongside the answer text.
- Copy and layout should not hide retrieval behind the answer.
- Marketing language must match implemented behavior—no claiming “hybrid retrieval” if the path is mocked.

**Implication:** Never ship demo UI that returns templated answers. If the pipeline is down, show an error—not a plausible fabrication.

---

## 2. Abstention Before Hallucination

**When evidence is weak, AtlasIQ refuses—not guesses.**

- Abstention is triggered by measurable signals (e.g., max retrieval score below threshold, empty result set), not only by prompt pleading.
- Abstention responses use explicit, professional language: what was searched, why confidence was insufficient, suggested next steps.
- Private/grounded mode must abstain rather than fall back to world knowledge.

**Implication:** Demo scripts include at least one question designed to fail retrieval, proving the guardrail works.

---

## 3. Explainability and Provenance

**Every answer must be auditable back to source documents.**

- Retrieved chunks, scores, and source paths are always available in the Evidence Inspector.
- Citations in answers reference real sources that appear in the retrieval set.
- Chunk metadata includes at minimum: `source`, `domain`, `chunk_index`.

**Implication:** “Black box answer + trust us” is unacceptable for enterprise positioning.

---

## 4. Measurable Retrieval Quality

**Retrieval is a product feature, not an implementation detail.**

- Golden-set evaluation includes Recall@k and context overlap metrics.
- Retrieval changes require re-running eval before demo or merge.
- Hybrid retrieval parameters (keyword weight, top-k, threshold) are configurable and documented.

**Implication:** Do not optimize solely for demo anecdotes; optimize for reproducible metrics on `evaluation_dataset.json`.

---

## 5. Versioned AI Behavior

**Prompts, models, and thresholds are versioned artifacts—not invisible code constants.**

- Prompts live in `prompts/` as named, versioned files (see [PROMPTS.md](./PROMPTS.md)).
- Evaluation results record `prompt_version`, `model_id`, and key thresholds.
- CHANGELOG documents behavior changes that affect answers or scores.

**Implication:** “We changed a string in app.py” is not an acceptable release process for a knowledge product.

---

## 6. Evaluation-Driven Development

**Features ship with a measurement plan.**

- New retrieval or generation behavior → update or extend golden set → run eval → compare to baseline.
- Regressions block merge when CI smoke eval is enabled.
- LLM-as-judge supplements but does not replace deterministic metrics.

**Implication:** V1 is not complete without `run_eval.py` and a documented baseline report.

---

## 7. Explicit Uncertainty

**AtlasIQ communicates confidence honestly.**

- Distinguish: grounded answer, partial coverage, conflicting sources, insufficient evidence.
- Do not display precision (e.g., “98% faithfulness”) without a defined measurement behind it.
- Judge scores appear in **Evaluation** surface and offline reports; live UI shows only computed runtime signals unless judge is invoked synchronously (V1: judge is primarily offline).

**Implication:** Remove or replace all hardcoded telemetry from prototype UI before calling V1 done.

---

## Principle Conflicts — Resolution Guide

| Conflict | Resolution |
|----------|------------|
| Fluency vs evidence | Evidence wins; shorten answer if needed |
| Speed vs reranking | Reranking optional; default off for latency-sensitive demo |
| Coverage vs abstention | Abstention wins in grounded mode |
| Judge score vs deterministic F1 | Report both; F1 gates CI, judge informs quality review |
| UI polish vs real pipeline | Real pipeline first; polish around truth |

---

## Anti-Patterns (Explicitly Rejected)

1. **Demoware metrics** — Static latency, fake chunk lists, hardcoded faithfulness
2. **Prompt archaeology** — Prompts embedded in UI files with no version ID
3. **Silent corpus drift** — Indexed data differs from committed corpus with no rebuild path
4. **Citation theater** — Citations in answer text that don’t map to retrieved chunks
5. **Eval optional** — Shipping retrieval changes without golden-set run
6. **Consumer chat UX** — Bubble UI, emoji status, gradient-heavy “AI magic” branding

---

## Related Documents

- [PRODUCT.md](./PRODUCT.md) — Product definition
- [EVALUATION.md](./EVALUATION.md) — How principles become metrics
- [PROMPTS.md](./PROMPTS.md) — Versioned prompt contract
