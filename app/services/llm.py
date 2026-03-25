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
                        "enum": ["balance", "trades", "portfolio"],
                        "description": (
                            "balance: 원화/달러 잔고 조회. "
                            "trades: 거래내역 조회. "
                            "portfolio: 포트폴리오 분석 조회."
                        ),
                    },
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
                    "type":          {"type": "string", "enum": ["price", "daily", "period_chart", "ranking", "index", "exchange"]},
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

# (tool_name, type) → 템플릿 함수
_TEMPLATE_DISPATCH: dict[tuple[str, str], callable] = {
    ("get_db_data", "balance"):           format_balance,
    ("get_db_data", "trades"):            format_trades,
    ("get_db_data", "portfolio"):         format_portfolio,
    ("get_market_summary", "korea"):      format_korea_summary,
    ("get_market_summary", "us"):         format_us_summary,
    ("get_market_summary", "stock_news"): format_stock_news,
    ("execute_order", "buy"):             format_order,
    ("execute_order", "sell"):            format_order,
    ("execute_order", "exchange"):        format_order,
}

# get_db_data는 템플릿 포맷 후 LLM에 전달해 자연어 답변 생성
# 나머지(market_summary, execute_order)는 템플릿을 그대로 반환
_DB_TOOLS = {"get_db_data"}


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

                "■ get_market_summary — 시황/뉴스 요약\n"
                "  트리거 키워드: 시황, 이슈, 뉴스, 요약, 소식, 분위기, 현황, 어때, 어떻게 됐어\n\n"

                "  ▷ korea — 트리거: 한국, 국장, 국내, 한국 시장, 한국 증시\n"
                "    응답 시 [현재 시장 정보]의 '한국 시황 기준' 문구를 함께 제시하세요.\n\n"

                "  ▷ us — 트리거: 미국, 미장, 해외, 월스트리트, 뉴욕, 뉴욕 증시, 미국 증시, 미국 마감\n"
                "    ※ 나스닥/S&P500/다우가 '어때·현황·분위기·요약·마감' 등과 함께 오면 → us\n"
                "    ※ 나스닥/S&P500/다우가 '얼마야·지수·수치' 등 숫자를 물으면 → get_market_data(index)\n"
                "    응답 시 [현재 시장 정보]의 '미국 시황 기준' 문구를 함께 제시하세요.\n\n"

                "  ▷ stock_news — 트리거: 특정 종목 이름 또는 종목 코드 + 뉴스/소식/기사\n"
                "    ※ 종목명/코드 없이 '반도체 뉴스', '바이오 뉴스'처럼 섹터만 언급하면\n"
                "       tool을 호출하지 말고 '어떤 종목의 뉴스가 궁금하신가요?'라고 되물으세요.\n\n"

                "  ※ 특정 시장을 언급하지 않은 모호한 질문('시황', '뉴스 알려줘', '장 어때')은\n"
                "     어떤 시장인지 되물으세요. get_market_summary를 호출하지 마세요.\n\n"

                "■ get_db_data — 사용자 계좌·거래내역·포트폴리오 조회\n"
                "  도구 결과가 반환되면 리포트를 직접 읽고 사용자 질문에 바로 답변하세요.\n"
                "  전체 내역 요청(보여줘/알려줘)은 리포트 전체를 출력하고,\n"
                "  특정 항목 질문(얼마야/몇 번/어때)은 해당 수치만 골라 간결하게 답변하세요.\n\n"

                "  ▷ balance — 트리거: 잔고, 계좌, 달러 잔고, 원화 잔고, 주문 가능, 출금 가능, 총 자산\n"
                "    리포트 포함 항목: 원화 총잔고, 원화 주문/출금 가능, 달러 총잔고, 달러 주문/출금 가능\n"
                "    ※ 주문 가능 = 출금 가능 (동일 필드). 주식 평가금액은 포함되지 않음.\n\n"

                "  ▷ trades — 트리거: 거래내역, 거래이력, 내가 뭐 샀어, 내가 뭐 팔았어, 매수 이력,\n"
                "              매도 이력, 거래 몇 번, 매수 몇 번, 매도 몇 번, 최근에 뭐 샀어,\n"
                "              제일 많이 산 종목, [종목명] 거래내역 있어\n"
                "    리포트 포함 항목: 총 거래 횟수(매수/매도), 최근 N건 거래 리스트(종목·방향·가격·수량·일시)\n"
                "    ※ 특정 종목 필터링 불가. recent 리스트에서 해당 종목 확인 후 없으면 안내.\n\n"

                "  ▷ portfolio — 트리거: 포트폴리오, 투자 현황, 수익률, 평가금액, 총 평가금액,\n"
                "                MDD, 최대 낙폭, 변동성, 승률, 리스크, 위험, 집중도, 섹터 비중,\n"
                "                국내/해외 비율, 제일 많이 오른 종목, 제일 많이 내린 종목, 손실 종목,\n"
                "                [종목명] 수익률, [종목명] 얼마 벌었어, [종목명] 손익\n"
                "    리포트 포함 항목: 총평가금액, 기간별 수익률(1/3/6개월), 평가/실현손익,\n"
                "                     최고/최저 종목, 종목별 수익률, 섹터·종목 집중도,\n"
                "                     국내/해외 비율, MDD, 변동성, 거래 승률, 손익비\n"
                "    ※ 승률 = win_count / sell_count × 100\n"
                "    ※ '제일 많이 오른 종목' 단독 질문 = 내 포트폴리오 기준 → portfolio 호출 (ranking 금지)\n"
                "    ※ '[종목명] 수익률 어떻게 돼?' = 내가 보유한 해당 종목의 수익률 → portfolio 호출\n"
                "       (get_market_data 사용 금지 — 시장 차트와 혼동하지 말 것)\n\n"

                "■ get_market_data — 실시간 시세·지수·랭킹·환율 조회\n\n"

                "  ▷ price — 트리거: 주가, 현재가, 지금 얼마, 주가 알려줘\n"
                "    ※ 종목 없으면 '어떤 종목을 조회할까요?'라고 되물으세요.\n"
                "    ※ price = 실시간 현재가. 오늘 고가/저가/시가/종가는 daily 사용.\n\n"

                "  ▷ daily — 트리거: 오늘 고가, 오늘 저가, 오늘 시가, 오늘 종가, 오늘 거래량\n"
                "    ※ 오늘의 OHLCV(시가·고가·저가·종가·거래량)는 daily, 실시간 현재가는 price.\n\n"

                "  ▷ period_chart — 트리거: 차트, 일봉, 주봉, 월봉, 연봉, N개월 차트, 기간 흐름\n"
                "    ※ 분봉 차트는 현재 미지원입니다.\n"
                "    ※ 종목 없으면 '어떤 종목의 차트를 보여드릴까요?'라고 되물으세요.\n"
                "    ※ '[종목명] 수익률'은 period_chart가 아닌 get_db_data(portfolio) 사용.\n\n"

                "  ▷ ranking — 트리거: 순위, 많이 거래되는, 많이 오른, 많이 내린, 급등, 급락, 대장주\n"
                "    ranking_type 결정 규칙 (반드시 지정):\n"
                "      volume     : 거래량, 많이 거래되는, 거래대금, 거래량 순위, 시가총액 순위\n"
                "      change_rate: 오른/내린/급등/급락/상한가/하한가/등락률/상승률/하락률\n"
                "      foreign_buy: 외국인 사는/매수/순매수, 외국인이 많이 파는/순매도\n\n"

                "  ▷ index — 트리거: 코스피, 코스닥, 코스피200, 다우, 다우존스, S&P500, 에스앤피,\n"
                "              닛케이, 항셍, 지수, 나스닥 지수, 나스닥 얼마야\n"
                "    ※ 지수 수치 조회에만 사용. 시황/분위기는 get_market_summary 사용.\n\n"

                "  ▷ exchange — 트리거: 환율, 원달러, 달러 얼마, 유로 환율, 엔화 환율,\n"
                "                환전하면 얼마야, N달러 원화로 얼마야\n"
                "    ※ '환율 조회'는 exchange. '환전 실행'은 execute_order(exchange).\n\n"

                "■ execute_order — 매수·매도·환전 실행\n\n"

                "  ▷ buy/sell — 반드시 아래 두 가지가 모두 있어야 호출:\n"
                "      (1) 종목 이름 또는 종목 코드\n"
                "      (2) 실행 키워드: 사줘/사/매수/팔아줘/팔아/매도/팔자/사자/살게요/팔게요\n"
                "    하나라도 없으면 절대 호출하지 말고 누락 정보를 되물으세요.\n\n"

                "  ▷ exchange — 반드시 아래 세 가지가 모두 있어야 호출:\n"
                "      (1) 기준통화 (예: 원화, KRW, 달러)\n"
                "      (2) 표시통화 (예: 달러로, 원화로, USD)\n"
                "      (3) 실행 키워드: 환전해줘/바꿔줘/충전해줘\n"
                "    ※ '환전하면 얼마야', '달러 얼마야' 같은 조회 질문은 get_market_data(exchange).\n"
                "    하나라도 없으면 절대 호출하지 말고 누락 정보를 되물으세요.\n\n"

                "■ tool_calls 없음 (자유 질의)\n"
                "  위 도구 중 어느 것도 해당하지 않으면 자세한 질문을 하도록 유도하세요.\n\n"

                "■ 금융 답변 규칙\n"
                "  수익/이익이 날 때: '플러스', '수익', '상승', '+N%' — '양성' 사용 금지\n"
                "  손실이 날 때: '마이너스', '손실', '하락', '-N%' — '음성' 사용 금지\n"
                "  숫자 표현: 금액은 '원' 또는 'USD' 단위를 붙여 표기\n"
                "  주관적 평가 금지: '우수하다', '좋다', '나쁘다', '훌륭하다', '걱정된다' 등\n"
                "  데이터를 있는 그대로 전달하고 평가·해석·의견은 추가하지 마세요.\n\n"

                "■ 중요: 도구를 호출할 때는 반드시 function call 형식(tool_calls)을 사용하세요.\n"
                "  절대로 JSON 텍스트를 직접 출력하지 마세요. 예: {\"name\": ...} 형태로 출력 금지."
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
        direct_replies = []   # 템플릿 그대로 반환 (market_summary, execute_order)
        tool_results   = []   # LLM에 전달할 결과 (get_db_data 포맷, get_market_data raw)
        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            fn_args = tc["function"].get("arguments", {})
            if isinstance(fn_args, str):
                fn_args = json.loads(fn_args)

            result = _dispatch(fn_name, fn_args, user_context)

            formatter = _TEMPLATE_DISPATCH.get((fn_name, fn_args.get("type")))
            if formatter:
                formatted = formatter(result)
                if fn_name in _DB_TOOLS:
                    # DB 데이터는 포맷 후 LLM에 전달 → LLM이 질문에 맞게 자연어 답변
                    tool_results.append(
                        f"[조회 결과]\n{formatted}\n\n"
                        f"위 데이터를 바탕으로 사용자의 질문 '{user_message}'에 직접 답변하세요. "
                        f"전체 내역이 필요한 질문은 리포트 전체를, 특정 항목만 묻는 질문은 해당 항목만 간결하게 답변하세요."
                    )
                else:
                    # 시황/주문 결과는 템플릿 그대로 반환
                    direct_replies.append(formatted)
            else:
                if isinstance(result, dict) and result.get("error"):
                    tool_results.append(f"[오류] 데이터를 불러오지 못했습니다: {result.get('message', result.get('error'))}")
                else:
                    tool_results.append(json.dumps(result, ensure_ascii=False))

        # 직접 반환할 템플릿이 있으면 즉시 반환
        if direct_replies:
            return "\n\n".join(direct_replies)

        # 나머지는 LLM에 전달해 자연어 답변 생성
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
