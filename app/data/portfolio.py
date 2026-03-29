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
        ORDER BY cost_basis DESC
    """
    rows = fetch_all(sql, {"account_id": account_id}) or []

    exchange_data = get_market_data(type="exchange", currency_pair="USDKRW")
    usdkrw = float(exchange_data.get("rate") or 0)

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
        if current_price > 0:
            current_value = current_price * quantity
            current_value_krw = current_value * usdkrw if market_cat == "overseas" else current_value
            if avg_buy_price > 0:
                return_rate = round((current_price - avg_buy_price) / avg_buy_price * 100, 2)

        holdings.append({
            "stock_code":        stock_code,
            "stock_name":        stock_name,
            "sector":            sector or "기타",
            "market_type":       market_cat,
            "quantity":          int(quantity),
            "avg_buy_price":     avg_buy_price,
            "cost_basis":        cost_basis,
            "current_price":     current_price,
            "current_value_krw": current_value_krw,
            "return_rate":       return_rate,
        })

    total_cost = sum(h["cost_basis"] for h in holdings) or 1
    return {
        "holdings":    holdings,
        "total_count": len(holdings),
        "total_cost":  total_cost,
        "usdkrw":      usdkrw,
    }


def get_portfolio_returns(account_id: str) -> dict:
    """기간별 수익률(일/1M/3M/6M)과 MDD를 반환합니다."""
    sql = """
        WITH snapshots AS (
            SELECT total_value, daily_return, snapshot_date,
                   ROW_NUMBER() OVER (ORDER BY snapshot_date DESC) AS rn
            FROM portfolio_snapshots
            WHERE account_id = :account_id
        ),
        base_1m AS (
            SELECT total_value FROM portfolio_snapshots
            WHERE account_id = :account_id
              AND snapshot_date <= TRUNC(SYSDATE) - 30
            ORDER BY snapshot_date DESC FETCH FIRST 1 ROWS ONLY
        ),
        base_3m AS (
            SELECT total_value FROM portfolio_snapshots
            WHERE account_id = :account_id
              AND snapshot_date <= TRUNC(SYSDATE) - 90
            ORDER BY snapshot_date DESC FETCH FIRST 1 ROWS ONLY
        ),
        base_6m AS (
            SELECT total_value FROM portfolio_snapshots
            WHERE account_id = :account_id
              AND snapshot_date <= TRUNC(SYSDATE) - 180
            ORDER BY snapshot_date DESC FETCH FIRST 1 ROWS ONLY
        ),
        mdd AS (
            SELECT MIN((total_value - peak) / peak * 100) AS mdd
            FROM (
                SELECT total_value,
                       MAX(total_value) OVER (ORDER BY snapshot_date
                           ROWS UNBOUNDED PRECEDING) AS peak
                FROM portfolio_snapshots
                WHERE account_id = :account_id
            )
        )
        SELECT
            s_today.daily_return,
            ROUND((s_today.total_value - b1.total_value) / b1.total_value * 100, 2) AS return_1m,
            ROUND((s_today.total_value - b3.total_value) / b3.total_value * 100, 2) AS return_3m,
            ROUND((s_today.total_value - b6.total_value) / b6.total_value * 100, 2) AS return_6m,
            mdd.mdd
        FROM       (SELECT * FROM snapshots WHERE rn = 1) s_today
        CROSS JOIN base_1m b1
        CROSS JOIN base_3m b3
        CROSS JOIN base_6m b6
        CROSS JOIN mdd
    """
    row = fetch_one(sql, {"account_id": account_id}) or (0, 0, 0, 0, 0)
    daily_return, return_1m, return_3m, return_6m, mdd = row
    mdd_val = float(mdd or 0)
    return {
        "daily_return": float(daily_return or 0),
        "return_1m":    float(return_1m    or 0),
        "return_3m":    float(return_3m    or 0),
        "return_6m":    float(return_6m    or 0),
        "mdd":          mdd_val,
        "recovery_needed": round(abs(mdd_val) / (100 - abs(mdd_val)) * 100, 2) if mdd_val < 0 else 0.0,
    }


def get_sector_concentration(account_id: str) -> dict:
    """섹터별 보유 비중을 반환합니다."""
    sql = """
        SELECT
            i.sector,
            i.market_type,
            SUM(h.holding_quantity * h.avg_buy_price) AS cost_basis
        FROM holdings h
        JOIN instruments i ON h.instrument_id = i.instrument_id
        WHERE h.account_id       = :account_id
          AND h.holding_quantity > 0
        GROUP BY i.sector, i.market_type
        ORDER BY cost_basis DESC
    """
    rows = fetch_all(sql, {"account_id": account_id}) or []

    total = sum(float(row[2] or 0) for row in rows) or 1
    sectors = [
        {
            "sector":      row[0] or "기타",
            "market_type": _to_market_category(row[1]),
            "weight":      round(float(row[2] or 0) / total * 100, 1),
        }
        for row in rows
    ]

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
        SELECT ROUND(STDDEV(daily_return), 2)
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

    returns_sql = """
        SELECT i.stock_name, i.stock_code, h.avg_buy_price, h.holding_quantity
        FROM holdings h
        JOIN instruments i ON h.instrument_id = i.instrument_id
        WHERE h.account_id       = :account_id
          AND h.holding_quantity > 0
    """
    rows = fetch_all(returns_sql, {"account_id": account_id}) or []

    stock_returns = []
    for stock_name, stock_code, avg_buy_price, quantity in rows:
        avg_buy_price = float(avg_buy_price or 0)
        if avg_buy_price <= 0:
            continue
        price_data    = get_market_data(type="price", stock_code=stock_code)
        current_price = float(price_data.get("current_price") or 0)
        if current_price > 0:
            return_rate    = round((current_price - avg_buy_price) / avg_buy_price * 100, 2)
            unrealized_pnl = round((current_price - avg_buy_price) * float(quantity or 0), 0)
            stock_returns.append({
                "name":           stock_name,
                "return_rate":    return_rate,
                "unrealized_pnl": unrealized_pnl,
            })

    stock_returns_sorted = sorted(stock_returns, key=lambda x: x["return_rate"])
    best_stock  = stock_returns_sorted[-1] if stock_returns_sorted else None
    worst_stock = stock_returns_sorted[0]  if stock_returns_sorted else None

    realized_sql = """
        SELECT NVL(SUM(net_amount), 0)
        FROM executions
        WHERE account_id = :account_id
          AND order_side  = 'SELL'
    """
    realized_row = fetch_one(realized_sql, {"account_id": account_id}) or (0,)
    realized_pnl = float(realized_row[0] or 0)
    unrealized_pnl = sum(s["unrealized_pnl"] for s in stock_returns)

    return {
        "volatility":      volatility,
        "mdd":             mdd_val,
        "recovery_needed": round(abs(mdd_val) / (100 - abs(mdd_val)) * 100, 2) if mdd_val < 0 else 0.0,
        "best_stock":      best_stock,
        "worst_stock":     worst_stock,
        "realized_pnl":    realized_pnl,
        "unrealized_pnl":  unrealized_pnl,
        "stock_returns":   stock_returns,
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

    avg_win       = float(avg_win       or 0)
    avg_loss      = float(avg_loss      or 0)
    sell_count_n  = int(sell_count      or 0)
    win_count_n   = int(win_count       or 0)
    win_rate      = round(win_count_n / sell_count_n * 100, 1) if sell_count_n > 0 else 0.0
    profit_factor = round(avg_win / abs(avg_loss), 2) if avg_loss != 0 else 0.0

    return {
        "total_trades":   int(total_trades  or 0),
        "buy_count":      int(buy_count     or 0),
        "sell_count":     sell_count_n,
        "win_count":      win_count_n,
        "loss_count":     int(loss_count    or 0),
        "win_rate":       win_rate,
        "avg_win":        avg_win,
        "avg_loss":       avg_loss,
        "profit_factor":  profit_factor,
        "total_realized": float(total_realized or 0),
    }


def get_portfolio_summary(account_id: str) -> dict:
    """
    템플릿 출력용 포트폴리오 전체 요약 데이터를 반환합니다.
    format_portfolio() 의 입력 형식과 동일합니다.
    """
    holdings   = get_holdings(account_id)
    returns    = get_portfolio_returns(account_id)
    risk       = get_portfolio_risk(account_id)
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
        "realized_pnl":         risk.get("realized_pnl",   0),
        "return_1m":            returns.get("return_1m", 0),
        "return_3m":            returns.get("return_3m", 0),
        "return_6m":            returns.get("return_6m", 0),
        "best_stock":           risk.get("best_stock"),
        "worst_stock":          risk.get("worst_stock"),
        "sector_concentration": sector_concentration,
        "stock_concentration":  stock_concentration,
        "domestic_ratio":       domestic_ratio,
        "foreign_ratio":        round(100 - domestic_ratio, 1),
        "mdd":                  risk.get("mdd", 0),
        "recovery_needed":      risk.get("recovery_needed", 0),
        "volatility":           risk.get("volatility", 0),
        "total_trades":         trade_stat.get("total_trades", 0),
        "win_count":            trade_stat.get("win_count",    0),
        "loss_count":           trade_stat.get("loss_count",   0),
        "avg_win":              trade_stat.get("avg_win",  0),
        "avg_loss":             trade_stat.get("avg_loss", 0),
        "profit_factor":        trade_stat.get("profit_factor", 0),
    }
