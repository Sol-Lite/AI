# SageMaker Ollama Proxy

Sol-Lite FastAPI가 SageMaker `InvokeEndpoint`만 호출하면, 컨테이너 내부에서 Ollama `/api/chat`과 `/api/generate`로 이어주는 커스텀 인퍼런스 컨테이너입니다.

- `/ping`: Ollama 프로세스와 모델 준비 상태 확인
- `/invocations`: SageMaker 규약 엔드포인트
- 내부 동작: `ollama serve` 실행 후 로컬 `http://127.0.0.1:11434`로 프록시

## Request Contract

`/invocations`는 두 가지 모드를 받습니다.

1. Chat

```json
{
  "route": "chat",
  "model": "llama3.1:8b",
  "messages": [{"role": "user", "content": "삼성전자 현재가 알려줘"}],
  "tools": [],
  "tool_choice": "auto",
  "options": {"temperature": 0, "num_predict": 1024}
}
```

응답은 Ollama `/api/chat` 응답을 그대로 반환합니다.

2. Generate

```json
{
  "route": "generate",
  "model": "llama3.1:8b",
  "prompt": "반드시 JSON 한 줄로 출력",
  "format": "json",
  "options": {"temperature": 0.1, "num_predict": 2048}
}
```

응답은 Ollama `/api/generate` 응답을 그대로 반환합니다.

## Model Loading

기본 동작은 컨테이너 시작 시 `OLLAMA_MODEL`을 준비하는 방식입니다.

- `OLLAMA_PRELOAD_MODEL=true`: 시작 시 모델 pull/create
- `OLLAMA_MODEL=llama3.1:8b`: 기본 모델 이름
- `OLLAMA_REQUIRE_MODEL=true`: `/ping`에서 모델 준비 여부까지 확인
- `OLLAMA_READY_MAX_ATTEMPTS=90`: Ollama API readiness 대기 횟수

`/opt/ml/model/Modelfile`이 있으면 `ollama create $OLLAMA_MODEL -f /opt/ml/model/Modelfile`을 사용합니다. 예시는 [Modelfile.example](/Users/inter4259/project/Sol-Lite/AI/sagemaker/ollama-proxy/Modelfile.example)에 있습니다.

## Build And Push

로컬이나 CI에서 아래 스크립트로 ECR까지 밀 수 있습니다.

```bash
cd sagemaker/ollama-proxy
chmod +x build_and_push.sh update_endpoint.sh
AWS_REGION=ap-northeast-2 \
ECR_REPOSITORY=sollite-ollama-proxy \
IMAGE_TAG=$(git rev-parse --short HEAD) \
DOCKER_PLATFORM=linux/amd64 \
./build_and_push.sh
```

출력 마지막 줄의 `IMAGE_URI=...` 값을 다음 단계에서 사용합니다.

맥에서 빌드할 때는 `linux/amd64`를 유지해야 합니다. SageMaker GPU endpoint는 x86_64 기준으로 맞추는 편이 안전합니다.
또한 SageMaker는 `application/vnd.oci.image.index.v1+json` 이미지를 거부할 수 있으므로, 스크립트는 `buildx --load` 후 `docker push`로 단일 manifest 이미지를 올리도록 맞춰져 있습니다.

## Update Endpoint

기존 endpoint를 유지한 채 model/config만 새로 만들고 `update-endpoint`로 교체합니다.

```bash
cd sagemaker/ollama-proxy
ENDPOINT_NAME=sollite-llama3-8b \
IMAGE_URI=<build_and_push.sh 결과 IMAGE_URI> \
SAGEMAKER_EXECUTION_ROLE_ARN=<SageMaker 실행 Role ARN> \
INSTANCE_TYPE=ml.g5.2xlarge \
OLLAMA_MODEL=llama3.1:8b \
CONTAINER_STARTUP_HEALTH_CHECK_TIMEOUT_SECONDS=1800 \
MODEL_DATA_DOWNLOAD_TIMEOUT_SECONDS=1800 \
./update_endpoint.sh
```

필요한 환경값:

- `ENDPOINT_NAME`: 교체할 SageMaker endpoint 이름
- `IMAGE_URI`: ECR에 올라간 커스텀 이미지 URI
- `SAGEMAKER_EXECUTION_ROLE_ARN`: SageMaker가 이미지/S3를 읽을 실행 역할
- `INSTANCE_TYPE`: Ollama를 올릴 ML 인스턴스. 현재 서비스 기준 `ml.g5.2xlarge` 유지 권장
- `MODEL_DATA_URL`:
  `/opt/ml/model/Modelfile`을 쓰고 싶을 때만 전달

## Network Notes

- `OLLAMA_PRELOAD_MODEL=true`로 두면 컨테이너 시작 시 `ollama pull` 또는 `ollama create`가 실행됩니다.
- 따라서 endpoint가 있는 서브넷에서 외부로 나가는 경로가 있어야 합니다. VPC 내부 private subnet만 쓰면 NAT 또는 동등한 egress가 필요합니다.
- 외부 egress가 없다면 모델을 이미지에 bake 하거나, `MODEL_DATA_URL`로 전달하는 `model.tar.gz` 안에 `Modelfile`을 포함하는 방식으로 운영해야 합니다.
- 모델 준비 시간이 길 수 있으므로 `ContainerStartupHealthCheckTimeoutInSeconds`는 넉넉하게 두는 편이 안전합니다.

## FastAPI Env Change

FastAPI 쪽은 아래 설정으로 전환합니다.

```text
LLM_PROVIDER=sagemaker
SAGEMAKER_RUNTIME_MODE=ollama_proxy
SAGEMAKER_ENDPOINT_NAME=<custom-endpoint-name>
OLLAMA_MODEL=llama3.1:8b
```

현재 Sol-Lite 앱은 위 설정일 때:

- 일반 채팅: SageMaker `route=chat`
- 시장 요약 JSON 생성: SageMaker `route=generate`, `format=json`

으로 동작하도록 [llm.py](/Users/inter4259/project/Sol-Lite/AI/app/core/llm.py#L1)에서 이미 분기돼 있습니다.
