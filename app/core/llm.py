import json
import logging
import re
from typing import Any

import httpx
from json_repair import repair_json

from app.core.config import (
    AWS_REGION,
    LLM_PROVIDER,
    LLM_TIMEOUT_SECONDS,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    SAGEMAKER_ENDPOINT_NAME,
    SAGEMAKER_RUNTIME_MODE,
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


def _invoke_sagemaker_ollama_proxy(payload: dict) -> dict:
    response = _get_sagemaker_client().invoke_endpoint(
        EndpointName=SAGEMAKER_ENDPOINT_NAME,
        ContentType="application/json",
        Body=json.dumps(payload, ensure_ascii=False),
    )
    data = json.loads(response["Body"].read())
    if not isinstance(data, dict):
        raise ValueError(f"Unexpected Ollama proxy response shape: {data}")
    return data


def _json_candidates(text: str) -> list[str]:
    stripped = text.strip()
    candidates: list[str] = []
    if stripped:
        candidates.append(stripped)

    for match in re.finditer(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE):
        block = match.group(1).strip()
        if block:
            candidates.append(block)

    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = stripped.find(open_ch)
        end = stripped.rfind(close_ch)
        if start != -1 and end != -1 and start < end:
            snippet = stripped[start:end + 1].strip()
            if snippet:
                candidates.append(snippet)

    seen = set()
    unique: list[str] = []
    for cand in candidates:
        if cand not in seen:
            seen.add(cand)
            unique.append(cand)
    return unique


def _coerce_json_text(text: str) -> str | None:
    for candidate in _json_candidates(text):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, (dict, list)):
                return json.dumps(parsed, ensure_ascii=False)
        except json.JSONDecodeError:
            pass

        try:
            repaired = repair_json(candidate)
            parsed = json.loads(repaired)
            if isinstance(parsed, (dict, list)):
                return json.dumps(parsed, ensure_ascii=False)
        except Exception:
            pass
    return None


def _invoke_sagemaker_json_generation(
    prompt: str,
    max_tokens: int = 2048,
) -> str:
    strict_prompt = (
        "당신은 JSON API입니다.\n"
        "반드시 유효한 JSON 하나만 출력하세요.\n"
        "마크다운, 코드블록, 설명, 파이썬 코드, 예시는 절대 출력하지 마세요.\n"
        "응답의 첫 글자는 { 또는 [ 이어야 하고 마지막 글자는 } 또는 ] 이어야 합니다.\n\n"
        f"{prompt}"
    )
    raw = _invoke_sagemaker_text_generation(
        prompt=strict_prompt,
        temperature=0,
        max_tokens=max_tokens,
    )
    coerced = _coerce_json_text(raw)
    if coerced:
        return coerced

    logger.warning(
        "SageMaker JSON 정규화 실패, 재시도합니다: %s",
        raw[:300].replace("\n", " "),
    )
    repair_prompt = (
        "다음 텍스트를 의미를 유지한 유효한 JSON 하나로 다시 작성하세요.\n"
        "설명 없이 JSON만 출력하세요.\n\n"
        f"{raw}"
    )
    repaired_raw = _invoke_sagemaker_text_generation(
        prompt=repair_prompt,
        temperature=0,
        max_tokens=max_tokens,
    )
    coerced = _coerce_json_text(repaired_raw)
    if coerced:
        return coerced

    raise ValueError(
        "SageMaker JSON coercion failed. "
        f"raw={raw[:300]!r}, repaired={repaired_raw[:300]!r}"
    )


def _normalize_json_output(raw: str, source: str) -> str:
    coerced = _coerce_json_text(raw)
    if coerced:
        return coerced
    raise ValueError(f"{source} returned non-JSON output: {raw[:300]!r}")


def chat_message(
    messages: list[dict],
    tools: list | None = None,
    temperature: float = 0,
    max_tokens: int = 1024,
    tool_choice: str = "auto",
) -> dict:
    provider = get_provider_name()

    if provider == "sagemaker":
        if SAGEMAKER_RUNTIME_MODE == "ollama_proxy":
            payload = {
                "route": "chat",
                "model": OLLAMA_MODEL,
                "messages": messages,
                "tools": tools or [],
                "tool_choice": tool_choice,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            }
            data = _invoke_sagemaker_ollama_proxy(payload)
            return data.get("message", {})

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
        if SAGEMAKER_RUNTIME_MODE == "ollama_proxy":
            payload = {
                "route": "generate",
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "format": "json",
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            }
            data = _invoke_sagemaker_ollama_proxy(payload)
            return _normalize_json_output(data.get("response", "{}"), "SageMaker Ollama proxy")

        return _invoke_sagemaker_json_generation(prompt=prompt, max_tokens=max_tokens)

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
    return _normalize_json_output(response.json().get("response", "{}"), "Ollama")
