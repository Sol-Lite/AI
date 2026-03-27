"""
(11) 거래내역 agent tools — Oracle DB

llama가 tool calling으로 선택해서 호출하는 개별 함수들.
전체 데이터를 한 번에 가져오지 않고 질문에 필요한 함수만 호출합니다.

tools:
    get_trade_summary     — 총 거래 횟수, 매수/매도 횟수
    get_recent_trades     — 최근 N건 거래 목록
    get_trades_by_stock   — 특정 종목의 거래 내역
"""
from app.db.oracle import fetch_one, fetch_all


def get_trade_summary(account_id: str) -> dict:
    """총 거래 횟수, 매수 횟수, 매도 횟수를 반환합니다."""
    sql = """
        SELECT
            COUNT(DISTINCT ORDER_ID)                                             AS total,
            COUNT(DISTINCT CASE WHEN ORDER_SIDE = 'buy'  THEN ORDER_ID END)     AS buy_count,
            COUNT(DISTINCT CASE WHEN ORDER_SIDE = 'sell' THEN ORDER_ID END)     AS sell_count
        FROM executions
        WHERE account_id = :account_id
    """
    row = fetch_one(sql, {"account_id": account_id}) or (0, 0, 0)
    return {
        "total":      int(row[0] or 0),
        "buy_count":  int(row[1] or 0),
        "sell_count": int(row[2] or 0),
    }


def get_recent_trades(account_id: str, limit: int = 10) -> dict:
    """최근 거래 내역 목록을 반환합니다."""
    sql = """
        SELECT
            i.STOCK_NAME,
            ex.ORDER_SIDE,
            ex.EXECUTION_PRICE,
            ex.EXECUTION_QUANTITY,
            ex.EXECUTED_AT
        FROM executions ex
        LEFT JOIN instruments i ON ex.INSTRUMENT_ID = i.INSTRUMENT_ID
        WHERE ex.account_id = :account_id
        ORDER BY ex.EXECUTED_AT DESC
        FETCH FIRST :limit ROWS ONLY
    """
    rows = fetch_all(sql, {"account_id": account_id, "limit": limit}) or []
    return {
        "trades": [
            {
                "stock_name":  row[0],
                "side":        row[1],
                "price":       float(row[2] or 0),
                "quantity":    int(row[3]   or 0),
                "amount":      float(row[2] or 0) * int(row[3] or 0),
                "executed_at": str(row[4]),
            }
            for row in rows
        ]
    }


def get_trades_by_stock(account_id: str, stock_code: str) -> dict:
    """특정 종목의 전체 거래 내역을 반환합니다."""
    sql = """
        SELECT
            i.STOCK_NAME,
            ex.ORDER_SIDE,
            ex.EXECUTION_PRICE,
            ex.EXECUTION_QUANTITY,
            ex.EXECUTED_AT
        FROM executions ex
        LEFT JOIN instruments i ON ex.INSTRUMENT_ID = i.INSTRUMENT_ID
        WHERE ex.account_id  = :account_id
          AND i.STOCK_CODE   = :stock_code
        ORDER BY ex.EXECUTED_AT DESC
    """
    rows = fetch_all(sql, {"account_id": account_id, "stock_code": stock_code}) or []
    stock_name = rows[0][0] if rows else stock_code
    return {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "count":      len(rows),
        "trades": [
            {
                "side":        row[1],
                "price":       float(row[2] or 0),
                "quantity":    int(row[3]   or 0),
                "executed_at": str(row[4]),
            }
            for row in rows
        ],
    }
