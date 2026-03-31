"""
잔고 응답 템플릿 (대화체)
"""

_SEP = "━" * 22


def _parse_cash_balances(data: dict) -> dict[str, float]:
    """cashBalances 배열에서 currencyCode별 totalAmount를 추출합니다."""
    result = {}
    for entry in data.get("cashBalances") or []:
        code = (entry.get("currencyCode") or "").upper()
        if code:
            result[code] = float(entry.get("totalAmount") or 0)
    return result


def format_balance(data: dict, balance_type: str = "summary") -> str:
    if data.get("error"):
        return "잔고 데이터를 불러올 수 없습니다. 잠시 후 다시 시도해 주세요."

    total_assets = float(data.get("totalAssets")  or 0)
    cash_map     = _parse_cash_balances(data)
    krw          = cash_map.get("KRW", float(data.get("totalCashKrw") or 0))
    usd          = cash_map.get("USD", 0.0)

    if balance_type == "krw":
        return f"**💰 보유 원화**\n\n{_SEP}\n\n원화(KRW) 잔고는 **{krw:,.0f}원**이에요."

    if balance_type == "usd":
        return f"**💵 보유 달러**\n\n{_SEP}\n\n달러(USD) 잔고는 **${usd:,.2f}**이에요."

    if balance_type == "cash":
        lines = [f"**💰 현금 잔고**\n\n{_SEP}\n"]
        lines.append(f"- 원화(KRW): **{krw:,.0f}원**")
        if usd:
            lines.append(f"- 달러(USD): **${usd:,.2f}**")
        return "\n".join(lines)

    if balance_type == "total_assets":
        return f"**💰 총 자산**\n\n{_SEP}\n\n총 자산은 **{total_assets:,.0f}원**이에요."

    # summary (기본값) — 총 자산 + 통화별 현금 잔고
    lines = [f"**💰 내 잔고**\n\n{_SEP}\n", f"총 자산은 **{total_assets:,.0f}원**이에요."]
    lines.append(f"- 원화(KRW): **{krw:,.0f}원**")
    if usd:
        lines.append(f"- 달러(USD): **${usd:,.2f}**")
    return "\n".join(lines)
