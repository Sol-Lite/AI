"""
세션/대화 히스토리 분석 헬퍼

dispatcher와 handlers에서 공통으로 사용하는 세션 컨텍스트 분석 함수들.
MongoDB 대화 기록을 읽어 직전 tool 사용 패턴을 감지합니다.
"""

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
