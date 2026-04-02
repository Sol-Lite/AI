#!/usr/bin/env bash
set -euo pipefail

AWS_REGION="${AWS_REGION:-ap-northeast-2}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text)}"
ECR_REPOSITORY="${ECR_REPOSITORY:-sollite-ollama-proxy}"
IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M%S)}"
DOCKER_PLATFORM="${DOCKER_PLATFORM:-linux/amd64}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}:${IMAGE_TAG}"

echo "[build] ensuring ECR repository exists: ${ECR_REPOSITORY}"
if ! aws ecr describe-repositories \
  --region "${AWS_REGION}" \
  --repository-names "${ECR_REPOSITORY}" >/dev/null 2>&1; then
  aws ecr create-repository \
    --region "${AWS_REGION}" \
    --repository-name "${ECR_REPOSITORY}" >/dev/null
fi

echo "[build] logging into ECR"
aws ecr get-login-password --region "${AWS_REGION}" | \
  docker login \
    --username AWS \
    --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo "[build] building image: ${IMAGE_URI} (${DOCKER_PLATFORM})"
docker build \
  --platform "${DOCKER_PLATFORM}" \
  -t "${IMAGE_URI}" \
  "${SCRIPT_DIR}"

echo "[build] pushing image"
docker push "${IMAGE_URI}"

echo "[build] done"
echo "IMAGE_URI=${IMAGE_URI}"
