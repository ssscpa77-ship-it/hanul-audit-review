#!/usr/bin/env bash
# Streamlit만 재시작 — 공개 URL(터널)은 유지 (업데이트 반영)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
APP_PORT="${STREAMLIT_SERVER_PORT:-8505}"
STAMP="${ROOT}/.deploy_stamp"
SERVER_LOG="${ROOT}/.server.log"

echo "=== 앱 재시작 (공개 URL 유지) ==="

# KB 캐시 초기화
"$ROOT/VENV/bin/python3" - <<'PY' 2>/dev/null || true
import knowledge_base as kb
for name in ("_cached_standard_procedures",):
    fn = getattr(kb, name, None)
    if fn and hasattr(fn, "cache_clear"):
        fn.cache_clear()
print("KB 캐시 초기화")
PY

pid="$(lsof -ti :"$APP_PORT" -sTCP:LISTEN 2>/dev/null | head -1 || true)"
if [[ -n "${pid:-}" ]]; then
  kill "$pid" 2>/dev/null || true
  sleep 2
fi

nohup "$ROOT/VENV/bin/streamlit" run app.py \
  --server.port="$APP_PORT" \
  --server.address=0.0.0.0 \
  --server.headless=true >>"$SERVER_LOG" 2>&1 &

sleep 4
date "+%Y-%m-%d %H:%M:%S" > "$STAMP"
echo "✓ Streamlit 재시작 (포트 $APP_PORT)"

if [[ -f "${ROOT}/.tunnel.url" ]]; then
  echo "✓ 공개 URL (변경 없음): $(cat "${ROOT}/.tunnel.url")"
  echo "  앱 진입: $(cat "${ROOT}/.tunnel.url")?app=1"
fi
