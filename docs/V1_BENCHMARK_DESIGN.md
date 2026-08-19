# AtlasIQ V1 — Benchmark Design (Proposed)

**Phase:** 2–4  
**Status:** `PROPOSED_NOT_FROZEN` — blocked on independent Grok review  
**Artifact:** `evaluation_dataset_v1_proposed.json`  
**Legacy set retained:** `evaluation_dataset.json` (30 cases, unchanged)

## Phase 2 — What the current 30 already test

| Present | Count (approx.) |
|---------|-----------------|
| Answerable / true positive | 30/30 |
| Identifier-specific | 15 |
| Identifier-free | 15 |
| Ambiguous (shared boilerplate) | ~11 |
| Numeric | 30 |
| Citation-oriented (implicit) | 30 |
| Paraphrase gold wording | ~17 |

**Absent from the 30:** wrong-entity, adversarial premise, true negatives / abstention, multi-document, cross-domain, conflict, explicit evidence-insufficiency labels, structured `expected_answer` / `key_facts`.

**Corpus can test but 30 don’t:** abstention, adversarial correction, multi-doc key-fact coverage, acceptable-source ambiguity, underspecified abstain.

**Neither corpus nor 30 can test:** same-entity conflict detection (no conflicting docs).

## Phase 3 — Target matrix (behavioral)

| Behavior bucket | Expected behavior | Proposed coverage |
|-----------------|-------------------|-------------------|
| Strong entity-specific TP | `answer` | SKU / policy / legal with IDs |
| Sibling discrimination | `answer` + single acceptable source | Unique add-seat / uptime / AE |
| Identifier-free shared fact | `answer` + many `acceptable_sources` | Tier2 rate, TCV/inflation, CPQ ledger |
| Underspecified ambiguity | `abstain` | Base price w/o Module; AE max w/o Framework |
| True negative / unsupported | `abstain` | Framework 99, Region 42, GDPR, Acme price, mobile SKU |
| Adversarial / wrong premise | `correct_premise` | False Module/Framework numbers in question |
| Multi-document / cross-domain | `answer` | Module+Framework; Region+Module |
| Numeric precision | `answer` | Region uptime to 2 decimals |
| Citation correctness | `answer` + `required_citations` | Module 8 seat price |
| Conflict | — | **OUT OF SCOPE** for V1 freeze |

**Assumed product policy (pending acceptance):** V1 has no `clarify` mode. Underspecified questions with multiple incompatible answers → **`abstain`**.

## Phase 4 — Schema (proposed)

```json
{
  "id": "v1_case_001",
  "type": ["answerable", "identifier_specific", "..."],
  "question": "...",
  "expected_answer": "... or null if abstain",
  "key_facts": ["$53,000", "..."],
  "acceptable_sources": ["corpus/..."],
  "required_citations": ["corpus/..."],
  "expect_abstention": false,
  "expected_behavior": "answer|abstain|correct_premise",
  "source": "primary path for legacy tools",
  "notes": "optional"
}
```

Not every field is required on every case.

## Proposed set summary

See `evaluation_dataset_v1_proposed.json`:

- **~51 cases** (coverage-optimized; not padded to 100)
- Mechanical check: every non-abstain `key_fact` (except soft labels) appears in at least one `acceptable_sources` file — **0 validation errors** at generation time
- **Not frozen** until Grok independent review + adjudication
