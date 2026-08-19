# AtlasIQ V1 — container image for demo / internet hosting
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.cache/huggingface \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501 \
    ATLASIQ_REQUIRE_AUTH=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

RUN chmod +x scripts/entrypoint.sh \
 && mkdir -p chroma_db eval_results .streamlit .cache/huggingface

# Pre-warm embedding model + build index at image build time when network allows.
# If build-time indexing fails (offline), entrypoint will index on first boot.
RUN python3 scripts/index_corpus.py || echo "[atlasiq] deferring index to container start"

EXPOSE 8501

# Secrets at runtime:
#   -e GROQ_API_KEY=...
#   -e ATLASIQ_APP_PASSWORD=...
#   -e ATLASIQ_REQUIRE_AUTH=1
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health')" || exit 1

CMD ["./scripts/entrypoint.sh"]
