"""
잔고
"""
def format_balance(data: dict) -> str:
    """
    잔고 조회 결과를 사용자 친화적 텍스트로 변환합니다.

    Args:
        data: _query_balance() 반환값
            {
                "krw_available": float,
                "krw_total":     float,
                "usd_available": float,
                "usd_total":     float,
            }
    """
    krw_available = data.get("krw_available", 0)
    krw_total     = data.get("krw_total", 0)
    usd_available = data.get("usd_available", 0)
    usd_total     = data.get("usd_total", 0)

    lines = ["계좌잔고\n"]

    lines.append("원화 (KRW)")
    lines.append(f"  • 총 자산:       {krw_total:>15,.0f} 원")
    lines.append(f"  • 주문/출금 가능:     {krw_available:>15,.0f} 원")

    if usd_total > 0 or usd_available > 0:
        lines.append("")
        lines.append("달러 (USD)")
        lines.append(f"  • 총 자산:       {usd_total:>15,.2f} USD")
        lines.append(f"  • 주문/출금 가능:     {usd_available:>15,.2f} USD")

    return "\n".join(lines)
