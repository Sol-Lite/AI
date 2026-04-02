#!/usr/bin/env bash
set -euo pipefail

AWS_REGION="${AWS_REGION:-ap-northeast-2}"
ENDPOINT_NAME="${ENDPOINT_NAME:?ENDPOINT_NAME is required}"
IMAGE_URI="${IMAGE_URI:?IMAGE_URI is required}"
SAGEMAKER_EXECUTION_ROLE_ARN="${SAGEMAKER_EXECUTION_ROLE_ARN:?SAGEMAKER_EXECUTION_ROLE_ARN is required}"

INSTANCE_TYPE="${INSTANCE_TYPE:-ml.g5.2xlarge}"
INITIAL_INSTANCE_COUNT="${INITIAL_INSTANCE_COUNT:-1}"
VARIANT_NAME="${VARIANT_NAME:-AllTraffic}"

OLLAMA_MODEL="${OLLAMA_MODEL:-llama3.1:8b}"
OLLAMA_PRELOAD_MODEL="${OLLAMA_PRELOAD_MODEL:-true}"
OLLAMA_REQUIRE_MODEL="${OLLAMA_REQUIRE_MODEL:-true}"
OLLAMA_REQUEST_TIMEOUT_SECONDS="${OLLAMA_REQUEST_TIMEOUT_SECONDS:-300}"
OLLAMA_READY_MAX_ATTEMPTS="${OLLAMA_READY_MAX_ATTEMPTS:-90}"

MODEL_DATA_URL="${MODEL_DATA_URL:-}"
MODEL_DATA_DOWNLOAD_TIMEOUT_SECONDS="${MODEL_DATA_DOWNLOAD_TIMEOUT_SECONDS:-1800}"
CONTAINER_STARTUP_HEALTH_CHECK_TIMEOUT_SECONDS="${CONTAINER_STARTUP_HEALTH_CHECK_TIMEOUT_SECONDS:-1800}"

TIMESTAMP="${TIMESTAMP:-$(date +%Y%m%d%H%M%S)}"
MODEL_NAME="${MODEL_NAME:-${ENDPOINT_NAME}-model-${TIMESTAMP}}"
ENDPOINT_CONFIG_NAME="${ENDPOINT_CONFIG_NAME:-${ENDPOINT_NAME}-config-${TIMESTAMP}}"

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

export IMAGE_URI
export MODEL_NAME
export ENDPOINT_CONFIG_NAME
export SAGEMAKER_EXECUTION_ROLE_ARN
export OLLAMA_MODEL
export OLLAMA_PRELOAD_MODEL
export OLLAMA_REQUIRE_MODEL
export OLLAMA_REQUEST_TIMEOUT_SECONDS
export OLLAMA_READY_MAX_ATTEMPTS
export MODEL_DATA_URL
export VARIANT_NAME
export INITIAL_INSTANCE_COUNT
export INSTANCE_TYPE
export MODEL_DATA_DOWNLOAD_TIMEOUT_SECONDS
export CONTAINER_STARTUP_HEALTH_CHECK_TIMEOUT_SECONDS

python3 - <<'PY' > "${TMP_DIR}/create-model.json"
import json
import os

container = {
    "Image": os.environ["IMAGE_URI"],
    "Environment": {
        "OLLAMA_MODEL": os.environ["OLLAMA_MODEL"],
        "OLLAMA_PRELOAD_MODEL": os.environ["OLLAMA_PRELOAD_MODEL"],
        "OLLAMA_REQUIRE_MODEL": os.environ["OLLAMA_REQUIRE_MODEL"],
        "OLLAMA_REQUEST_TIMEOUT_SECONDS": os.environ["OLLAMA_REQUEST_TIMEOUT_SECONDS"],
        "OLLAMA_READY_MAX_ATTEMPTS": os.environ["OLLAMA_READY_MAX_ATTEMPTS"],
    },
}

model_data_url = os.environ.get("MODEL_DATA_URL", "")
if model_data_url:
    container["ModelDataUrl"] = model_data_url

payload = {
    "ModelName": os.environ["MODEL_NAME"],
    "ExecutionRoleArn": os.environ["SAGEMAKER_EXECUTION_ROLE_ARN"],
    "PrimaryContainer": container,
}

print(json.dumps(payload))
PY

python3 - <<'PY' > "${TMP_DIR}/create-endpoint-config.json"
import json
import os

payload = {
    "EndpointConfigName": os.environ["ENDPOINT_CONFIG_NAME"],
    "ProductionVariants": [
        {
            "VariantName": os.environ["VARIANT_NAME"],
            "ModelName": os.environ["MODEL_NAME"],
            "InitialInstanceCount": int(os.environ["INITIAL_INSTANCE_COUNT"]),
            "InstanceType": os.environ["INSTANCE_TYPE"],
            "InitialVariantWeight": 1.0,
            "ModelDataDownloadTimeoutInSeconds": int(os.environ["MODEL_DATA_DOWNLOAD_TIMEOUT_SECONDS"]),
            "ContainerStartupHealthCheckTimeoutInSeconds": int(
                os.environ["CONTAINER_STARTUP_HEALTH_CHECK_TIMEOUT_SECONDS"]
            ),
        }
    ],
}

print(json.dumps(payload))
PY

echo "[deploy] creating SageMaker model: ${MODEL_NAME}"
aws sagemaker create-model \
  --region "${AWS_REGION}" \
  --cli-input-json "file://${TMP_DIR}/create-model.json"

echo "[deploy] creating endpoint config: ${ENDPOINT_CONFIG_NAME}"
aws sagemaker create-endpoint-config \
  --region "${AWS_REGION}" \
  --cli-input-json "file://${TMP_DIR}/create-endpoint-config.json"

if aws sagemaker describe-endpoint \
  --region "${AWS_REGION}" \
  --endpoint-name "${ENDPOINT_NAME}" >/dev/null 2>&1; then
  echo "[deploy] updating endpoint: ${ENDPOINT_NAME}"
  aws sagemaker update-endpoint \
    --region "${AWS_REGION}" \
    --endpoint-name "${ENDPOINT_NAME}" \
    --endpoint-config-name "${ENDPOINT_CONFIG_NAME}" >/dev/null
else
  echo "[deploy] creating endpoint: ${ENDPOINT_NAME}"
  aws sagemaker create-endpoint \
    --region "${AWS_REGION}" \
    --endpoint-name "${ENDPOINT_NAME}" \
    --endpoint-config-name "${ENDPOINT_CONFIG_NAME}" >/dev/null
fi

echo "[deploy] waiting for endpoint to become InService"
aws sagemaker wait endpoint-in-service \
  --region "${AWS_REGION}" \
  --endpoint-name "${ENDPOINT_NAME}"

echo "[deploy] done"
echo "MODEL_NAME=${MODEL_NAME}"
echo "ENDPOINT_CONFIG_NAME=${ENDPOINT_CONFIG_NAME}"
echo "ENDPOINT_NAME=${ENDPOINT_NAME}"
