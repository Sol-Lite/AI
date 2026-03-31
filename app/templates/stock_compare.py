"""
종목 간 등락률/등락폭 비교 응답 템플릿
"""


def _josa(name: str, josa_pair: tuple[str, str]) -> str:
    """받침 유무에 따라 조사 반환. josa_pair: (받침O, 받침X) 예) ("이", "가")"""
    if not name:
        return josa_pair[0]
    code = ord(name[-1])
    if 0xAC00 <= code <= 0xD7A3:
        has_batchim = (code - 0xAC00) % 28 != 0
    else:
        has_batchim = False
    return josa_pair[0] if has_batchim else josa_pair[1]


def format_stock_compare(stocks: list[dict]) -> str:
    """
    Args:
        stocks: [{"stock_name": str, "current_price": float, "change": float, "change_rate": float, "currency": str}, ...]
    """
    if not stocks:
        return "비교할 종목 데이터를 불러오지 못했어요."

    def _fmt_price(p, currency="KRW"):
        if currency == "USD":
            return f"${float(p):,.2f}"
        return f"{float(p):,.0f}원"

    def _icon(rate):
        r = float(rate or 0)
        return "🔺" if r > 0 else ("🔻" if r < 0 else "-")

    lines = []
    for s in stocks:
        name   = s.get("stock_name") or s.get("stock_code", "-")
        price  = float(s.get("current_price") or 0)
        change = float(s.get("change") or 0)
        rate   = float(s.get("change_rate") or 0)
        cur    = s.get("currency", "KRW")
        icon   = _icon(rate)
        r_sign = "+" if rate > 0 else ""
        lines.append(
            f"**{name}** {_fmt_price(price, cur)}  "
            f"{icon} {_fmt_price(abs(change), cur)} ({r_sign}{rate:.2f}%)"
        )

    # 등락률 기준 정렬 결과 요약
    ranked   = sorted(stocks, key=lambda s: float(s.get("change_rate") or 0), reverse=True)
    top      = ranked[0]
    top_name = top.get("stock_name") or top.get("stock_code", "-")
    top_rate = float(top.get("change_rate") or 0)

    summary = ""
    if len(ranked) >= 2:
        bottom      = ranked[-1]
        bottom_name = bottom.get("stock_name") or bottom.get("stock_code", "-")
        bottom_rate = float(bottom.get("change_rate") or 0)

        if top_rate > 0 and bottom_rate >= 0:
            ji = _josa(top_name, ("이", "가"))
            summary = f"\n오늘은 **{top_name}**{ji} {top_rate:+.2f}%로 가장 많이 올랐어요."
        elif top_rate <= 0 and bottom_rate < 0:
            ji = _josa(bottom_name, ("이", "가"))
            summary = f"\n오늘은 **{bottom_name}**{ji} {bottom_rate:.2f}%로 가장 많이 내렸어요."
        else:
            ji = _josa(top_name, ("이", "가"))
            summary = f"\n등락률 기준으로 **{top_name}**{ji} {top_rate:+.2f}%로 가장 높아요."

    return "  \n".join(lines) + summary
