# AtlasIQ V1 — Corpus Testability Matrix

**Phase:** 1  
**Decision:** `CORPUS_STATUS = FREEZE`  
**Date context:** Product validation mission (post T16)

## Inventory

| Domain | Docs | Entity pattern | Distinguishing facts | Shared / near-duplicate facts |
|--------|------|----------------|----------------------|-------------------------------|
| SKU / Module | 17 (`product_tier_01`–`17`) | Module N | Base $ (unique), add-seat $ (unique) | Tier2 `$0.00012`, Tier3 rider, 12% TCV / 4% inflation, 25 seats |
| Policy / Framework | 16 (`discount_matrix_policy_01`–`16`) | Framework N | AE max %, RSD band (unique per doc) | CPQ ledger 24h → commission forfeiture; exec/indemnification pattern |
| Legal / Region | 17 (`sla_agreement_region_01`–`17`) | Region NN | Uptime % (9 unique values / 17 docs) | Below-95% credit text; 100% liability cap |

**Total:** 50 markdown documents. **No** duplicate Module/Framework/Region IDs. **No** intentional same-entity contradictions.

## Capability support

| Capability | Supported? | How / limit |
|------------|------------|-------------|
| Exact lookup | Yes | Bullet/section facts |
| Entity-specific lookup | Yes | Module / Framework / Region IDs |
| Identifier-free lookup | Yes | But often ambiguous when facts are shared |
| Sibling discrimination | Yes | Via unique base/add-seat/uptime/AE/RSD when ID present |
| Numeric precision | Yes | Currency, %, uptime to 2 decimals |
| Policy lookup | Yes | DoA matrix |
| Legal/SLA lookup | Yes | Uptime, credits, liability |
| Citation validation | Yes | Stable `corpus/...` paths |
| Abstention / negatives | Yes | Out-of-range IDs, absent topics (no corpus edit needed) |
| Ambiguity | Yes | Shared boilerplate across siblings |
| Wrong-entity testing | Yes | Cross-module false prices / false AE caps |
| Adversarial premise | Yes | False numeric premise in question |
| Multi-document / cross-domain | Yes | e.g. Module fee + Framework AE in one question |
| Conflict detection | **No** | No conflicting statements for the same entity |
| Paraphrase testing | Yes | Natural rewording of the same facts |
| Evidence sufficiency | Yes | Underspecified questions (no Module/Framework) |
| Clarify mode | **N/A** | Not implemented in V1 pipeline (answer \| abstain only) |

## Decision Gate A — Corpus

**`CORPUS_STATUS = FREEZE`**

**Rationale:** Existing corpus adequately tests the V1 Sales/CPQ knowledge-assistant contract (SKU pricing, CPQ authority, SLA terms, citations, abstention, sibling traps). Conflict detection is **not** a claimed implemented V1 behavior; extending the corpus solely for conflicts would change product definition without necessity.

**Not done:** No corpus files added, removed, or rewritten.
