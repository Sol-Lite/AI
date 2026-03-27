"""
(11) 거래내역 / (12) 포트폴리오 분석 / unknown 폴백 — Ollama tool calling agent

Ollama /api/chat 의 tools 파라미터를 사용해 ReAct 루프를 구성합니다.

흐름:
  1. 사용자 메시지 + tool 목록을 llama에 전송
  2. llama가 tool_calls 반환 → 해당 tool 실행 → 결과를 messages에 추가
  3. llama가 최종 텍스트 답변을 반환할 때까지 반복 (최대 MAX_TURNS 회)
  4. 최종 content를 사용자에게 반환

지원 도구:
  [거래내역]
    get_trade_summary     — 총 거래 횟수, 매수/매도 횟수
    get_recent_trades     — 최근 N건 거래 목록
    get_trades_by_stock   — 특정 종목의 거래 내역

  [포트폴리오]
    get_holdings          — 현재 보유 종목 목록
    get_portfolio_returns — 기간별 수익률 및 MDD
    get_sector_concentration — 섹터별 비중
    get_portfolio_risk    — 변동성, MDD, 최고/최저 수익 종목
    get_trade_stats       — 거래 통계 (승률, 손익비)
"""
import json
import httpx
from app.core.config import OLLAMA_BASE_URL, OLLAMA_MODEL

MAX_TURNS = 5   # tool call 반복 최대 횟수

# ── tool 정의 (Ollama tools 파라미터 형식) ────────────────────────────────────

_TRADE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_trade_summary",
            "description": "사용자의 총 거래 횟수, 매수 횟수, 매도 횟수를 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_trades",
            "description": "최근 거래 내역 목록을 조회합니다. 종목명, 매수/매도 구분, 체결가, 수량, 체결일시를 포함합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "조회할 최근 거래 건수 (기본값: 10)",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_trades_by_stock",
            "description": "특정 종목의 전체 거래 내역을 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "stock_code": {
                        "type": "string",
                        "description": "조회할 종목 코드 (예: 005930, AAPL)",
                    }
                },
                "required": ["stock_code"],
            },
        },
    },
]

_PORTFOLIO_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_holdings",
            "description": "현재 보유 중인 종목 목록과 수량, 평균 단가, 현재 평가금액, 수익률을 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_portfolio_returns",
            "description": "포트폴리오의 기간별 수익률(일간, 1개월, 3개월, 6개월)과 MDD(최대낙폭)를 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sector_concentration",
            "description": "보유 종목의 섹터(업종)별 비중과 국내/해외 비중을 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_portfolio_risk",
            "description": "포트폴리오 리스크 지표를 조회합니다: 변동성(표준편차), MDD, 최고/최저 수익 종목, 실현/미실현 손익.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_trade_stats",
            "description": "매매 통계를 조회합니다: 총 거래 수, 승률, 평균 이익/손실, 손익비(profit factor), 총 실현손익.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]


# ── tool 실행기 ───────────────────────────────────────────────────────────────

def _make_trade_executor(account_id: str):
    """account_id를 클로저로 캡처한 거래내역 tool 실행 함수를 반환합니다."""
    from app.agent.trade_tools import (
        get_trade_summary,
        get_recent_trades,
        get_trades_by_stock,
    )

    def execute(name: str, args: dict) -> str:
        if name == "get_trade_summary":
            result = get_trade_summary(account_id)
        elif name == "get_recent_trades":
            result = get_recent_trades(account_id, limit=args.get("limit", 10))
        elif name == "get_trades_by_stock":
            result = get_trades_by_stock(account_id, stock_code=args["stock_code"])
        else:
            result = {"error": f"Unknown tool: {name}"}
        return json.dumps(result, ensure_ascii=False)

    return execute


def _make_portfolio_executor(account_id: str):
    """account_id를 클로저로 캡처한 포트폴리오 tool 실행 함수를 반환합니다."""
    from app.agent.portfolio_tools import (
        get_holdings,
        get_portfolio_returns,
        get_sector_concentration,
        get_portfolio_risk,
        get_trade_stats,
    )

    def execute(name: str, args: dict) -> str:
        if name == "get_holdings":
            result = get_holdings(account_id)
        elif name == "get_portfolio_returns":
            result = get_portfolio_returns(account_id)
        elif name == "get_sector_concentration":
            result = get_sector_concentration(account_id)
        elif name == "get_portfolio_risk":
            result = get_portfolio_risk(account_id)
        elif name == "get_trade_stats":
            result = get_trade_stats(account_id)
        else:
            result = {"error": f"Unknown tool: {name}"}
        return json.dumps(result, ensure_ascii=False)

    return execute


# ── ReAct 루프 ────────────────────────────────────────────────────────────────

def _run_agent(
    system_prompt: str,
    user_message: str,
    tools: list,
    execute_tool,
) -> str:
    """
    Ollama tool calling ReAct 루프.

    1. messages + tools 를 llama에 전송
    2. tool_calls가 있으면 → 실행 → tool 결과를 messages에 추가 → 재전송
    3. content가 있는 응답이 오면 최종 답변으로 반환
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_message},
    ]

    with httpx.Client(timeout=120) as client:
        for _ in range(MAX_TURNS):
            payload = {
                "model":    OLLAMA_MODEL,
                "messages": messages,
                "tools":    tools,
                "stream":   False,
                "options":  {"temperature": 0},  # 할루시네이션 최소화
            }
            try:
                resp = client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
                resp.raise_for_status()
            except httpx.TimeoutException:
                return "응답 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요."
            except Exception as e:
                return f"AI 응답 오류: {e}"

            data    = resp.json()
            message = data.get("message", {})
            tool_calls = message.get("tool_calls") or []

            if not tool_calls:
                # 최종 텍스트 답변
                return message.get("content", "답변을 생성하지 못했습니다.")

            # tool 실행 후 결과를 messages에 추가
            messages.append({"role": "assistant", "tool_calls": tool_calls})
            for call in tool_calls:
                fn   = call.get("function", {})
                name = fn.get("name", "")
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}

                tool_result = execute_tool(name, args)
                messages.append({
                    "role":    "tool",
                    "name":    name,
                    "content": tool_result,
                })

    return "처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."


# ── (11) 거래내역 agent ───────────────────────────────────────────────────────

_TRADES_SYSTEM = """당신은 주식 투자 어시스턴트입니다.
반드시 제공된 도구(tools)를 먼저 호출하여 실제 데이터를 조회한 후 답변하세요.
절대로 도구를 호출하지 않고 스스로 데이터를 추측하거나 지어내지 마세요.
질문에 필요한 도구만 선택적으로 호출하고, 조회된 데이터를 바탕으로 한국어로 간결하게 답하세요.
도구 호출 결과가 비어있으면 "거래 내역이 없습니다"라고 답하세요."""


def ask_trades(user_context: dict, user_message: str) -> str:
    """거래내역 질문에 대해 llama tool calling agent로 답변합니다."""
    account_id    = user_context.get("account_id", "")
    execute_tool  = _make_trade_executor(account_id)
    return _run_agent(_TRADES_SYSTEM, user_message, _TRADE_TOOLS, execute_tool)


# ── (12) 포트폴리오 분석 agent ────────────────────────────────────────────────

_PORTFOLIO_SYSTEM = """당신은 투자 포트폴리오 분석 전문가입니다.
반드시 제공된 도구(tools)를 먼저 호출하여 실제 데이터를 조회한 후 답변하세요.
절대로 도구를 호출하지 않고 스스로 데이터를 추측하거나 지어내지 마세요.
질문에 필요한 도구만 선택적으로 호출하고, 조회된 수치를 구체적으로 언급하며 한국어로 간결하게 답하세요.
도구 호출 결과가 비어있으면 "보유 종목이 없습니다"라고 답하세요."""


def ask_portfolio(user_context: dict, user_message: str) -> str:
    """포트폴리오 질문에 대해 llama tool calling agent로 답변합니다."""
    account_id   = user_context.get("account_id", "")
    execute_tool = _make_portfolio_executor(account_id)
    return _run_agent(_PORTFOLIO_SYSTEM, user_message, _PORTFOLIO_TOOLS, execute_tool)


# ── unknown 폴백 agent ────────────────────────────────────────────────────────

_GENERAL_SYSTEM = """당신은 주식 투자 어시스턴트입니다.
사용자의 질문이 보유 종목, 수익률, 손익, 거래내역과 관련된 경우 반드시 도구(tools)를 먼저 호출하여 실제 데이터를 조회한 후 답변하세요.
절대로 도구를 호출하지 않고 스스로 데이터를 추측하거나 지어내지 마세요.
투자와 전혀 무관한 질문에는 "투자 관련 질문만 답변할 수 있습니다."라고 안내하세요."""

_ALL_TOOLS = _TRADE_TOOLS + _PORTFOLIO_TOOLS


def _make_general_executor(account_id: str):
    trade_exec     = _make_trade_executor(account_id)
    portfolio_exec = _make_portfolio_executor(account_id)

    def execute(name: str, args: dict) -> str:
        trade_names = {"get_trade_summary", "get_recent_trades", "get_trades_by_stock"}
        if name in trade_names:
            return trade_exec(name, args)
        return portfolio_exec(name, args)

    return execute


def ask_general(user_context: dict, user_message: str) -> str:
    """키워드로 intent를 못 잡은 경우 거래+포트폴리오 전체 tool을 갖고 답변합니다."""
    account_id   = user_context.get("account_id", "")
    execute_tool = _make_general_executor(account_id)
    return _run_agent(_GENERAL_SYSTEM, user_message, _ALL_TOOLS, execute_tool)
