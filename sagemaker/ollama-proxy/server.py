import logging
import os
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("ollama-proxy")

app = FastAPI(title="SageMaker Ollama Proxy")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_REQUEST_TIMEOUT_SECONDS", "300"))
OLLAMA_REQUIRE_MODEL = os.getenv("OLLAMA_REQUIRE_MODEL", "true").lower() == "true"


def _merge_options(payload: dict[str, Any]) -> dict[str, Any]:
    options = dict(payload.get("options") or {})
    if "temperature" in payload and "temperature" not in options:
        options["temperature"] = payload["temperature"]
    if "max_tokens" in payload and "num_predict" not in options:
        options["num_predict"] = payload["max_tokens"]
    return options


def _client() -> httpx.Client:
    return httpx.Client(timeout=OLLAMA_TIMEOUT_SECONDS)


def _ensure_success(response: httpx.Response) -> dict[str, Any]:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500]
        raise HTTPException(status_code=502, detail=f"Ollama upstream error: {detail}") from exc
    data = response.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail=f"Unexpected Ollama response: {data}")
    return data


def _tags() -> dict[str, Any]:
    with _client() as client:
        response = client.get(f"{OLLAMA_BASE_URL}/api/tags")
    return _ensure_success(response)


def _model_available(model_name: str) -> bool:
    data = _tags()
    models = data.get("models") or []
    return any(m.get("name") == model_name for m in models if isinstance(m, dict))


def _proxy_chat(payload: dict[str, Any]) -> dict[str, Any]:
    model = payload.get("model") or OLLAMA_MODEL
    tools = payload.get("tools") or []
    if payload.get("tool_choice") == "none":
        tools = []

    body: dict[str, Any] = {
        "model": model,
        "messages": payload.get("messages") or [],
        "stream": False,
        "options": _merge_options(payload),
    }
    if tools:
        body["tools"] = tools
    if "format" in payload:
        body["format"] = payload["format"]
    if "keep_alive" in payload:
        body["keep_alive"] = payload["keep_alive"]

    logger.info("proxy chat: model=%s messages=%d", model, len(body["messages"]))
    with _client() as client:
        response = client.post(f"{OLLAMA_BASE_URL}/api/chat", json=body)
    return _ensure_success(response)


def _proxy_generate(payload: dict[str, Any]) -> dict[str, Any]:
    model = payload.get("model") or OLLAMA_MODEL
    body: dict[str, Any] = {
        "model": model,
        "prompt": payload.get("prompt", ""),
        "stream": False,
        "options": _merge_options(payload),
    }
    if "format" in payload:
        body["format"] = payload["format"]
    if "keep_alive" in payload:
        body["keep_alive"] = payload["keep_alive"]

    logger.info("proxy generate: model=%s prompt_len=%d", model, len(body["prompt"]))
    with _client() as client:
        response = client.post(f"{OLLAMA_BASE_URL}/api/generate", json=body)
    return _ensure_success(response)


@app.get("/ping")
def ping() -> JSONResponse:
    try:
        if OLLAMA_REQUIRE_MODEL and not _model_available(OLLAMA_MODEL):
            return JSONResponse(
                status_code=503,
                content={"status": "loading", "reason": f"model {OLLAMA_MODEL} not ready"},
            )
        _tags()
        return JSONResponse({"status": "ok", "model": OLLAMA_MODEL})
    except Exception as exc:  # noqa: BLE001
        logger.exception("ping failed")
        return JSONResponse(status_code=503, content={"status": "error", "detail": str(exc)})


@app.post("/invocations")
async def invocations(request: Request) -> JSONResponse:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON object body is required")

    route = payload.get("route")
    if route is None:
        if "messages" in payload:
            route = "chat"
        elif "prompt" in payload:
            route = "generate"

    if route == "chat":
        return JSONResponse(_proxy_chat(payload))
    if route == "generate":
        return JSONResponse(_proxy_generate(payload))

    raise HTTPException(
        status_code=400,
        detail="Unsupported payload. Use route=chat with messages or route=generate with prompt.",
    )
