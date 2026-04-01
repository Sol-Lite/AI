"""
(12) 포트폴리오 분석 tools — Oracle DB + Spring API

tools:
    get_holdings             — 현재 보유 종목 목록 (수량, 평균단가, 평가금액)
    get_portfolio_returns    — 기간별 수익률 (일/1M/3M/6M) 및 MDD
    get_sector_concentration — 섹터별 비중
    get_portfolio_risk       — 변동성, MDD, 최고/최저 수익 종목
    get_trade_stats          — 거래 통계 (승률, 손익비, 실현손익)

template:
    get_portfolio_summary    — 위 함수들을 조합해 format_portfolio() 입력용 dict 반환
"""
from app.db.oracle import fetch_one, fetch_all
from app.data.market import get_market_data

# DB의 market_type → domestic/overseas 변환
_DOMESTIC_MARKETS = {"KOSPI", "KOSDAQ"}


def _to_market_category(market_type: str) -> str:
    return "domestic" if (market_type or "").upper() in _DOMESTIC_MARKETS else "overseas"


def get_holdings(account_id: str) -> dict:
    """현재 보유 종목 목록과 평가금액을 반환합니다."""
    sql = """
        SELECT
            i.stock_code,
            i.stock_name,
            i.sector,
            i.market_type,
            h.holding_quantity,
            h.avg_buy_price,
            h.holding_quantity * h.avg_buy_price AS cost_basis
        FROM holdings h
        JOIN instruments i ON h.instrument_id = i.instrument_id
        WHERE h.account_id       = :account_id
          AND h.holding_quantity > 0
    """
    rows = fetch_all(sql, {"account_id": account_id}) or []

    exchange_data = get_market_data(type="exchange", currency_pair="USDKRW")
    usdkrw = float(exchange_data.get("rate") or 0)
    if usdkrw <= 0:
        usdkrw = 1.0   # 환율 조회 실패 시 fallback (해외 비중 계산 부정확할 수 있음)

    holdings = []
    for stock_code, stock_name, sector, market_type, quantity, avg_buy_price, cost_basis in rows:
        quantity      = float(quantity      or 0)
        avg_buy_price = float(avg_buy_price or 0)
        cost_basis    = float(cost_basis    or 0)
        market_cat    = _to_market_category(market_type)

        price_data    = get_market_data(type="price", stock_code=stock_code)
        current_price = float(price_data.get("current_price") or 0)

        current_value_krw = 0.0
        return_rate       = 0.0
        price_for_value   = current_price if current_price > 0 else avg_buy_price
        if price_for_value > 0:
            raw_value = price_for_value * quantity
            current_value_krw = raw_value * usdkrw if market_cat == "overseas" else raw_value
        if current_price > 0 and avg_buy_price > 0:
            return_rate = round((current_price - avg_buy_price) / avg_buy_price * 100, 2)

        cost_basis_krw = cost_basis * usdkrw if market_cat == "overseas" else cost_basis
        holdings.append({
            "stock_code":        stock_code,
            "stock_name":        stock_name,
            "sector":            sector or "기타",
            "market_type":       market_cat,
            "quantity":          int(quantity),
            "avg_buy_price":     avg_buy_price,
            "cost_basis":        cost_basis,
            "cost_basis_krw":    cost_basis_krw,
            "current_price":     current_price,
            "current_value_krw": current_value_krw,
            "return_rate":       return_rate,
        })

    holdings.sort(key=lambda h: h["cost_basis_krw"], reverse=True)
    total_cost_krw = sum(h["cost_basis_krw"] for h in holdings) or 1
    return {
        "holdings":       holdings,
        "total_count":    len(holdings),
        "total_cost":     total_cost_krw,
        "usdkrw":         usdkrw,
    }


def get_portfolio_returns(account_id: str) -> dict:
    """기간별 수익률(일/1M/3M/6M)과 MDD를 반환합니다."""
    # 오늘 기준 최신 스냅샷
    today_sql = """
        SELECT total_value, daily_return
        FROM portfolio_snapshots
        WHERE account_id = :account_id
        ORDER BY snapshot_date DESC
        FETCH FIRST 1 ROWS ONLY
    """
    today_row = fetch_one(today_sql, {"account_id": account_id}) or (0, 0)
    today_val    = float(today_row[0] or 0)
    daily_return = float(today_row[1] or 0)

    def _base_return(days: int) -> float | None:
        row = fetch_one("""
            SELECT total_value FROM portfolio_snapshots
            WHERE account_id = :account_id
              AND snapshot_date <= TRUNC(SYSDATE) - :days
            ORDER BY snapshot_date DESC
            FETCH FIRST 1 ROWS ONLY
        """, {"account_id": account_id, "days": days})
        if row and row[0] and float(row[0]) > 0 and today_val > 0:
            return round((today_val - float(row[0])) / float(row[0]) * 100, 2)
        return None

    mdd_row = fetch_one("""
        SELECT MIN((total_value - peak) / peak * 100)
        FROM (
            SELECT total_value,
                   MAX(total_value) OVER (ORDER BY snapshot_date
                       ROWS UNBOUNDED PRECEDING) AS peak
            FROM portfolio_snapshots
            WHERE account_id = :account_id
        )
    """, {"account_id": account_id}) or (0,)
    mdd_val = float(mdd_row[0] or 0)
    # DB가 비율 형태(예: -0.04595 = -4.595%)로 반환하는 경우 퍼센트로 변환
    if mdd_val != 0 and abs(mdd_val) < 1:
        mdd_val = round(mdd_val * 100, 4)

    return {
        "daily_return": daily_return,
        "return_1m":    _base_return(30),
        "return_3m":    _base_return(90),
        "return_6m":    _base_return(180),
        "mdd":          mdd_val,
        "recovery_needed": round(abs(mdd_val) / (100 - abs(mdd_val)) * 100, 2) if mdd_val < 0 else 0.0,
    }


def get_sector_concentration(account_id: str) -> dict:
    """섹터별 보유 비중을 반환합니다. 현재 평가금액(KRW 환산) 기준으로 비중을 계산합니다."""
    # get_holdings는 이미 current_value_krw를 올바르게 계산함 (환율 적용 포함)
    holdings_data = get_holdings(account_id)
    holdings = holdings_data.get("holdings", [])

    # 섹터 × 국내/해외 조합별로 current_value_krw 합산
    sector_map: dict[tuple, float] = {}
    for h in holdings:
        key = (h.get("sector", "기타"), h.get("market_type", "domestic"))
        sector_map[key] = sector_map.get(key, 0.0) + h.get("current_value_krw", 0.0)

    total = sum(sector_map.values()) or 1
    sectors = [
        {
            "sector":      sector or "기타",
            "market_type": market_cat,
            "weight":      round(value / total * 100, 1),
        }
        for (sector, market_cat), value in sector_map.items()
    ]
    sectors.sort(key=lambda x: x["weight"], reverse=True)

    domestic_weight = round(
        sum(s["weight"] for s in sectors if s["market_type"] == "domestic"), 1
    )
    return {
        "sectors":         sectors,
        "domestic_weight": domestic_weight,
        "overseas_weight": round(100 - domestic_weight, 1),
    }


def get_portfolio_risk(account_id: str) -> dict:
    """포트폴리오 리스크 지표: 변동성, MDD, 최고/최저 수익 종목을 반환합니다."""
    volatility_sql = """
        SELECT ROUND(STDDEV(daily_return) * 100, 2)
        FROM portfolio_snapshots
        WHERE account_id   = :account_id
          AND snapshot_date >= TRUNC(SYSDATE) - 30
    """
    vol_row    = fetch_one(volatility_sql, {"account_id": account_id}) or (0,)
    volatility = float(vol_row[0] or 0)

    mdd_sql = """
        SELECT MIN((total_value - peak) / peak * 100)
        FROM (
            SELECT total_value,
                   MAX(total_value) OVER (ORDER BY snapshot_date
                       ROWS UNBOUNDED PRECEDING) AS peak
            FROM portfolio_snapshots
            WHERE account_id = :account_id
        )
    """
    mdd_row = fetch_one(mdd_sql, {"account_id": account_id}) or (0,)
    mdd_val = float(mdd_row[0] or 0)
    # DB가 비율 형태(예: -0.04595 = -4.595%)로 반환하는 경우 퍼센트로 변환
    if mdd_val != 0 and abs(mdd_val) < 1:
        mdd_val = round(mdd_val * 100, 4)

    returns_sql = """
        SELECT i.stock_name, i.stock_code, i.market_type, h.avg_buy_price, h.holding_quantity
        FROM holdings h
        JOIN instruments i ON h.instrument_id = i.instrument_id
        WHERE h.account_id       = :account_id
          AND h.holding_quantity > 0
    """
    rows = fetch_all(returns_sql, {"account_id": account_id}) or []

    # 해외 종목 환산을 위한 환율 조회 (USD/KRW)
    usdkrw = 1.0
    try:
        _ex = get_market_data(type="exchange", currency_pair="USDKRW")
        usdkrw = float(_ex.get("rate") or 1.0)
    except Exception:
        pass

    stock_returns = []
    missing_price_stocks = []
    for stock_name, stock_code, market_type, avg_buy_price, quantity in rows:
        avg_buy_price = float(avg_buy_price or 0)
        if avg_buy_price <= 0:
            continue
        is_overseas   = _to_market_category(market_type) == "overseas"
        price_data    = get_market_data(type="price", stock_code=stock_code)
        current_price = float(price_data.get("current_price") or 0)
        if current_price > 0:
            return_rate    = round((current_price - avg_buy_price) / avg_buy_price * 100, 2)
            pnl_raw        = (current_price - avg_buy_price) * float(quantity or 0)
            # 해외 종목: USD → KRW 환산
            unrealized_pnl = round(pnl_raw * usdkrw if is_overseas else pnl_raw, 0)
            stock_returns.append({
                "name":           stock_name,
                "stock_code":     stock_code,
                "return_rate":    return_rate,
                "unrealized_pnl": unrealized_pnl,
            })
        else:
            missing_price_stocks.append(stock_name)

    stock_returns_sorted = sorted(stock_returns, key=lambda x: x["return_rate"])
    best_stock  = stock_returns_sorted[-1] if stock_returns_sorted else None
    worst_stock = stock_returns_sorted[0]  if stock_returns_sorted else None

    # 양수 수익 종목 (오름차순), 음수 수익 종목 (오름차순: 가장 손실 큰 것이 앞)
    pos_stocks = [s for s in stock_returns_sorted if s["return_rate"] > 0]
    neg_stocks = [s for s in stock_returns_sorted if s["return_rate"] < 0]

    # net_amount는 거래금액이므로 매도총금액만 계산 가능 (실현손익 아님)
    realized_sql = """
        SELECT NVL(SUM(net_amount), 0)
        FROM executions
        WHERE account_id = :account_id
          AND order_side  = 'SELL'
    """
    realized_row = fetch_one(realized_sql, {"account_id": account_id}) or (0,)
    total_sell_amount = float(realized_row[0] or 0)
    unrealized_pnl = sum(s["unrealized_pnl"] for s in stock_returns)

    return {
        "volatility":      volatility,
        "mdd":             mdd_val,
        "recovery_needed": round(abs(mdd_val) / (100 - abs(mdd_val)) * 100, 2) if mdd_val < 0 else 0.0,
        "best_stock":      best_stock,
        "worst_stock":     worst_stock,
        "pos_count":       len(pos_stocks),
        "neg_count":       len(neg_stocks),
        "pos_best":        pos_stocks[-1] if pos_stocks else None,            # 수익률 최고
        "pos_worst":       pos_stocks[0]  if len(pos_stocks) >= 2 else None,  # 수익률 최소
        "neg_worst":       neg_stocks[0]  if neg_stocks else None,            # 손실률 최고 (가장 손실 큰)
        "neg_best":        neg_stocks[-1] if len(neg_stocks) >= 2 else None,  # 손실률 최소 (가장 손실 적은)
        "total_sell_amount":    total_sell_amount,
        "realized_pnl":         None,
        "unrealized_pnl":       unrealized_pnl if not missing_price_stocks else None,
        "prices_incomplete":    missing_price_stocks if missing_price_stocks else None,
        "stock_returns":        stock_returns,
    }


def get_trade_stats(account_id: str) -> dict:
    """거래 통계: 총 거래 수, 승률, 평균 손익, 손익비를 반환합니다."""
    sql = """
        SELECT
            COUNT(*)                                                                           AS total_trades,
            COUNT(CASE WHEN order_side = 'BUY'  THEN 1 END)                                   AS buy_count,
            COUNT(CASE WHEN order_side = 'SELL' THEN 1 END)                                   AS sell_count,
            COUNT(CASE WHEN order_side = 'SELL' AND net_amount > 0 THEN 1 END)                AS win_count,
            COUNT(CASE WHEN order_side = 'SELL' AND net_amount < 0 THEN 1 END)                AS loss_count,
            NVL(AVG(CASE WHEN order_side = 'SELL' AND net_amount > 0 THEN net_amount END), 0) AS avg_win,
            NVL(AVG(CASE WHEN order_side = 'SELL' AND net_amount < 0 THEN net_amount END), 0) AS avg_loss,
            NVL(SUM(net_amount), 0)                                                           AS total_realized
        FROM executions
        WHERE account_id = :account_id
    """
    row = fetch_one(sql, {"account_id": account_id}) or (0, 0, 0, 0, 0, 0, 0, 0)
    total_trades, buy_count, sell_count, win_count, loss_count, avg_win, avg_loss, total_realized = row

    # net_amount는 거래금액(항상 양수)이므로 win/loss 구분 불가
    # 신뢰 가능한 값만 반환
    return {
        "total_trades":   int(total_trades  or 0),
        "buy_count":      int(buy_count     or 0),
        "sell_count":     int(sell_count    or 0),
        "win_count":      None,
        "loss_count":     None,
        "win_rate":       None,
        "avg_win":        None,
        "avg_loss":       None,
        "profit_factor":  None,
        "total_realized": float(total_realized or 0),
    }


def get_portfolio_summary(account_id: str) -> dict:
    """
    템플릿 출력용 포트폴리오 전체 요약 데이터를 반환합니다.
    format_portfolio() 의 입력 형식과 동일합니다.
    """
    holdings   = get_holdings(account_id)
    risk       = get_portfolio_risk(account_id)
    returns    = get_portfolio_returns(account_id)
    returns["best_stock"]  = risk.get("best_stock")
    returns["worst_stock"] = risk.get("worst_stock")
    returns["pos_count"]   = risk.get("pos_count", 0)
    returns["neg_count"]   = risk.get("neg_count", 0)
    returns["pos_best"]    = risk.get("pos_best")
    returns["pos_worst"]   = risk.get("pos_worst")
    returns["neg_worst"]   = risk.get("neg_worst")
    returns["neg_best"]    = risk.get("neg_best")
    trade_stat = get_trade_stats(account_id)

    holding_list = holdings.get("holdings", [])
    total_val    = sum(h.get("current_value_krw", 0) for h in holding_list) or 1

    stock_concentration = sorted(
        [
            {"stock": h["stock_name"], "weight": round(h.get("current_value_krw", 0) / total_val * 100, 1)}
            for h in holding_list
        ],
        key=lambda x: -x["weight"],
    )

    sector_map: dict[str, float] = {}
    for h in holding_list:
        s = h.get("sector", "기타")
        sector_map[s] = sector_map.get(s, 0) + h.get("current_value_krw", 0)
    sector_concentration = sorted(
        [{"sector": s, "weight": round(v / total_val * 100, 1)} for s, v in sector_map.items()],
        key=lambda x: -x["weight"],
    )

    domestic_val   = sum(h.get("current_value_krw", 0) for h in holding_list if h.get("market_type") == "domestic")
    domestic_ratio = round(domestic_val / total_val * 100, 1)

    return {
        "unrealized_pnl":       risk.get("unrealized_pnl", 0),
        "realized_pnl":         None,
        "return_1m":            returns.get("return_1m"),   # None = 해당 기간 데이터 없음
        "return_3m":            returns.get("return_3m"),
        "return_6m":            returns.get("return_6m"),
        "best_stock":           risk.get("best_stock"),
        "worst_stock":          risk.get("worst_stock"),
        "pos_count":            risk.get("pos_count", 0),
        "neg_count":            risk.get("neg_count", 0),
        "pos_best":             risk.get("pos_best"),
        "pos_worst":            risk.get("pos_worst"),
        "neg_worst":            risk.get("neg_worst"),
        "neg_best":             risk.get("neg_best"),
        "sector_concentration": sector_concentration,
        "stock_concentration":  stock_concentration,
        "domestic_ratio":       domestic_ratio,
        "foreign_ratio":        round(100 - domestic_ratio, 1),
        "mdd":                  risk.get("mdd", 0),
        "recovery_needed":      risk.get("recovery_needed", 0),
        "volatility":           risk.get("volatility", 0),
        "total_trades":         trade_stat.get("total_trades", 0),
        "buy_count":            trade_stat.get("buy_count",    0),
        "sell_count":           trade_stat.get("sell_count",   0),
        "win_count":            trade_stat.get("win_count",    0),
        "loss_count":           trade_stat.get("loss_count",   0),
        "win_rate":             trade_stat.get("win_rate",     0.0),
        "avg_win":              trade_stat.get("avg_win",  0),
        "avg_loss":             trade_stat.get("avg_loss", 0),
        "profit_factor":        trade_stat.get("profit_factor", 0),
    }
