# AtlasIQ — Evidence-grounded Sales/CPQ Intelligence (V1)

AtlasIQ answers Sales/CPQ questions **only when retrieved corpus evidence is sufficient**. It cites sources, abstains on underspecified or out-of-scope questions, and exposes provenance in a Streamlit product UI.

> **Demo corpus:** synthetic 50-document Sales/CPQ knowledge base — not a real customer’s commercial data.

## What V1 includes

- Hybrid retrieval over SKU / policy / SLA markdown corpus
- Evidence threshold gate + entity / unsupported / underspecified abstention
- Grounded generation via Groq (`openai/gpt-oss-120b` by default)
- Password gate for public hosting (`ATLASIQ_APP_PASSWORD`)
- Knowledge Workspace, Evidence Inspector, Reliability, Observability, Settings, Evaluation
- Docker image + compose for demo deployment

## Requirements

- Python 3.10+ (3.12 recommended)
- Groq API key (`GROQ_API_KEY`)
- Local disk for Chroma persistence (`chroma_db/`)
- For public URLs: app password + `ATLASIQ_REQUIRE_AUTH=1`

## Local setup

```bash
git clone <your-repo-url>
cd glass-box-rag
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env — set GROQ_API_KEY=...
python3 scripts/index_corpus.py
streamlit run app.py
```

Optional model override:

```bash
export GROQ_MODEL=openai/gpt-oss-120b
```

## Public / internet demo (recommended)

**Do not expose Streamlit without a password.**

```bash
export GROQ_API_KEY=...
export ATLASIQ_APP_PASSWORD='choose-a-strong-password'
export ATLASIQ_REQUIRE_AUTH=1
docker compose up --build
```

Or without Docker:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# set password = "..."
export GROQ_API_KEY=...
export ATLASIQ_REQUIRE_AUTH=1
export ATLASIQ_APP_PASSWORD='...'
python3 scripts/index_corpus.py
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

Put HTTPS termination (Caddy / nginx / cloud LB) in front of port 8501.

### Streamlit Community Cloud

1. Deploy the repo.
2. Add secrets: `GROQ_API_KEY`, and `password` (see `.streamlit/secrets.toml.example`).
3. Also set env `ATLASIQ_REQUIRE_AUTH=1` if the platform supports it (or rely on secrets password alone — the UI gate activates whenever a password is configured).
4. Confirm Evaluation artifacts `run_v1_clean_full.json` and `run_phase8_challenge_clean_v3.json` are present (git allowlisted).

### Settings → Deployment readiness

The in-app checklist validates API key presence, auth, non-empty index, corpus path, and preferred eval artifacts — without printing secrets.

## Evaluation (offline)

Authoritative clean artifacts:

- `eval_results/run_v1_clean_full.json`
- `eval_results/run_phase8_challenge_clean_v3.json`

```bash
python3 run_eval.py --skip-judge --output eval_results/run_v1_clean_full.json
```

Phase 9 full-suite re-eval may be deferred when Groq **TPD** is exhausted. Rate-limited partials are quarantined.

## Safety

- Never commit `.env` or `.streamlit/secrets.toml`
- Never screenshot or log API keys / passwords
- Prefer Grounded mode for demos
- Treat Evaluation ERROR as infrastructure, not product FP/FN
- Groq free-tier TPD: wait for daily reset; do not tight-loop retries

## Product surfaces

| Surface | Purpose |
|---------|---------|
| Knowledge Workspace | Ask → retrieve → answer / abstain → citations → evidence |
| Evidence Inspector | Provenance, chunks, scores, model, trust state |
| Reliability | Failure modes and engineering controls |
| Observability | Index + latency |
| Settings | Mode, threshold, rerank, corpus sync, **deploy readiness** |
| Evaluation | Authoritative `run_*.json` metrics only |
