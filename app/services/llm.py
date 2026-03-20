"""
llama tool calling 처리 — Ollama /api/chat 엔드포인트 사용
"""
import json
import httpx
from app.core.config import OLLAMA_BASE_URL, OLLAMA_MODEL
from app.tools import get_market_summary, get_db_data, get_market_data, execute_order

# ── Tool 스키마 정의 (llama3.1 tool_use 포맷) ──────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_market_summary",
            "description": "한국/미국 시황 요약 또는 특정 종목의 뉴스 요약을 반환합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["korea", "us", "stock_news"],
                        "description": "korea: 한국 시황(KOSDAQ), us: 미국 시황(NASDAQ), stock_news: 종목별 뉴스",
                    },
                    "stock_code": {"type": "string", "description": "종목 코드 (stock_news 시 필요, 예: 005930)"},
                },
                "required": ["type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_db_data",
            "description": "잔고, 최근 거래내역, 포트폴리오 분석 등 사용자의 내부 DB 데이터를 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "type":  {"type": "string", "enum": ["balance", "trades", "portfolio"]},
                    "limit": {"type": "integer", "description": "trades 조회 건수 (기본 3)"},
                },
                "required": ["type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_data",
            "description": "주가, 차트, 거래량/등락 랭킹, 지수, 환율 등 실시간 시장 데이터를 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "type":          {"type": "string", "enum": ["price", "chart", "ranking", "index", "exchange"]},
                    "stock_code":    {"type": "string"},
                    "market":        {"type": "string", "enum": ["domestic", "overseas"]},
                    "ranking_type":  {"type": "string", "enum": ["volume", "change_rate", "foreign_buy"]},
                    "index_code":    {"type": "string", "enum": ["KOSPI", "NASDAQ"]},
                    "currency_pair": {"type": "string", "enum": ["USDKRW", "EURKRW"]},
                },
                "required": ["type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_order",
            "description": "주식 매수/매도 또는 환전 주문을 실행합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "type":          {"type": "string", "enum": ["buy", "sell", "exchange"]},
                    "stock_code":    {"type": "string"},
                    "quantity":      {"type": "integer"},
                    "price":         {"type": "integer", "description": "생략 시 시장가"},
                    "from_currency": {"type": "string"},
                    "to_currency":   {"type": "string"},
                    "amount":        {"type": "integer"},
                },
                "required": ["type"],
            },
        },
    },
]

_TOOL_DISPATCH = {
    "get_market_summary": get_market_summary,
    "get_db_data":        get_db_data,
    "get_market_data":    get_market_data,
    "execute_order":      execute_order,
}


# ── 메인 chat 함수 ─────────────────────────────────────────────────────────────

def chat(user_message: str, user_context: dict) -> str:
    """
    사용자 메시지를 받아 llama tool calling 루프를 실행하고 최종 응답을 반환합니다.

    Args:
        user_message: 사용자 입력 텍스트
        user_context: 세션에서 추출한 {"user_id": ..., "account_id": ...}
                      LLM 스키마에는 노출되지 않으며, 도구 호출 시 코드가 직접 주입합니다.
    """
    messages = [{"role": "user", "content": user_message}]

    while True:
        response = _call_ollama(messages)
        msg = response["message"]
        messages.append(msg)

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            return msg.get("content", "")

        # 도구 실행 — user_context는 LLM이 채운 fn_args와 별도로 주입
        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            fn_args = tc["function"].get("arguments", {})
            if isinstance(fn_args, str):
                fn_args = json.loads(fn_args)

            result = _dispatch(fn_name, fn_args, user_context)
            messages.append({
                "role":    "tool",
                "content": json.dumps(result, ensure_ascii=False),
            })


def _call_ollama(messages: list[dict]) -> dict:
    with httpx.Client(timeout=60) as client:
        resp = client.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model":    OLLAMA_MODEL,
                "messages": messages,
                "tools":    TOOLS,
                "stream":   False,
            },
        )
        resp.raise_for_status()
        return resp.json()


def _dispatch(fn_name: str, fn_args: dict, user_context: dict):
    fn = _TOOL_DISPATCH.get(fn_name)
    if fn is None:
        return {"error": f"Unknown tool: {fn_name}"}
    try:
        # user_context가 필요한 도구(get_db_data, execute_order)에만 주입
        # get_market_summary, get_market_data는 공용 데이터라 불필요
        if fn_name in ("get_db_data", "execute_order"):
            return fn(**fn_args, user_context=user_context)
        return fn(**fn_args)
    except Exception as e:
        return {"error": str(e)}
