"""
llama tool calling 처리 — Ollama /api/chat 엔드포인트 사용
"""
import json
import httpx
from app.core.config import OLLAMA_BASE_URL, OLLAMA_MODEL
from app.tools import get_market_summary, get_db_data, get_market_data, execute_order
from app.templates.account import format_balance
from app.templates.trades import format_trades
from app.templates.portfolio import format_portfolio
from app.templates.market_summary import format_korea_summary, format_us_summary, format_stock_news
from app.templates.order import format_order

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
            "description": "사용자의 잔고, 거래내역, 포트폴리오 데이터를 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["balance", "trades", "portfolio", "balance_detail", "trades_detail", "portfolio_detail"],
                        "description": (
                            "balance/trades/portfolio: 전체 조회 → 포맷된 리포트 반환. "
                            "balance_detail/trades_detail/portfolio_detail: 세부 질문 → LLM이 자연어로 답변."
                        ),
                    },
                    "limit": {"type": "integer", "description": "trades/trades_detail 조회 건수 (기본 3)"},
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

# (tool_name, type) → 템플릿 함수. 등록된 경우 LLM 대신 템플릿으로 직접 반환.
_TEMPLATE_DISPATCH: dict[tuple[str, str], callable] = {
    ("get_db_data", "balance"):        format_balance,
    ("get_db_data", "trades"):         format_trades,
    ("get_db_data", "portfolio"):      format_portfolio,
    ("get_market_summary", "korea"):      format_korea_summary,
    ("get_market_summary", "us"):         format_us_summary,
    ("get_market_summary", "stock_news"): format_stock_news,
    ("execute_order", "buy"):             format_order,
    ("execute_order", "sell"):            format_order,
    ("execute_order", "exchange"):        format_order,
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
    messages = [
        {
            "role": "system",
            "content": (
                "당신은 투자 어시스턴트입니다. 한국어로 간결하게 답변하세요.\n\n"
                "■ get_market_summary — 시황·뉴스 요청 시 사용\n"
                "  - korea:      '한국 증시', '코스닥 어때', '오늘 시장 어때'\n"
                "  - us:         '미국 장', '나스닥 어때', '나스닥 지금 어떻게 돼', '월가 어때', '미국 증시'\n"
                "  ※ '나스닥'이 시황·분위기 질문이면 us, 나스닥 지수 수치가 궁금하면 get_market_data(index)\n"
                "  - stock_news: '삼성전자 뉴스', '특정 종목 관련 기사'\n\n"
                "■ get_db_data — 사용자 계좌, 거래내역, 포트폴리오 데이터 조회 시 사용\n"
                "  전체 조회 (포맷된 리포트 반환):\n"
                "  - balance:   '잔고 보여줘', '잔고 알려줘', '계좌 잔고 조회'\n"
                "  - trades:    '거래내역 보여줘', '최근 거래 알려줘'\n"
                "  - portfolio: '포트폴리오 분석해줘', '내 포트폴리오 어때'\n"
                "  특정 값 질문 (LLM이 직접 답변):\n"
                "  - balance_detail:   '원화 얼마야?', '달러 잔고', '출금 가능 금액'\n"
                "  - trades_detail:    '매수 몇 번 했어?', '최근에 뭐 샀어?', '매도 건수'\n"
                "  - portfolio_detail: '평가금액 얼마야?', '총 평가금액 알려줘', 'MDD 얼마야?', '삼성전자 수익률'\n"
                "  ※ '전체 리포트'가 아닌 특정 수치 하나를 묻는 질문은 반드시 _detail 타입을 사용하세요.\n\n"
                "■ get_market_data — 실시간 시세·지수·환율·랭킹 조회 시 사용\n"
                "  - price:        '삼성전자 현재가', '지금 얼마야'\n"
                "  - chart:        '차트 보여줘', '분봉'\n"
                "  - daily:        '오늘 고가/저가', '시가 종가'\n"
                "  - period_chart: '최근 한 달 차트', '주간 차트'\n"
                "  - ranking:      '거래량 상위', '많이 오른 종목', '외국인 순매수'\n"
                "  ※ ranking 요청 시 type=ranking, ranking_type(volume/change_rate/foreign_buy)을 반드시 함께 지정하세요.\n"
                "  - index:        '코스피 지수', '나스닥 지수'\n"
                "  - exchange:     '환율 알려줘', '달러 얼마야'\n\n"
                "■ execute_order — 매수·매도·환전 요청 시 사용\n"
                "  - buy:      '삼성전자 10주 사줘' → stock_code, quantity 필수\n"
                "  - sell:     '삼성전자 5주 팔아줘' → stock_code, quantity 필수\n"
                "  - exchange: '달러로 환전해줘', '원화로 바꿔줘'\n"
                "  ※ 매수/매도 시 종목명과 수량이 모두 있어야 execute_order를 호출할 수 있습니다.\n"
                "     종목명 또는 수량 중 하나라도 없으면 절대 execute_order를 호출하지 말고 "
                "반드시 부족한 정보를 되물어보세요."
            ),
        },
        {"role": "user", "content": user_message},
    ]

    while True:
        response = _call_ollama(messages)
        msg = response["message"]
        messages.append(msg)

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            return msg.get("content", "")

        # 도구 실행 — user_context는 LLM이 채운 fn_args와 별도로 주입
        template_replies = []
        tool_results = []
        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            fn_args = tc["function"].get("arguments", {})
            if isinstance(fn_args, str):
                fn_args = json.loads(fn_args)

            result = _dispatch(fn_name, fn_args, user_context)

            formatter = _TEMPLATE_DISPATCH.get((fn_name, fn_args.get("type")))
            if formatter:
                template_replies.append(formatter(result))
            else:
                tool_results.append(json.dumps(result, ensure_ascii=False))

        # 템플릿이 있는 결과는 바로 반환
        if template_replies:
            return "\n\n".join(template_replies)

        # 템플릿 없는 결과는 LLM에 다시 전달
        for content in tool_results:
            messages.append({"role": "tool", "content": content})


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
