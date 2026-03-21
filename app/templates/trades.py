"""
거래내역 관련 응답 템플릿
"""
def format_trades(data: dict) -> str:
    """
    거래내역 조회 결과를 사용자 친화적 텍스트로 변환합니다.

    Args:
        data: _query_trades() 반환값
            {
                "total":      int,
                "buy_count":  int,
                "sell_count": int,
                "recent": [
                    {"stock_name": str, "side": str, "price": int,
                     "quantity": int, "executed_at": str},
                    ...
                ]
            }
    """
    total      = data.get("total", 0)
    buy_count  = data.get("buy_count", 0)
    sell_count = data.get("sell_count", 0)
    recent     = data.get("recent", [])

    lines = ["거래내역\n"]

    if total == 0:
        lines.append("아직 거래 이력이 없습니다.")
        return "\n".join(lines)
    
    if not recent:
        lines.append("\n최근 체결 내역을 불러올 수 없습니다.")
        return "\n".join(lines)
    
    lines.append(f"총 거래 횟수: {total}건  (매수 {buy_count}건 / 매도 {sell_count}건)")
    lines.append("\n최근 거래내역")
    for idx, trade in enumerate(recent, start=1):
        side_label = "매도" if trade.get("side") == "sell" else "매수"
        price    = trade.get("price", 0)
        quantity = trade.get("quantity", 0)
        amount   = price * quantity

        lines.append(
            f"\n{idx}. [{side_label}] {trade.get('stock_name', '-')}\n"
            f"   {price:,.0f}원 × {quantity}주 = {amount:,.0f}원\n"
            f"   체결일: {trade.get('executed_at', '-')}"
        )

    lines.append("\n※ 안내: 최근 체결 기준 내역이며, 주문 상태/체결 수수료 반영 시점에 따라 앱 표시와 차이가 날 수 있습니다.")

    return "\n".join(lines)
