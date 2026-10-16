#!/bin/bash
# 맥(Apple Silicon)에서 Qwen3-VL을 로컬로 띄우는 스크립트. 상황판의 "AI 상담"이 이 서버를 쓴다.
# 처음 한 번 모델을 내려받음 (8B 약 6GB / 30B-A3B 약 18GB). 다른 노트북은 이거 없이도 상황판은 돌아감(규칙 기반 응답).
#   ./run_qwen_local.sh            # 기본 8B (빠름)
#   ./run_qwen_local.sh 30b        # 30B-A3B (한국어·판단 더 좋음, 메모리 32GB 이상 권장)
set -e
cd "$(dirname "$0")"
MODEL=mlx-community/Qwen3-VL-8B-Instruct-4bit
[ "$1" = "30b" ] && MODEL=mlx-community/Qwen3-VL-30B-A3B-Instruct-4bit
if [ ! -x .venv-llm/bin/python ]; then
  command -v uv >/dev/null || { echo "uv 필요: brew install uv"; exit 1; }
  uv venv -q --python 3.12 .venv-llm
  uv pip install -q --python .venv-llm/bin/python mlx-vlm
fi
echo "Qwen 서버 시작: $MODEL → http://127.0.0.1:8091/v1"
exec .venv-llm/bin/python -m mlx_vlm.server --model "$MODEL" --host 127.0.0.1 --port 8091 --max-tokens 600
