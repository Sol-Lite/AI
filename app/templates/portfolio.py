"""
포트폴리오 분석 응답 템플릿
"""

_SEP = "━" * 22


def _sign(v: float) -> str:
    return "+" if v >= 0 else ""


def _pct(v: float) -> str:
    return f"{_sign(v)}{v:.2f}%"


def _icon(v: float) -> str:
    return "🔺" if v > 0 else "🔻" if v < 0 else "➖"


def format_portfolio(data: dict) -> str:
    unrealized_pnl  = data.get("unrealized_pnl", 0)
    realized_pnl    = data.get("realized_pnl",   0)
    return_1m       = data.get("return_1m", 0)
    return_3m       = data.get("return_3m", 0)
    return_6m       = data.get("return_6m", 0)
    best_stock      = data.get("best_stock")
    worst_stock     = data.get("worst_stock")

    sectors         = data.get("sector_concentration", [])
    stocks          = data.get("stock_concentration",  [])
    domestic_ratio  = data.get("domestic_ratio", 0)
    foreign_ratio   = data.get("foreign_ratio",  0)

    mdd             = data.get("mdd", 0)
    recovery_needed = data.get("recovery_needed", 0)
    volatility      = data.get("volatility", 0)
    total_trades    = data.get("total_trades", 0)
    win_count       = data.get("win_count",    0)
    loss_count      = data.get("loss_count",   0)
    avg_win         = data.get("avg_win",  0)
    avg_loss        = data.get("avg_loss", 0)
    profit_factor   = data.get("profit_factor", 0)

    sections = ["**📊 포트폴리오 분석**", _SEP]

    # ── 손익 현황 ─────────────────────────────────────────────────────────────
    block = ["**💰 손익 현황**"]
    block.append(f"• 평가손익  {_icon(unrealized_pnl)} {_sign(unrealized_pnl)}{unrealized_pnl:,.0f}원")
    block.append(f"• 실현손익  {_icon(realized_pnl)} {_sign(realized_pnl)}{realized_pnl:,.0f}원")
    sections.append("  \n".join(block))

    # ── 기간별 수익률 ─────────────────────────────────────────────────────────
    block = ["**📈 기간별 수익률**"]
    block.append(f"• 1개월  {_icon(return_1m)} {_pct(return_1m)}")
    block.append(f"• 3개월  {_icon(return_3m)} {_pct(return_3m)}")
    block.append(f"• 6개월  {_icon(return_6m)} {_pct(return_6m)}")
    if best_stock:
        block.append(f"• 최고  🔺 {best_stock['name']}  {_pct(best_stock.get('return_rate', best_stock.get('return', 0)))}")
    if worst_stock:
        block.append(f"• 최저  🔻 {worst_stock['name']}  {_pct(worst_stock.get('return_rate', worst_stock.get('return', 0)))}")
    sections.append("  \n".join(block))

    # ── 포트폴리오 구성 ───────────────────────────────────────────────────────
    block = ["**🗂 포트폴리오 구성**"]
    block.append(f"• 국내 {domestic_ratio}%  /  해외 {foreign_ratio}%")
    if sectors:
        block.append("• 섹터별 비중")
        for s in sectors:
            block.append(f"  　{s['sector']}  {s['weight']}%")
    if stocks:
        block.append("• 종목별 비중 (상위 5)")
        for s in stocks[:5]:
            block.append(f"  　{s['stock']}  {s['weight']}%")
        if len(stocks) > 5:
            block.append("  　...")
    sections.append("  \n".join(block))

    # ── 리스크 지표 ───────────────────────────────────────────────────────────
    block = ["**⚠️ 리스크 지표**"]
    block.append(f"• 최대 낙폭 (MDD)   {mdd:.2f}%")
    block.append(f"• 회복 필요 수익률  +{recovery_needed:.2f}%")
    block.append(f"• 일간 변동성       {volatility:.2f}%")
    sections.append("  \n".join(block))

    # ── 거래 통계 ─────────────────────────────────────────────────────────────
    block = ["**🎯 거래 통계**"]
    block.append(f"• 총 거래  {total_trades}회")
    block.append(f"• 수익 {win_count}회  /  손실 {loss_count}회")
    block.append(f"• 평균 수익금  +{avg_win:,.0f}원")
    block.append(f"• 평균 손실금  -{abs(avg_loss):,.0f}원")
    block.append(f"• 손익비  {profit_factor}배")
    sections.append("  \n".join(block))

    sections.append(_SEP)
    return "\n\n".join(sections)
