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
from app.templates.stock_compare import format_stock_compare
from app.templates.guide import _GUIDE_MESSAGE, _FALLBACK_MESSAGE, _INVEST_ADVICE_MESSAGE


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
    indices = data if isinstance(data, list) else data.get("indices", [])
    return {
        "type": "index",
        "reply": format_index(data, user_message=message),
        "data": {"indices": indices},
        "_is_template": True,
    }


def _handle_exchange_rate(params: dict, user_context: dict, message: str) -> dict:
    currency_pair = params.get("currency_pair", "USDKRW")
    data = get_market_data(type="exchange", currency_pair=currency_pair)
    if isinstance(data, dict) and data.get("error"):
        return {"reply": "환율 데이터를 불러올 수 없습니다. 잠시 후 다시 시도해 주세요."}
    return {
        "type": "exchange_rate",
        "reply": format_exchange_rate(data),
        "data": {
            "currency_pair": currency_pair,
            "rate":          data.get("rate"),
            "change":        data.get("change"),
            "change_rate":   data.get("change_rate") or data.get("changeRate"),
        },
        "_is_template": True,
    }


def _handle_ranking(params: dict, user_context: dict, message: str) -> dict:
    ranking_type = params.get("ranking_type", "trading-volume")
    market = params.get("market", "domestic")
    data = get_market_data(type="ranking", ranking_type=ranking_type, market=market)
    if isinstance(data, dict) and data.get("error"):
        return {"reply": "순위 데이터를 불러올 수 없습니다. 잠시 후 다시 시도해 주세요."}
    return {
        "type": "ranking",
        "reply": format_ranking(data),
        "data": {
            "ranking_type": ranking_type,
            "market": market,
            "stocks": data.get("stocks", data) if isinstance(data, dict) else data,
        },
        "_is_template": True,
    }


def _handle_chart_price(params: dict, user_context: dict, message: str) -> dict:
    if params.get("multi_stock"):
        return {"reply": "현재가는 종목 하나씩 조회할 수 있어요. 어떤 종목의 시세를 볼까요?\n예) 삼성전자 현재가"}
    if params.get("stock_not_found"):
        return {"reply": "종목명을 정확히 입력해 주세요.\n예) 삼성전자 시세, AAPL 주가"}
    stock_code = params.get("stock_code")
    account_id = user_context.get("account_id", "")
    if not stock_code:
        return {"reply": "어떤 종목의 시세를 조회할까요? 종목명이나 코드를 알려주세요.\n예) 삼성전자 시세, 005930 주가"}
    data = get_market_data(type="price", stock_code=stock_code)
    if isinstance(data, dict) and data.get("error"):
        if data.get("error") == "not_found":
            return {"reply": f"종목을 찾을 수 없습니다. 종목명을 다시 확인해 주세요."}
        return {"reply": "시세 데이터를 불러올 수 없습니다. 잠시 후 다시 시도해 주세요."}
    tool_ctx = _get_tool_context("get_stock_price", {"stock_code": stock_code}, data)
    card_data = {
        "stock_code":    data.get("stock_code") or stock_code,
        "stock_name":    data.get("stock_name", ""),
        "market_type":   data.get("market_type"),
        "exchange_code": data.get("exchange_code"),
    }
    return {
        "type": "stock_price",
        "reply": format_chart_price(data),
        "data": card_data,
        "_tool_context": tool_ctx,
        "_is_template": True,
    }


def _handle_balance(params: dict, user_context: dict, message: str) -> dict:
    data = get_db_data(type="balance", user_context=user_context)
    if isinstance(data, dict) and data.get("error"):
        return {"reply": "잔고 조회에 실패했습니다. 잠시 후 다시 시도해 주세요."}
    balance_type = params.get("balance_type", "summary")
    return {
        "type": "balance",
        "reply": format_balance(data, balance_type=balance_type),
        "data": {
            "total_assets":    data.get("totalAssets"),
            "total_cash_krw":  data.get("totalCashKrw"),
            "balance_type":    balance_type,
        },
        "_is_template": True,
    }


def _handle_buy_intent(params: dict, user_context: dict, message: str) -> dict:
    if params.get("multi_stock"):
        return {"reply": "주문은 종목 하나씩 진행할 수 있어요. 어떤 종목을 거래하시겠어요?\n예) 삼성전자 매수"}
    stock_code = params.get("stock_code")
    if not stock_code:
        return {"reply": "어떤 종목을 거래하시겠어요? 종목명을 알려주세요.\n예) 신한지주 거래/매수/매도"}
    resolved  = _resolve_code(stock_code) or stock_code
    disp_name = params.get("stock_name") or resolved
    return {
        "type":       "order",
        "reply":      f"**{disp_name}** 주문 정보를 입력하세요:",
        "stock_code": resolved,
    }


def _handle_sell_intent(params: dict, user_context: dict, message: str) -> dict:
    if params.get("multi_stock"):
        return {"reply": "주문은 종목 하나씩 진행할 수 있어요. 어떤 종목을 매도하시겠어요?\n예) 삼성전자 매도"}
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
    return {"reply": f"{korea_text}\n\n{us_text}", "_tool_context": tool_ctx, "_is_template": True}


def _handle_korea_summary(params: dict, user_context: dict, message: str) -> dict:
    data = get_market_summary(type="korea")
    tool_ctx = _get_tool_context("get_market_summary", {"market": "korea"}, data)
    return {"type": "market_overview", "reply": format_korea_summary(data), "_tool_context": tool_ctx, "_is_template": True}


def _handle_us_summary(params: dict, user_context: dict, message: str) -> dict:
    data = get_market_summary(type="us")
    tool_ctx = _get_tool_context("get_market_summary", {"market": "us"}, data)
    return {"type": "market_overview", "reply": format_us_summary(data), "_tool_context": tool_ctx, "_is_template": True}


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
    from app.chatbot.resolver import SECTOR_KEYWORDS as _SECTOR_KEYWORDS
    from app.templates.stock_news import format_holdings_news
    if params.get("stock_not_found"):
        return {"reply": "종목명을 정확히 입력해 주세요.\n예) 삼성전자 뉴스, AAPL 뉴스"}
    stock_code  = params.get("stock_code")
    stock_codes = params.get("stock_codes")  # 복수 종목

    # 여러 종목 뉴스 — 종목별 최신 1건씩 표시
    if stock_codes:
        results = []
        tool_ctx: list[dict] = []
        for code in stock_codes:
            data = get_market_summary(type="stock_news", stock_code=code)
            if isinstance(data, dict) and not data.get("error"):
                results.append(data)
                tool_ctx.extend(_get_tool_context("get_stock_news", {"stock_code": code}, data))
        if not results:
            return {"reply": "조회된 뉴스가 없어요."}
        return {"type": "stock_news", "reply": format_holdings_news(results), "_tool_context": tool_ctx, "_is_template": True}

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
    reply = format_stock_news(data)
    has_news = bool(data.get("news"))
    return {
        "type": "stock_news",
        "reply": reply,
        "stock_code": data.get("stock_code") or stock_code,
        "stock_name": data.get("stock_name") or "",
        "_tool_context": tool_ctx,
        "_is_template": has_news,
    }


_HOLDINGS_NEWS_RE = re.compile(
    r"(보유|가진)\s*한?\s*(종목|주식).*(뉴스|기사|소식)"
    r"|"
    r"(뉴스|기사|소식).*(보유|가진)\s*한?\s*(종목|주식)"
    r"|"
    r"내\s*가?\s*보유.*(뉴스|기사|소식)"
    r"|"
    r"(뉴스|기사|소식).*내\s*가?\s*보유"
)

_PORTFOLIO_SIMPLE_RE = re.compile(
    r"^(내\s*)?(포트폴리오|포폴)(\s*(분석|보여|조회|알려|현황|요약))?(\s*(줘|해줘|해줘요|볼게|볼래))?$"
)

_TRADES_SIMPLE_RE = re.compile(
    r"^(내\s*)?(거래\s*내역|주문\s*내역|주문내역|거래내역|매매\s*내역|매매내역|체결\s*내역|체결내역)(\s*(보여|조회|알려))?(\s*(줘|해줘|해줘요|볼게|볼래))?$"
)
_TRADES_BY_DATE_RE = re.compile(
    r"(\d{1,2}월\s*\d{1,2}일|\d{4}-\d{2}-\d{2}|\d{2}-\d{2})"
    r".*?(거래\s*내역|주문\s*내역|주문내역|거래내역|매매\s*내역|매매내역|체결\s*내역|체결내역)"
    r"|"
    r"(거래\s*내역|주문\s*내역|주문내역|거래내역|매매\s*내역|매매내역|체결\s*내역|체결내역)"
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
    "returns":  ["수익률", "수익", "실적", "기간별", "1개월", "3개월", "6개월", "최고", "손실 최소", "최저", "best", "worst"],
    "sector":   ["섹터", "업종", "구성", "비중", "포트폴리오 구성", "국내", "해외", "분산"],
    "risk":     ["리스크", "risk", "위험", "mdd", "낙폭", "최대 낙폭", "변동", "변동성", "회복", "손익", "평가", "실현"],
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
            return {"reply": format_portfolio(data), "_tool_context": tool_ctx, "_is_template": True}
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
            return {"type": "stock_news", "reply": format_holdings_news(results), "_tool_context": tool_ctx, "_is_template": True}
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
            return {"reply": format_portfolio_analysis(data, metric_type), "_tool_context": tool_ctx, "_is_template": True}
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
    from app.templates.trades import format_trades, format_trades_by_date, format_trades_by_stock

    msg = message.strip()
    account_id = user_context.get("account_id", "")

    # 종목 지정 + 시점/과거형 패턴 → by_stock 직접 처리
    if params.get("stock_code"):
        try:
            from app.data.trades import get_trades_by_stock
            stock_code = params["stock_code"]
            data = get_trades_by_stock(account_id, stock_code=stock_code)
            tool_ctx = _get_tool_context("get_trade_history",
                                         {"query_type": "by_stock", "stock_code": stock_code}, data)
            return {"reply": format_trades_by_stock(data), "_tool_context": tool_ctx, "_is_template": True}
        except Exception:
            pass
    # 종목 미지정 + 과거형 패턴 (로그아웃 후 맥락 없음) → 안내문구
    elif re.search(r"(언제|어제|최근에?|며칠|몇\s*일)\s*(샀|팔았|매수했|매도했|거래했|주문했)"
                   r"|(샀|팔았|매수했|매도했|거래했|주문했)(지|나|니|어|요)", msg):
        return {"reply": "어떤 종목의 거래내역을 조회할까요? 종목명을 함께 알려주세요.\n예) 삼성전자 언제 샀지?, 엔비디아 최근 거래내역"}

    # 날짜별 거래내역 조회 → 템플릿
    if _TRADES_BY_DATE_RE.search(msg):
        try:
            from app.data.trades import get_trades_by_date
            m = re.search(r"\d{1,2}월\s*\d{1,2}일|\d{4}-\d{2}-\d{2}|\d{2}-\d{2}", msg)
            if m:
                data = get_trades_by_date(account_id, m.group())
                tool_ctx = _get_tool_context("get_trade_history",
                                             {"query_type": "by_date", "date": m.group()}, data)
                return {"reply": format_trades_by_date(data), "_tool_context": tool_ctx, "_is_template": True}
        except Exception:
            pass

    # 단순 거래내역 조회 → 템플릿
    if _TRADES_SIMPLE_RE.match(msg):
        try:
            from app.data.trades import get_trades_template_data
            data = get_trades_template_data(account_id)
            tool_ctx = _get_tool_context("get_trade_history", {"query_type": "recent"}, data)
            return {"reply": format_trades(data), "_tool_context": tool_ctx, "_is_template": True}
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

# 매수·매도 투자 추천 요청 패턴 (시스템이 답할 수 없는 질문)
_INVEST_ADVICE_RE = re.compile(
    # "살까해", "팔까해", "매수할까해", "사려고" 등 의사 표현(주문 intent)은 제외
    r"(사야|팔아야|매수해야|매도해야"
    r"|살까(?!해|하다|하고|하려)|팔까(?!해|하다|하고|하려)"
    r"|매수할까(?!해|하다|하고|하려)|매도할까(?!해|하다|하고|하려)"
    r"|사도 돼|팔아도 돼|사도돼|팔아도돼"
    r"|살만해|팔만해|살 만해|팔 만해"
    r"|추천.*?(매수|매도|종목)"
    r"|매수.*?추천|매도.*?추천|종목.*?추천"
    r"|어떤 종목.*?(사|살|매수)"
    r")"
)


def _handle_stock_compare(params: dict, user_context: dict, message: str) -> dict:
    """명시적으로 지정된 2개 이상 종목의 시세를 조회해 등락률/등락폭을 비교합니다."""
    stock_codes: list[tuple[str, str]] = params.get("stock_codes", [])  # [(code, name), ...]
    if len(stock_codes) < 2:
        return {"reply": "비교할 종목을 두 개 이상 알려주세요.\n예) 삼성전자 SK하이닉스 비교"}

    results  = []
    failed   = []
    tool_ctx = []
    for code, name in stock_codes:
        data = get_market_data(type="price", stock_code=code)
        if isinstance(data, dict) and data.get("error"):
            failed.append(name or code)
            continue
        results.append(data)
        tool_ctx.extend(_get_tool_context("get_stock_price", {"stock_code": code}, data))

    if not results:
        return {"reply": "시세 데이터를 불러올 수 없습니다. 잠시 후 다시 시도해 주세요."}

    reply = format_stock_compare(results)
    if failed:
        reply += f"\n({', '.join(failed)}은(는) 조회에 실패했어요.)"

    return {
        "type": "stock_price",
        "reply": reply,
        "_tool_context": tool_ctx,
        "_is_template": True,
    }


def _handle_invest_advice(params: dict, user_context: dict, message: str) -> dict:
    return {"reply": _INVEST_ADVICE_MESSAGE}


def _handle_unknown(params: dict, user_context: dict, message: str) -> dict:
    # 매수·매도 추천 요청 → 서비스 범위 외 안내 (unknown intent로 도달한 경우 대비)
    if _INVEST_ADVICE_RE.search(message):
        return {"reply": _INVEST_ADVICE_MESSAGE}

    # 섹터/테마 키워드가 포함된 질문 → 안내 메시지
    from app.chatbot.resolver import SECTOR_KEYWORDS as _SECTOR_KEYWORDS
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
        import json as _json
        from app.agent.llm_agent import ask_general
        reply, tool_ctx = ask_general(user_context, message)

        # 에이전트가 get_stock_news를 호출한 경우 → 뉴스 없음/오류 모두 템플릿 형식으로 통일
        for _msg in tool_ctx:
            if _msg.get("role") == "tool" and _msg.get("name") == "get_stock_news":
                try:
                    _data = _json.loads(_msg["content"]) if isinstance(_msg["content"], str) else _msg["content"]
                    if not _data.get("news"):
                        # 뉴스 없음(수집 안됨) 또는 종목 미인식 → 템플릿 형식으로 통일
                        _template_data = {
                            "stock_code": _data.get("stock_code") or message,
                            "stock_name": _data.get("stock_name") or message,
                            "news": [],
                        }
                        reply = format_stock_news(_template_data)
                except Exception:
                    pass
                break

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
    "invest_advice":  _handle_invest_advice,
    "stock_compare":  _handle_stock_compare,
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


# ── 입력 전처리 / 숏컷 / intent 보정 ─────────────────────────────────────────
# (이전에 main.py에 분산되어 있던 라우팅 보조 로직)

# 종목명 only 패턴 — 의도 키워드 없이 종목명(+조사)만 있는 경우
_STOCK_ONLY_STRIP_RE = re.compile(r"[?은는이가도요\s]+$")

# 시세/뉴스 intent 키워드 — 제거 후 남은 토큰이 있으면 사용자가 종목을 지정한 것으로 판단
_PRICE_INTENT_WORDS_RE = re.compile(
    r"시세|주가|현재가|가격|얼마|알려줘|알려줘요|봐줘|보여줘|조회|확인|어때|어떄"
    r"|현재|지금|오늘|뉴스|소식|기사|최근|최신"
)


def _has_explicit_stock_token(message: str) -> bool:
    """
    메시지에서 intent 키워드를 제거한 뒤 종목처럼 보이는 토큰이 남아 있으면 True.
    사용자가 종목을 지정했지만 resolve에 실패한 경우를 감지합니다.
    """
    cleaned = _PRICE_INTENT_WORDS_RE.sub("", message).strip()
    cleaned = re.sub(r"[?!.은는이가도요\s]+", "", cleaned)
    return bool(cleaned)

# 명확한 의도 키워드 목록 (이게 있으면 router가 처리)
INTENT_KW: frozenset[str] = frozenset({
    "현재가", "시세", "주가", "차트", "뉴스", "기사", "소식", "순위", "랭킹",
    "환율", "잔고", "지수", "시황", "매수", "매도", "매매", "주문", "환전", "얼마", "가격",
})

# 직전 tool → 숏컷 대상
_SHORTCUT_TOOLS = {"get_stock_price", "get_stock_news"}

# 이전 대화 맥락이 있어야 의미가 명확해지는 모호한 패턴
_AMBIGUOUS_RE = re.compile(
    r"(제일|가장|젤)\s*(많이\s*(오른|내린|상승|하락)|수익|손해|위험|좋은|나쁜)"
    r"|"
    r"(수익률|손익|비중|비율)\s*(이|가|은|는)?\s*(얼마|어때|어떻게|높|낮)"
)

# 이전에 조회한 종목끼리 비교하는 패턴
_COMPARISON_RE = re.compile(
    r"(두|세|네|여러|그|이)\s*(종목|주식|회사)\s*(중|에서|가운데)"
    r"|"
    r"(둘|셋|넷)\s*중"
    r"|"
    r"어느\s*(쪽|게|것|종목|주식)\s*(이|가)?\s*(더|많이)"
    r"|"
    r"(두|세|여러|이)\s*(종목|주식)\s*(비교|차이)"
    r"|"
    r"(가장|제일|젤)\s*(많이)?\s*(오른|내린|상승|하락)"
    r"|"
    r"더\s*(많이|크게)?\s*(오른|내린|올랐|내렸)"
)

# 종목명과 함께 와도 포트폴리오 도구가 필요한 키워드
_PORTFOLIO_KW_RE = re.compile(r"손익|손익비|평가손익|실현손익|수익금|손실금|평가액")

# 보유 종목 대상 비교 패턴 — 항상 agent로
_PORTFOLIO_COMPARISON_RE = re.compile(
    r"보유\s*(종목|주식|중|한).*?(가장|제일|젤|많이|오른|내린|올랐|내렸|수익|손해|높|낮)"
    r"|"
    r"(가장|제일|젤|더)\s*(많이)?\s*(오른|내린|올랐|내렸|수익|손실).*보유"
)

_PORTFOLIO_TOOLS = {"get_portfolio_info", "get_trade_history"}
_PRICE_TOOLS     = {"get_stock_price", "get_stock_news"}


def _last_tool_was_portfolio(account_id: str, session_since: float | None = None) -> bool:
    """최근 대화에서 포트폴리오/거래 tool을 사용했으면 True"""
    try:
        from app.db.mongo import get_chat_history
        history = get_chat_history(account_id, limit=6, since=session_since)
        for msg in reversed(history):
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                tool_name = msg["tool_calls"][0].get("function", {}).get("name", "")
                return tool_name in _PORTFOLIO_TOOLS
    except Exception:
        pass
    return False


def _has_recent_price_context(account_id: str, session_since: float | None = None) -> bool:
    """최근 대화에서 가격/뉴스 tool을 2회 이상 사용했으면 True (종목 비교 맥락 감지)"""
    try:
        from app.db.mongo import get_chat_history
        history = get_chat_history(account_id, limit=8, since=session_since)
        count = sum(
            1 for msg in history
            if msg.get("role") == "assistant" and msg.get("tool_calls")
            and msg["tool_calls"][0].get("function", {}).get("name") in _PRICE_TOOLS
        )
        return count >= 2
    except Exception:
        pass
    return False


def try_shortcut(
    message: str,
    account_id: str,
    session_since: float | None = None,
) -> dict | None:
    """
    종목명만 있는 짧은 메시지 + 직전 응답이 price/news/order인 경우
    LLM 없이 바로 해당 동작을 재실행하고 반환합니다.

    예) 직전이 삼성전자 시세 조회였고 "SK하닉은?" → get_stock_price(SK하이닉스) 직접 실행
    """
    msg = message.strip()

    # 명확한 의도 키워드가 있으면 패스 (router가 처리)
    if any(kw in msg for kw in INTENT_KW):
        return None

    from app.stock_ref import resolve_from_csv, _normalize_message, _apply_synonyms

    # 종목명 해석: 원본 먼저 시도 → 실패 시 조사 제거 후 재시도
    code, name = resolve_from_csv(_normalize_message(msg))
    if not code:
        base = _STOCK_ONLY_STRIP_RE.sub("", msg)
        if not base:
            return None
        code, name = resolve_from_csv(_normalize_message(base))
    if not code:
        return None

    # 종목명 외 다른 내용이 있으면 숏컷 bypass → router/agent가 처리
    msg_expanded = _apply_synonyms(_normalize_message(msg))
    msg_stripped = _STOCK_ONLY_STRIP_RE.sub("", msg_expanded)
    remaining = msg_stripped.lower().replace(name.lower(), "").strip()
    if remaining:
        return None

    # 직전 응답 확인 (최근 4턴, 현재 세션만)
    try:
        from app.db.mongo import get_chat_history
        history = get_chat_history(account_id, limit=4, since=session_since)
    except Exception:
        return None

    # 세션 내 tool_call 없음 → 의도를 알 수 없으므로 안내문구
    has_tool_call = any(m.get("tool_calls") for m in history)
    if not has_tool_call:
        return {
            "reply": (
                f"**{name}**에 대해 어떤 정보를 원하시나요?\n"
                f"예) {name} 현재가  /  {name} 뉴스  /  {name} 매수"
            )
        }

    # buy/sell 주문 단축키: 직전 assistant가 "주문 정보를 입력하세요:" 형태
    for m in reversed(history):
        if m.get("role") == "assistant":
            if "주문 정보를 입력하세요:" in m.get("content", ""):
                return {
                    "type":       "order",
                    "reply":      f"**{name}** 주문 정보를 입력하세요:",
                    "stock_code": code,
                }
            break

    # price/news tool 단축키: 직전 tool_calls 확인
    last_tool = None
    for m in reversed(history):
        if m.get("role") == "assistant" and m.get("tool_calls"):
            last_tool = m["tool_calls"][0].get("function", {}).get("name")
            break

    if last_tool not in _SHORTCUT_TOOLS:
        return None

    if last_tool == "get_stock_price":
        data = get_market_data(type="price", stock_code=code)
        if isinstance(data, dict) and data.get("error"):
            return None
        tool_ctx = _get_tool_context("get_stock_price", {"stock_code": code}, data)
        return {"reply": format_chart_price(data), "_tool_context": tool_ctx, "_is_template": True}

    if last_tool == "get_stock_news":
        from app.templates.stock_news import format_stock_news as _fmt_news
        data = get_market_summary(type="stock_news", stock_code=code)
        if isinstance(data, dict) and data.get("error"):
            return None
        if not data.get("stock_name"):
            data = {**data, "stock_name": name}
        tool_ctx = _get_tool_context("get_stock_news", {"stock_code": code}, data)
        return {
            "reply": _fmt_news(data),
            "_tool_context": tool_ctx,
            "_is_template": bool(data.get("news")),
        }

    return None


def pre_dispatch(
    intent: str,
    params: dict,
    message: str,
    account_id: str,
    session_since: float | None = None,
) -> tuple[str, dict]:
    """
    router.detect()가 반환한 (intent, params)를 문맥 기반으로 보정합니다.
    이전에 main.py에 분산되어 있던 intent 재분류 로직을 통합합니다.

    Returns:
        (intent, params) — 보정된 값
    """
    # 손익/평가손익 키워드 → chart_price 오라우팅 방지
    if intent == "chart_price" and _PORTFOLIO_KW_RE.search(message):
        intent = "unknown"

    # 모호한 질문 + 직전 포트폴리오 tool → agent
    if intent in ("ranking", "chart_price", "unknown") and _AMBIGUOUS_RE.search(message):
        if _last_tool_was_portfolio(account_id, session_since):
            intent = "unknown"

    # "보유 종목 중 가장 많이 오른 건?" → 포트폴리오 대상 비교이므로 항상 agent
    if intent in ("ranking", "chart_price", "unknown") and _PORTFOLIO_COMPARISON_RE.search(message):
        intent = "unknown"

    # 종목 비교 질문 처리
    if intent in ("ranking", "chart_price", "unknown") and _COMPARISON_RE.search(message):
        # 보유 종목 비교가 아닌 경우 → 명시적 종목 추출 시도
        if not _PORTFOLIO_COMPARISON_RE.search(message) and "보유" not in message:
            try:
                from app.stock_ref import resolve_all_from_csv, _normalize_message
                all_stocks = resolve_all_from_csv(_normalize_message(message))
                if len(all_stocks) >= 2:
                    # 명시적 종목 2개 이상 → 가격 조회 비교 템플릿
                    intent = "stock_compare"
                    params = {**params, "stock_codes": all_stocks}
                else:
                    # 종목 특정 불가 + 직전 가격 조회 2회 이상 → agent
                    if _has_recent_price_context(account_id, session_since):
                        intent = "unknown"
            except Exception:
                if _has_recent_price_context(account_id, session_since):
                    intent = "unknown"
        else:
            # 보유 종목 비교 → agent
            intent = "unknown"

    # 매수·매도 intent인데 추천 질문 형태 → invest_advice 안내
    if intent in ("buy_intent", "sell_intent") and _INVEST_ADVICE_RE.search(message):
        intent = "invest_advice"

    # 시세/뉴스 intent인데 종목 미지정
    if intent in ("chart_price", "stock_news") and not params.get("stock_code"):
        if _has_explicit_stock_token(message):
            # 종목처럼 보이는 토큰이 있었는데 resolve 실패 → "찾을 수 없음" 처리
            params = {**params, "stock_not_found": True}
        else:
            # 순수 follow-up (종목 언급 없음) → 히스토리에서 마지막 종목 추출
            try:
                from app.db.mongo import get_chat_history
                from app.agent.llm_agent import _extract_last_stock
                _hist = get_chat_history(account_id, limit=6, since=session_since)
                _last_stock = _extract_last_stock(_hist)
                if _last_stock:
                    params = {**params, "stock_code": _last_stock}
            except Exception:
                pass

    return intent, params
