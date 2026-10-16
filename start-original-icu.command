#!/bin/zsh
# 더블클릭하면 3교대가 추가된 ICU 전체 상황판을 실행하고 웹 브라우저를 엽니다.
set -u

TASK_ICU_DIR="${0:A:h}"
TASK_ICU_APP="$TASK_ICU_DIR/icu-board"
if [[ ! -f "$TASK_ICU_APP/server.py" && -f "$TASK_ICU_DIR/server.py" ]]; then
  TASK_ICU_APP="$TASK_ICU_DIR"
fi
TASK_ICU_PYTHON='/Users/iganghun/.local/bin/python3'

if [[ ! -f "$TASK_ICU_APP/server.py" ]]; then
  print '3교대 ICU 앱을 찾지 못했습니다:' "$TASK_ICU_APP"
  read 'REPLY?Enter를 누르면 종료합니다. '
  exit 1
fi

if [[ ! -x "$TASK_ICU_PYTHON" ]]; then
  TASK_ICU_PYTHON="$(command -v python3)"
fi
if [[ -z "$TASK_ICU_PYTHON" || ! -x "$TASK_ICU_PYTHON" ]]; then
  print 'Python 3 실행 파일을 찾지 못했습니다.'
  read 'REPLY?Enter를 누르면 종료합니다. '
  exit 1
fi

cd "$TASK_ICU_APP" || exit 1
export PYTHONDONTWRITEBYTECODE=1
export POOL=mimic

"$TASK_ICU_PYTHON" -u - <<'PY'
import sys
import threading
import webbrowser

import server

url = "http://127.0.0.1:8000/"
try:
    httpd = server.ThreadingHTTPServer(("127.0.0.1", 8000), server.H)
except OSError as error:
    print(f"ICU 상황판 서버를 시작하지 못했습니다: {error}", file=sys.stderr)
    print("기존 상황판이 실행 중이면 그 터미널에서 Ctrl+C로 종료한 뒤 다시 실행하세요.", file=sys.stderr)
    sys.exit(1)

threading.Thread(target=server.ticker, daemon=True).start()
print(f"ICU 전체 상황판: {url}")
print("8개 ICU · 64병상 · 간호사 40명/조 · 데이/이브닝/나이트 3교대")
print("이 터미널을 열어 두세요. 종료하려면 Ctrl+C를 누르세요.")
try:
    webbrowser.open(url)
except Exception as error:
    print(f"브라우저 자동 열기를 건너뜁니다. 위 주소를 직접 여세요: {error}")
try:
    httpd.serve_forever()
except KeyboardInterrupt:
    print("\nICU 상황판을 종료했습니다.")
finally:
    httpd.server_close()
PY

TASK_ICU_STATUS=$?
if (( TASK_ICU_STATUS != 0 )); then
  read 'REPLY?Enter를 누르면 종료합니다. '
fi
exit "$TASK_ICU_STATUS"
