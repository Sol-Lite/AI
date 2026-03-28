"""
잔고
"""

_SEP = "━" * 22


def format_balance(data: dict, balance_type: str = "summary") -> str:
    """
    잔고 조회 결과를 사용자 친화적 텍스트로 변환합니다.

    Args:
        data: Spring API /api/balance/summary 반환값
            {
                "totalCashKrw":                      float,
                "totalStockBuyAmount":                float,
                "totalStockEvaluation":               float,
                "totalStockUnrealizedProfitLoss":     float,
                "totalStockUnrealizedProfitLossRate": float,
                "totalAssets":                        float,
                "accountProfitLoss":                  float,
                "accountProfitLossRate":              float,
                "cashBalances": [
                    {"currencyCode": str, "availableAmount": float, "totalAmount": float}
                ],
                "holdingCount": int,
            }
    """
    if data.get("error"):
        return "잔고 데이터를 불러올 수 없습니다. 잠시 후 다시 시도해 주세요."

    total_assets = float(data.get("totalAssets")  or 0)
    total_cash   = float(data.get("totalCashKrw") or 0)

    if balance_type == "total_assets":
        return f"**총 자산**\n{_SEP}\n💰 {total_assets:,.0f} 원"

    if balance_type == "cash":
        return f"**현금 잔고**\n{_SEP}\n💵 {total_cash:,.0f} 원"

    # summary (기본값)
    lines = [
        "**내 계좌 요약**",
        _SEP,
        f"총 자산:          {total_assets:>15,.0f} 원",
        f"현금 잔고:        {total_cash:>15,.0f} 원",
    ]
    return "  \n".join(lines)
