"""
get_db_data - 내부 DB 조회 (잔고 / 거래내역 / 포트폴리오 분석)
"""
from typing import Literal
from app.db.oracle import fetch_one, fetch_all
from AI.app.hardcoding.get_market_data import get_market_data
import requests
def get_trade_data(
    type: Literal[],
    user_context: dict,
    limit: int = 3,
) -> dict:
    """
    내부 DB에서 사용자 데이터를 조회합니다.

    Args:
        type: 
        user_context: 세션에서 주입된 {"user_id": ..., "account_id": ...}
    Returns:
        type별 상이한 딕셔너리
    """
    account_id = user_context["account_id"]

    query_trades(account_id, limit)

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