"""
포트폴리오 분석 응답 템플릿
"""

_SEP = "━" * 22


def _sign(v) -> str:
    return "+" if (v or 0) >= 0 else ""


def _pct(v) -> str:
    if v is None:
        return "데이터 없음"
    return f"{_sign(v)}{float(v):.2f}%"


def _icon(v) -> str:
    if v is None:
        return "➖"
    return "🔺" if v > 0 else "🔻" if v < 0 else "➖"



def _return_line(label: str, icon: str, stock: dict) -> str:
    rate = stock.get("return_rate", stock.get("return", 0))
    return f"• {label}  {icon} {stock['name']}  {_pct(rate)}"


def format_portfolio(data: dict) -> str:
    unrealized_pnl  = data.get("unrealized_pnl", 0)
    return_1m  = data.get("return_1m")
    return_3m  = data.get("return_3m")
    return_6m  = data.get("return_6m")
    pos_best   = data.get("pos_best")
    pos_worst  = data.get("pos_worst")
    neg_worst  = data.get("neg_worst")
    neg_best   = data.get("neg_best")

    stocks          = data.get("stock_concentration",  [])
    domestic_ratio  = data.get("domestic_ratio", 0)
    foreign_ratio   = data.get("foreign_ratio",  0)

    mdd             = data.get("mdd", 0)
    recovery_needed = data.get("recovery_needed", 0)
    volatility      = data.get("volatility", 0)
    total_trades    = data.get("total_trades", 0)

    sections = ["**📊 포트폴리오 분석**", _SEP]

    # ── 손익 현황 ─────────────────────────────────────────────────────────────
    prices_incomplete = data.get("prices_incomplete")
    block = ["**💰 손익 현황**"]
    if prices_incomplete:
        missing_str = "·".join(prices_incomplete)
        block.append(f"• 평가손익  ➖ 조회 불가 ({missing_str} 현재가 없음)")
    elif unrealized_pnl is not None:
        block.append(f"• 평가손익  {_icon(unrealized_pnl)} {_sign(unrealized_pnl)}{unrealized_pnl:,.0f}원")
    else:
        block.append(f"• 평가손익  ➖ 조회 불가")
    sections.append("  \n".join(block))

    # ── 기간별 수익률 ─────────────────────────────────────────────────────────
    has_period = any(r is not None for r in [return_1m, return_3m, return_6m])
    if has_period or pos_best or neg_worst:
        block = ["**📈 기간별 수익률**"]
        if return_1m is not None:
            block.append(f"• 1개월  {_icon(return_1m)} {_pct(return_1m)}")
        if return_3m is not None:
            block.append(f"• 3개월  {_icon(return_3m)} {_pct(return_3m)}")
        if return_6m is not None:
            block.append(f"• 6개월  {_icon(return_6m)} {_pct(return_6m)}")
        if pos_best:
            block.append(_return_line("수익률 최고", "🔺", pos_best))
        if pos_worst:
            block.append(_return_line("수익률 최소", "🔺", pos_worst))
        if neg_worst:
            block.append(_return_line("손실률 최고", "🔻", neg_worst))
        if neg_best:
            block.append(_return_line("손실률 최소", "🔻", neg_best))
        sections.append("  \n".join(block))

    # ── 포트폴리오 구성 ───────────────────────────────────────────────────────
    block = ["**🗂 포트폴리오 구성**"]
    block.append(f"• 국내 {domestic_ratio}%  /  해외 {foreign_ratio}%")
    if stocks:
        label = "• 종목별 비중 (상위 5)" if len(stocks) > 5 else "• 종목별 비중"
        block.append(label)
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
    sell_count = data.get("sell_count", 0)
    block = ["**🎯 거래 통계**"]
    block.append(f"• 총 거래  {total_trades}회  (매수 {data.get('buy_count', 0)}회 / 매도 {sell_count}회)")
    sections.append("  \n".join(block))

    sections.append(_SEP)
    return "\n\n".join(sections)


# ── 지표별 포커스 분석 ─────────────────────────────────────────────────────────

def _summary_returns(data: dict) -> str:
    r1, r3, r6 = data.get("return_1m"), data.get("return_3m"), data.get("return_6m")
    pos_best  = data.get("pos_best")
    neg_worst = data.get("neg_worst")
    ref   = r6 if r6 is not None else (r3 if r3 is not None else r1)
    label = "6개월" if r6 is not None else ("3개월" if r3 is not None else "1개월")
    parts = [f"{label} 기준 {_pct(ref)}"] if ref is not None else []
    if pos_best:
        parts.append(f"수익률 최고 {pos_best['name']} {_pct(pos_best.get('return_rate', 0))}")
    if neg_worst:
        parts.append(f"손실률 최고 {neg_worst['name']} {_pct(neg_worst.get('return_rate', 0))}")
    return (" / ".join(parts) + "입니다.") if parts else "기간별 수익률 데이터가 없습니다."



def _summary_risk(data: dict) -> str:
    mdd  = data.get("mdd", 0)
    vol  = data.get("volatility", 0)
    rec  = data.get("recovery_needed", 0)
    parts = [f"MDD {mdd:.2f}%", f"일간 변동성 {vol:.2f}%"]
    if rec > 0:
        parts.append(f"회복 필요 수익률 +{rec:.2f}%")
    return " / ".join(parts) + "입니다."


def _summary_stats(data: dict) -> str:
    total = data.get("total_trades", 0)
    buy   = data.get("buy_count",   0)
    sell  = data.get("sell_count",  0)
    return f"총 {total}회 거래 (매수 {buy}회 / 매도 {sell}회)입니다."


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
    "risk":     _summary_risk,
    "stats":    _summary_stats,
    "holdings": _summary_holdings,
}

_METRIC_LABEL = {
    "returns":  "📈 기간별 수익률",
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
        r1       = data.get("return_1m")
        r3       = data.get("return_3m")
        r6       = data.get("return_6m")
        pos_best  = data.get("pos_best")
        pos_worst = data.get("pos_worst")
        neg_worst = data.get("neg_worst")
        neg_best  = data.get("neg_best")
        block = []
        if r1 is not None:
            block.append(f"• 1개월  {_icon(r1)} {_pct(r1)}")
        if r3 is not None:
            block.append(f"• 3개월  {_icon(r3)} {_pct(r3)}")
        if r6 is not None:
            block.append(f"• 6개월  {_icon(r6)} {_pct(r6)}")
        if pos_best:
            block.append(_return_line("수익률 최고", "🔺", pos_best))
        if pos_worst:
            block.append(_return_line("수익률 최소", "🔺", pos_worst))
        if neg_worst:
            block.append(_return_line("손실률 최고", "🔻", neg_worst))
        if neg_best:
            block.append(_return_line("손실률 최소", "🔻", neg_best))
        if block:
            sections.append("  \n".join(block))

    elif metric_type == "sector":
        stocks         = data.get("stock_concentration",  [])
        domestic_ratio = data.get("domestic_ratio", 0)
        foreign_ratio  = data.get("foreign_ratio",  0)
        block = []
        block.append(f"• 국내 {domestic_ratio}%  /  해외 {foreign_ratio}%")
        if stocks:
            label = "• 종목별 비중 (상위 5)" if len(stocks) > 5 else "• 종목별 비중"
            block.append(label)
            for s in stocks[:5]:
                block.append(f"  　{s['stock']}  {s['weight']}%")
            if len(stocks) > 5:
                block.append("  　...")
        sections.append("  \n".join(block))

    elif metric_type == "risk":
        unrealized_pnl  = data.get("unrealized_pnl", 0)
        mdd             = data.get("mdd", 0)
        recovery_needed = data.get("recovery_needed", 0)
        volatility      = data.get("volatility", 0)
        block = []
        block.append(f"• 평가손익  {_icon(unrealized_pnl)} {_sign(unrealized_pnl)}{unrealized_pnl:,.0f}원")
        block.append(f"• 최대 낙폭 (MDD)   {mdd:.2f}%")
        block.append(f"• 회복 필요 수익률  +{recovery_needed:.2f}%")
        block.append(f"• 일간 변동성       {volatility:.2f}%")
        sections.append("  \n".join(block))

    elif metric_type == "stats":
        total_trades = data.get("total_trades", 0)
        buy_count    = data.get("buy_count",  0)
        sell_count   = data.get("sell_count", 0)
        block = []
        block.append(f"• 총 거래  {total_trades}회")
        block.append(f"• 매수 {buy_count}회  /  매도 {sell_count}회")
        sections.append("  \n".join(block))

    elif metric_type == "holdings":
        stocks         = data.get("stock_concentration", [])
        domestic_ratio = data.get("domestic_ratio", 0)
        foreign_ratio  = data.get("foreign_ratio",  0)
        block = []
        block.append(f"• 보유 종목 수  {len(stocks)}개")
        block.append(f"• 국내 {domestic_ratio}%  /  해외 {foreign_ratio}%")
        if stocks:
            label = "• 종목별 비중 (상위 5)" if len(stocks) > 5 else "• 종목별 비중"
            block.append(label)
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
