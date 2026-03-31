"""
의도(intent) → 핸들러 라우팅 디스패처

흐름:
  main.py → try_shortcut() → (shortcut hit) → return
                           → detect() → pre_dispatch() → dispatch() → handler

각 의도별 처리는 handlers.py 참고.
"""
import re

from app.chatbot import handlers as _h
from app.chatbot.session import _last_tool_was_portfolio, _has_recent_price_context
from app.data.market import get_market_data
from app.data.news import get_market_summary
from app.templates.chart_price import format_chart_price
from app.templates.stock_news import format_stock_news
from app.stock_ref import resolve_from_csv, _normalize_message, _apply_synonyms, resolve_all_from_csv


# ── 핸들러 매핑 테이블 ────────────────────────────────────────────────────────

_HANDLERS = {
    "greeting":       _h._handle_greeting,
    "index":          _h._handle_index,
    "exchange_rate":  _h._handle_exchange_rate,
    "ranking":        _h._handle_ranking,
    "chart_price":    _h._handle_chart_price,
    "balance":        _h._handle_balance,
    "buy_intent":     _h._handle_buy_intent,
    "sell_intent":    _h._handle_sell_intent,
    "invest_advice":  _h._handle_invest_advice,
    "stock_compare":  _h._handle_stock_compare,
    "exchange_order": _h._handle_exchange_order,
    "market_summary": _h._handle_market_summary,
    "korea_summary":  _h._handle_korea_summary,
    "us_summary":     _h._handle_us_summary,
    "stock_news":     _h._handle_stock_news,
    "portfolio":      _h._handle_portfolio,
    "trades":         _h._handle_trades,
    "unknown":        _h._handle_unknown,
}


def dispatch(intent: str, params: dict, user_context: dict, original_message: str = "") -> dict:
    handler = _HANDLERS.get(intent, _h._handle_unknown)
    return handler(params, user_context, original_message)


# ── 라우팅 보조 상수 ──────────────────────────────────────────────────────────

# 명확한 의도 키워드 (이게 있으면 router가 처리, shortcut 패스)
INTENT_KW: frozenset[str] = frozenset({
    "현재가", "시세", "주가", "차트", "뉴스", "기사", "소식", "순위", "랭킹",
    "환율", "잔고", "지수", "시황", "매수", "매도", "매매", "주문", "환전", "얼마", "가격",
})

# 종목명 only 패턴 — 의도 키워드 없이 종목명(+조사)만 있는 경우
_STOCK_ONLY_STRIP_RE = re.compile(r"[?은는이가도요\s]+$")

# 직전 tool → shortcut 대상
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

# 매수·매도 투자 추천 요청 패턴
_INVEST_ADVICE_RE = re.compile(
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

# 시세/뉴스 intent 키워드 — 제거 후 남은 토큰으로 사용자가 종목을 지정했는지 판단
_PRICE_INTENT_WORDS_RE = re.compile(
    r"시세|주가|현재가|가격|얼마|알려줘|알려줘요|봐줘|보여줘|조회|확인|어때|어떄"
    r"|현재|지금|오늘|뉴스|소식|기사|최근|최신"
)


def _has_explicit_stock_token(message: str) -> bool:
    """intent 키워드를 제거한 뒤 종목처럼 보이는 토큰이 남아 있으면 True."""
    cleaned = _PRICE_INTENT_WORDS_RE.sub("", message).strip()
    cleaned = re.sub(r"[?!.은는이가도요\s]+", "", cleaned)
    return bool(cleaned)


# ── shortcut ──────────────────────────────────────────────────────────────────

def try_shortcut(
    message: str,
    account_id: str,
    session_since: float | None = None,
) -> dict | None:
    """
    종목명만 있는 짧은 메시지 + 직전 응답이 price/news/order인 경우
    LLM 없이 바로 해당 동작을 재실행합니다.
    """
    msg = message.strip()

    if any(kw in msg for kw in INTENT_KW):
        return None

    code, name = resolve_from_csv(_normalize_message(msg))
    if not code:
        base = _STOCK_ONLY_STRIP_RE.sub("", msg)
        if not base:
            return None
        code, name = resolve_from_csv(_normalize_message(base))
    if not code:
        return None

    # 종목명 외 다른 내용이 있으면 bypass
    # (종목명 자체가 '이'로 끝나는 경우를 위해 먼저 종목명을 제거한 뒤 조사를 처리)
    msg_expanded = _apply_synonyms(_normalize_message(msg))
    remaining = msg_expanded.lower().replace(name.lower(), "").strip()
    remaining_stripped = _STOCK_ONLY_STRIP_RE.sub("", remaining)
    if remaining_stripped.strip():
        return None

    try:
        from app.db.mongo import get_chat_history
        history = get_chat_history(account_id, limit=4, since=session_since)
    except Exception:
        return None

    # 세션 내 tool_call 없음 → 어떤 정보를 원하는지 안내
    if not any(m.get("tool_calls") for m in history):
        return {
            "reply": (
                f"**{name}**에 대해 어떤 정보를 원하시나요?\n"
                f"예) {name} 현재가  /  {name} 뉴스  /  {name} 매수"
            )
        }

    # 직전 assistant가 주문 UI였으면 주문 단축키
    for m in reversed(history):
        if m.get("role") == "assistant":
            if "주문 정보를 입력하세요:" in m.get("content", ""):
                return {
                    "type":       "order",
                    "reply":      f"**{name}** 주문 정보를 입력하세요:",
                    "stock_code": code,
                }
            break

    # price/news tool 단축키
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
        tool_ctx = _h._get_tool_context("get_stock_price", {"stock_code": code}, data)
        card_data = {
            "stock_code":    data.get("stock_code") or code,
            "stock_name":    data.get("stock_name", name),
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

    if last_tool == "get_stock_news":
        data = get_market_summary(type="stock_news", stock_code=code)
        if isinstance(data, dict) and data.get("error"):
            return None
        if not data.get("stock_name"):
            data = {**data, "stock_name": name}
        tool_ctx = _h._get_tool_context("get_stock_news", {"stock_code": code}, data)
        return {
            "reply": format_stock_news(data),
            "_tool_context": tool_ctx,
            "_is_template": bool(data.get("news")),
        }

    return None


# ── pre_dispatch ──────────────────────────────────────────────────────────────

def pre_dispatch(
    intent: str,
    params: dict,
    message: str,
    account_id: str,
    session_since: float | None = None,
) -> tuple[str, dict]:
    """
    router.detect()가 반환한 (intent, params)를 문맥 기반으로 보정합니다.

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

    # "보유 종목 중 가장 많이 오른 건?" → 항상 agent
    if intent in ("ranking", "chart_price", "unknown") and _PORTFOLIO_COMPARISON_RE.search(message):
        intent = "unknown"

    # 종목 비교 질문 처리
    if intent in ("ranking", "chart_price", "unknown") and _COMPARISON_RE.search(message):
        if not _PORTFOLIO_COMPARISON_RE.search(message) and "보유" not in message:
            try:
                all_stocks = resolve_all_from_csv(_normalize_message(message))
                if len(all_stocks) >= 2:
                    intent = "stock_compare"
                    params = {**params, "stock_codes": all_stocks}
                elif _has_recent_price_context(account_id, session_since):
                    intent = "unknown"
            except Exception:
                if _has_recent_price_context(account_id, session_since):
                    intent = "unknown"
        else:
            intent = "unknown"

    # 매수·매도 intent인데 추천 질문 형태 → invest_advice 안내
    if intent in ("buy_intent", "sell_intent", "unknown") and _INVEST_ADVICE_RE.search(message):
        intent = "invest_advice"

    # 시세/뉴스 intent인데 종목 미지정
    if intent in ("chart_price", "stock_news") and not params.get("stock_code"):
        if _has_explicit_stock_token(message):
            params = {**params, "stock_not_found": True}
        else:
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
