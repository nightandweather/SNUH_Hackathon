#!/usr/bin/env bash
# Run against an existing OpenAI-compatible model service, without starting vLLM.
set -euo pipefail
cd "$(dirname "$0")"
RUNTIME="${ICU_RUNTIME:-$HOME/workspace/icu-runtime}"
PY="${ICU_PYTHON:-$RUNTIME/venv/bin/python}"
export ICU_LLM_CONFIG="${ICU_LLM_CONFIG:-$RUNTIME/llm-config.json}"
if [ ! -f "$ICU_LLM_CONFIG" ] && [ -z "${LLM_BASE_URL:-}" ]; then
  echo "Set LLM_BASE_URL or create the private server-local $ICU_LLM_CONFIG."
  echo 'JSON fields: base (documented API base URL), model (model ID), key (API key).'
  exit 1
fi
if [ ! -f "$ICU_LLM_CONFIG" ]; then unset ICU_LLM_CONFIG; fi
export POOL="${POOL:-mimic}" ICU_COHORT=surgical HOST=127.0.0.1 PORT="${PORT:-8000}"
exec "$PY" -u server.py
