"""
도구 2: get_db_data - 내부 DB 조회 (잔고 / 거래내역 / 포트폴리오 분석)
TODO: Oracle 연동 시 _query_*() 함수 내부를 실제 쿼리로 교체
"""
from typing import Literal


def get_db_data(
    type: Literal["balance", "trades", "portfolio"],
    user_context: dict,
    limit: int = 3,
) -> dict:
    """
    내부 DB에서 사용자 데이터를 조회합니다.

    Args:
        type: "balance" | "trades" | "portfolio"
        user_context: 세션에서 주입된 {"user_id": ..., "account_id": ...}
        limit: trades 조회 시 최근 건수 (기본값 3)

    Returns:
        type별 상이한 딕셔너리
    """
    account_id = user_context["account_id"]

    if type == "balance":
        return _query_balance(account_id)
    elif type == "trades":
        return _query_trades(account_id, limit)
    elif type == "portfolio":
        return _query_portfolio(account_id)
    else:
        raise ValueError(f"Unknown type: {type}")


# ── balance ──────────────────────────────────────────────────────────────────
# 잔고
def _query_balance(conn, account_id: str) -> dict:
    sql = """
        SELECT
            cb.currency_code,
            cb.available_amount,
            cb.total_amount
        FROM cash_balances cb
        WHERE cb.account_id = :account_id
    """

    cursor = conn.cursor()
    cursor.execute(sql, {"account_id": account_id})

    rows = cursor.fetchall()

    # 기본값 세팅
    result = {
        "krw_available": 0,
        "krw_total": 0,
        "usd_available": 0,
        "usd_total": 0,
        "total_eval": 0,
    }
    for currency_code, available, total in rows:
        if currency_code == "KRW":
            result["krw_available"] = available
            result["krw_total"] = total
        elif currency_code == "USD":
            result["usd_available"] = available
            result["usd_total"] = total

        # 총합 누적
        result["total_eval"] += total or 0

    return result

# ── trades ───────────────────────────────────────────────────────────────────
# 거래내역
def _query_trades(account_id: str, limit: int) -> dict:
    from app.db.oracle import fetch_one, fetch_all

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
            SELECT i.STOCK_NAME, ex.ORDER_SIDE, ex.PRICE, ex.QUANTITY, ex.EXECUTED_AT
            FROM executions ex
                LEFT JOIN orders o      ON ex.ORDER_ID  = o.ORDER_ID
                LEFT JOIN instruments i ON o.STOCK_CODE = i.STOCK_CODE
            WHERE ex.account_id = :account_id
              AND ex.ORDER_SIDE  = 'buy'
            ORDER BY ex.EXECUTED_AT DESC
            FETCH FIRST :limit ROWS ONLY
        ),
        last_sell AS (
            SELECT i.STOCK_NAME, ex.ORDER_SIDE, ex.PRICE, ex.QUANTITY, ex.EXECUTED_AT
            FROM executions ex
                LEFT JOIN orders o      ON ex.ORDER_ID  = o.ORDER_ID
                LEFT JOIN instruments i ON o.STOCK_CODE = i.STOCK_CODE
            WHERE ex.account_id = :account_id
              AND ex.ORDER_SIDE  = 'sell'
            ORDER BY ex.EXECUTED_AT DESC
            FETCH FIRST :limit ROWS ONLY
        )
        SELECT STOCK_NAME, ORDER_SIDE, PRICE, QUANTITY, EXECUTED_AT FROM last_buy
        UNION ALL
        SELECT STOCK_NAME, ORDER_SIDE, PRICE, QUANTITY, EXECUTED_AT FROM last_sell
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


# ── portfolio ─────────────────────────────────────────────────────────────────
# 포트폴리오
def _query_portfolio(account_id: str) -> dict:
    # TODO: portfolio_snapshots WHERE account_id = :account_id + Redis 실시간 시세로 교체
    return {
        # 누적 수익
        "total_return":    12.3,
        "unrealized_pnl":  320_000,
        "realized_pnl":    150_000,
        "best_stock":  {"name": "삼성전자", "return": 18.2},
        "worst_stock": {"name": "NAVER",   "return": -3.1},
        # 기간별 수익률
        "return_1m": 2.1,
        "return_3m": 5.4,
        "return_6m": 9.8,
        # 섹터/종목 집중도
        "sector_concentration": [
            {"sector": "반도체", "weight": 42},
            {"sector": "IT",    "weight": 28},
            {"sector": "금융",  "weight": 20},
            {"sector": "기타",  "weight": 10},
        ],
        "stock_concentration": [
            {"stock": "삼성전자",  "weight": 35},
            {"stock": "SK하이닉스","weight": 22},
            {"stock": "NAVER",    "weight": 15},
            {"stock": "기타",     "weight": 28},
        ],
        "domestic_ratio": 80,
        "foreign_ratio":  20,
        # 리스크
        "mdd":               -8.3,
        "recovery_needed":    9.1,
        "volatility":         2.1,
        "kospi_volatility":   1.2,
        # 거래 통계
        "total_trades": 20,
        "win_count":    12,
        "loss_count":    8,
        "avg_win":    25_000,
        "avg_loss":   10_000,
        "profit_factor": 2.5,
        # 오늘 실시간
        "yesterday_total": 5_200_000,
        "current_total":   5_350_000,
        "daily_return":    2.88,
    }
