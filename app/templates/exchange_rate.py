"""
환율 응답 템플릿
"""

_SEP = "─" * 24

_PAIR_LABEL = {
    "USDKRW": "달러/원 (USD/KRW)",
    "EURKRW": "유로/원 (EUR/KRW)",
    "JPYKRW": "엔/원  (JPY/KRW)",
    "GBPKRW": "파운드/원 (GBP/KRW)",
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
            }
    """
    pair   = data.get("currency_pair", "USDKRW")
    rate   = float(data.get("rate") or 0)
    change = float(data.get("change") or 0)

    label = _PAIR_LABEL.get(pair, pair)

    if change > 0:
        sign = "▲"
    elif change < 0:
        sign = "▼"
    else:
        sign = "-"

    lines = [
        f"■ 환율  {label}",
        _SEP,
        f"  현재   {rate:>10,.2f}원",
    ]

    if change:
        lines.append(f"  등락   {sign}{abs(change):,.2f}원")

    return "\n".join(lines)
