"""
도구 4: execute_order - LS증권 API 연동 (주문 실행: 매수/매도/환전)
"""
import uuid
from datetime import date
from typing import Literal


def execute_order(
    type: Literal["buy", "sell", "exchange"],
    user_context: dict,
    stock_code: str | None = None,
    quantity: int | None = None,
    price: int | None = None,
    from_currency: str | None = None,
    to_currency: str | None = None,
    amount: int | None = None,
) -> dict:
    """
    주문을 실행합니다.

    Args:
        type: "buy" | "sell" | "exchange"
        user_context: 세션에서 주입된 {"user_id": ..., "account_id": ...}
        stock_code: 종목코드 (buy/sell 시 필요)
        quantity: 수량 (buy/sell 시 필요)
        price: 주문가 (buy/sell 시, 생략 시 시장가)
        from_currency: 환전 출발 통화 (exchange 시)
        to_currency: 환전 도착 통화 (exchange 시)
        amount: 환전 금액 (exchange 시)
    """
    account_id = user_context["account_id"]

    if type in ("buy", "sell"):
        return _place_stock_order(type, account_id, stock_code, quantity, price)
    elif type == "exchange":
        return _place_fx_order(account_id, from_currency, to_currency, amount)
    else:
        raise ValueError(f"Unknown type: {type}")


# ── 주식 주문 ──────────────────────────────────────────────────────────────────

_MOCK_STOCK_NAMES = {
    "005930": "삼성전자",
    "000660": "SK하이닉스",
    "035420": "NAVER",
    "AAPL":   "Apple",
    "NVDA":   "NVIDIA",
}

_MOCK_MARKET_PRICES = {
    "005930": 75_000,
    "000660": 195_000,
    "035420": 210_000,
    "AAPL":   225,
    "NVDA":   875,
}

def _place_stock_order(
    side: str,
    account_id: str,
    stock_code: str | None,
    quantity: int | None,
    price: int | None,
) -> dict:
    # TODO: LS증권 API CSPAT00601(국내주문)/해외주문 API 호출로 교체 (account_id 사용)
    if not stock_code or not quantity:
        raise ValueError("stock_code와 quantity는 필수입니다.")

    exec_price = price or _MOCK_MARKET_PRICES.get(stock_code, 0)
    order_id = f"ORD-{date.today().strftime('%Y%m%d')}-{uuid.uuid4().hex[:3].upper()}"

    return {
        "order_id":     order_id,
        "status":       "accepted",
        "stock_name":   _MOCK_STOCK_NAMES.get(stock_code, stock_code),
        "type":         side,
        "quantity":     quantity,
        "price":        exec_price,
        "total_amount": exec_price * quantity,
    }


# ── 환전 주문 ──────────────────────────────────────────────────────────────────

_MOCK_FX_RATES = {
    ("KRW", "USD"): 1_380.5,
    ("USD", "KRW"): 1_380.5,
    ("KRW", "EUR"): 1_490.2,
    ("EUR", "KRW"): 1_490.2,
}

def _place_fx_order(
    account_id: str,
    from_currency: str | None,
    to_currency: str | None,
    amount: int | None,
) -> dict:
    # TODO: LS증권 FX API 호출로 교체 (account_id 사용)
    if not from_currency or not to_currency or not amount:
        raise ValueError("from_currency, to_currency, amount는 필수입니다.")

    rate = _MOCK_FX_RATES.get((from_currency, to_currency), 1.0)
    if from_currency == "KRW":
        converted = round(amount / rate, 2)
    else:
        converted = round(amount * rate, 0)

    fx_order_id = f"FX-{date.today().strftime('%Y%m%d')}-{uuid.uuid4().hex[:3].upper()}"

    return {
        "fx_order_id": fx_order_id,
        "status":      "completed",
        "from":        {"currency": from_currency, "amount": amount},
        "to":          {"currency": to_currency,   "amount": converted},
        "applied_rate": rate,
    }
