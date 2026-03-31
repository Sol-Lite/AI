"""
intent별 핸들러 함수 모음

각 핸들러는 (params, user_context, message) → dict 시그니처를 따릅니다.
dispatcher.py의 _HANDLERS 테이블에 등록되어 호출됩니다.
"""
import re
import json

from app.data.market import get_market_data
from app.data.news import get_market_summary
from app.data.account import get_db_data
from app.templates.index import format_index
from app.templates.ranking import format_ranking
from app.templates.chart_price import format_chart_price
from app.templates.exchange_rate import format_exchange_rate
from app.templates.account import format_balance
from app.templates.stock_news import format_korea_summary, format_us_summary, format_stock_news
from app.templates.guide import _GUIDE_MESSAGE, _FALLBACK_MESSAGE, _INVEST_ADVICE_MESSAGE

# 섹터/테마 키워드 — 종목명이 아닌 것들 (stock_news, unknown 핸들러에서 사용)
SECTOR_KEYWORDS: frozenset[str] = frozenset({
    "바이오", "반도체", "제약", "화학", "자동차", "it", "금융", "에너지",
    "헬스케어", "게임", "엔터", "식품", "건설", "철강", "전기차", "배터리",
    "2차전지", "항공", "조선", "보험", "은행", "유통", "통신", "방산",
})


# ── 공통 유틸리티 ──────────────────────────────────────────────────────────────

def _get_tool_context(tool_name: str, args: dict, result: dict) -> list:
    """템플릿 경로용 tool_call + tool_result 메시지 목록을 반환합니다. 저장은 main.py가 담당."""
    return [
        {"role": "assistant", "tool_calls": [{"function": {"name": tool_name, "arguments": args}}]},
        {"role": "tool", "name": tool_name, "content": json.dumps(result, ensure_ascii=False)},
    ]


def _resolve_code(stock_code: str) -> str | None:
    """입력값이 코드 형식이면 그대로, 아니면 Oracle DB에서 종목명으로 코드 조회."""
    if re.match(r'^[A-Z0-9]{1,10}(\.[A-Z]{1,2})?$', str(stock_code)):
        return stock_code
    try:
        from app.db.oracle import resolve_stock_code
        return resolve_stock_code(stock_code)
    except Exception:
        return None


# ── 섹터 안내 문구 ─────────────────────────────────────────────────────────────

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


# ── 핸들러별 정규식 패턴 ───────────────────────────────────────────────────────

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
    r"^(내\s*)?(거래\s*내역|주문\s*내역|주문내역|거래내역|매매\s*내역|매매내역|체결\s*내역|체결내역)"
    r"(\s*(보여|조회|알려|확인|보기))?"
    r"(\s*(줘|해줘|해줘요|볼게|볼래|하고\s*싶어|하고\s*싶어요|하고\s*싶은데))?$"
)

_TRADES_BY_DATE_RE = re.compile(
    r"(\d{1,2}월\s*\d{1,2}일|\d{4}-\d{2}-\d{2}|\d{2}-\d{2})"
    r".*?(거래\s*내역|주문\s*내역|주문내역|거래내역|매매\s*내역|매매내역|체결\s*내역|체결내역)"
    r"|"
    r"(거래\s*내역|주문\s*내역|주문내역|거래내역|매매\s*내역|매매내역|체결\s*내역|체결내역)"
    r".*?(\d{1,2}월\s*\d{1,2}일|\d{4}-\d{2}-\d{2}|\d{2}-\d{2})"
)

_TRADE_COMPARE_RE = re.compile(
    r"매수.{0,10}(많|적|더|비교|차이).{0,10}매도"
    r"|매도.{0,10}(많|적|더|비교|차이).{0,10}매수"
    r"|매수.{0,5}매도.{0,10}(어느|뭐가|어떤|더|많|적)"
    r"|매도.{0,5}매수.{0,10}(어느|뭐가|어떤|더|많|적)"
)

# 포트폴리오 외 다른 도메인 키워드 — 이것이 함께 있으면 agent로 위임
_CROSS_DOMAIN_RE = re.compile(r"뉴스|기사|소식|시세|주가|현재가|얼마")

_METRIC_KEYWORDS: dict[str, list[str]] = {
    "returns":  ["수익률", "수익", "실적", "기간별", "1개월", "3개월", "6개월", "최고", "손실 최소", "최저", "best", "worst"],
    "sector":   ["섹터", "업종", "구성", "비중", "포트폴리오 구성", "국내", "해외", "분산"],
    "risk":     ["리스크", "risk", "위험", "mdd", "낙폭", "최대 낙폭", "변동", "변동성", "회복", "손익", "평가", "실현"],
    "stats":    ["거래 통계", "승률", "손익비", "거래수", "체결 통계", "평균 수익", "평균 손실"],
    "holdings": ["보유 종목", "종목 수", "종목별", "보유", "holdings"],
}


def _detect_metric_type(msg: str) -> str | None:
    """메시지에서 포트폴리오 지표 유형을 감지합니다."""
    lower = msg.lower()
    for metric_type, keywords in _METRIC_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return metric_type
    return None


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
        return {"reply": "종목명이 하나일 때만 답변이 가능해요. 종목명을 하나만 입력해 주세요.\n예) 삼성전자 시세"}
    if params.get("stock_not_found"):
        return {"reply": "종목명을 정확히 입력해 주세요.\n예) 삼성전자 시세, AAPL 주가"}
    stock_code = params.get("stock_code")
    if not stock_code:
        return {"reply": "어떤 종목의 시세를 조회할까요? 종목명이나 코드를 알려주세요.\n예) 삼성전자 시세, 005930 주가"}
    data = get_market_data(type="price", stock_code=stock_code)
    if isinstance(data, dict) and data.get("error"):
        if data.get("error") == "not_found":
            return {"reply": "종목을 찾을 수 없습니다. 종목명을 다시 확인해 주세요."}
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
        return {"reply": "종목명이 하나일 때만 답변이 가능해요. 종목명을 하나만 입력해 주세요.\n예) 삼성전자 매수"}
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
        return {"reply": "종목명이 하나일 때만 답변이 가능해요. 종목명을 하나만 입력해 주세요.\n예) 삼성전자 매도"}
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


_UNSUPPORTED_CURRENCY_RE = re.compile(r"엔화|엔|유로|파운드|위안|달러\s*외|원화\s*외")
_SUPPORTED_CURRENCY_RE  = re.compile(r"달러|원화|USD|KRW")


def _handle_exchange_order(params: dict, user_context: dict, message: str) -> dict:
    if _UNSUPPORTED_CURRENCY_RE.search(message) and not _SUPPORTED_CURRENCY_RE.search(message):
        return {
            "reply": (
                "현재 **달러(USD) ↔ 원화(KRW)** 환전만 지원하고 있어요.\n"
                "엔화, 유로, 파운드, 위안 등 다른 통화 환전은 아직 제공되지 않아요."
            )
        }
    return {
        "type":  "exchange",
        "reply": "환전 정보를 입력하세요:",
    }


def _handle_market_summary(params: dict, user_context: dict, message: str) -> dict:
    korea = get_market_summary(type="korea")
    us    = get_market_summary(type="us")
    tool_ctx = (
        _get_tool_context("get_market_summary", {"market": "korea"}, korea)
        + _get_tool_context("get_market_summary", {"market": "us"}, us)
    )
    return {
        "type":         "market_overview",
        "reply":        f"{format_korea_summary(korea)}\n\n{format_us_summary(us)}",
        "_tool_context": tool_ctx,
        "_is_template": True,
    }


def _handle_korea_summary(params: dict, user_context: dict, message: str) -> dict:
    data = get_market_summary(type="korea")
    tool_ctx = _get_tool_context("get_market_summary", {"market": "korea"}, data)
    return {"type": "market_overview", "reply": format_korea_summary(data), "_tool_context": tool_ctx, "_is_template": True}


def _handle_us_summary(params: dict, user_context: dict, message: str) -> dict:
    data = get_market_summary(type="us")
    tool_ctx = _get_tool_context("get_market_summary", {"market": "us"}, data)
    return {"type": "market_overview", "reply": format_us_summary(data), "_tool_context": tool_ctx, "_is_template": True}


def _handle_stock_news(params: dict, user_context: dict, message: str) -> dict:
    if params.get("multi_stock"):
        return {"reply": "종목명이 하나일 때만 답변이 가능해요. 종목명을 하나만 입력해 주세요.\n예) 삼성전자 뉴스"}

    if params.get("stock_not_found"):
        return {"reply": "종목명을 정확히 입력해 주세요.\n예) 삼성전자 뉴스, AAPL 뉴스"}

    stock_code = params.get("stock_code")

    # 섹터/테마 키워드 질문이면 안내 메시지 반환
    if not stock_code or stock_code.lower() in SECTOR_KEYWORDS:
        if any(kw in message.lower() for kw in SECTOR_KEYWORDS):
            return {"reply": _SECTOR_GUIDE}

    if not stock_code:
        return {"reply": "어떤 종목의 기사를 조회할까요? 종목명을 알려주세요.\n예) 신한지주 기사"}

    data = get_market_summary(type="stock_news", stock_code=stock_code)
    if isinstance(data, dict) and data.get("error"):
        return {"reply": data["error"]}
    tool_ctx = _get_tool_context("get_stock_news", {"stock_code": stock_code}, data)
    reply = format_stock_news(data)
    return {
        "type": "stock_news",
        "reply": reply,
        "stock_code": data.get("stock_code") or stock_code,
        "stock_name": data.get("stock_name") or "",
        "_tool_context": tool_ctx,
        "_is_template": bool(data.get("news")),
    }


def _handle_portfolio(params: dict, user_context: dict, message: str) -> dict:
    from app.templates.portfolio import format_portfolio, format_portfolio_analysis

    msg        = message.strip()
    account_id = user_context.get("account_id", "")

    # 단순 포트폴리오 조회 → 전체 템플릿
    if _PORTFOLIO_SIMPLE_RE.match(msg):
        try:
            from app.data.portfolio import get_portfolio_summary
            data     = get_portfolio_summary(account_id)
            tool_ctx = _get_tool_context("get_portfolio_info", {"info_type": "holdings"}, data)
            return {"reply": format_portfolio(data), "_tool_context": tool_ctx, "_is_template": True}
        except Exception:
            return {"reply": "포트폴리오 데이터를 불러올 수 없어요. 잠시 후 다시 시도해 주세요."}

    # 보유 종목 뉴스 → 직접 처리
    if _HOLDINGS_NEWS_RE.search(msg):
        try:
            from app.data.portfolio import get_holdings
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

    # 크로스도메인 질문 → agent
    if _CROSS_DOMAIN_RE.search(msg):
        try:
            from app.agent.llm_agent import ask_general
            reply, tool_ctx = ask_general(user_context, message)
            return {"reply": reply, "_tool_context": tool_ctx}
        except Exception:
            return {"reply": _FALLBACK_MESSAGE}

    # 특정 지표 질문 → 포커스 분석
    metric_type = _detect_metric_type(msg)
    if metric_type:
        try:
            from app.data.portfolio import get_portfolio_summary
            data     = get_portfolio_summary(account_id)
            tool_ctx = _get_tool_context("get_portfolio_info", {"info_type": metric_type}, data)
            return {"reply": format_portfolio_analysis(data, metric_type), "_tool_context": tool_ctx, "_is_template": True}
        except Exception:
            pass

    # 그 외 → agent
    try:
        from app.agent.llm_agent import ask_general
        reply, tool_ctx = ask_general(user_context, message)
        return {"reply": reply, "_tool_context": tool_ctx}
    except Exception:
        return {"reply": _FALLBACK_MESSAGE}


def _handle_trades(params: dict, user_context: dict, message: str) -> dict:
    from app.templates.trades import format_trades, format_trades_by_date, format_trades_by_stock

    msg        = message.strip()
    account_id = user_context.get("account_id", "")

    # 종목 지정 → by_stock
    if params.get("stock_code"):
        try:
            from app.data.trades import get_trades_by_stock
            stock_code = params["stock_code"]
            data       = get_trades_by_stock(account_id, stock_code=stock_code)
            tool_ctx   = _get_tool_context("get_trade_history",
                                           {"query_type": "by_stock", "stock_code": stock_code}, data)
            return {"reply": format_trades_by_stock(data), "_tool_context": tool_ctx, "_is_template": True}
        except Exception:
            pass
    # 종목 미지정 + 과거형 패턴 → 안내문구
    elif re.search(
        r"(언제|어제|최근에?|며칠|몇\s*일)\s*(샀|팔았|매수했|매도했|거래했|주문했)"
        r"|(샀|팔았|매수했|매도했|거래했|주문했)(지|나|니|어|요)",
        msg,
    ):
        return {"reply": "어떤 종목의 거래내역을 조회할까요? 종목명을 함께 알려주세요.\n예) 삼성전자 언제 샀지?, 엔비디아 최근 거래내역"}

    # 날짜별 거래내역
    if _TRADES_BY_DATE_RE.search(msg):
        try:
            from app.data.trades import get_trades_by_date
            m = re.search(r"\d{1,2}월\s*\d{1,2}일|\d{4}-\d{2}-\d{2}|\d{2}-\d{2}", msg)
            if m:
                data     = get_trades_by_date(account_id, m.group())
                tool_ctx = _get_tool_context("get_trade_history",
                                             {"query_type": "by_date", "date": m.group()}, data)
                return {"reply": format_trades_by_date(data), "_tool_context": tool_ctx, "_is_template": True}
        except Exception:
            pass

    # 단순 거래내역 조회
    if _TRADES_SIMPLE_RE.match(msg):
        try:
            from app.data.trades import get_trades_template_data
            data     = get_trades_template_data(account_id)
            tool_ctx = _get_tool_context("get_trade_history", {"query_type": "recent"}, data)
            return {"reply": format_trades(data), "_tool_context": tool_ctx, "_is_template": True}
        except Exception:
            pass

    # 그 외 → agent
    try:
        from app.agent.llm_agent import ask_general
        reply, tool_ctx = ask_general(user_context, message)
        return {"reply": reply, "_tool_context": tool_ctx}
    except Exception:
        return {"reply": _FALLBACK_MESSAGE}



def _handle_invest_advice(params: dict, user_context: dict, message: str) -> dict:
    return {"reply": _INVEST_ADVICE_MESSAGE}


def _handle_unknown(params: dict, user_context: dict, message: str) -> dict:
    # 섹터/테마 키워드가 포함된 질문 → 안내 메시지
    if any(kw in message.lower() for kw in SECTOR_KEYWORDS):
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

        # 에이전트가 get_stock_price를 단 1회 호출하고
        # 메시지가 "종목명만" 입력한 단순 조회인 경우에만 카드 형식으로 변환
        # (비교/복합 질문은 텍스트 응답 유지)
        _price_results = [
            m for m in tool_ctx
            if m.get("role") == "tool" and m.get("name") == "get_stock_price"
        ]
        if len(_price_results) == 1:
            try:
                import json as _json
                _pd = _json.loads(_price_results[0]["content"]) if isinstance(_price_results[0]["content"], str) else _price_results[0]["content"]
                if isinstance(_pd, dict) and not _pd.get("error"):
                    # LLM이 tool 호출 시 사용한 stock_code 인자도 수집
                    _lm_arg = ""
                    for _tc in tool_ctx:
                        if _tc.get("role") == "assistant" and _tc.get("tool_calls"):
                            for _call in _tc["tool_calls"]:
                                if _call.get("function", {}).get("name") == "get_stock_price":
                                    _lm_arg = str(_call["function"].get("arguments", {}).get("stock_code", ""))
                                    break

                    # 종목명을 제거한 뒤 의미 있는 내용이 남으면 복합 질문 → 카드 제외
                    _strip_re = re.compile(r'[?은는이가도요\s!.,]+')
                    _candidates = {s.lower() for s in (_pd.get("stock_name", ""), _lm_arg) if s}
                    _is_simple = any(
                        not _strip_re.sub("", message.lower().replace(c, ""))
                        for c in _candidates
                    )
                    if _is_simple:
                        return {
                            "type": "stock_price",
                            "reply": reply,
                            "data": {
                                "stock_code":    _pd.get("stock_code", ""),
                                "stock_name":    _pd.get("stock_name", ""),
                                "market_type":   _pd.get("market_type"),
                                "exchange_code": _pd.get("exchange_code"),
                            },
                            "_tool_context": tool_ctx,
                        }
            except Exception:
                pass

        # 에이전트가 get_stock_news를 호출한 경우 → 카드 형식으로 변환
        for _msg in tool_ctx:
            if _msg.get("role") == "tool" and _msg.get("name") == "get_stock_news":
                try:
                    import json as _json
                    _data = _json.loads(_msg["content"]) if isinstance(_msg["content"], str) else _msg["content"]
                    if not _data.get("news"):
                        _data = {
                            "stock_code": _data.get("stock_code") or message,
                            "stock_name": _data.get("stock_name") or message,
                            "news": [],
                        }
                    return {
                        "type":         "stock_news",
                        "reply":        format_stock_news(_data),
                        "stock_code":   _data.get("stock_code") or "",
                        "stock_name":   _data.get("stock_name") or "",
                        "_tool_context": tool_ctx,
                        "_is_template": True,
                    }
                except Exception:
                    pass
                break

        return {"reply": reply, "_tool_context": tool_ctx}
    except Exception:
        return {"reply": _FALLBACK_MESSAGE}
