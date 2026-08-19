# AtlasIQ — Prompt Versioning Contract

**Version:** V1  
**Status:** Engineering contract (pre-implementation)  
**Prompt root:** `prompts/`

---

## Purpose

Prompt versioning is a **first-class AtlasIQ capability**. Generation, abstention, and evaluation behavior must be reproducible, reviewable, and regression-tested. Prompt text must not live as invisible string literals inside Python application modules.

This contract aligns with:

- [PRODUCT.md](./PRODUCT.md) — versioned prompts as a V1 capability
- [PRODUCT_PRINCIPLES.md](./PRODUCT_PRINCIPLES.md) — “Versioned AI Behavior”
- [ARCHITECTURE.md](./ARCHITECTURE.md) — generation loads `prompts/{version}/`
- [EVALUATION.md](./EVALUATION.md) — eval reports must record `prompt_version`

---

## Design Rules

1. **Prompts live in files** under `prompts/<version>/`, not in `app.py` or pipeline modules (except a thin loader).
2. **Every runtime and eval run records `prompt_version`** (directory name, e.g. `v1`).
3. **Immutable published versions:** once `v1` is used in a locked baseline, do not silently edit it; create `v2`.
4. **One directory = one coherent behavior set.** All files in a version are intended to be used together.
5. **Template placeholders** are substituted at runtime by the generation/judge layer; placeholders are documented below.
6. **Tone:** professional enterprise English; no emojis; no consumer-chat slang.

---

## Repository Layout

```
prompts/
└── v1/
    ├── answer_grounded.txt      # Grounded / Private enterprise Q&A
    ├── answer_general.txt       # General / non-grounded mode
    ├── abstention.txt           # Insufficient-evidence response
    └── judge_faithfulness.txt   # Offline LLM-as-judge
```

Future versions:

```
prompts/
├── v1/   # frozen after baseline lock
└── v2/   # copy + intentional changes; CHANGELOG entry required
```

---

## V1 Prompt Set — Ownership and Purpose

| File | Owner / consumer | Purpose |
|------|------------------|---------|
| `answer_grounded.txt` | `atlas/generation.py` (target) | Evidence-first Q&A: answer only from retrieved context; cite `[C1]…[Cn]` |
| `answer_general.txt` | `atlas/generation.py` (target) | Non-grounded mode: general knowledge; must not claim corpus provenance |
| `abstention.txt` | `atlas/pipeline.py` / generation (target) | Professional refusal when score gate fails or evidence is insufficient |
| `judge_faithfulness.txt` | `eval/judge.py` (target) | Offline judge for faithfulness, completeness, citation quality (JSON) |

### Mode mapping (target)

| Execution mode | Prompt file |
|----------------|-------------|
| Grounded / Private / Auto-with-RAG | `answer_grounded.txt` |
| General / Auto-without-RAG | `answer_general.txt` |
| Abstention (score gate or model-declared insufficiency) | `abstention.txt` |
| Offline evaluation judge | `judge_faithfulness.txt` |

---

## Template Placeholders

Runtime substitution (exact placeholder names for V1 loaders):

| Placeholder | Used in | Meaning |
|-------------|---------|---------|
| `{{CONTEXT}}` | `answer_grounded.txt` | Numbered context block: `[C1] source=…` + chunk text, etc. |
| `{{QUESTION}}` | answer + abstention + judge | User question |
| `{{REASON}}` | `abstention.txt` | Optional system reason (e.g. “max retrieval score below threshold”) |
| `{{THRESHOLD}}` | `abstention.txt` | Optional configured similarity threshold (string) |
| `{{RETRIEVED_CHUNKS}}` | `judge_faithfulness.txt` | Same style as context block for judge |
| `{{ANSWER}}` | `judge_faithfulness.txt` | Model answer under review |
| `{{EXPECTED_CONTEXT}}` | `judge_faithfulness.txt` | Golden `expected_context` — **completeness only**; judge must not use it to invent support for claims |

Loader glue may also prepend/append system/user roles as required by the Groq chat API; the **semantic contract** of each file remains in the `.txt` content.

---

## Recording `prompt_version` in Metadata

### Runtime (`PipelineResult` / Observability — target)

Every answer (including abstention) should expose:

```json
{
  "prompt_version": "v1",
  "prompt_files": {
    "generation": "prompts/v1/answer_grounded.txt",
    "abstention": "prompts/v1/abstention.txt"
  },
  "model_id": "llama-3.3-70b-versatile"
}
```

### Evaluation report (required — see EVALUATION.md)

```json
{
  "prompt_version": "v1",
  "judge_prompt": "prompts/v1/judge_faithfulness.txt",
  "model_id": "llama-3.3-70b-versatile"
}
```

Changing any file under the active version without bumping the directory name is treated as a **silent behavior change** and is forbidden after baseline lock.

---

## Process: Creating `v2` Without Silently Changing `v1`

1. Copy `prompts/v1/` → `prompts/v2/`.
2. Edit only files under `v2/`.
3. Document the behavioral intent in [CHANGELOG.md](./CHANGELOG.md) (what changed and why).
4. Point config / Settings default (or eval flag) to `prompt_version=v2`.
5. Run `run_eval.py` with `prompt_version=v2`; compare to `v1` baseline.
6. Do not delete or overwrite `v1` while it remains a reported baseline version.
7. Merge only after eval deltas are understood (retrieval metrics may be unchanged; generation/judge may shift).

**Allowed without a new version directory (pre-baseline only):** editorial typo fixes in draft `v1` before the first locked baseline eval. After baseline lock, typos that alter model behavior still require `v2` or a documented patch version policy.

---

## How Prompt Changes Are Evaluated

| Change type | Required evaluation |
|-------------|---------------------|
| `answer_grounded.txt` | Full core eval: Answer F1, citation metrics, judge faithfulness mean |
| `answer_general.txt` | Manual demo check; optional smoke (general mode not primary golden path) |
| `abstention.txt` | Live abstention demo + P1 abstention cases when available |
| `judge_faithfulness.txt` | Re-judge prior answers if comparing judge methodology; document in CHANGELOG that judge methodology changed (scores not comparable across judge prompt versions without re-run) |

CI smoke (P1) gates retrieval primarily; generation prompt regressions are caught by local full eval before demo.

---

## Consistency With Product Principles

| Principle | Prompt implication |
|-----------|-------------------|
| Evidence before fluency | `answer_grounded.txt` forbids unsupported claims |
| Abstention before hallucination | Score gate + `abstention.txt`; grounded prompt also refuses when context is thin |
| Explainability / provenance | Mandatory `[C#]` citations tied to supplied context |
| Explicit uncertainty | No fabricated confidence scores in abstention or answers |
| Evaluation-driven development | Judge prompt versioned; scores recorded with `prompt_version` |

---

## What Is Not Implemented Yet

As of this contract phase:

- Prompt loaders and `prompts/` wiring are **not** present in application code.
- Current `app.py` does not load these files.
- Eval runner / judge that consume `judge_faithfulness.txt` are **not** implemented.

These files define the **V1 contract** for upcoming implementation.

---

## Related Documents

- [EVALUATION.md](./EVALUATION.md)
- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [PRODUCT_PRINCIPLES.md](./PRODUCT_PRINCIPLES.md)
- [CHANGELOG.md](./CHANGELOG.md)
- [DEMO.md](./DEMO.md)
