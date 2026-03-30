"""
잔고 응답 템플릿 (대화체)
"""


def format_balance(data: dict, balance_type: str = "summary") -> str:
    if data.get("error"):
        return "잔고 데이터를 불러올 수 없습니다. 잠시 후 다시 시도해 주세요."

    total_assets = float(data.get("totalAssets")  or 0)
    total_cash   = float(data.get("totalCashKrw") or 0)

    if balance_type == "cash":
        return f"현금 잔고는 **{total_cash:,.0f}원**이에요."

    if balance_type == "total_assets":
        return f"총 자산은 **{total_assets:,.0f}원**이에요."

    # summary (기본값) — 총 자산 + 현금 잔고 함께
    return (
        f"총 자산은 **{total_assets:,.0f}원**이에요.  \n"
        f"그 중 현금 잔고는 {total_cash:,.0f}원이에요."
    )
