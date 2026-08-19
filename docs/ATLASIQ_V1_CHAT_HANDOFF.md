# AtlasIQ V1 — Chat Handoff

## Product
AtlasIQ is a **Streamlit + Python AI Sales & CPQ Deal Assistant**.
Positioning: **Build deals. Price accurately. Create customer-ready quotes. Close with confidence.**
It should feel like a Sales/CPQ product, not a generic RAG chatbot.

## Critical model distinction
- **AtlasIQ application LLM:** `openai/gpt-oss-120b` via Groq.
- Config: `atlas/config.py` → `GenerationConfig.model_id`; optional `GROQ_MODEL`.
- Secret: `GROQ_API_KEY`.
- **Cursor's coding-agent model (e.g. Grok 4.5 Medium) is separate and must not be confused with the application LLM.**

## Current state
Productization is complete. No Phase 10.
Focus now: **final product acceptance → deployment → demo → LinkedIn builder story**.

Corpus: 50 synthetic enterprise docs (17 SKU/product, 16 policy, 17 legal). Label corpus as synthetic in public demo.

## Evaluation history
Original 59-case clean authoritative run:
`eval_results/run_v1_clean_full.json`
TP/TN/FP/FN/WRONG/ERROR = **50/9/0/0/0/0**
Recall@3 = 1.0; key-fact = 1.0; citation ≈ 0.98; false abstention = 0; FP answer = 0; ERROR = 0.

Phase 8 authoritative:
`eval_results/run_phase8_challenge_clean_v3.json`
TP/TN/FP/FN/WRONG/ERROR = **39/17/0/0/1/0**, Recall@3=1.0, citation=1.0.
Residual was `p8_case_024` multi-document completeness.

Phase 9 fixed that real retrieval issue:
`diversify_by_query_entities` in `atlas/retrieval.py`.
Focused proof for p8_case_024 passed: **$53,000 + 29% + 99.10%**.
Full Phase 9 clean re-eval was blocked by Groq TPD 429; rate-limited artifacts are quarantined/non-authoritative.

Productization report:
`eval_results/PRODUCTIZATION_REPORT.md`

32 non-LLM tests passed, 1 live Groq test deselected.

## Product capabilities
UI now includes:
- QUESTION → RETRIEVAL → ANSWER → CITATIONS → EVIDENCE journey
- distinct Abstention vs Error states
- Evidence Inspector
- Reliability surface
- Evaluation authority filtering
- clean evaluation metrics
- HTML escaping / visual polish

Important system principle:
**ERROR ≠ ABSTENTION ≠ WRONG ANSWER.**
API/pipeline failures must never become TP/TN/FP/FN.

## Product bugs already found/fixed
1. Customer-specific negotiated price soft-refusal → hard abstention.
2. Underspecified pricing/discount questions → abstention/clarification.
3. Unsupported topics → hard abstention.
4. Entity metadata boost ignored by abstention gate → fixed.
5. Multi-entity top-k crowding → fixed with query-entity diversification.
6. Unicode citation/key-fact scoring issue → fixed.
7. Evaluation UI treating composed/rate-limited artifacts as authoritative → fixed.

## Demo questions
1. “What is the annual base subscription for Module 12, and how many seats are included?” → $53,000 / 25 seats + evidence.
2. “What is the maximum AE discount for Framework 10?” → up to 9% + policy citation.
3. “What is the Tier 2 price?” → $0.00012.
4. “What is the price for Framework 99?” → hard abstention; no generation.
5. “What negotiated price did Acme receive?” → hard abstention; never invent customer-specific price.
6. “What is the maximum AE discount?” → underspecified; clarify/abstain.

## What to do next
Do NOT start another giant benchmark or architecture phase by default.
Use renewed Cursor Pro intelligently for **targeted** work.

First perform one final end-to-end **UI/product acceptance pass**:
- Sales Assistant positioning
- Workspace / deal workflow
- sample questions
- pricing/discount experience
- citations and Evidence Inspector
- Abstention vs Error
- Reliability
- Evaluation
- public-demo safety

Then deploy a safe public demo:
- authentication/password
- secrets only via environment
- pre-indexed Chroma
- usage protection / quota awareness
- synthetic corpus disclosure
- HTTPS hosting

Then create the LinkedIn Builder story around:
**product thinking + AI system design + reliability engineering + evaluation discipline + deliberate abstention + evidence grounding + commercial workflow design + builder execution.**

Core narrative:
“I built an AI Sales Assistant that knows when it has enough evidence to answer, knows when it should abstain, distinguishes system failures from product outcomes, exposes the evidence behind recommendations, and measures its own reliability.”

## Working style
Preserve the existing architecture unless a genuine product bug is found.
Do not make Streamlit impersonate React. Optimize Streamlit-native UX: hierarchy, terminology, spacing, trust, workflow clarity, and commercial usefulness.
