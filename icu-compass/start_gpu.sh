#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
APP_DIR="$PWD"
RUNTIME="${ICU_RUNTIME:-$HOME/workspace/icu-runtime}"
PY="$RUNTIME/venv/bin/python"
export HF_HOME="$RUNTIME/hf-cache"
export HF_ENDPOINT=http://huggingface.khdp-cache-server
export HF_HUB_DISABLE_XET=1
export LLM_BASE_URL=http://127.0.0.1:8091/v1
export LLM_MODEL="${ICU_MODEL_ID:-Qwen/Qwen3-VL-8B-Instruct-FP8}"
MODEL_PATH="${ICU_MODEL_PATH:-$RUNTIME/models/Qwen3-VL-8B-Instruct-FP8}"
if [ ! -f "$MODEL_PATH/config.json" ]; then MODEL_PATH="$LLM_MODEL"; fi
mkdir -p "$RUNTIME/logs"
if ! curl -fsS --max-time 2 http://127.0.0.1:8091/health >/dev/null; then
  if [ -f "$RUNTIME/model.pid" ] && kill -0 "$(cat "$RUNTIME/model.pid")" 2>/dev/null; then
    echo "Model is still starting; see $RUNTIME/logs/model.log"
  else
    nohup "$RUNTIME/venv/bin/vllm" serve "$MODEL_PATH" --served-model-name "$LLM_MODEL" \
      --host 127.0.0.1 --port 8091 --dtype bfloat16 \
      --max-model-len 8192 --max-num-seqs 1 \
      --gpu-memory-utilization 0.90 --enforce-eager \
      --limit-mm-per-prompt '{"image":1,"video":0}' \
      --mm-processor-kwargs '{"max_pixels":1048576}' \
      > "$RUNTIME/logs/model.log" 2>&1 < /dev/null &
    echo $! > "$RUNTIME/model.pid"
  fi
fi
if ! curl -fsS --max-time 2 http://127.0.0.1:8000/api/state >/dev/null; then
  nohup env POOL="${POOL:-mimic}" ICU_COHORT=surgical HOST=127.0.0.1 PORT=8000 \
    PYTHONDONTWRITEBYTECODE=1 "$PY" -u "$APP_DIR/server.py" \
    > "$RUNTIME/logs/app.log" 2>&1 < /dev/null &
  echo $! > "$RUNTIME/app.pid"
fi
echo "App: authenticated Jupyter URL + /proxy/8000/"
echo "Model startup/download can take several minutes. Run bash status_gpu.sh."
