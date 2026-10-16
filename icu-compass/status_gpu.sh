#!/usr/bin/env bash
set -u
RUNTIME="${ICU_RUNTIME:-$HOME/workspace/icu-runtime}"
nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv
curl -fsS --max-time 3 http://127.0.0.1:8091/v1/models || true
curl -fsS --max-time 3 http://127.0.0.1:8000/api/llm || true
tail -n 12 "$RUNTIME/logs/model.log"
