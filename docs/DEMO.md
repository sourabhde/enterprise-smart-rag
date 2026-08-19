# AtlasIQ — Recruiter / Hiring Manager Demonstration

**Version:** V1 target demo script  
**Status:** Pre-implementation contract  
**Audience:** Recruiters, hiring managers, engineering leaders

---

## Purpose

This document defines the intended **live demonstration** of AtlasIQ as a serious enterprise knowledge intelligence product—not a generic chatbot tour.

It distinguishes:

| Status | Meaning |
|--------|---------|
| **V1 target** | Behavior the demo must show after implementation |
| **Current (contract phase)** | Prototype UI shell; mock indexing/answers; real corpus + partial golden set exist |

Do **not** present mock answers or hardcoded metrics as product capability.

---

## Demo Narrative (30–45 seconds of framing)

**Problem:** Enterprise teams cannot trust fluent AI answers on pricing, discount authority, or SLA terms without provenance.

**Product:** AtlasIQ retrieves from an indexed corpus, answers only when evidence is sufficient, cites sources, and measures quality on a golden set.

**Proof:** Live grounded Q&A → Evidence Inspector → abstention → eval report → real latency.

---

## Intended Product Presentation (UI)

The current Streamlit UI is a **prototype shell only**. The demo presentation must use a **substantially redesigned** enterprise UI (V1 target), not preserve the current visual design for compatibility.

### Presentation principles

- Professional B2B knowledge platform; restrained, information-dense, readable
- Strong hierarchy: question → answer → citations → evidence → metrics
- Evidence and provenance visually prominent (not buried in a debug expander)
- Neutral palette; subtle borders; tables/lists for chunks and eval results
- No emoji navigation, gamified health widgets, excessive gradients, or ChatGPT-clone bubbles
- Every displayed metric comes from the real pipeline or a real eval report

### Surfaces used in the demo

1. **Knowledge Workspace** — ask questions; show grounded answer + citations  
2. **Evidence / Source Inspector** — ranked chunks, scores, sources, used/unused  
3. **Evaluation** — last golden-set run (Recall@k, F1, judge scores)  
4. **System / Observability** — index health, latency breakdown  
5. **Settings** (brief) — grounded mode, threshold, optional rerank

---

## Demo Flow (Target V1)

### 0. Preconditions (before the meeting)

1. Corpus indexed from committed `corpus/` (50 markdown files).  
2. Grounded mode enabled; similarity threshold set; rerank optional (call out if on).  
3. Golden eval run completed; report available on Evaluation surface or from `eval_results/`.  
4. Confirm no fake faithfulness / fake chunk lists in UI.

### 1. Grounded enterprise question

Ask a corpus-backed commercial or policy question (see scripted Q1–Q3).

**Show:** Concise answer with factual numbers and `[C1]` / `[C2]` citations.

**Say:** “Answers are constrained to retrieved evidence—not general web knowledge.”

### 2. Visible citations

Point to citation markers in the answer and the mapped source paths.

**Show:** Citation ↔ chunk ID ↔ file path consistency.

### 3. Evidence Inspector

Open the Evidence / Source Inspector.

**Show:** Ranked chunks, similarity/combined scores, domain, source path, which chunks were used in generation.

**Say:** “This is the audit trail for the answer—what a deal desk or compliance reviewer would inspect.”

### 4. Abstention / insufficient evidence

Ask an out-of-corpus or deliberately unanswerable question (see Q4).

**Show:** Professional abstention message; no fabricated policy; no invented confidence percentage unless the system supplies a real score.

**Say:** “When evidence is weak, AtlasIQ refuses rather than hallucinating.”

### 5. Evaluation / quality evidence

Open the Evaluation surface (or open a saved eval report).

**Show:** Source Recall@3, answer/context F1, citation metrics, mean judge faithfulness, `prompt_version` and `model_id` in metadata.

**Say:** “Quality is measurable and regression-testable—not anecdotal.”

### 6. Observability / latency

Open System / Observability.

**Show:** Files indexed, chunk count, retrieve_ms / generate_ms / total_ms for the last query (real timings).

**Avoid:** Hardcoded “99% faithfulness” or sleep-simulated processing.

---

## Scripted Demo Questions

Questions are grounded in the **existing synthetic corpus**. Adjust module/policy numbers if a live run prefers a different golden case.

### Q1 — Commercial / SKU (grounded)

**Question:**  
“What is the annual base platform subscription for Module 12, and how many named user seats are included?”

**Expected evidence domain:** `corpus/skus/product_tier_12.md`  
**Demo point:** Numeric grounding + citation to SKU doc.

### Q2 — Discount policy / authority (grounded)

**Question:**  
“Under Framework 10, what is the maximum discretionary discount an Account Executive can approve without higher authorization?”

**Expected evidence domain:** `corpus/policies/discount_matrix_policy_10.md`  
**Demo point:** Policy version specificity; cite policy path; Inspector shows policy chunk.

### Q3 — Legal / SLA (grounded)

**Question:**  
“What monthly uptime availability does the vendor commit to for production workloads in Region 01, and what remedy applies if availability drops below 95.0%?”

**Expected evidence domain:** `corpus/legal/sla_agreement_region_01.md`  
**Demo point:** Multi-fact answer with citations; legal tone without overclaiming.

### Q4 — Abstention (insufficient evidence)

**Question:**  
“What is our HIPAA breach notification timeline for US healthcare customers?”

**Expected behavior (V1 target):** Abstain — corpus has no HIPAA content.  
**Demo point:** Explicit refusal; Evidence Inspector empty or below-threshold; no invented regulation.

### Q5 — Optional stretch (conflict awareness narrative)

**Question:**  
“What discount can a Regional Sales Director approve?”

**Demo point (V1 target, soft):** Multiple policy versions may retrieve; if conflict surfacing is not implemented yet, **do not claim it**—instead show Inspector with multiple policy sources and note that V1 prioritizes provenance over silent resolution (per PRODUCT.md). Prefer Q1–Q4 for a clean first demo.

---

## Timing Guide (≈8–10 minutes)

| Minute | Step |
|--------|------|
| 0:00–0:45 | Problem + product framing |
| 0:45–3:00 | Q1 + citations + Inspector |
| 3:00–5:00 | Q2 or Q3 (second domain) |
| 5:00–6:30 | Q4 abstention |
| 6:30–8:30 | Evaluation + observability |
| 8:30–10:00 | Architecture one-liner (shared pipeline for UI + eval) + Q&A |

---

## What Not to Demo as “Done”

Until implemented and verified:

- Mock corpus indexing or templated answers in current `app.py`
- Cross-encoder reranking (toggle may exist; only claim if wired)
- Automatic conflict resolution
- Live LLM-as-judge scores in the chat UI (V1 judge is primarily offline per PRODUCT_PRINCIPLES)
- Fabricated faithfulness percentages

---

## Success Criteria for the Demo Session

From [PRODUCT.md](./PRODUCT.md):

- 3/3 grounded scripted questions with visible citations  
- Evidence Inspector always shows real retrieved chunks  
- Clear abstention on out-of-corpus question  
- Eval report reproducible / visible  
- Zero fake telemetry  

---

## Related Documents

- [PRODUCT.md](./PRODUCT.md) — Surfaces and UI direction  
- [PRODUCT_PRINCIPLES.md](./PRODUCT_PRINCIPLES.md) — Evidence and abstention principles  
- [EVALUATION.md](./EVALUATION.md) — Metrics shown in Evaluation surface  
- [PROMPTS.md](./PROMPTS.md) — Grounded / abstention / judge prompts  
- [ARCHITECTURE.md](./ARCHITECTURE.md) — Pipeline shared by UI and eval  
