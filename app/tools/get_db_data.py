"""
도구 2: get_db_data - 내부 DB 조회 (잔고 / 거래내역 / 포트폴리오 분석)
"""
from typing import Literal
from app.db.oracle import fetch_one, fetch_all
from app.tools.get_market_data import get_market_data
import requests
def get_db_data(
    type: Literal["balance", "trades", "portfolio", "balance_detail", "trades_detail", "portfolio_detail"],
    user_context: dict,
    limit: int = 3,
) -> dict:
    """
    내부 DB에서 사용자 데이터를 조회합니다.

    Args:
        type: 전체 조회(템플릿 반환) — "balance" | "trades" | "portfolio"
              세부 질문(LLM 답변) — "balance_detail" | "trades_detail" | "portfolio_detail"
        user_context: 세션에서 주입된 {"user_id": ..., "account_id": ...}
        limit: trades 조회 시 최근 건수 (기본값 3)

    Returns:
        type별 상이한 딕셔너리
    """
    account_id = user_context["account_id"]

    if type in ("balance", "balance_detail"):
        return _query_balance(account_id)
    elif type in ("trades", "trades_detail"):
        return _query_trades(account_id, limit)
    elif type in ("portfolio", "portfolio_detail"):
        return _query_portfolio(account_id)
    else:
        raise ValueError(f"Unknown type: {type}")

SPRING_BASE_URL = "http://localhost:8080"

def _call_spring_api(path: str, params: dict | None = None):
    try:
        url = f"{SPRING_BASE_URL}{path}"
        res = requests.get(url, params=params, timeout=3)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        return {
            "success": False,
            "error": "SPRING_API_ERROR",
            "message": str(e)
        }



# ── balance: 잔고 ──────────────────────────────────────────────────────────────────
# def _query_balance(account_id: str) -> dict:
#     sql = """
#         SELECT
#             cb.currency_code,
#             SUM(cb.available_amount) AS available_amount,
#             SUM(cb.total_amount) AS total_amount
#         FROM cash_balances cb
#         WHERE cb.account_id = :account_id
#         GROUP BY cb.currency_code
#     """

#     rows = fetch_all(sql, {"account_id": account_id}) or []

#     # 기본값 세팅
#     result = {
#         "krw_available": 0,
#         "krw_total": 0,
#         "usd_available": 0,
#         "usd_total": 0,
#         "total_eval": 0,
#     }
#     for currency_code, available, total in rows:
#         ccy = (currency_code or "").strip().upper()
#         if ccy == "KRW":
#             result["krw_available"] = float(available or 0)
#             result["krw_total"] = float(total or 0)
#         elif ccy == "USD":
#             result["usd_available"] = float(available or 0)
#             result["usd_total"] = float(total or 0)
#     return result

def _query_balance(account_id: str) -> dict:
    return _call_spring_api("/api/balance/cash")

# ── trades: 거래내역 ───────────────────────────────────────────────────────────────────
def _query_trades(account_id: str, limit: int) -> dict:

    cnt_sql = """
        SELECT
            COUNT(DISTINCT ex.ORDER_ID)                                             AS total,
            COUNT(DISTINCT CASE WHEN ex.ORDER_SIDE = 'buy'  THEN ex.ORDER_ID END)  AS buy_count,
            COUNT(DISTINCT CASE WHEN ex.ORDER_SIDE = 'sell' THEN ex.ORDER_ID END)  AS sell_count
        FROM executions ex
        WHERE ex.account_id = :account_id
    """
    cnt_row = fetch_one(cnt_sql, {"account_id": account_id}) or (0, 0, 0)
    total, buy_count, sell_count = cnt_row

    recent_sql = """
        WITH last_buy AS (
            SELECT
                i.STOCK_NAME,
                ex.ORDER_SIDE,
                ex.EXECUTION_PRICE,
                ex.EXECUTION_QUANTITY,
                ex.EXECUTED_AT
            FROM executions ex
                LEFT JOIN instruments i ON ex.INSTRUMENT_ID = i.INSTRUMENT_ID
            WHERE ex.account_id = :account_id
              AND ex.ORDER_SIDE  = 'buy'
            ORDER BY ex.EXECUTED_AT DESC
            FETCH FIRST :limit ROWS ONLY
        ),
        last_sell AS (
            SELECT
                i.STOCK_NAME,
                ex.ORDER_SIDE,
                ex.EXECUTION_PRICE,
                ex.EXECUTION_QUANTITY,
                ex.EXECUTED_AT
            FROM executions ex
                LEFT JOIN instruments i ON ex.INSTRUMENT_ID = i.INSTRUMENT_ID
            WHERE ex.account_id = :account_id
              AND ex.ORDER_SIDE  = 'sell'
            ORDER BY ex.EXECUTED_AT DESC
            FETCH FIRST :limit ROWS ONLY
        )
        SELECT STOCK_NAME, ORDER_SIDE, EXECUTION_PRICE, EXECUTION_QUANTITY, EXECUTED_AT FROM last_buy
        UNION ALL
        SELECT STOCK_NAME, ORDER_SIDE, EXECUTION_PRICE, EXECUTION_QUANTITY, EXECUTED_AT FROM last_sell
        ORDER BY EXECUTED_AT DESC
    """
    rows = fetch_all(recent_sql, {"account_id": account_id, "limit": limit})
    recent = [
        {
            "stock_name":  row[0],
            "side":        row[1],
            "price":       row[2],
            "quantity":    row[3],
            "executed_at": str(row[4]),
        }
        for row in rows
    ]

    return {
        "total":      total,
        "buy_count":  buy_count,
        "sell_count": sell_count,
        "recent":     recent,
    }


# ── portfolio: 포트폴리오 ─────────────────────────────────────────────────────────────────
def _query_portfolio(account_id: str) -> dict:
    # ── 스냅샷: 오늘/어제 평가액, 기간별 수익률, MDD ──────────────────────
    snapshot_sql = """
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
            s_yest.total_value                                                        AS yesterday_total,
            ROUND((s_today.total_value - b1.total_value) / b1.total_value * 100, 2)  AS return_1m,
            ROUND((s_today.total_value - b3.total_value) / b3.total_value * 100, 2)  AS return_3m,
            ROUND((s_today.total_value - b6.total_value) / b6.total_value * 100, 2)  AS return_6m,
            mdd.mdd
        FROM       (SELECT * FROM snapshots WHERE rn = 1) s_today
        CROSS JOIN (SELECT * FROM snapshots WHERE rn = 2) s_yest
        CROSS JOIN base_1m b1
        CROSS JOIN base_3m b3
        CROSS JOIN base_6m b6
        CROSS JOIN mdd
    """
    snap = fetch_one(snapshot_sql, {"account_id": account_id}) or (0, 0, 0, 0, 0, 0)
    daily_return, yesterday_total, return_1m, return_3m, return_6m, mdd = snap

    # ── 보유 종목: 종목/섹터 집중도, 국내/해외 비율, best/worst stock ────
    holdings_sql = """
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
        WHERE h.account_id     = :account_id
          AND h.holding_quantity > 0
    """
    holding_rows = fetch_all(holdings_sql, {"account_id": account_id}) or []

    # 실시간 환율 조회 (해외주식 KRW 환산에 사용)
    exchange_data = get_market_data(type="exchange", currency_pair="USDKRW")
    usdkrw = float(exchange_data.get("rate") or 0)

    # 현금 잔고 조회
    cash_sql = """
        SELECT currency_code, SUM(available_amount), SUM(total_amount)
        FROM cash_balances
        WHERE account_id = :account_id
        GROUP BY currency_code
    """
    cash_rows = fetch_all(cash_sql, {"account_id": account_id}) or []
    cash_krw = 0.0
    cash_usd = 0.0
    for currency_code, _, total in cash_rows:
        ccy = (currency_code or "").strip().upper()
        if ccy == "KRW":
            cash_krw = float(total or 0)
        elif ccy == "USD":
            cash_usd = float(total or 0)

    total_cost = sum(float(row[6] or 0) for row in holding_rows) or 1  # 매수금액 합계 (국내/해외 비율 계산용)

    sector_map: dict[str, float] = {}  # 섹터별 실시간 평가액
    stock_map:  dict[str, float] = {}  # 종목별 실시간 평가액
    domestic_cost  = 0.0
    overseas_cost  = 0.0
    domestic_stock_value = 0.0       # 국내주식 실시간 평가액 (KRW)
    overseas_value_usd = 0.0   # 해외주식 실시간 평가액 (USD)
    stock_returns: list[dict] = []

    for stock_code, stock_name, sector, market_type, quantity, avg_buy_price, cost_basis in holding_rows:
        cost_basis    = float(cost_basis    or 0)
        avg_buy_price = float(avg_buy_price or 0)
        quantity      = float(quantity      or 0)

        if market_type == "domestic":
            domestic_cost += cost_basis
        else:
            overseas_cost += cost_basis

        # 현재가 조회 → 실시간 평가액 계산
        price_data    = get_market_data(type="price", stock_code=stock_code, market=market_type)
        current_price = float(price_data.get("current_price") or 0)
        if current_price > 0:
            current_value = current_price * quantity
            # 해외주식은 KRW 환산해서 집계
            current_value_krw = current_value * usdkrw if market_type != "domestic" else current_value

            if market_type == "domestic":
                domestic_stock_value += current_value
            else:
                overseas_value_usd += current_value

            sector_map[sector] = sector_map.get(sector, 0) + current_value_krw
            stock_map[stock_name] = stock_map.get(stock_name, 0) + current_value_krw

            if avg_buy_price > 0:
                return_rate    = round((current_price - avg_buy_price) / avg_buy_price * 100, 2)
                unrealized_pnl = round((current_price - avg_buy_price) * quantity, 0)
                stock_returns.append({
                    "name":           stock_name,
                    "return_rate":    return_rate,
                    "unrealized_pnl": unrealized_pnl,
                })

    overseas_value_krw = round(overseas_value_usd * usdkrw, 0)

    # 실시간 총평가금액
    current_total_krw = domestic_stock_value + overseas_value_krw + cash_krw + round(cash_usd * usdkrw, 0)
    current_total_usd = round((domestic_stock_value + cash_krw) / usdkrw, 2) + overseas_value_usd + cash_usd if usdkrw > 0 else 0.0

    # 실시간 평가액 기준 섹터/종목 집중도
    total_value_for_weight = sum(sector_map.values()) or 1
    sector_concentration = [
        {"sector": s, "weight": round(v / total_value_for_weight * 100, 1)}
        for s, v in sorted(sector_map.items(), key=lambda x: -x[1])
    ]
    stock_concentration = sorted(
        [{"stock": s, "weight": round(v / total_value_for_weight * 100, 1)} for s, v in stock_map.items()],
        key=lambda x: -x["weight"],
    )
    domestic_ratio = round(domestic_cost / total_cost * 100, 1)
    foreign_ratio  = round(100 - domestic_ratio, 1)

    stock_returns_sorted = sorted(stock_returns, key=lambda x: x["return_rate"])
    best_stock     = {"name": stock_returns_sorted[-1]["name"], "return": stock_returns_sorted[-1]["return_rate"]} if stock_returns_sorted else None
    worst_stock    = {"name": stock_returns_sorted[0]["name"],  "return": stock_returns_sorted[0]["return_rate"]}  if stock_returns_sorted else None
    unrealized_pnl = sum(s["unrealized_pnl"] for s in stock_returns)

    # ── 거래 통계 ─────────────────────────────────────────────────────────
    trade_sql = """
        SELECT
            COUNT(*)                                                                          AS total_trades,
            COUNT(CASE WHEN order_side = 'buy'  THEN 1 END)                                  AS buy_count,
            COUNT(CASE WHEN order_side = 'sell' THEN 1 END)                                  AS sell_count,
            COUNT(CASE WHEN order_side = 'sell' AND net_amount > 0 THEN 1 END)               AS win_count,
            COUNT(CASE WHEN order_side = 'sell' AND net_amount < 0 THEN 1 END)               AS loss_count,
            NVL(AVG(CASE WHEN order_side = 'sell' AND net_amount > 0 THEN net_amount END), 0) AS avg_win,
            NVL(AVG(CASE WHEN order_side = 'sell' AND net_amount < 0 THEN net_amount END), 0) AS avg_loss
        FROM executions
        WHERE account_id = :account_id
    """
    trade_row = fetch_one(trade_sql, {"account_id": account_id}) or (0, 0, 0, 0, 0, 0, 0)
    total_trades, buy_count, sell_count, win_count, loss_count, avg_win, avg_loss = trade_row

    avg_win       = float(avg_win  or 0)
    avg_loss      = float(avg_loss or 0)
    profit_factor = round(avg_win / abs(avg_loss), 2) if avg_loss != 0 else 0

    # ── 실현손익 ──────────────────────────────────────────────────────────
    realized_sql = """
        SELECT NVL(SUM(net_amount), 0)
        FROM executions
        WHERE account_id = :account_id
          AND order_side  = 'sell'
    """
    realized_row = fetch_one(realized_sql, {"account_id": account_id}) or (0,)
    realized_pnl = float(realized_row[0] or 0)

    # ── 변동성: 최근 30일 daily_return 표준편차 ───────────────────────────
    volatility_sql = """
        SELECT ROUND(STDDEV(daily_return), 2)
        FROM portfolio_snapshots
        WHERE account_id   = :account_id
          AND snapshot_date >= TRUNC(SYSDATE) - 30
    """
    vol_row = fetch_one(volatility_sql, {"account_id": account_id}) or (0,)
    volatility = float(vol_row[0] or 0)

    # ── 회복 필요 수익률: MDD 기준 peak 복귀에 필요한 수익률 ──────────────
    mdd_val = float(mdd or 0)
    recovery_needed = round(abs(mdd_val) / (100 - abs(mdd_val)) * 100, 2) if mdd_val < 0 else 0.0

    return {
        # 실시간 총평가금액
        "current_total_krw": current_total_krw,
        "current_total_usd": current_total_usd,
        "usdkrw":            usdkrw,
        # 국내/해외 평가액 & 매수금액
        "domestic_stock_value":     domestic_stock_value,
        "domestic_cost":      domestic_cost,
        "overseas_value_usd": overseas_value_usd,
        "overseas_value_krw": overseas_value_krw,
        "overseas_cost":      overseas_cost,
        # 현금
        "cash_krw": cash_krw,
        "cash_usd": cash_usd,
        # 스냅샷 기준 (어제)
        "yesterday_total": float(yesterday_total or 0),
        "daily_return":    float(daily_return    or 0),
        # 기간별 수익률
        "return_1m": float(return_1m or 0),
        "return_3m": float(return_3m or 0),
        "return_6m": float(return_6m or 0),
        # 손익
        "realized_pnl":   realized_pnl,
        "unrealized_pnl": unrealized_pnl,
        # 섹터/종목 집중도
        "sector_concentration": sector_concentration,
        "stock_concentration":  stock_concentration,
        "domestic_ratio": domestic_ratio,
        "foreign_ratio":  foreign_ratio,
        # 리스크
        "mdd":              mdd_val,
        "recovery_needed":  recovery_needed,
        "volatility":       volatility,
        # 종목별 손익
        "best_stock":    best_stock,
        "worst_stock":   worst_stock,
        "stock_returns": stock_returns,
        # 거래 통계
        "total_trades":  int(total_trades or 0),
        "buy_count":     int(buy_count    or 0),
        "sell_count":    int(sell_count   or 0),
        "win_count":     int(win_count    or 0),
        "loss_count":    int(loss_count   or 0),
        "avg_win":       avg_win,
        "avg_loss":      avg_loss,
        "profit_factor": profit_factor,
    }