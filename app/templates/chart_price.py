"""
차트+시세 응답 템플릿 (대화체)
"""


def _fmt_volume(volume: int) -> str:
    if volume >= 10000:
        man = volume // 10000
        rem = volume % 10000
        return f"{man:,}만 {rem:,}주" if rem else f"{man:,}만 주"
    return f"{volume:,}주"


def format_chart_price(data: dict) -> str:
    stock_name  = data.get("stock_name") or data.get("stock_code", "-")
    current     = float(data.get("current_price") or 0)
    change      = float(data.get("change") or 0)
    change_rate = float(data.get("change_rate") or 0)
    open_price  = float(data.get("open") or 0)
    high        = float(data.get("high") or 0)
    low         = float(data.get("low") or 0)
    volume      = int(data.get("volume") or 0)

    if change > 0:
        icon   = "🔺"
        trend  = "올랐어요"
    elif change < 0:
        icon   = "🔻"
        trend  = "내렸어요"
    else:
        icon   = "-"
        trend  = "보합이에요"

    lines = []

    # 첫 줄: 현재가
    lines.append(f"{stock_name} 지금 **{current:,.0f}원**이에요.")

    # 둘째 줄: 등락 + OHLC
    r_sign = "+" if change_rate > 0 else ""
    change_str = f"전일보다 {icon} {abs(change):,.0f}원 ({r_sign}{change_rate:.2f}%) {trend}"
    if open_price or high or low:
        ohlc_str = f"오늘 시가 {open_price:,.0f}원 / 고가 {high:,.0f}원 / 저가 {low:,.0f}원이에요"
        lines.append(f"{change_str}.  \n{ohlc_str}.")
    else:
        lines.append(f"{change_str}.")

    # 셋째 줄: 거래량
    if volume:
        lines.append(f"거래량은 {_fmt_volume(volume)}예요.")

    return "  \n".join(lines)
