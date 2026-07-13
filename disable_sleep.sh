#!/usr/bin/env bash
# 맥북 절전·잠자기 완화 — 검증 기간 동안 서버 유지용
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
CAFFEINATE_PID_FILE="${ROOT}/.caffeinate.pid"

echo "=== 절전·잠자기 설정 ==="

# 전원 연결·배터리 모두 시스템 슬립 최소화 (sudo 필요 시 비밀번호 입력)
if sudo -n pmset -a sleep 0 standby 0 powernap 0 disksleep 0 2>/dev/null; then
  echo "✓ pmset: 시스템 슬립 비활성화 (sleep/standby/powernap/disksleep=0)"
elif sudo pmset -a sleep 0 standby 0 powernap 0 disksleep 0 2>/dev/null; then
  echo "✓ pmset: 시스템 슬립 비활성화"
else
  echo "! pmset 변경 실패 — caffeinate 로 대체 유지합니다."
fi

# 디스플레이만 꺼질 수 있음 (서버는 유지). 완전 방지 시: sudo pmset -a displaysleep 0
sudo pmset -a displaysleep 30 2>/dev/null || pmset -c displaysleep 30 2>/dev/null || true
echo "✓ 디스플레이 절전 30분 (시스템·네트워크는 유지)"

# caffeinate — 시스템 잠자기만 방지 (화면 절전은 허용)
pkill -f "caffeinate -dims" 2>/dev/null || true
existing="$(pgrep -f "caffeinate -ims" 2>/dev/null | head -1 || true)"
if [[ -n "${existing:-}" ]]; then
  echo "✓ caffeinate 이미 실행 중 (PID $existing)"
  echo "$existing" > "$CAFFEINATE_PID_FILE"
else
  nohup caffeinate -ims >>"${ROOT}/.keep_alive.log" 2>&1 &
  echo $! > "$CAFFEINATE_PID_FILE"
  echo "✓ caffeinate 시작 (화면 꺼짐 허용, PID $(cat "$CAFFEINATE_PID_FILE"))"
fi

echo ""
echo "현재 전원 설정:"
pmset -g custom | grep -E "sleep|standby|displaysleep|powernap" || pmset -g
echo ""
echo "복원(검증 종료 후): ./restore_sleep.sh"
