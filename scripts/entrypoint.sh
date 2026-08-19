#!/usr/bin/env bash
# AtlasIQ container/process entrypoint: ensure index exists, then start Streamlit.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PYTHONUNBUFFERED=1

echo "[atlasiq] checking corpus index…"
python3 - <<'PY'
from atlas.store import collection_count
try:
    n = collection_count()
except Exception as exc:
    print(f"[atlasiq] index check failed ({exc}); will attempt index")
    n = 0
if n and n > 0:
    print(f"[atlasiq] index ready ({n} chunks)")
    raise SystemExit(0)
print("[atlasiq] empty index — running scripts/index_corpus.py")
raise SystemExit(2)
PY
status=$?
if [[ "$status" -eq 2 ]]; then
  python3 scripts/index_corpus.py
fi

PORT="${PORT:-${STREAMLIT_SERVER_PORT:-8501}}"
ADDR="${STREAMLIT_SERVER_ADDRESS:-0.0.0.0}"

echo "[atlasiq] starting Streamlit on ${ADDR}:${PORT}"
exec streamlit run app.py \
  --server.port "$PORT" \
  --server.address "$ADDR" \
  --browser.gatherUsageStats false
