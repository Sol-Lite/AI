"""
의도(intent) → 도구 호출 → 템플릿 포맷 디스패처

각 의도별 처리:
    index          → get_market_data("index")           → format_index()
    exchange_rate  → get_market_data("exchange")        → format_exchange_rate()
    ranking        → get_market_data("ranking")         → format_ranking()
    chart_price    → get_market_data("price")           → format_chart_price()
    balance        → get_db_data("balance")             → format_balance()
    buy_intent     → action: "activate_buy"
    sell_intent    → action: "activate_sell"
    exchange_order → action: "activate_exchange"
    korea_summary  → get_market_summary("korea")        → format_korea_summary()
    us_summary     → get_market_summary("us")           → format_us_summary()
    stock_news     → get_market_summary("stock_news")   → format_stock_news()
    unknown        → 안내 메시지
"""
import re

from app.data.market import get_market_data
from app.data.news import get_market_summary
from app.data.account import get_db_data
from app.templates.index import format_index
from app.templates.ranking import format_ranking
from app.templates.chart_price import format_chart_price
from app.templates.exchange_rate import format_exchange_rate
from app.templates.account import format_balance
from app.templates.stock_news import format_korea_summary, format_us_summary, format_stock_news
from app.templates.guide import _GUIDE_MESSAGE, _FALLBACK_MESSAGE


def dispatch(intent: str, params: dict, user_context: dict, original_message: str = "") -> dict:
    """
    의도(intent)에 따라 적절한 도구를 호출하고 응답 딕셔너리를 반환합니다.

    Returns:
        {
            "reply":         str,            # 채팅 응답 텍스트
            "action":        str | None,     # 프론트엔드 액션 (activate_buy 등)
            "action_params": dict | None,    # 액션 파라미터
        }
    """
    handler = _HANDLERS.get(intent, _handle_unknown)
    return handler(params, user_context, original_message)


# ── 핸들러 함수 ───────────────────────────────────────────────────────────────

def _handle_greeting(params: dict, user_context: dict, message: str) -> dict:
    return {"reply": _GUIDE_MESSAGE}

def _handle_index(params: dict, user_context: dict, message: str) -> dict:
    data = get_market_data(type="index")
    if isinstance(data, dict) and data.get("error"):
        return {"reply": "지수 데이터를 불러올 수 없습니다. 잠시 후 다시 시도해 주세요."}
    return {"reply": format_index(data, user_message=message)}


def _handle_exchange_rate(params: dict, user_context: dict, message: str) -> dict:
    currency_pair = params.get("currency_pair", "USDKRW")
    data = get_market_data(type="exchange", currency_pair=currency_pair)
    if isinstance(data, dict) and data.get("error"):
        return {"reply": "환율 데이터를 불러올 수 없습니다. 잠시 후 다시 시도해 주세요."}
    return {"reply": format_exchange_rate(data)}


def _handle_ranking(params: dict, user_context: dict, message: str) -> dict:
    ranking_type = params.get("ranking_type", "trading-volume")
    market = params.get("market", "domestic")
    data = get_market_data(type="ranking", ranking_type=ranking_type, market=market)
    if isinstance(data, dict) and data.get("error"):
        return {"reply": "순위 데이터를 불러올 수 없습니다. 잠시 후 다시 시도해 주세요."}
    return {"reply": format_ranking(data)}


def _handle_chart_price(params: dict, user_context: dict, message: str) -> dict:
    stock_code = params.get("stock_code")
    account_id = user_context.get("account_id", "")
    if not stock_code:
        return {"reply": "어떤 종목의 시세를 조회할까요? 종목명이나 코드를 알려주세요.\n예) 삼성전자 시세, 005930 주가"}
    data = get_market_data(type="price", stock_code=stock_code)
    if isinstance(data, dict) and data.get("error"):
        if data.get("error") == "not_found":
            return {"reply": f"'{stock_code}' 종목을 찾을 수 없습니다. 종목명을 다시 확인해 주세요."}
        return {"reply": "시세 데이터를 불러올 수 없습니다. 잠시 후 다시 시도해 주세요."}
    tool_ctx = _get_tool_context("get_stock_price", {"stock_code": stock_code}, data)
    return {"reply": format_chart_price(data), "_tool_context": tool_ctx}


def _handle_balance(params: dict, user_context: dict, message: str) -> dict:
    data = get_db_data(type="balance", user_context=user_context)
    if isinstance(data, dict) and data.get("error"):
        return {"reply": "잔고 조회에 실패했습니다. 잠시 후 다시 시도해 주세요."}
    balance_type = params.get("balance_type", "summary")
    return {"reply": format_balance(data, balance_type=balance_type)}


def _handle_buy_intent(params: dict, user_context: dict, message: str) -> dict:
    stock_code = params.get("stock_code")
    if not stock_code:
        return {"reply": "어떤 종목을 매수하시겠어요? 종목명을 알려주세요.\n예) 신한지주 매수"}
    resolved  = _resolve_code(stock_code) or stock_code
    disp_name = params.get("stock_name") or resolved
    return {
        "type":       "order",
        "reply":      f"**{disp_name}** 주문 정보를 입력하세요:",
        "stock_code": resolved,
    }


def _handle_sell_intent(params: dict, user_context: dict, message: str) -> dict:
    stock_code = params.get("stock_code")
    if not stock_code:
        return {"reply": "어떤 종목을 매도하시겠어요? 종목명을 알려주세요.\n예) 신한지주 매도"}
    resolved  = _resolve_code(stock_code) or stock_code
    disp_name = params.get("stock_name") or resolved
    return {
        "type":       "order",
        "reply":      f"**{disp_name}** 주문 정보를 입력하세요:",
        "stock_code": resolved,
    }


def _handle_exchange_order(params: dict, user_context: dict, message: str) -> dict:
    return {
        "type":  "exchange",
        "reply": "환전 정보를 입력하세요:",
    }


def _handle_market_summary(params: dict, user_context: dict, message: str) -> dict:
    korea = get_market_summary(type="korea")
    us    = get_market_summary(type="us")
    korea_text = format_korea_summary(korea)
    us_text    = format_us_summary(us)
    tool_ctx = (
        _get_tool_context("get_market_summary", {"market": "korea"}, korea)
        + _get_tool_context("get_market_summary", {"market": "us"}, us)
    )
    return {"reply": f"{korea_text}\n\n{us_text}", "_tool_context": tool_ctx}


def _handle_korea_summary(params: dict, user_context: dict, message: str) -> dict:
    data = get_market_summary(type="korea")
    tool_ctx = _get_tool_context("get_market_summary", {"market": "korea"}, data)
    return {"reply": format_korea_summary(data), "_tool_context": tool_ctx}


def _handle_us_summary(params: dict, user_context: dict, message: str) -> dict:
    data = get_market_summary(type="us")
    tool_ctx = _get_tool_context("get_market_summary", {"market": "us"}, data)
    return {"reply": format_us_summary(data), "_tool_context": tool_ctx}


_SECTOR_GUIDE = (
    "섹터/업종별 뉴스는 제공하지 않아요.  \n"
    "아래 기능을 이용해 주세요.  \n\n"
    "• 종목별 뉴스  \n"
    "　예) 삼성전자 뉴스  \n\n"
    "• 한국 시황  \n"
    "　예) 오늘 국내 시황  \n\n"
    "• 미국 시황  \n"
    "　예) 미국 시장 어때"
)


def _handle_stock_news(params: dict, user_context: dict, message: str) -> dict:
    from app.chatbot.resolver import _SECTOR_KEYWORDS
    stock_code = params.get("stock_code")
    account_id = user_context.get("account_id", "")

    # 섹터/테마 키워드 질문이면 안내 메시지 반환
    if not stock_code or stock_code.lower() in _SECTOR_KEYWORDS:
        msg_lower = message.lower()
        if any(kw in msg_lower for kw in _SECTOR_KEYWORDS):
            return {"reply": _SECTOR_GUIDE}

    if not stock_code:
        return {"reply": "어떤 종목의 기사를 조회할까요? 종목명을 알려주세요.\n예) 신한지주 기사"}
    data = get_market_summary(type="stock_news", stock_code=stock_code)
    if isinstance(data, dict) and data.get("error"):
        return {"reply": data["error"]}
    tool_ctx = _get_tool_context("get_stock_news", {"stock_code": stock_code}, data)
    return {"reply": format_stock_news(data), "_tool_context": tool_ctx}


_HOLDINGS_NEWS_RE = re.compile(
    r"(보유|가진)\s*(종목|주식).*(뉴스|기사|소식)"
    r"|"
    r"(뉴스|기사|소식).*(보유|가진)\s*(종목|주식)"
)

_PORTFOLIO_SIMPLE_RE = re.compile(
    r"^(내\s*)?(포트폴리오|포폴)(\s*(분석|보여|조회|알려|현황|요약))?(\s*(줘|해줘|해줘요|볼게|볼래))?$"
)
_TRADES_SIMPLE_RE = re.compile(
    r"^(내\s*)?(거래\s*내역|거래내역|매매\s*내역|체결\s*내역)(\s*(보여|조회|알려))?(\s*(줘|해줘|해줘요|볼게|볼래))?$"
)


_TRADES_BY_DATE_RE = re.compile(
    r"(\d{1,2}월\s*\d{1,2}일|\d{4}-\d{2}-\d{2}|\d{2}-\d{2})"
    r".*?(거래\s*내역|거래내역|체결\s*내역|매매\s*내역)"
    r"|"
    r"(거래\s*내역|거래내역|체결\s*내역|매매\s*내역)"
    r".*?(\d{1,2}월\s*\d{1,2}일|\d{4}-\d{2}-\d{2}|\d{2}-\d{2})"
)


def _get_tool_context(tool_name: str, args: dict, result: dict) -> list:
    """템플릿 경로용 tool_call + tool_result 메시지 목록을 반환합니다. 저장은 main.py가 담당."""
    import json
    return [
        {"role": "assistant", "tool_calls": [{"function": {"name": tool_name, "arguments": args}}]},
        {"role": "tool", "name": tool_name, "content": json.dumps(result, ensure_ascii=False)},
    ]


_METRIC_KEYWORDS: dict[str, list[str]] = {
    "returns":  ["수익률", "수익", "실적", "기간별", "1개월", "3개월", "6개월", "최고", "최저", "best", "worst"],
    "sector":   ["섹터", "업종", "구성", "비중", "포트폴리오 구성", "국내", "해외", "분산"],
    "risk":     ["리스크", "위험", "mdd", "낙폭", "변동", "변동성", "회복", "손익", "평가", "실현"],
    "stats":    ["거래 통계", "승률", "손익비", "거래수", "체결 통계", "평균 수익", "평균 손실"],
    "holdings": ["보유 종목", "종목 수", "종목별", "보유", "holdings"],
}

# 포트폴리오 외 다른 도메인 키워드 — 이것이 함께 있으면 agent로 위임
_CROSS_DOMAIN_RE = re.compile(r"뉴스|기사|소식|시세|주가|현재가|얼마")


def _detect_metric_type(msg: str) -> str | None:
    """메시지에서 포트폴리오 지표 유형을 감지합니다."""
    lower = msg.lower()
    for metric_type, keywords in _METRIC_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return metric_type
    return None


def _handle_portfolio(params: dict, user_context: dict, message: str) -> dict:
    from app.templates.portfolio import format_portfolio, format_portfolio_analysis

    msg = message.strip()
    account_id = user_context.get("account_id", "")

    # 단순 포트폴리오 조회 → 전체 템플릿
    if _PORTFOLIO_SIMPLE_RE.match(msg):
        try:
            from app.data.portfolio import get_portfolio_summary
            data = get_portfolio_summary(account_id)
            tool_ctx = _get_tool_context("get_portfolio_info", {"info_type": "holdings"}, data)
            return {"reply": format_portfolio(data), "_tool_context": tool_ctx}
        except Exception:
            pass

    # 보유 종목 뉴스 → 전용 핸들러 (multi-step tool call 대신 직접 처리)
    if _HOLDINGS_NEWS_RE.search(msg):
        try:
            from app.data.portfolio import get_holdings
            from app.data.news import get_market_summary
            from app.templates.stock_news import format_holdings_news

            holdings = get_holdings(account_id).get("holdings", [])
            if not holdings:
                return {"reply": "현재 보유 중인 종목이 없습니다."}

            results = []
            for h in holdings:
                news_data = get_market_summary(type="stock_news", stock_code=h["stock_code"])
                results.append({
                    "stock_code": h["stock_code"],
                    "stock_name": h["stock_name"],
                    "news":       news_data.get("news", []),
                })
            tool_ctx = _get_tool_context("get_portfolio_info", {"info_type": "holdings"}, {"holdings": holdings})
            return {"reply": format_holdings_news(results), "_tool_context": tool_ctx}
        except Exception:
            pass

    # 그 외 크로스도메인 질문 → agent
    if _CROSS_DOMAIN_RE.search(msg):
        try:
            from app.agent.llm_agent import ask_general
            reply, tool_ctx = ask_general(user_context, message)
            return {"reply": reply, "_tool_context": tool_ctx}
        except Exception:
            return {"reply": _FALLBACK_MESSAGE}

    # 특정 지표 질문 → 포커스 분석 + 한 줄 요약
    metric_type = _detect_metric_type(msg)
    if metric_type:
        try:
            from app.data.portfolio import get_portfolio_summary
            data = get_portfolio_summary(account_id)
            tool_ctx = _get_tool_context("get_portfolio_info", {"info_type": metric_type}, data)
            return {"reply": format_portfolio_analysis(data, metric_type), "_tool_context": tool_ctx}
        except Exception:
            pass

    # 그 외 포트폴리오 질문 → agent
    try:
        from app.agent.llm_agent import ask_general
        reply, tool_ctx = ask_general(user_context, message)
        return {"reply": reply, "_tool_context": tool_ctx}
    except Exception:
        return {"reply": _FALLBACK_MESSAGE}


def _handle_trades(params: dict, user_context: dict, message: str) -> dict:
    from app.templates.trades import format_trades, format_trades_by_date

    msg = message.strip()
    account_id = user_context.get("account_id", "")

    # 날짜별 거래내역 조회 → 템플릿
    if _TRADES_BY_DATE_RE.search(msg):
        try:
            from app.data.trades import get_trades_by_date
            m = re.search(r"\d{1,2}월\s*\d{1,2}일|\d{4}-\d{2}-\d{2}|\d{2}-\d{2}", msg)
            if m:
                data = get_trades_by_date(account_id, m.group())
                tool_ctx = _get_tool_context("get_trade_history",
                                             {"query_type": "by_date", "date": m.group()}, data)
                return {"reply": format_trades_by_date(data), "_tool_context": tool_ctx}
        except Exception:
            pass

    # 단순 거래내역 조회 → 템플릿
    if _TRADES_SIMPLE_RE.match(msg):
        try:
            from app.data.trades import get_trades_template_data
            data = get_trades_template_data(account_id)
            tool_ctx = _get_tool_context("get_trade_history", {"query_type": "recent"}, data)
            return {"reply": format_trades(data), "_tool_context": tool_ctx}
        except Exception:
            pass

    # 그 외 거래내역 질문 → agent
    try:
        from app.agent.llm_agent import ask_general
        reply, tool_ctx = ask_general(user_context, message)
        return {"reply": reply, "_tool_context": tool_ctx}
    except Exception:
        return {"reply": _FALLBACK_MESSAGE}


_TRADE_COMPARE_RE = re.compile(
    r"매수.{0,10}(많|적|더|비교|차이).{0,10}매도"
    r"|매도.{0,10}(많|적|더|비교|차이).{0,10}매수"
    r"|매수.{0,5}매도.{0,10}(어느|뭐가|어떤|더|많|적)"
    r"|매도.{0,5}매수.{0,10}(어느|뭐가|어떤|더|많|적)"
)


def _handle_unknown(params: dict, user_context: dict, message: str) -> dict:
    # 섹터/테마 키워드가 포함된 질문 → 안내 메시지
    from app.chatbot.resolver import _SECTOR_KEYWORDS
    if any(kw in message.lower() for kw in _SECTOR_KEYWORDS):
        return {"reply": _SECTOR_GUIDE}

    # 매수 vs 매도 비교 질문 → 직접 계산 (LLM 비교 환각 방지)
    if _TRADE_COMPARE_RE.search(message):
        try:
            from app.data.trades import get_trade_summary
            account_id = str(user_context.get("account_id") or "")
            if account_id:
                data = get_trade_summary(account_id)
                buy  = int(data.get("buy_count",  0))
                sell = int(data.get("sell_count", 0))
                if buy > sell:
                    reply = f"매수가 더 많아요. 매수 {buy}건, 매도 {sell}건입니다."
                elif sell > buy:
                    reply = f"매도가 더 많아요. 매도 {sell}건, 매수 {buy}건입니다."
                else:
                    reply = f"매수와 매도가 각각 {buy}건으로 같아요."
                tool_ctx = _get_tool_context("get_trade_history", {"query_type": "recent"}, data)
                return {"reply": reply, "_tool_context": tool_ctx}
        except Exception:
            pass

    # 그 외 모든 자연어 → general agent
    try:
        from app.agent.llm_agent import ask_general
        reply, tool_ctx = ask_general(user_context, message)
        return {"reply": reply, "_tool_context": tool_ctx}
    except Exception:
        return {"reply": _FALLBACK_MESSAGE}


# ── 핸들러 매핑 테이블 ────────────────────────────────────────────────────────

_HANDLERS = {
    "greeting":       _handle_greeting,
    "index":          _handle_index,
    "exchange_rate":  _handle_exchange_rate,
    "ranking":        _handle_ranking,
    "chart_price":    _handle_chart_price,
    "balance":        _handle_balance,
    "buy_intent":     _handle_buy_intent,
    "sell_intent":    _handle_sell_intent,
    "exchange_order": _handle_exchange_order,
    "market_summary": _handle_market_summary,
    "korea_summary":  _handle_korea_summary,
    "us_summary":     _handle_us_summary,
    "stock_news":     _handle_stock_news,
    "portfolio":      _handle_portfolio,
    "trades":         _handle_trades,
    "unknown":        _handle_unknown,
}


# ── 유틸리티 ──────────────────────────────────────────────────────────────────

def _resolve_code(stock_code: str) -> str | None:
    """
    입력값이 코드 형식이면 그대로, 아니면 Oracle DB에서 종목명으로 코드 조회.
    DB 연결이 없는 경우 None 반환 (호출부에서 원본 값 사용).
    """
    if re.match(r'^[A-Z0-9]{1,10}(\.[A-Z]{1,2})?$', str(stock_code)):
        return stock_code
    try:
        from app.db.oracle import resolve_stock_code
        return resolve_stock_code(stock_code)
    except Exception:
        return None
