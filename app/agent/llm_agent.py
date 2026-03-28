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
                        "description": "조회할 종목 코드 또는 종목명 (예: 005930, 삼성전자, AAPL)",
                    }
                },
                "required": ["stock_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_trades_by_date",
            "description": "특정 날짜의 전체 거래 내역을 조회합니다. 날짜를 언급한 거래 조회 질문에 사용하세요.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "조회할 날짜 (예: 2026-03-27, 3월 27일, 03-27)",
                    }
                },
                "required": ["date"],
            },
        },
    },
]

_PORTFOLIO_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_holdings",
            "description": (
                "현재 보유 종목 목록을 조회합니다. "
                "각 종목의 수량, 평균 단가, 현재가, 수익률, market_type(domestic=국내/overseas=해외)을 포함합니다. "
                "종목 비중, 국내/해외 종목 구성, 특정 종목 보유 여부를 물을 때 사용합니다. "
                "섹터(업종) 비중 질문에는 사용하지 마세요."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_portfolio_returns",
            "description": (
                "기간별 수익률(일간, 1개월, 3개월, 6개월)과 MDD(최대낙폭)를 조회합니다. "
                "수익률 추이, 기간별 성과 질문에 사용합니다."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sector_concentration",
            "description": (
                "섹터(업종)별 비중을 조회합니다. 각 섹터의 market_type(domestic=국내/overseas=해외)을 포함합니다. "
                "섹터 비중, 업종 비중 질문에만 사용합니다. "
                "종목 비중 질문에는 사용하지 마세요."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_portfolio_risk",
            "description": (
                "평가손익(미실현 손익), 실현손익, 변동성, MDD, 최고 수익 종목, 최저 수익 종목을 조회합니다. "
                "손익 현황, 평가손익, 실현손익, 리스크, 최고/최저 수익 종목 질문에 사용합니다. "
                "승률이나 거래 횟수 질문에는 사용하지 마세요."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_trade_stats",
            "description": (
                "매매 통계를 조회합니다: 총 거래 수, 승률, 평균 수익금/손실금, 손익비(profit factor). "
                "승률, 손익비, 거래 통계 질문에만 사용합니다. "
                "평가손익이나 수익률 질문에는 사용하지 마세요."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
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
        get_trades_by_date,
    )

    def execute(name: str, args: dict) -> str:
        if name == "get_trade_summary":
            result = get_trade_summary(account_id)
        elif name == "get_recent_trades":
            result = get_recent_trades(account_id, limit=args.get("limit", 10))
        elif name == "get_trades_by_stock":
            result = get_trades_by_stock(account_id, stock_code=args["stock_code"])
        elif name == "get_trades_by_date":
            result = get_trades_by_date(account_id, date=args["date"])
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

                try:
                    tool_result = execute_tool(name, args)
                except Exception as e:
                    tool_result = json.dumps({"error": str(e)}, ensure_ascii=False)
                messages.append({
                    "role":    "tool",
                    "name":    name,
                    "content": tool_result,
                })

    return "처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."


# ── (11) 거래내역 agent ───────────────────────────────────────────────────────

_TRADES_SYSTEM = """당신은 친근한 주식 투자 어시스턴트입니다.
반드시 도구(tools)를 먼저 호출해 실제 데이터를 확인한 후 답변하세요.
절대로 데이터를 추측하거나 지어내지 마세요.
자연스러운 한국어 구어체로 간결하게 답하세요.

도구 선택 기준:
- 특정 종목의 거래 이력을 물으면 → get_trades_by_stock
- 특정 날짜의 거래를 물으면 → get_trades_by_date
- 전체 거래내역이나 최근 거래를 물으면 → get_trade_summary + get_recent_trades

날짜/시간 관련 질문(언제 샀지, 몇 월에 팔았지, 최근에 언제 샀지 등)에는 반드시 executed_at 값을 포함해 답하세요.
예) "가장 최근 매수는 2026-03-26이에요."

거래 내역이 없을 때는 "해당 종목 거래 이력이 없어요."라고 답하세요."""


def ask_trades(user_context: dict, user_message: str) -> str:
    """거래내역 질문에 대해 llama tool calling agent로 답변합니다."""
    account_id    = user_context.get("account_id", "")
    execute_tool  = _make_trade_executor(account_id)
    return _run_agent(_TRADES_SYSTEM, user_message, _TRADE_TOOLS, execute_tool)


# ── (12) 포트폴리오 분석 agent ────────────────────────────────────────────────

_PORTFOLIO_SYSTEM = """당신은 친근한 투자 포트폴리오 어시스턴트입니다.
반드시 도구(tools)를 먼저 호출해 실제 데이터를 확인한 후 답변하세요.
절대로 데이터를 추측하거나 지어내지 마세요.
한국어와 영어만 사용하세요. 다른 언어(러시아어 등)는 절대 사용하지 마세요.
주관적인 분석, 투자 의견, 인사이트는 추가하지 마세요. 데이터만 전달하세요.
항목을 나열할 때는 줄바꿈을 사용해 가독성 있게 출력하세요.

도구 선택 규칙 (반드시 준수):
- 손익 현황 / 평가손익 / 실현손익 / 수익·손실 금액 → get_portfolio_risk
- 리스크 / 변동성 / MDD / 최고·최저 수익 종목 → get_portfolio_risk
- 기간별 수익률 (1개월, 3개월, 6개월) → get_portfolio_returns
- 승률 / 손익비 / 거래 통계 → get_trade_stats
- 종목 비중 / 국내·해외 종목 구성 / 보유 종목 → get_holdings
- 섹터 비중 / 업종 비중 → get_sector_concentration

국내/해외 구분:
- get_holdings 결과에서 market_type=="domestic" 이면 국내, "overseas" 이면 해외
- get_sector_concentration 결과에서 market_type=="domestic" 이면 국내 섹터, "overseas" 이면 해외 섹터
- "국내 종목 비중" 질문 → get_holdings에서 domestic 항목만 나열
- "해외 종목 비중" 질문 → get_holdings에서 overseas 항목만 나열
- "국내 섹터 비중" 질문 → get_sector_concentration에서 domestic 항목만 나열
- "해외 섹터 비중" 질문 → get_sector_concentration에서 overseas 항목만 나열

최고/최저 수익 종목:
- 반드시 get_portfolio_risk 결과의 best_stock, worst_stock 값을 그대로 사용하세요.
- 직접 계산하거나 추측하지 마세요.

리스크 분석 출력 형식 (괄호 안에 영어 변수명을 절대 쓰지 마세요):
변동성: {volatility}%
최대 낙폭(MDD): {mdd}%
회복 필요 수익률: +{recovery_needed}%
최고 수익 종목: {best_stock.name} / 수익률 {best_stock.return_rate}%
최저 수익 종목: {worst_stock.name} / 수익률 {worst_stock.return_rate}%
평가손익: {unrealized_pnl}원
실현손익: {realized_pnl}원

출력 금지 사항:
- "volatility", "mdd", "best_stock", "worst_stock", "unrealized_pnl" 등 영어 변수명을 답변에 포함하지 마세요.
- "포트폴리오를 조정하세요", "전략을 재평가하세요" 등 투자 조언을 추가하지 마세요.

종목 보유 여부:
- 보유 중이면: "네, X 종목 Y주 보유 중이에요." (다른 종목 나열 금지)
- 보유하지 않으면: "X 종목은 현재 보유하고 있지 않아요." (보유 종목 나열 금지)
- 전체 보유 종목: "현재 보유하고 있는 종목은 다음과 같습니다."로 시작

증권사 이름(미래에셋, 키움 등)은 절대 답변에 포함하지 마세요."""


def ask_portfolio(user_context: dict, user_message: str) -> str:
    """포트폴리오 질문에 대해 llama tool calling agent로 답변합니다."""
    account_id   = user_context.get("account_id", "")
    execute_tool = _make_portfolio_executor(account_id)
    return _run_agent(_PORTFOLIO_SYSTEM, user_message, _PORTFOLIO_TOOLS, execute_tool)


# ── unknown 폴백 agent ────────────────────────────────────────────────────────

_GENERAL_SYSTEM = """당신은 친근한 주식 투자 어시스턴트입니다.
보유 종목, 수익률, 손익, 거래내역과 관련된 질문은 반드시 도구(tools)를 먼저 호출해 실제 데이터를 확인한 후 답변하세요.
절대로 데이터를 추측하거나 지어내지 마세요.
자연스러운 한국어 구어체로 간결하게 답하세요.
투자와 전혀 무관한 질문에는 "투자 관련 질문만 답변드릴 수 있어요."라고 안내하세요.

현재가/시세 안내:
- 현재가, 주가, 시세 정보는 제공하는 도구가 없습니다.
- 사용자가 특정 종목의 현재 주가나 시세를 물어보는 것 같으면 (예: "하닉은?", "삼전 얼마야?") 도구를 호출하지 말고 아래처럼 안내하세요:
  "{종목명} 시세라고 입력해 주시면 현재가를 조회해 드릴 수 있어요."

거래내역 관련 규칙:
- 특정 종목의 거래를 물으면 → get_trades_by_stock 호출
- 특정 날짜의 거래를 물으면 → get_trades_by_date 호출
- 날짜/시간 관련 질문(언제 샀지, 최근에 언제 등)에는 반드시 executed_at 값을 포함해 답하세요.
  예) "가장 최근 삼성전자 매수는 2026-03-26이에요."
- 거래 이력이 없으면 "해당 종목 거래 이력이 없어요."라고 답하세요.

보유 종목 관련 규칙:
- 특정 종목 보유 여부를 물으면 → get_holdings 호출
- 보유 중이면: "네, X 종목 Y주 보유 중이에요." (다른 종목 나열 금지)
- 보유하지 않으면: "X 종목은 현재 보유하고 있지 않아요." (보유 종목 나열 금지)

출력 금지:
- "volatility", "mdd", "best_stock", "unrealized_pnl" 등 영어 변수명을 답변에 포함하지 마세요.
- 투자 조언이나 포트폴리오 조정 권유를 추가하지 마세요."""

_ALL_TOOLS = _TRADE_TOOLS + _PORTFOLIO_TOOLS


def _make_general_executor(account_id: str):
    trade_exec     = _make_trade_executor(account_id)
    portfolio_exec = _make_portfolio_executor(account_id)

    def execute(name: str, args: dict) -> str:
        trade_names = {"get_trade_summary", "get_recent_trades", "get_trades_by_stock", "get_trades_by_date"}
        if name in trade_names:
            return trade_exec(name, args)
        return portfolio_exec(name, args)

    return execute


def ask_general(user_context: dict, user_message: str) -> str:
    """키워드로 intent를 못 잡은 경우 거래+포트폴리오 전체 tool을 갖고 답변합니다."""
    account_id   = user_context.get("account_id", "")
    execute_tool = _make_general_executor(account_id)
    return _run_agent(_GENERAL_SYSTEM, user_message, _ALL_TOOLS, execute_tool)
