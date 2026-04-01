"""
거래내역 관련 응답 템플릿
"""

_SEP = "━" * 22
_SIDE_ICON = {"sell": "🔴 매도", "buy": "🔵 매수"}
_DOMESTIC_MARKETS = {"KOSPI", "KOSDAQ"}


def _is_overseas(market_type: str) -> bool:
    """국내(KOSPI/KOSDAQ)가 아니면 해외로 판별 — portfolio.py와 동일 기준"""
    return bool(market_type) and market_type.upper() not in _DOMESTIC_MARKETS


def _fmt_price(price: float, market_type: str) -> str:
    """국내 → 원, 해외 → 달러 표기"""
    if _is_overseas(market_type):
        return f"${price:,.2f}"
    return f"{price:,.0f}원"


def _fmt_amount(price: float, qty: int, market_type: str) -> str:
    if _is_overseas(market_type):
        return f"**${price * qty:,.2f}**"
    return f"**{price * qty:,.0f}원**"


def _fmt_dt(dt_str: str) -> str:
    """'2026-03-27 16:12:57.380624' → '03/27 16:12'"""
    try:
        dt = str(dt_str)
        date_part = dt[5:10].replace("-", "/")
        time_part = dt[11:16]
        return f"{date_part} {time_part}"
    except Exception:
        return str(dt_str)


def format_trades(data: dict) -> str:
    """
    전체 거래내역 요약 템플릿.
    data: {"total", "buy_count", "sell_count", "recent": [...]}
    """
    total      = data.get("total", 0)
    buy_count  = data.get("buy_count", 0)
    sell_count = data.get("sell_count", 0)
    recent     = data.get("recent", [])

    lines = ["**📋 거래내역**", _SEP]

    if total == 0:
        lines.append("아직 거래 이력이 없습니다.")
        lines.append(_SEP)
        return "  \n".join(lines)

    lines.append(f"총 **{total}건**  (🔵 매수 {buy_count}건  /  🔴 매도 {sell_count}건)")
    lines.append(_SEP)

    if recent:
        lines.append("**최근 거래내역**")
        for idx, trade in enumerate(recent, start=1):
            side  = trade.get("side", "buy")
            label = _SIDE_ICON.get(side, "🔵 매수")
            name  = trade.get("stock_name", "-")
            price = trade.get("price", 0)
            qty   = trade.get("quantity", 0)
            mtype = trade.get("market_type", "")
            dt    = _fmt_dt(trade.get("executed_at", ""))

            lines.append(
                f"{idx}. {label}  \n"
                f"　　**{name}**  {dt}  \n"
                f"　　{_fmt_price(price, mtype)} × {qty}주 = {_fmt_amount(price, qty, mtype)}"
            )

    lines.append(_SEP)
    return "  \n".join(lines)


def format_trades_by_date(data: dict) -> str:
    """
    특정 날짜 거래내역 템플릿.
    data: {"date", "count", "trades": [...]}
    """
    date   = data.get("date", "")
    count  = data.get("count", 0)
    trades = data.get("trades", [])

    try:
        parts = date.split("-")
        date_label = f"{int(parts[1])}월 {int(parts[2])}일"
    except Exception:
        date_label = date

    lines = [f"**📋 {date_label} 거래내역**", _SEP]

    if count == 0:
        lines.append(f"{date_label}에 체결된 거래가 없습니다.")
        lines.append(_SEP)
        return "  \n".join(lines)

    sell_count = sum(1 for t in trades if t.get("side") == "sell")
    buy_count  = count - sell_count

    lines.append(f"총 **{count}건**  (🔵 매수 {buy_count}건  /  🔴 매도 {sell_count}건)")
    lines.append(_SEP)

    for idx, t in enumerate(trades, start=1):
        side  = t.get("side", "buy")
        label = _SIDE_ICON.get(side, "🔵 매수")
        name  = t.get("stock_name", "-")
        price = t.get("price", 0)
        qty   = t.get("quantity", 0)
        mtype = t.get("market_type", "")
        dt    = _fmt_dt(t.get("executed_at", ""))
        lines.append(
            f"{idx}. {label}  \n"
            f"　　**{name}**  {dt}  \n"
            f"　　{_fmt_price(price, mtype)} × {qty}주 = {_fmt_amount(price, qty, mtype)}"
        )

    lines.append(_SEP)
    return "  \n".join(lines)


def format_trades_by_stock(data: dict) -> str:
    """
    특정 종목 거래내역 템플릿 (대화체).
    data: {"stock_name", "count", "trades": [...]}
    """
    name   = data.get("stock_name") or data.get("stock_code", "-")
    count  = data.get("count", 0)
    trades = data.get("trades", [])

    if count == 0:
        return f"{name} 거래 이력이 없어요."

    lines = [f"**{name}** 거래내역이에요. (총 {count}건)"]

    mtype_stock = data.get("market_type", "")
    for idx, t in enumerate(trades[:5], start=1):
        side  = t.get("side", "buy")
        label = _SIDE_ICON.get(side, "🔵 매수")
        price = t.get("price", 0)
        qty   = t.get("quantity", 0)
        mtype = t.get("market_type", mtype_stock)
        dt    = _fmt_dt(t.get("executed_at", ""))
        lines.append(
            f"{idx}. {label}  \n"
            f"　　{dt}  /  {_fmt_price(price, mtype)} × {qty}주"
        )

    if count > 5:
        lines.append(f"외 {count - 5}건 더 있어요.")

    return "  \n".join(lines)
