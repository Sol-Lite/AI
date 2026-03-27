"""
잔고
"""

_SEP = "━" * 22


def format_balance(data: dict) -> str:
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

    total_assets      = float(data.get("totalAssets")      or 0)
    total_cash        = float(data.get("totalCashKrw")     or 0)
    holding_count     = int(data.get("holdingCount")       or 0)

    stock_buy         = float(data.get("totalStockBuyAmount")                or 0)
    stock_eval        = float(data.get("totalStockEvaluation")               or 0)
    stock_pl          = float(data.get("totalStockUnrealizedProfitLoss")     or 0)
    stock_pl_rate     = float(data.get("totalStockUnrealizedProfitLossRate") or 0)

    acct_pl           = float(data.get("accountProfitLoss")     or 0)
    acct_pl_rate      = float(data.get("accountProfitLossRate") or 0)

    cash_balances     = data.get("cashBalances") or []

    def _sign(val: float) -> str:
        return "🔺" if val > 0 else "🔻" if val < 0 else "-"

    sections = ["**내 계좌 요약**", _SEP]

    # ── 자산 현황 ──
    asset_block = [
        "**💰 자산 현황**",
        f"총 자산          {total_assets:>15,.0f} 원",
        f"현금 잔고        {total_cash:>15,.0f} 원",
    ]
    sections.append("  \n".join(asset_block))

    

    # sections.append(_SEP)
    return "\n\n".join(sections)
