"""
차트+시세 응답 템플릿
"""

_SEP = "─" * 24


def format_chart_price(data: dict) -> str:
    """
    시세 조회 결과를 사용자 친화적 텍스트로 변환합니다.

    Args:
        data: get_market_data(type="price") 반환값
            {
                "stock_name":    str,
                "stock_code":    str,
                "current_price": int | float,
                "change":        int | float,   # 전일 대비 변화량
                "change_rate":   float,          # 전일 대비 변화율 (%)
                "open":          int | float,
                "high":          int | float,
                "low":           int | float,
                "volume":        int,
            }
    """
    stock_name  = data.get("stock_name") or data.get("stock_code", "-")
    current     = float(data.get("current_price") or 0)
    change      = float(data.get("change") or 0)
    change_rate = float(data.get("change_rate") or 0)
    open_price  = float(data.get("open") or 0)
    high        = float(data.get("high") or 0)
    low         = float(data.get("low") or 0)
    volume      = int(data.get("volume") or 0)

    if change > 0:
        sign = "▲"
    elif change < 0:
        sign = "▼"
    else:
        sign = "-"

    lines = [
        f"■ {stock_name} 시세",
        _SEP,
        f"  현재가  {current:>12,.0f}원",
        f"  등락    {sign}{abs(change):,.0f}원  ({sign}{abs(change_rate):.2f}%)",
    ]

    if open_price or high or low:
        lines += [
            _SEP,
            f"  시가    {open_price:>12,.0f}원",
            f"  고가    {high:>12,.0f}원",
            f"  저가    {low:>12,.0f}원",
        ]

    if volume:
        lines += [
            _SEP,
            f"  거래량  {volume:>12,}주",
        ]

    return "\n".join(lines)
