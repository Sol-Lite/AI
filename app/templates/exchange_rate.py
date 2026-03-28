"""
환율 응답 템플릿
"""

_SEP = "━" * 22

_PAIR_META = {
    "USDKRW": ("달러/원",   "USD", "💵"),
    "EURKRW": ("유로/원",   "EUR", "💶"),
    "JPYKRW": ("엔/원",     "JPY", "💴"),
    "GBPKRW": ("파운드/원", "GBP", "💷"),
}


def format_exchange_rate(data: dict) -> str:
    """
    환율 조회 결과를 사용자 친화적 텍스트로 변환합니다.

    Args:
        data: get_market_data(type="exchange") 반환값
            {
                "currency_pair": str,    # 예: "USDKRW"
                "rate":          float,  # 현재 환율 (원 기준)
                "change":        float,  # 전일 대비 변화량
                "change_rate":   float,  # 전일 대비 변화율 (%)
            }
    """
    pair        = data.get("currency_pair", "USDKRW")
    rate        = float(data.get("rate")        or 0)
    change      = float(data.get("change")      or 0)
    change_rate = float(data.get("change_rate") or 0)

    label, unit, emoji = _PAIR_META.get(pair, ("환율", pair[:3], "💱"))

    if change > 0:
        sign, arrow = "+", "🔺"
    elif change < 0:
        sign, arrow = "",  "🔻"
    else:
        sign, arrow = "",  "-"

    if not rate:
        return f"**{label}**\n{_SEP}\n환율 데이터를 불러올 수 없습니다."

    # JPY는 100엔 기준으로 표시
    if pair == "JPYKRW":
        forward_str = f"100 {unit}  →  **{rate * 100:,.2f} 원**"
        reverse_str = f"1,000 원  →  **{1000 / rate:.2f} {unit}**"
    else:
        forward_str = f"1 {unit}  →  **{rate:,.2f} 원**"
        reverse_str = f"1,000 원  →  **{1000 / rate:.4f} {unit}**"

    change_str = (
        f"전일 대비  {arrow} {abs(change):,.2f}원  ({sign}{abs(change_rate):.2f}%)"
        if change else ""
    )

    lines = [f"{emoji} **{label}**", _SEP, forward_str, reverse_str]
    if change_str:
        lines.append(change_str)

    return "  \n".join(lines)
