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

from app.hardcoding.get_market_data import get_market_data
from app.hardcoding.get_market_summary import get_market_summary
from app.hardcoding.get_balance_data import get_db_data
from app.templates.index import format_index
from app.templates.ranking import format_ranking
from app.templates.chart_price import format_chart_price
from app.templates.exchange_rate import format_exchange_rate
from app.templates.account import format_balance
from app.templates.stock_news import format_korea_summary, format_us_summary, format_stock_news

_UNKNOWN_REPLY = (
    "죄송합니다, 요청을 정확히 이해하지 못했어요.\n"
    "아래 기능을 이용해 보세요:\n"
    "  • 지수 조회 (코스피, 코스닥, 나스닥 등)\n"
    "  • 환율 조회 (달러, 유로, 엔화)\n"
    "  • 주식 순위 조회 (거래량, 상승률 등)\n"
    "  • 종목 시세/차트 조회\n"
    "  • 잔고 조회\n"
    "  • 매수 / 매도\n"
    "  • 환전\n"
    "  • 한국/미국 시황 요약\n"
    "  • 종목별 뉴스 요약"
)


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
    if not stock_code:
        return {"reply": "어떤 종목의 시세를 조회할까요? 종목명이나 코드를 알려주세요.\n예) 삼성전자 시세, 005930 주가"}
    data = get_market_data(type="price", stock_code=stock_code)
    if isinstance(data, dict) and data.get("error"):
        if data.get("error") == "not_found":
            return {"reply": f"'{stock_code}' 종목을 찾을 수 없습니다. 종목명을 다시 확인해 주세요."}
        return {"reply": "시세 데이터를 불러올 수 없습니다. 잠시 후 다시 시도해 주세요."}
    return {"reply": format_chart_price(data)}


def _handle_balance(params: dict, user_context: dict, message: str) -> dict:
    data = get_db_data(type="balance", user_context=user_context)
    if isinstance(data, dict) and data.get("error"):
        return {"reply": "잔고 조회에 실패했습니다. 잠시 후 다시 시도해 주세요."}
    return {"reply": format_balance(data)}


def _handle_buy_intent(params: dict, user_context: dict, message: str) -> dict:
    stock_code = params.get("stock_code")
    if not stock_code:
        return {
            "reply": "어떤 종목을 매수하시겠어요? 종목명이나 코드를 알려주세요.\n예) 삼성전자 매수, 005930 사고 싶어",
        }
    resolved = _resolve_code(stock_code)
    display = resolved or stock_code
    return {
        "reply": f"{display} 매수 주문 화면을 활성화합니다.",
        "action": "activate_buy",
        "action_params": {"stock_code": resolved or stock_code},
    }


def _handle_sell_intent(params: dict, user_context: dict, message: str) -> dict:
    stock_code = params.get("stock_code")
    if not stock_code:
        return {
            "reply": "어떤 종목을 매도하시겠어요? 종목명이나 코드를 알려주세요.\n예) 삼성전자 매도, 005930 팔고 싶어",
        }
    resolved = _resolve_code(stock_code)
    display = resolved or stock_code
    return {
        "reply": f"{display} 매도 주문 화면을 활성화합니다.",
        "action": "activate_sell",
        "action_params": {"stock_code": resolved or stock_code},
    }


def _handle_exchange_order(params: dict, user_context: dict, message: str) -> dict:
    return {
        "reply": "환전 화면을 활성화합니다.",
        "action": "activate_exchange",
        "action_params": {},
    }


def _handle_korea_summary(params: dict, user_context: dict, message: str) -> dict:
    data = get_market_summary(type="korea")
    return {"reply": format_korea_summary(data)}


def _handle_us_summary(params: dict, user_context: dict, message: str) -> dict:
    data = get_market_summary(type="us")
    return {"reply": format_us_summary(data)}


def _handle_stock_news(params: dict, user_context: dict, message: str) -> dict:
    stock_code = params.get("stock_code")
    if not stock_code:
        return {"reply": "어떤 종목의 뉴스를 조회할까요? 종목명이나 코드를 알려주세요.\n예) 삼성전자 뉴스, AAPL 기사"}
    data = get_market_summary(type="stock_news", stock_code=stock_code)
    if isinstance(data, dict) and data.get("error"):
        return {"reply": data["error"]}
    return {"reply": format_stock_news(data)}


def _handle_trades(params: dict, user_context: dict, message: str) -> dict:
    from app.agent.trade_tool import get_trade_data
    from app.agent.llm_agent import is_complex_query, ask_trades
    from app.templates.trades import format_trades

    data = get_trade_data(user_context)
    if isinstance(data, dict) and data.get("error"):
        return {"reply": "거래내역 조회에 실패했습니다. 잠시 후 다시 시도해 주세요."}

    if is_complex_query(message):
        return {"reply": ask_trades(data, message)}
    return {"reply": format_trades(data)}


def _handle_portfolio(params: dict, user_context: dict, message: str) -> dict:
    from app.agent.portfolio_tool import get_portfolio_data
    from app.agent.llm_agent import is_complex_query, ask_portfolio
    from app.templates.portfolio import format_portfolio

    data = get_portfolio_data(user_context)
    if isinstance(data, dict) and data.get("error"):
        return {"reply": "포트폴리오 조회에 실패했습니다. 잠시 후 다시 시도해 주세요."}

    if is_complex_query(message):
        return {"reply": ask_portfolio(data, message)}
    return {"reply": format_portfolio(data)}


def _handle_unknown(params: dict, user_context: dict, message: str) -> dict:
    return {"reply": _UNKNOWN_REPLY}


# ── 핸들러 매핑 테이블 ────────────────────────────────────────────────────────

_HANDLERS = {
    "index":          _handle_index,
    "exchange_rate":  _handle_exchange_rate,
    "ranking":        _handle_ranking,
    "chart_price":    _handle_chart_price,
    "balance":        _handle_balance,
    "buy_intent":     _handle_buy_intent,
    "sell_intent":    _handle_sell_intent,
    "exchange_order": _handle_exchange_order,
    "korea_summary":  _handle_korea_summary,
    "us_summary":     _handle_us_summary,
    "stock_news":     _handle_stock_news,
    "trades":         _handle_trades,
    "portfolio":      _handle_portfolio,
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
