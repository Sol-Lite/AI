"""
llama tool calling 처리 — Ollama /api/chat 엔드포인트 사용
"""
import json
import httpx
from datetime import datetime, timezone, timedelta
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


# ── 시장 시간 컨텍스트 ─────────────────────────────────────────────────────────

def _get_market_context() -> str:
    """현재 KST 기준 국장/미장 마감 여부를 반환합니다."""
    KST = timezone(timedelta(hours=9))
    now = datetime.now(KST)
    h, m, month = now.hour, now.minute, now.month

    # 국장: 9:00 ~ 15:30
    korea_before_close = (9 <= h < 15) or (h == 15 and m < 30)
    korea_note = "어제 일자 장 마감 시황" if korea_before_close else "오늘 일자 장 마감 시황"

    # 미장 서머타임(3~11월): 22:30~05:00, 해제(11~3월): 23:30~06:00
    is_summer = 3 <= month <= 11
    if is_summer:
        us_open = (h == 22 and m >= 30) or (h == 23) or (0 <= h < 5)
    else:
        us_open = (h == 23 and m >= 30) or (0 <= h < 6)
    us_note = "오늘 일자 장 마감 시황" if us_open else "어제 일자 장 마감 시황"

    return (
        f"현재 시각(KST): {now.strftime('%H:%M')}\n"
        f"한국 시황 기준: {korea_note}\n"
        f"미국 시황 기준: {us_note}"
    )


# ── 메인 chat 함수 ─────────────────────────────────────────────────────────────

def chat(user_message: str, user_context: dict) -> str:
    """
    사용자 메시지를 받아 llama tool calling 루프를 실행하고 최종 응답을 반환합니다.

    Args:
        user_message: 사용자 입력 텍스트
        user_context: 세션에서 추출한 {"user_id": ..., "account_id": ...}
                      LLM 스키마에는 노출되지 않으며, 도구 호출 시 코드가 직접 주입합니다.
    """
    market_ctx = _get_market_context()
    messages = [
        {
            "role": "system",
            "content": (
                "당신은 투자 어시스턴트입니다. 한국어로 간결하게 답변하세요.\n\n"
                f"[현재 시장 정보]\n{market_ctx}\n\n"

                "■ get_market_summary — 시황·뉴스 키워드: 시황, 이슈, 뉴스, 요약, 소식\n\n"
                "  ▷ korea (키워드: 한국, 국장, 국내)\n"
                "    - 한국 시장에 대한 언급이 있을 때만 호출하세요.\n"
                "    - 응답 시 위 [현재 시장 정보]의 '한국 시황 기준' 문구를 반드시 함께 제시하세요.\n\n"
                "  ▷ us (키워드: 해외, 미국, 미장)\n"
                "    - 미국 시장에 대한 언급이 있을 때만 호출하세요.\n"
                "    - '나스닥'이 시황·분위기 질문이면 us, 나스닥 지수 수치가 궁금하면 get_market_data(index).\n"
                "    - 응답 시 위 [현재 시장 정보]의 '미국 시황 기준' 문구를 반드시 함께 제시하세요.\n\n"
                "  ▷ stock_news (키워드: 종목 이름, 종목 코드)\n"
                "    - 질문에 종목 이름 또는 종목 코드가 있을 때만 호출하세요.\n"
                "    - 종목 정보 없이 '반도체 뉴스', '바이오 주식 뉴스' 등을 물으면 "
                "'어떤 종목의 뉴스가 궁금하신가요? 종목 이름 또는 코드로 보내주세요.'라고 되물으세요.\n\n"
                "  ※ '증시', '장' 처럼 특정 시장(한국/미국)이 명시되지 않으면 "
                "어떤 시장인지 포함시켜 달라고 되물으세요. get_market_summary를 호출하지 마세요.\n\n"

                "■ get_db_data — 사용자 계좌·거래·포트폴리오 데이터 조회\n\n"
                "  ▷ balance (키워드: 계좌잔고, 계좌, 잔고)\n"
                "  ▷ balance_detail (키워드: 총 자산, 주문 가능 금액, 출금 가능 금액, 자산)\n"
                "  ▷ trades (키워드: 최근 거래, 거래내역, 거래이력, 내역, 이력, 최근 거래내역, 거래 기록)\n"
                "  ▷ trades_detail (키워드: 총 거래 횟수, 거래 건수, 매도 건수, 매수 건수,\n"
                "       최근 매도 내역, 최근 매수 내역, 최근 매도 기록, 최근 매수 기록, 매도 기록, 매수 기록)\n"
                "  ▷ portfolio (키워드: 포트폴리오, 포트폴리오 분석)\n"
                "  ▷ portfolio_detail (키워드: 평가액, 평가금액, 실시간 총평가금액, 국내주식 평가액,\n"
                "       실시간 평가액, 수익률, 전일 대비 수익률, 손익, 집중도, 비중, 리스크,\n"
                "       최대 낙폭, 회복 필요 수익률, MDD, 변동성, 수익 종목, 수익 매도 건수,\n"
                "       손실 매도 건수, 거래 통계)\n"
                "  ※ '전체 리포트'가 아닌 특정 수치 하나를 묻는 질문은 반드시 _detail 타입을 사용하세요.\n\n"

                "■ get_market_data — 실시간 시세·지수·환율·랭킹 조회\n\n"
                "  ▷ price (키워드: 현재가, 전일대비, 등락률, 거래량, 주가, 종가, 시가)\n"
                "    - 종목 정보 없이 질문하면 '어떤 종목을 조회할까요?'라고 되물으세요.\n\n"
                "  ▷ period_chart\n"
                "    - 1차 키워드: 차트\n"
                "    - 2차 키워드: 일봉, 주봉, 월봉, 연봉\n"
                "    - 종목 정보 없이 질문하면 '어떤 종목의 차트를 보여드릴까요?'라고 되물으세요.\n\n"
                "  ▷ ranking\n"
                "    - 1차 키워드: 순위, 많은 종목, 높은 종목, 낮은 종목, 적은 종목\n"
                "    - 2차 키워드(ranking_type): 거래대금, 급상승(change_rate), 거래량(volume), 급하락, 시가총액\n"
                "    - ranking_type은 volume / change_rate / foreign_buy 중 하나를 반드시 지정하세요.\n\n"
                "  ▷ index (키워드: 코스피, 코스닥, 지수, 나스닥)\n"
                "  ▷ exchange (키워드: 환율, 원화, 달러)\n\n"

                "■ execute_order — 매수·매도·환전 주문\n\n"
                "  ▷ buy/sell\n"
                "    - 다음 두 가지가 모두 있어야만 호출하세요:\n"
                "      (1) 종목 이름 또는 종목 코드\n"
                "      (2) 거래/매수/매도/팔게요/살게요/팔아줘/사줘/판다/산다/팔자/사자 등 거래 키워드\n"
                "    - 하나라도 없으면 절대 호출하지 말고 누락된 정보를 되물으세요.\n\n"
                "  ▷ exchange\n"
                "    - 다음 세 가지가 모두 있어야만 호출하세요:\n"
                "      (1) 기준통화  (2) 표시통화(환전하고자 하는 화폐 단위)  (3) 환전 키워드\n"
                "    - 하나라도 없으면 절대 호출하지 말고 누락된 정보를 되물으세요.\n\n"

                "■ tool_calls 없음 (자유 질의)\n"
                "  위 도구 중 어느 것도 해당하지 않으면 자세한 질문을 하도록 유도하세요."
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
