#!/bin/zsh
set -eu
task_dir="${0:A:h}/icu-board"
cd "$task_dir"
if ! command -v python3 >/dev/null 2>&1; then
  print "Python 3.10 이상을 설치한 뒤 다시 실행하세요."
  exit 1
fi
python3 pod_check.py --offline
print "병상 예약 시연: http://127.0.0.1:${PORT:-8002}/planning"
print "전체 병동 상황판: http://127.0.0.1:${PORT:-8002}/"
POOL=synth OFFLINE_DEMO=1 PLANNER_MODE=offline HOST=127.0.0.1 PORT="${PORT:-8002}" python3 server.py
