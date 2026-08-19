# AtlasIQ V1 — Productization Report

**Date:** 2026-08-17 (updated: deployment blockers + UI polish)  
**Scope:** Public demo / internet deployment readiness (UI, observability, docs, deploy)  
**Explicitly out of scope:** Full 59 / Phase-8 evals, Groq API calls in this pass, Phase 10

---

## Verdict

AtlasIQ V1 is **demo-ready with deploy controls**. Password gate, readiness checklist, Docker path, synthetic-corpus disclaimer, and rate-limit UX are in place. **Still required of the operator:** set secrets, enable auth, choose a host with HTTPS, and use a Groq plan with enough TPD for traffic.

Phase 9 product hardening remains complete; full post-fix suite re-eval stays **deferred (Groq TPD)**.

---

## Deployment blockers — resolution status

| Blocker | Status | Resolution |
|---------|--------|------------|
| Secrets / API keys in UI | **Resolved** | Key never rendered; Settings shows boolean only |
| No auth on Streamlit | **Resolved (code)** | `ATLASIQ_APP_PASSWORD` / secrets `password` gate; `ATLASIQ_REQUIRE_AUTH=1` fails closed without password; Docker defaults require auth |
| Host binding | **Resolved** | `scripts/entrypoint.sh` + compose bind `0.0.0.0:8501`; README documents reverse proxy |
| Empty index / cold start | **Resolved** | Entrypoint indexes if empty; Dockerfile attempts build-time index; Settings Index button |
| Eval artifacts gitignored | **Resolved** | Allowlist preferred clean JSONs + reports in `.gitignore` |
| Synthetic corpus confusion | **Resolved** | Persistent disclaimer banner + README callout |
| Groq TPD / 429 | **Mitigated (not eliminated)** | Friendly rate-limit UX distinct from abstention; generation error classifies 429; operator must use adequate Groq plan |
| Phase 9 suite proof incomplete | **Deferred** | Documented; Evaluation surface prefers Phase 8 clean artifacts |

---

## UI polish (this pass)

- Password sign-in screen for protected deploys
- Synthetic corpus disclaimer on Workspace + Settings
- Example query chips for demos
- Rate-limit / missing-key error copy (not abstention)
- Settings → **Deployment readiness** checklist
- Sidebar access-mode warning when open/local
- Footer trust line on all surfaces
- Streamlit theme + Docker/compose packaging

---

## How to run a protected demo

```bash
export GROQ_API_KEY=...
export ATLASIQ_APP_PASSWORD='...'
export ATLASIQ_REQUIRE_AUTH=1
docker compose up --build
```

Or local: `streamlit run app.py` (open mode with sidebar warning until password is set).

---

## Tests run (no LLM API)

```text
38 passed, 1 deselected
```

Includes `tests/test_deploy_readiness.py`.

---

## Remaining operator work before public launch

1. Set `GROQ_API_KEY` + `ATLASIQ_APP_PASSWORD` on the host.
2. Keep `ATLASIQ_REQUIRE_AUTH=1` for any public URL.
3. Terminate TLS in front of Streamlit.
4. Confirm Groq plan TPD for expected demo traffic.
5. When TPD recovers: run deferred Phase 9 clean evals once (offline CLI).

**STOP.** No full eval executed in this pass. No Phase 10.
