#!/usr/bin/env bash
set -euo pipefail

export OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"
export PYTHONUNBUFFERED=1

MODEL_NAME="${OLLAMA_MODEL:-llama3.1:8b}"
MODEL_DIR="${SAGEMAKER_MODEL_DIR:-/opt/ml/model}"
PRELOAD_MODEL="${OLLAMA_PRELOAD_MODEL:-true}"
READY_MAX_ATTEMPTS="${OLLAMA_READY_MAX_ATTEMPTS:-90}"

wait_for_ollama() {
  local max_attempts="${1:-60}"
  local attempt=1
  while [ "$attempt" -le "$max_attempts" ]; do
    if curl -fsS "http://${OLLAMA_HOST}/api/tags" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
    attempt=$((attempt + 1))
  done
  return 1
}

model_exists() {
  curl -fsS "http://${OLLAMA_HOST}/api/tags" | tr -d '[:space:]' | grep -Fq "\"name\":\"${MODEL_NAME}\""
}

prepare_model() {
  if [ "${PRELOAD_MODEL}" != "true" ]; then
    return 0
  fi

  if model_exists; then
    echo "[entrypoint] Ollama model ${MODEL_NAME} already present"
    return 0
  fi

  if [ -f "${MODEL_DIR}/Modelfile" ]; then
    echo "[entrypoint] creating Ollama model from ${MODEL_DIR}/Modelfile"
    ollama create "${MODEL_NAME}" -f "${MODEL_DIR}/Modelfile"
    return 0
  fi

  echo "[entrypoint] pulling Ollama model ${MODEL_NAME}"
  ollama pull "${MODEL_NAME}"
}

if [ "${1:-serve}" = "serve" ]; then
  echo "[entrypoint] starting ollama serve on ${OLLAMA_HOST}"
  ollama serve &
  OLLAMA_PID=$!
  cleanup() {
    if kill -0 "${OLLAMA_PID}" >/dev/null 2>&1; then
      kill "${OLLAMA_PID}" >/dev/null 2>&1 || true
      wait "${OLLAMA_PID}" >/dev/null 2>&1 || true
    fi
  }
  trap cleanup EXIT TERM INT

  if ! wait_for_ollama "${READY_MAX_ATTEMPTS}"; then
    echo "[entrypoint] ollama did not become ready in time" >&2
    exit 1
  fi

  prepare_model

  echo "[entrypoint] starting SageMaker inference server on :8080"
  exec uvicorn server:app --host 0.0.0.0 --port 8080
fi

exec "$@"
