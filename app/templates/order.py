"""
주문 완료 응답 템플릿 (매수 / 매도 / 환전)
"""


def format_order(data: dict) -> str:
    """
    주문 실행 결과를 사용자 친화적 완료 메시지로 변환합니다.

    Args:
        data: execute_order() 반환값
            매수/매도:
            {
                "order_id":     str,   # 주문 번호 (예: "ORD-20260321-A3F")
                "status":       str,   # "accepted"
                "stock_name":   str,   # 종목명 (예: "삼성전자")
                "type":         str,   # "buy" | "sell"
                "quantity":     int,   # 수량
                "price":        int,   # 체결가
                "total_amount": int,   # 총 체결금액
            }
            환전:
            {
                "fx_order_id":  str,   # 환전 주문 번호 (예: "FX-20260321-B7C")
                "status":       str,   # "completed"
                "from":         {"currency": str, "amount": int | float},
                "to":           {"currency": str, "amount": int | float},
                "applied_rate": float, # 적용 환율
            }
    """
    if "fx_order_id" in data:
        return _format_exchange(data)
    return _format_stock_order(data)


def _format_stock_order(data: dict) -> str:
    order_id     = data.get("order_id", "-")
    stock_name   = data.get("stock_name", "-")
    order_type   = data.get("type", "")
    quantity     = int(data.get("quantity") or 0)
    price        = float(data.get("price") or 0)
    total_amount = float(data.get("total_amount") or 0)

    type_label = "매수" if order_type == "buy" else "매도"

    return (
        f"{stock_name} {quantity}주 {type_label} 주문이 완료되었습니다.\n"
        f"체결가 {price:,.0f}원\n"
        f"총 {total_amount:,.0f}원\n"
        f"주문번호 {order_id}"
    )


def _format_exchange(data: dict) -> str:
    fx_order_id  = data.get("fx_order_id", "-")
    from_info    = data.get("from", {})
    to_info      = data.get("to", {})
    applied_rate = data.get("applied_rate", 0)

    from_currency = from_info.get("currency", "")
    from_amount   = from_info.get("amount", 0)
    to_currency   = to_info.get("currency", "")
    to_amount     = to_info.get("amount", 0)

    if from_currency == "KRW":
        from_str = f"{from_amount:,.0f}원"
        to_str   = f"{to_amount:,.2f} {to_currency}"
    else:
        from_str = f"{from_amount:,.2f} {from_currency}"
        to_str   = f"{to_amount:,.0f}원"

    return (
        f"환전이 완료되었습니다.\n"
        f"{from_str}  →  {to_str}  (적용 환율 {applied_rate:,.2f})\n"
        f"주문번호 {fx_order_id}"
    )
