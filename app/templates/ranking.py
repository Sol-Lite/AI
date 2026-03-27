"""
랭킹 응답 템플릿
"""

_SEP = "─" * 24

_RANKING_TYPE_LABEL = {
    "trading-volume": "거래량 상위",
    "trading-value":  "거래대금 상위",
    "rising":         "상승률 상위",
    "falling":        "하락률 상위",
    "market-cap":     "시가총액 상위",
}


def format_ranking(data: dict) -> str:
    """
    랭킹 조회 결과를 한국어 텍스트로 변환합니다.

    Args:
        data: Spring API /api/market/stocks/ranking 반환값
            {
                "type":   str,   # trading-volume | trading-value | rising | falling | market-cap
                "market": str,   # domestic | overseas
                "stocks": [
                    {
                        "rank":        int,
                        "stockCode":   str,
                        "name":        str,
                        "price":       int | float,
                        "changeRate":  float,   # 등락률 (%)
                        "volume":      int,     # 거래량
                        "tradingValue": int,    # 거래대금
                    },
                    ...
                ]
            }
    """
    # Spring API가 리스트를 직접 반환하는 경우 처리
    if isinstance(data, list):
        stocks       = data
        ranking_type = ""
        market       = "domestic"
    else:
        ranking_type = data.get("type", "")
        market       = data.get("market", "domestic")
        stocks       = data.get("stocks") or []
        is_default   = data.get("is_default", False)

    label        = _RANKING_TYPE_LABEL.get(ranking_type, "순위")
    market_label = "해외" if market == "overseas" else "국내"

    lines = [f"{market_label} {label} TOP 10", _SEP]
    if is_default:
        lines.append("※ 요청하신 순위 유형을 정확히 인식하지 못해 거래량 순위로 보여드립니다.")
        lines.append("")

    if not stocks:
        lines.append("데이터가 없습니다.")
        return "\n".join(lines)

    for item in stocks[:10]:
        rank        = item.get("rank") or item.get("Rank", "")
        name        = item.get("name") or item.get("stockName", item.get("stockCode", ""))
        price       = item.get("price") or item.get("currentPrice", 0)
        change_rate = item.get("changeRate") or item.get("priceChangeRate", 0)

        # sign: "2"=상승, "5"=하락, "3"=보합, 나머지는 changeRate로 판단
        api_sign = str(item.get("sign", ""))
        if api_sign == "2":
            sign = "🔺"
        elif api_sign == "5":
            sign = "🔻"
        elif float(change_rate or 0) > 0:
            sign = "🔺"
        elif float(change_rate or 0) < 0:
            sign = "🔻"
        else:
            sign = None  # 보합
        rate_str = f"{sign}{abs(float(change_rate or 0)):.2f}%" if sign else "0.00%"
        lines.append(
            f"  {rank:>2}위  {name:<12}  {float(price or 0):>10,.0f}원  {rate_str}"
        )

    return "\n".join(lines)
