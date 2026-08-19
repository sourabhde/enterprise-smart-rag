# AtlasIQ — Product Definition

**Version:** V1 (demonstration)  
**Status:** Pre-implementation contract  
**Branch:** `atlasiq-v1`

---

## Product Vision

AtlasIQ is an **enterprise knowledge intelligence platform** that helps organizations answer high-stakes business questions from their own documents with **evidence-first answers**, **explicit provenance**, and **measurable quality**.

Unlike generic RAG chatbots that optimize for fluent prose, AtlasIQ is designed for environments where a wrong discount threshold, SLA percentage, or pricing figure has commercial and legal consequences. Every answer must be traceable to source material, inspectable by a human reviewer, and evaluable against a golden dataset.

AtlasIQ V1 is a **recruiter- and hiring-manager-facing production-style demonstration**: a working system with real retrieval, real evaluation, and a professional enterprise UI—not a slide deck or a mocked dashboard.

---

## Target Users

### Primary (V1 demo audience)

| User | What they need to see |
|------|------------------------|
| **Hiring managers / engineering leaders** | Architectural maturity, quality gates, observability, and honest handling of uncertainty |
| **Recruiters / portfolio reviewers** | Clear product story, live demo flow, measurable outcomes |
| **Enterprise AI / platform engineers** | Separation of concerns, eval-driven development, versioned behavior |

### Secondary (product direction, not V1 buyers)

| User | Future need |
|------|-------------|
| **Revenue operations / deal desk** | Authoritative answers on discount authority and pricing |
| **Legal / compliance** | SLA terms, liability caps, policy version clarity |
| **Sales engineering** | SKU tiers, API limits, contract terms |
| **Knowledge platform owners** | Regression-tested releases, corpus lifecycle, conflict surfacing |

---

## Enterprise Problem

Enterprise knowledge is fragmented across policies, product specs, legal agreements, and pricing matrices. Teams currently:

- Search SharePoint or wikis manually and hope they found the latest version
- Ask generic chatbots that **sound confident but cite nothing**
- Cannot **audit** why an AI gave a particular number
- Have **no regression testing** when corpus or prompts change
- Face **conflicting documents** (policy v1 vs v5, legacy txt vs current md) with no system to surface disagreement

The cost of a hallucinated discount cap or uptime SLA is not a bad UX moment—it is a compliance, revenue, or contractual risk.

---

## Primary Use Cases

1. **Policy lookup with authority** — “What discount can a Regional Sales Director approve under Framework 10?”
2. **Commercial terms** — “What is the base subscription for Module 12 and how many seats are included?”
3. **SLA and legal** — “What uptime commitment applies to Region 01 and what credits apply below 95%?”
4. **Evidence audit** — Reviewer inspects retrieved chunks and similarity scores behind an answer
5. **Quality assurance** — Operator runs golden-set evaluation before a demo or release
6. **Abstention** — System refuses to answer when retrieved evidence is insufficient rather than guessing

---

## What AtlasIQ Does

- **Ingests** a structured document corpus (markdown policies, SKUs, SLAs)
- **Chunks semantically** using embedding-distance boundaries, not arbitrary token splits
- **Indexes persistently** in a vector store (ChromaDB) with source metadata
- **Retrieves hybrid** (vector similarity + keyword signal) with optional cross-encoder reranking
- **Generates grounded answers** constrained to retrieved evidence
- **Cites sources explicitly** with provenance visible in the UI
- **Abstains** when confidence/evidence thresholds are not met
- **Evaluates** retrieval, generation, and citation quality against a golden dataset
- **Judges** faithfulness via LLM-as-judge in offline evaluation
- **Reports telemetry** — latency breakdown, chunk counts, real scores (never fabricated)

---

## What AtlasIQ Deliberately Does NOT Do (V1)

| Out of scope | Rationale |
|--------------|-----------|
| General-purpose open-domain chat | General mode may exist for comparison, but the product story is **grounded enterprise Q&A** |
| Autonomous agents / tool use | Scope control; V1 is retrieve-then-answer |
| Real-time multi-user auth / RBAC | Demo single-tenant; architecture leaves room for later |
| Automatic conflict resolution | V1 may **surface** conflicts; it does not pick a “winner” silently |
| Document authoring / CMS | Read-only knowledge consumption |
| Guaranteed legal advice | Assistant for internal document lookup, not a lawyer |
| Fabricated metrics | No hardcoded “99% faithfulness” in production UI |
| Emoji-driven or gamified UX | Professional B2B presentation standard |

---

## Key Product Capabilities

| Capability | V1 target |
|------------|-----------|
| Corpus ingestion & sync | Index `corpus/` into persistent vector store |
| Semantic chunking | Embedding-shift sentence boundaries (from proven baseline) |
| Hybrid retrieval | Cosine similarity + keyword rescore |
| Optional reranking | Cross-encoder toggle |
| Evidence-grounded generation | Groq Llama with evidence-first prompts |
| Citations & provenance | Inline source references + Evidence Inspector |
| Abstention | Score-gated refusal with explicit message |
| Golden evaluation | `evaluation_dataset.json` + `run_eval.py` |
| LLM-as-judge | Offline faithfulness/groundedness scoring |
| Latency telemetry | Retrieve / rerank / generate breakdown |
| Versioned prompts | Files under `prompts/`, recorded in eval results |

---

## Intended Product Surfaces

AtlasIQ V1 organizes the application into five surfaces. The current Streamlit file is a **prototype shell only**; the target UI is described here and in [DEMO.md](./DEMO.md).

### 1. Knowledge Workspace

Primary Q&A interface. User asks enterprise questions; answers appear with citation markers and an evidence confidence indicator. Restrained layout, strong typographic hierarchy, no decorative chat bubbles.

### 2. Evidence / Source Inspector

Dedicated panel (or slide-over) showing retrieved chunks ranked by score, source path, domain, chunk text, and whether each chunk was used in generation. Provenance is **visually prominent**, not buried in a debug expander.

### 3. Evaluation

View last eval run: Recall@k, answer overlap, citation accuracy, judge scores, latency percentiles. Supports reproducible “quality gate” narrative for reviewers.

### 4. System / Observability

Pipeline stage status, index health (files, chunks), inference latency, token usage where available. Every metric binds to real runtime data.

### 5. Settings / Configuration

Corpus path, similarity threshold, rerank toggle, execution mode (grounded / general), prompt version selector (future). Changes affect behavior predictably and are evaluable.

---

## UI Design Direction

The final UI must feel like a **serious B2B enterprise AI platform**, not a generic ChatGPT clone.

**Do**

- Professional, restrained, information-dense but readable layout
- Strong visual hierarchy (question → answer → evidence → metrics)
- Evidence and provenance as first-class visual elements
- Operational metrics that reflect actual pipeline output
- Neutral palette, subtle borders, table/list views for chunks and eval results

**Do not**

- Emoji-driven navigation or status indicators
- Excessive gradients, giant decorative cards, or gamified “health” widgets
- Fake metrics (hardcoded faithfulness, simulated chunk lists)
- Childish copy or consumer-chat aesthetics

---

## Success Metrics

### Demo success (recruiter session)

| Metric | Target |
|--------|--------|
| Live grounded answer with visible citations | 3/3 scripted questions |
| Evidence Inspector shows real retrieved chunks | Always |
| Abstention demo on out-of-corpus question | Clear refusal, no fabrication |
| Eval report reproducible via single command | Yes |
| No fake telemetry in UI | Zero hardcoded scores |

### Technical success (V1 release)

| Metric | Target |
|--------|--------|
| Source Recall@3 (golden set) | ≥ 0.80 |
| Mean context token F1 (top retrieved vs expected) | ≥ 0.50 |
| Citation accuracy (answer references golden source) | ≥ 0.70 |
| Judge faithfulness mean (1–5 scale) | ≥ 4.0 |
| P50 end-to-end latency | < 2s (local demo) |
| Corpus indexed | 50 md files |

### Product narrative success

Reviewers can articulate: *what problem AtlasIQ solves*, *how evidence is shown*, *how quality is measured*, and *what happens when evidence is insufficient*—without the presenter apologizing for mock behavior.

---

## Related Documents

- [PRODUCT_PRINCIPLES.md](./PRODUCT_PRINCIPLES.md) — Engineering and product values
- [ARCHITECTURE.md](./ARCHITECTURE.md) — System design
- [EVALUATION.md](./EVALUATION.md) — Quality measurement
- [PROMPTS.md](./PROMPTS.md) — Versioned prompt contract
- [DEMO.md](./DEMO.md) — Demonstration script
