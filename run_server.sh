#!/usr/bin/env bash
# 한울 감사조서 자가검토 — 사내 테스트 서버 (도메인 없이 LAN IP 접속)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ ! -x "$ROOT/VENV/bin/streamlit" ]]; then
  echo "오류: VENV/bin/streamlit 이 없습니다. 가상환경을 먼저 준비해 주세요." >&2
  exit 1
fi

PORT="${STREAMLIT_SERVER_PORT:-8505}"
export STREAMLIT_SERVER_PORT="$PORT"

echo ""
echo "=== 한울 감사조서 자가검토 · 사내 테스트 서버 ==="
echo ""
"$ROOT/VENV/bin/python3" - <<'PY'
import config

print("접속 URL (동일 사내망):")
for url in config.deployment_access_urls():
    print(f"  • {url}")
print("")
print("도메인 연결 시 .env 의 APP_BASE_URL 에 주소를 넣으면 위 목록이 대체됩니다.")
print("서버를 중지하려면 Ctrl+C")
print("")
PY

exec "$ROOT/VENV/bin/streamlit" run app.py \
  --server.port="$PORT" \
  --server.address=0.0.0.0 \
  --server.headless=true
