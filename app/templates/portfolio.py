"""
포트폴리오 분석 응답 템플릿
"""

_SEP = "─" * 24


def _sign(v: float) -> str:
    return "+" if v >= 0 else ""


def format_portfolio(data: dict) -> str:
    # ── 수익률 ────────────────────────────────────────────────────────────────
    unrealized_pnl  = data.get("unrealized_pnl", 0)
    realized_pnl    = data.get("realized_pnl",   0)
    return_1m       = data.get("return_1m", 0)
    return_3m       = data.get("return_3m", 0)
    return_6m       = data.get("return_6m", 0)
    best_stock      = data.get("best_stock")
    worst_stock     = data.get("worst_stock")

    # ── 집중도 ────────────────────────────────────────────────────────────────
    sectors         = data.get("sector_concentration", [])
    stocks          = data.get("stock_concentration",  [])
    domestic_ratio  = data.get("domestic_ratio", 0)
    foreign_ratio   = data.get("foreign_ratio",  0)

    # ── 리스크 ────────────────────────────────────────────────────────────────
    mdd             = data.get("mdd", 0)
    recovery_needed = data.get("recovery_needed", 0)
    volatility      = data.get("volatility", 0)
    total_trades    = data.get("total_trades", 0)
    win_count       = data.get("win_count",    0)
    loss_count      = data.get("loss_count",   0)
    avg_win         = data.get("avg_win",  0)
    avg_loss        = data.get("avg_loss", 0)
    profit_factor   = data.get("profit_factor", 0)

    lines = [
        "포트폴리오 분석 리포트",
        _SEP,
    ]

    # ── 수익률 섹션 ───────────────────────────────────────────────────────────
    lines.append("수익률")
    lines.append(f"  평가손익   {_sign(unrealized_pnl)}{unrealized_pnl:,.0f}원")
    lines.append(f"  실현손익   {_sign(realized_pnl)}{realized_pnl:,.0f}원")
    lines.append(
        f"  1개월 {_sign(return_1m)}{return_1m}%"
        f"   3개월 {_sign(return_3m)}{return_3m}%"
        f"   6개월 {_sign(return_6m)}{return_6m}%"
    )
    if best_stock:
        lines.append(f"  최고  {best_stock['name']}  {_sign(best_stock['return'])}{best_stock['return']}%")
    if worst_stock:
        lines.append(f"  최저  {worst_stock['name']}  {_sign(worst_stock['return'])}{worst_stock['return']}%")

    # ── 집중도 섹션 ───────────────────────────────────────────────────────────
    lines.append(_SEP)
    lines.append("집중도")
    lines.append(f"  국내 {domestic_ratio}%   해외 {foreign_ratio}%")
    if sectors:
        lines.append("  섹터")
        for s in sectors:
            lines.append(f"    {s['sector']:<8} {s['weight']}%")
    if stocks:
        lines.append("  종목")
        for s in stocks[:5]:
            lines.append(f"    {s['stock']:<10} {s['weight']}%")
        if len(stocks) > 5:
            lines.append("    ...")

    # ── 리스크 섹션 ───────────────────────────────────────────────────────────
    lines.append(_SEP)
    lines.append("리스크")
    lines.append(f"  최대 낙폭    {mdd}%")
    lines.append(f"  회복 필요    +{recovery_needed}%")
    lines.append(f"  일간 변동폭  {volatility}%")
    lines.append(f"  거래 {total_trades}회   수익 {win_count}회 / 손실 {loss_count}회")
    lines.append(f"  평균 수익  +{avg_win:,.0f}원")
    lines.append(f"  평균 손실  -{abs(avg_loss):,.0f}원")
    lines.append(f"  손익비     {profit_factor}배")
    lines.append(_SEP)

    return "\n".join(lines)
