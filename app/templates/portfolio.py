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


def _stock_label(stock: dict) -> tuple[str, str]:
    """best_stock/worst_stock 의 수익률 부호에 따라 (라벨, 아이콘) 반환"""
    rate = stock.get("return_rate", stock.get("return", 0))
    if isinstance(rate, str):
        is_neg = rate.startswith("-")
    else:
        is_neg = float(rate) < 0
    return ("손실 최소", "🔸") if is_neg else ("최고", "🔺")


def _worst_label(stock: dict) -> tuple[str, str]:
    rate = stock.get("return_rate", stock.get("return", 0))
    if isinstance(rate, str):
        is_neg = rate.startswith("-")
    else:
        is_neg = float(rate) < 0
    return ("최저", "🔻") if is_neg else ("수익 최소", "🔸")


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
        _bl, _bi = _stock_label(best_stock)
        block.append(f"• {_bl}  {_bi} {best_stock['name']}  {_pct(best_stock.get('return_rate', best_stock.get('return', 0)))}")
    if worst_stock:
        _wl, _wi = _worst_label(worst_stock)
        block.append(f"• {_wl}  {_wi} {worst_stock['name']}  {_pct(worst_stock.get('return_rate', worst_stock.get('return', 0)))}")
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


# ── 지표별 포커스 분석 ─────────────────────────────────────────────────────────

def _summary_returns(data: dict) -> str:
    r1, r3, r6 = data.get("return_1m", 0), data.get("return_3m", 0), data.get("return_6m", 0)
    best  = data.get("best_stock")
    worst = data.get("worst_stock")
    parts = [f"6개월 기준 {_pct(r6)}"]
    if best:
        _bl, _ = _stock_label(best)
        parts.append(f"{_bl} 종목 {best['name']} {_pct(best.get('return_rate', best.get('return', 0)))}")
    if worst:
        _wl, _ = _worst_label(worst)
        parts.append(f"{_wl} 종목 {worst['name']} {_pct(worst.get('return_rate', worst.get('return', 0)))}")
    return " / ".join(parts) + "입니다."


def _summary_sector(data: dict) -> str:
    sectors = data.get("sector_concentration", [])
    dom     = data.get("domestic_ratio", 0)
    fore    = data.get("foreign_ratio", 0)
    top = sectors[0] if sectors else None
    base = f"국내 {dom}% / 해외 {fore}% 비중"
    if top:
        base += f", 상위 섹터는 {top['sector']} {top['weight']}%"
    return base + "입니다."


def _summary_risk(data: dict) -> str:
    mdd  = data.get("mdd", 0)
    vol  = data.get("volatility", 0)
    rec  = data.get("recovery_needed", 0)
    parts = [f"MDD {mdd:.2f}%", f"일간 변동성 {vol:.2f}%"]
    if rec > 0:
        parts.append(f"회복 필요 수익률 +{rec:.2f}%")
    return " / ".join(parts) + "입니다."


def _summary_stats(data: dict) -> str:
    total  = data.get("total_trades", 0)
    win    = data.get("win_count", 0)
    sell   = data.get("loss_count", 0) + win
    rate   = round(win / sell * 100, 1) if sell > 0 else 0.0
    pf     = data.get("profit_factor", 0)
    return f"총 {total}회 거래 중 승률 {rate:.1f}%, 손익비 {pf}배입니다."


def _summary_holdings(data: dict) -> str:
    stocks = data.get("stock_concentration", [])
    count  = len(stocks)
    top    = stocks[0] if stocks else None
    base   = f"총 {count}개 종목 보유"
    if top:
        base += f", 비중 1위 {top['stock']} {top['weight']}%"
    return base + "입니다."


_METRIC_SUMMARY = {
    "returns":  _summary_returns,
    "sector":   _summary_sector,
    "risk":     _summary_risk,
    "stats":    _summary_stats,
    "holdings": _summary_holdings,
}

_METRIC_LABEL = {
    "returns":  "📈 기간별 수익률",
    "sector":   "🗂 포트폴리오 구성",
    "risk":     "⚠️ 리스크 지표",
    "stats":    "🎯 거래 통계",
    "holdings": "📋 보유 종목",
}


def format_portfolio_analysis(data: dict, metric_type: str) -> str:
    """
    특정 지표 질문에 대한 포커싱된 분석을 반환합니다.
    마지막에 수치 기반 한 줄 요약이 포함됩니다.
    """
    label   = _METRIC_LABEL.get(metric_type, "📊 포트폴리오 분석")
    sections = [f"**{label}**", _SEP]

    if metric_type == "returns":
        r1 = data.get("return_1m", 0)
        r3 = data.get("return_3m", 0)
        r6 = data.get("return_6m", 0)
        best  = data.get("best_stock")
        worst = data.get("worst_stock")
        block = []
        block.append(f"• 1개월  {_icon(r1)} {_pct(r1)}")
        block.append(f"• 3개월  {_icon(r3)} {_pct(r3)}")
        block.append(f"• 6개월  {_icon(r6)} {_pct(r6)}")
        if best:
            block.append(f"• 최고  🔺 {best['name']}  {_pct(best.get('return_rate', best.get('return', 0)))}")
        if worst:
            block.append(f"• 최저  🔻 {worst['name']}  {_pct(worst.get('return_rate', worst.get('return', 0)))}")
        sections.append("  \n".join(block))

    elif metric_type == "sector":
        sectors        = data.get("sector_concentration", [])
        stocks         = data.get("stock_concentration",  [])
        domestic_ratio = data.get("domestic_ratio", 0)
        foreign_ratio  = data.get("foreign_ratio",  0)
        block = []
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

    elif metric_type == "risk":
        unrealized_pnl  = data.get("unrealized_pnl", 0)
        realized_pnl    = data.get("realized_pnl",   0)
        mdd             = data.get("mdd", 0)
        recovery_needed = data.get("recovery_needed", 0)
        volatility      = data.get("volatility", 0)
        block = []
        block.append(f"• 평가손익  {_icon(unrealized_pnl)} {_sign(unrealized_pnl)}{unrealized_pnl:,.0f}원")
        block.append(f"• 실현손익  {_icon(realized_pnl)} {_sign(realized_pnl)}{realized_pnl:,.0f}원")
        block.append(f"• 최대 낙폭 (MDD)   {mdd:.2f}%")
        block.append(f"• 회복 필요 수익률  +{recovery_needed:.2f}%")
        block.append(f"• 일간 변동성       {volatility:.2f}%")
        sections.append("  \n".join(block))

    elif metric_type == "stats":
        total_trades = data.get("total_trades", 0)
        win_count    = data.get("win_count",    0)
        loss_count   = data.get("loss_count",   0)
        avg_win      = data.get("avg_win",  0)
        avg_loss     = data.get("avg_loss", 0)
        profit_factor = data.get("profit_factor", 0)
        block = []
        block.append(f"• 총 거래  {total_trades}회")
        block.append(f"• 수익 {win_count}회  /  손실 {loss_count}회")
        block.append(f"• 평균 수익금  +{avg_win:,.0f}원")
        block.append(f"• 평균 손실금  -{abs(avg_loss):,.0f}원")
        block.append(f"• 손익비  {profit_factor}배")
        sections.append("  \n".join(block))

    elif metric_type == "holdings":
        stocks         = data.get("stock_concentration", [])
        domestic_ratio = data.get("domestic_ratio", 0)
        foreign_ratio  = data.get("foreign_ratio",  0)
        block = []
        block.append(f"• 보유 종목 수  {len(stocks)}개")
        block.append(f"• 국내 {domestic_ratio}%  /  해외 {foreign_ratio}%")
        if stocks:
            block.append("• 종목별 비중 (상위 5)")
            for s in stocks[:5]:
                block.append(f"  　{s['stock']}  {s['weight']}%")
            if len(stocks) > 5:
                block.append("  　...")
        sections.append("  \n".join(block))

    # 한 줄 요약
    summarize = _METRIC_SUMMARY.get(metric_type)
    if summarize:
        summary = summarize(data)
        sections.append(_SEP)
        sections.append(f"**💡 요약** {summary}")
    else:
        sections.append(_SEP)

    return "\n\n".join(sections)
