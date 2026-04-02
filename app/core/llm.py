import json
import logging
from typing import Any

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


def _serialize_messages_for_sagemaker(
    messages: list[dict],
    tools: list | None = None,
) -> str:
    sections: list[str] = []

    if tools:
        tool_lines = [
            "[available_tools]",
            "Native function calling is not available in this environment.",
            "If a tool is needed, reply with exactly one plain text tool call.",
            "Single-argument example: get_stock_price(삼성전자)",
            'Multi-argument example: get_trade_history({"query_type":"recent","side":"buy","limit":1})',
            "",
            "Tool definitions:",
        ]
        for tool in tools:
            fn = tool.get("function", {})
            name = fn.get("name", "")
            desc = fn.get("description", "")
            params = json.dumps(fn.get("parameters", {}), ensure_ascii=False)
            tool_lines.append(f"- {name}: {desc}")
            tool_lines.append(f"  parameters: {params}")
        sections.append("\n".join(tool_lines))

    for message in messages:
        role = message.get("role", "user")

        if role == "assistant" and message.get("tool_calls"):
            calls = []
            for call in message.get("tool_calls", []):
                fn = call.get("function", {})
                name = fn.get("name", "")
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    arg_text = args
                else:
                    arg_text = json.dumps(args, ensure_ascii=False)
                calls.append(f"{name}({arg_text})")
            sections.append("[assistant]\n" + "\n".join(calls))
            continue

        if role == "tool":
            tool_name = message.get("name", "tool")
            content = str(message.get("content", ""))
            sections.append(f"[tool:{tool_name}]\n{content}")
            continue

        content = str(message.get("content", ""))
        sections.append(f"[{role}]\n{content}")

    sections.append("[assistant]")
    return "\n\n".join(sections)


def _extract_text_from_sagemaker_response(data: Any) -> str:
    if isinstance(data, str):
        return data.strip()

    if isinstance(data, list):
        for item in data:
            text = _extract_text_from_sagemaker_response(item)
            if text:
                return text
        return ""

    if isinstance(data, dict):
        for key in ("generated_text", "generation", "text", "output_text", "answer"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, (list, dict)):
                text = _extract_text_from_sagemaker_response(value)
                if text:
                    return text

        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message", {})
            if isinstance(message, dict):
                return str(message.get("content", "")).strip()

        if isinstance(data.get("content"), str):
            return data["content"].strip()

    return ""


def _invoke_sagemaker_text_generation(
    prompt: str,
    temperature: float = 0,
    max_tokens: int = 1024,
) -> str:
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": max_tokens,
            "return_full_text": False,
            "do_sample": temperature > 0,
            "temperature": temperature if temperature > 0 else 0.01,
        },
    }
    response = _get_sagemaker_client().invoke_endpoint(
        EndpointName=SAGEMAKER_ENDPOINT_NAME,
        ContentType="application/json",
        Body=json.dumps(payload, ensure_ascii=False),
    )
    data = json.loads(response["Body"].read())
    text = _extract_text_from_sagemaker_response(data)
    if not text:
        raise ValueError(f"Unexpected SageMaker response shape: {data}")
    return text


def chat_message(
    messages: list[dict],
    tools: list | None = None,
    temperature: float = 0,
    max_tokens: int = 1024,
    tool_choice: str = "auto",
) -> dict:
    provider = get_provider_name()

    if provider == "sagemaker":
        prompt = _serialize_messages_for_sagemaker(messages, tools)
        text = _invoke_sagemaker_text_generation(
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return {"content": text}

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
        return _invoke_sagemaker_text_generation(
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

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
