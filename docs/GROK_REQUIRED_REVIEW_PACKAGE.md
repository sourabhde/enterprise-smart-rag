# GROK_REQUIRED_REVIEW_PACKAGE

## Gate status

```
CURRENT_PHASE: 5 — Independent Validation
BLOCKER: Grok (xAI) is not available in this environment
EVIDENCE:
  - No Grok/xAI MCP tool registered
  - `grok` CLI not found
  - No XAI_API_KEY / GROK_API_KEY in the agent environment
  - Mission forbids pretending independent validation occurred
  - Mission forbids freezing the benchmark or continuing to Phases 6–14 until independent review is genuine
DECISION_REQUIRED: Provide Grok access OR run this package through Grok externally and return findings
RECOMMENDED_NEXT_ACTION: Independent Grok review of evaluation_dataset_v1_proposed.json against corpus/, then Phase 6 adjudication
```

## What was completed before this gate (Phases 1–4)

| Phase | Result |
|-------|--------|
| 1 Corpus testability | **`CORPUS_STATUS = FREEZE`** — see `docs/V1_CORPUS_TESTABILITY.md` |
| 2 Current 30 audit | All answerable; missing negatives/adversarial/multi-doc — see `docs/V1_BENCHMARK_DESIGN.md` |
| 3 Test matrix design | Behavioral matrix defined; conflict out of scope |
| 4 Structured gold | **`evaluation_dataset_v1_proposed.json`** (PROPOSED_NOT_FROZEN) |

**Not done (blocked):** benchmark freeze, eval-engine upgrade against frozen gold, full `answer_query()` benchmark run, product failure fixes, UI Evaluation wiring, packaging/README claims, final validation report.

## Inputs to give Grok

1. **Entire corpus:** all files under `corpus/**/*.md` (50 docs).
2. **Proposed benchmark:** `evaluation_dataset_v1_proposed.json`.
3. **Schema / design:** `docs/V1_BENCHMARK_DESIGN.md`.
4. **Corpus matrix:** `docs/V1_CORPUS_TESTABILITY.md`.
5. **Product contract excerpts (optional but recommended):** `docs/PRODUCT.md`, `docs/EVALUATION.md`, `docs/V1_HANDOFF.md` (LOCKED decisions).
6. **This instruction block** (below).

## Explicit instructions for Grok

Copy-paste:

```
You are an independent auditor for AtlasIQ V1, an enterprise Sales/CPQ knowledge assistant.

Do not assume the benchmark creator is correct.
Independently verify EVERY case in evaluation_dataset_v1_proposed.json against the source corpus.

For each case, check:
1. Is expected_answer supported by acceptable_sources (when expect_abstention=false)?
2. Are key_facts present in those sources (accounting for formatting like $1,600 vs $1600)?
3. Are acceptable_sources correct (not too narrow, not wrongly broad)?
4. If expect_abstention=true, is evidence genuinely insufficient / entity absent?
5. Is expected_behavior clear (answer | abstain | correct_premise)?
6. Are ambiguous / identifier-free cases labeled honestly?
7. Are multi-document cases actually requiring multiple docs?
8. Duplicate test intent?
9. Wrong citation expectations?
10. Missing important behavioral categories given the FREEZE corpus?

Product constraints:
- Pipeline behaviors are answer or abstain (no clarify mode). Underspecified multi-answer questions are proposed as abstain.
- Conflict detection is out of scope (corpus has no same-entity contradictions).
- Do not invent corpus facts.

Return:
- PASS / FAIL per case with evidence quotes
- List of required gold edits
- List of cases to drop or split
- Any product-policy questions that need a human decision
```

## Assumed policies awaiting acceptance

1. **Underspecified questions** (e.g. “What is the base subscription cost?” with no Module) → **`abstain`** (not “pick any module”).
2. **Shared identical facts** across siblings (e.g. Tier2 `$0.00012`) → **`answer`** with **all** matching docs in `acceptable_sources`.
3. **Conflict questions** → not included (corpus FREEZE; not a V1 claim).

If Grok or the user rejects (1), the ambiguous abstain cases must be redesigned before freeze.

## How to unblock

1. Run Grok on this package (chat, API, or Cursor with Grok).
2. Return structured findings (or paste into the repo as `eval_results/grok_benchmark_review.json` — optional).
3. Resume **Phase 6 — Benchmark Adjudication** (resolve disagreements against corpus; flag irresolvable items for user).
4. Only then freeze gold, upgrade eval metrics, and run the real shared-pipeline benchmark.

## Integrity statement

**No Grok independent validation was performed in this session.**  
Groq (generation/judge provider) is **not** a substitute for the required Grok review under this mission’s Phase 5 rules.
