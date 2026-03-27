"""
환율 응답 템플릿
"""

_SEP = "━" * 22


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

    if change > 0:
        sign = "🔺"
    elif change < 0:
        sign = "🔻"
    else:
        sign = "-"

    sections = [f"**달러/원 환율**", _SEP]

    if rate:
        krw_per_usd = f"{rate:,.2f}"
        usd_per_krw = f"{1 / rate:.6f}" if rate else "-"

        sections.append(
            f"**1 USD → {krw_per_usd} 원**  \n"
            f"1 원  → {usd_per_krw} USD"
        )

        change_str = f"{sign} {abs(change):,.2f}원  ({sign}{abs(change_rate):.2f}%)" if change else ""
        if change_str:
            sections.append(f"전일 대비  {change_str}")
    else:
        sections.append("환율 데이터를 불러올 수 없습니다.")

    sections.append(_SEP)
    return "\n\n".join(sections)
