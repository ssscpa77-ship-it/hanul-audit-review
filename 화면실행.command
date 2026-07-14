#!/bin/bash
# 감사조서 자가검토 — 더블클릭 실행 (Mac 전용)
cd "$(dirname "$0")" || exit 1

clear
echo ""
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║   감사조서 자가검토 — 실행 중                ║"
echo "  ╚══════════════════════════════════════════════╝"
echo ""
echo "  잠시만 기다려 주세요 (약 20초)..."
echo ""

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
chmod +x keep_alive.sh run_tunnel.sh sync_public_url.sh 2>/dev/null || true

# 이전 감시 프로세스 정리
if [[ -f .keep_alive.pid ]]; then
  old="$(cat .keep_alive.pid 2>/dev/null || true)"
  [[ -n "$old" ]] && kill "$old" 2>/dev/null || true
fi
rm -f .keep_alive.pid

# 서버 시작
if ! lsof -i :8505 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "  [1/3] 앱 시작..."
  nohup VENV/bin/streamlit run app.py --server.port=8505 --server.address=0.0.0.0 --server.headless=true >>.server.log 2>&1 &
  sleep 5
fi

if ! lsof -i :8506 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "  [2/3] 접속 게이트웨이 시작..."
  nohup VENV/bin/python share_gateway.py >>.gateway.log 2>&1 &
  sleep 2
fi

echo "  [3/3] 공개 URL 연결..."
./run_tunnel.sh 8506 share 2>&1 | tail -1

URL=""
[[ -f .tunnel.url ]] && URL="$(tr -d '[:space:]' < .tunnel.url)"
[[ -z "$URL" && -f .tunnel.url.stable ]] && URL="$(tr -d '[:space:]' < .tunnel.url.stable)"

if [[ -z "$URL" ]]; then
  echo ""
  echo "  [오류] URL 생성 실패. 인터넷 연결을 확인하세요."
  read -r -p "  엔터 키를 누르면 창이 닫힙니다..."
  exit 1
fi

echo "$URL" > .tunnel.url.stable
APP_URL="${URL}/?app=1"
SHARE_URL="${URL}/?share=1"

echo ""
echo "  ══════════════════════════════════════════════"
echo "  실행 완료!"
echo ""
echo "  ▶ 앱 주소:"
echo "  $APP_URL"
echo ""
echo "  ▶ 교수님 전달용:"
echo "  $SHARE_URL"
echo "  ══════════════════════════════════════════════"
echo ""
echo "  ⚠️  이 터미널 창을 닫으면 접속이 끊깁니다."
echo ""

# 교수님 메시지 갱신
if [[ -f share/kakao_message.txt ]]; then
  sed "s|{{SHARE_URL}}|$SHARE_URL|" share/kakao_message.txt > 교수님_전달_메시지.txt 2>/dev/null || true
fi

echo "  브라우저를 엽니다..."
sleep 1
open "$APP_URL"

# 백그라운드 감시 (창 유지)
nohup ./keep_alive.sh >>.keep_alive.log 2>&1 &
echo ""
echo "  백그라운드 감시 시작됨. 이 창은 열어 두세요."
echo ""
read -r -p "  엔터 키를 누르면 창이 닫힙니다 (닫지 않는 것을 권장)..."
