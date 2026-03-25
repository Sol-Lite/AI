"""
도구 4: execute_order - Spring API 연동 (주문 실행: 매수/매도/환전)
"""
import uuid
from datetime import date
from typing import Literal

import httpx

from app.core.config import SPRING_BASE_URL


def execute_order(
    type: Literal["buy", "sell", "exchange"],
    user_context: dict,
    stock_code: str | None = None,
    market: str | None = None,
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
        user_context: 세션에서 주입된 {"user_id": ..., "account_id": ..., "token": ...}
        stock_code: 종목코드 또는 종목명 (buy/sell 시 필요)
        market: "KOSPI" | "KOSDAQ" | "NASDAQ" (buy/sell 시 필요)
        quantity: 수량 (buy/sell 시 필요)
        price: 주문가 (buy/sell 시, 생략 시 시장가)
        from_currency: 환전 출발 통화 (exchange 시)
        to_currency: 환전 도착 통화 (exchange 시)
        amount: 환전 금액 (exchange 시)
    """
    if type in ("buy", "sell"):
        return _place_stock_order(type, user_context["token"], stock_code, market, quantity, price)
    elif type == "exchange":
        return _place_fx_order(user_context["token"], from_currency, to_currency, amount)
    else:
        raise ValueError(f"Unknown type: {type}")


# ── 주식 주문 ──────────────────────────────────────────────────────────────────

def _place_stock_order(
    side: str,
    token: str,
    stock_code: str | None,
    market: str | None,
    quantity: int | None,
    price: int | None,
) -> dict:
    if not stock_code or not quantity:
        raise ValueError("stock_code와 quantity는 필수입니다.")

    order_side = "BUY" if side == "buy" else "SELL"
    order_kind = "LIMIT" if price else "MARKET"
    # LLM이 넘긴 market 우선, 없으면 코드 형태로 추론
    market_type = market or ("KOSPI" if stock_code.isdigit() else "NASDAQ")

    body = {
        "stockCode":      stock_code,
        "marketType":     market_type,
        "orderSide":      order_side,
        "orderKind":      order_kind,
        "orderChannel":   "CHAT",
        "orderPrice":     price or 0,
        "orderQuantity":  quantity,
        "idempotencyKey": str(uuid.uuid4()),
    }

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                f"{SPRING_BASE_URL}/api/orders",
                json=body,
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.RequestError as e:
        return {"error": True, "message": f"Spring 서버 연결 실패: {e}"}

    if resp.status_code not in (200, 201):
        return {"error": True, "message": f"주문 실패 ({resp.status_code}): {resp.text}"}

    data = resp.json()
    exec_price = data.get("orderPrice") or price or 0
    exec_qty   = data.get("orderQuantity") or quantity

    return {
        "order_id":     data.get("orderNo", "-"),
        "status":       "accepted",
        "stock_name":   data.get("stockName", stock_code),
        "type":         side,
        "quantity":     exec_qty,
        "price":        exec_price,
        "total_amount": exec_price * exec_qty,
    }


# ── 환전 주문 ──────────────────────────────────────────────────────────────────

_MOCK_FX_RATES = {
    ("KRW", "USD"): 1_380.5,
    ("USD", "KRW"): 1_380.5,
    ("KRW", "EUR"): 1_490.2,
    ("EUR", "KRW"): 1_490.2,
}

def _place_fx_order(
    token: str,
    from_currency: str | None,
    to_currency: str | None,
    amount: int | None,
) -> dict:
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
