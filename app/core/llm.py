import json
import logging

import httpx

from app.core.config import (
    AWS_REGION,
    LLM_PROVIDER,
    LLM_TIMEOUT_SECONDS,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    SAGEMAKER_ENDPOINT_NAME,
)

logger = logging.getLogger("llm")
_sagemaker_client = None


def get_provider_name() -> str:
    return LLM_PROVIDER


def _get_sagemaker_client():
    global _sagemaker_client
    if _sagemaker_client is None:
        import boto3

        _sagemaker_client = boto3.client("sagemaker-runtime", region_name=AWS_REGION)
    return _sagemaker_client


def chat_message(
    messages: list[dict],
    tools: list | None = None,
    temperature: float = 0,
    max_tokens: int = 1024,
    tool_choice: str = "auto",
) -> dict:
    provider = get_provider_name()

    if provider == "sagemaker":
        payload = {
            "messages": messages,
            "tools": tools or [],
            "tool_choice": tool_choice,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        response = _get_sagemaker_client().invoke_endpoint(
            EndpointName=SAGEMAKER_ENDPOINT_NAME,
            ContentType="application/json",
            Body=json.dumps(payload),
        )
        data = json.loads(response["Body"].read())
        return data.get("choices", [{}])[0].get("message", {})

    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "tools": tools or [],
        "stream": False,
        "options": {"temperature": temperature},
    }
    with httpx.Client(timeout=LLM_TIMEOUT_SECONDS) as client:
        response = client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
        response.raise_for_status()
    return response.json().get("message", {})


def generate_json_content(
    prompt: str,
    temperature: float = 0.1,
    max_tokens: int = 2048,
) -> str:
    provider = get_provider_name()

    if provider == "sagemaker":
        message = chat_message(
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return message.get("content", "{}")

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    with httpx.Client(timeout=LLM_TIMEOUT_SECONDS) as client:
        response = client.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload)
        response.raise_for_status()
    return response.json().get("response", "{}")
