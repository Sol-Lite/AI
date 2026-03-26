"""
(11) 거래내역 조회 — Oracle DB
"""
from app.db.oracle import fetch_one, fetch_all

def get_trade_data(user_context: dict, limit: int = 5) -> dict:
    """
    사용자의 거래내역을 Oracle DB에서 조회합니다.

    Args:
        user_context: {"user_id": ..., "account_id": ..., "token": ...}
        limit:        최근 매수/매도 각각 몇 건을 가져올지 (기본 5건)

    Returns:
        {
            "total":      int,
            "buy_count":  int,
            "sell_count": int,
            "recent": [
                {"stock_name": str, "side": str, "price": float,
                 "quantity": int, "executed_at": str},
                ...
            ]
        }
    """
    account_id = user_context["account_id"]
    return _query_trades(account_id, limit)


# ── 내부 구현 ──────────────────────────────────────────────────────────────────

def _query_trades(account_id: str, limit: int) -> dict:
    # 전체 거래 건수 집계
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

    # 최근 매수/매도 각 limit건 (UNION ALL → 최신순 정렬)
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
        SELECT STOCK_NAME, ORDER_SIDE, EXECUTION_PRICE, EXECUTION_QUANTITY, EXECUTED_AT
        FROM last_buy
        UNION ALL
        SELECT STOCK_NAME, ORDER_SIDE, EXECUTION_PRICE, EXECUTION_QUANTITY, EXECUTED_AT
        FROM last_sell
        ORDER BY EXECUTED_AT DESC
    """
    rows = fetch_all(recent_sql, {"account_id": account_id, "limit": limit}) or []
    recent = [
        {
            "stock_name":  row[0],
            "side":        row[1],
            "price":       float(row[2] or 0),
            "quantity":    int(row[3]   or 0),
            "executed_at": str(row[4]),
        }
        for row in rows
    ]

    return {
        "total":      int(total      or 0),
        "buy_count":  int(buy_count  or 0),
        "sell_count": int(sell_count or 0),
        "recent":     recent,
    }
