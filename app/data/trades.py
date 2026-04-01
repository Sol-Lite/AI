"""
(11) 거래내역 tools — Oracle DB

tools:
    get_trade_summary     — 총 거래 횟수, 매수/매도 횟수
    get_recent_trades     — 최근 N건 거래 목록
    get_trades_by_stock   — 특정 종목의 거래 내역
    get_trades_by_date    — 특정 날짜의 거래 내역

template:
    get_trades_template_data — 위 함수들을 조합해 format_trades() 입력용 dict 반환
"""
from app.db.oracle import fetch_one, fetch_all


def get_trade_summary(account_id: str) -> dict:
    """총 거래 횟수, 매수 횟수, 매도 횟수를 반환합니다."""
    sql = """
        SELECT
            COUNT(DISTINCT ORDER_ID)                                             AS total,
            COUNT(DISTINCT CASE WHEN ORDER_SIDE = 'BUY'  THEN ORDER_ID END)     AS buy_count,
            COUNT(DISTINCT CASE WHEN ORDER_SIDE = 'SELL' THEN ORDER_ID END)     AS sell_count
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
            ex.EXECUTED_AT,
            i.MARKET_TYPE
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
                "side":        row[1].lower() if row[1] else row[1],
                "price":       float(row[2] or 0),
                "quantity":    int(row[3]   or 0),
                "amount":      float(row[2] or 0) * int(row[3] or 0),
                "executed_at": str(row[4]),
                "market_type": str(row[5] or "").upper(),
            }
            for row in rows
        ]
    }


def get_trades_by_date(account_id: str, date: str, side: str | None = None) -> dict:
    """특정 날짜의 거래 내역을 반환합니다. side='sell'이면 매도만, side='buy'이면 매수만 반환합니다."""
    import re
    date = date.strip()
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})', date)
    if not m:
        m = re.match(r'(\d{1,2})월\s*(\d{1,2})일', date)
        if m:
            from datetime import date as _date
            _year = _date.today().year
            date = f"{_year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
        else:
            m = re.match(r'(\d{1,2})-(\d{1,2})', date)
            if m:
                from datetime import date as _date
                _year = _date.today().year
                date = f"{_year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"

    side_filter = ""
    params: dict = {"account_id": account_id, "trade_date": date}
    if side and side.upper() in ("BUY", "SELL"):
        side_filter = "AND ex.ORDER_SIDE = :side"
        params["side"] = side.upper()

    sql = f"""
        SELECT
            i.STOCK_NAME,
            ex.ORDER_SIDE,
            ex.EXECUTION_PRICE,
            ex.EXECUTION_QUANTITY,
            ex.EXECUTED_AT,
            i.MARKET_TYPE
        FROM executions ex
        LEFT JOIN instruments i ON ex.INSTRUMENT_ID = i.INSTRUMENT_ID
        WHERE ex.account_id = :account_id
          AND TRUNC(ex.EXECUTED_AT) = TO_DATE(:trade_date, 'YYYY-MM-DD')
          {side_filter}
        ORDER BY ex.EXECUTED_AT DESC
    """
    rows = fetch_all(sql, params) or []
    return {
        "date":  date,
        "count": len(rows),
        "trades": [
            {
                "stock_name":  row[0],
                "side":        row[1].lower() if row[1] else row[1],
                "price":       float(row[2] or 0),
                "quantity":    int(row[3]   or 0),
                "amount":      float(row[2] or 0) * int(row[3] or 0),
                "executed_at": str(row[4]),
                "market_type": str(row[5] or "").upper(),
            }
            for row in rows
        ],
    }


def get_trades_template_data(account_id: str) -> dict:
    """템플릿 출력용 거래내역 요약 데이터를 반환합니다. format_trades() 입력 형식."""
    summary = get_trade_summary(account_id)
    recent  = get_recent_trades(account_id, limit=5)
    return {
        "total":      summary["total"],
        "buy_count":  summary["buy_count"],
        "sell_count": summary["sell_count"],
        "recent":     recent["trades"],
    }


def get_trades_by_stock(account_id: str, stock_code: str) -> dict:
    """특정 종목의 전체 거래 내역을 반환합니다."""
    sql = """
        SELECT
            i.STOCK_NAME,
            ex.ORDER_SIDE,
            ex.EXECUTION_PRICE,
            ex.EXECUTION_QUANTITY,
            ex.EXECUTED_AT,
            i.MARKET_TYPE
        FROM executions ex
        LEFT JOIN instruments i ON ex.INSTRUMENT_ID = i.INSTRUMENT_ID
        WHERE ex.account_id  = :account_id
          AND (i.STOCK_CODE = :stock_code OR i.STOCK_NAME = :stock_code)
        ORDER BY ex.EXECUTED_AT DESC
    """
    rows = fetch_all(sql, {"account_id": account_id, "stock_code": stock_code}) or []
    stock_name = rows[0][0] if rows else stock_code
    market_type = str(rows[0][5] or "").upper() if rows else ""
    return {
        "stock_code":  stock_code,
        "stock_name":  stock_name,
        "market_type": market_type,
        "count":       len(rows),
        "trades": [
            {
                "side":        row[1].lower() if row[1] else row[1],
                "price":       float(row[2] or 0),
                "quantity":    int(row[3]   or 0),
                "executed_at": str(row[4]),
                "market_type": str(row[5] or "").upper(),
            }
            for row in rows
        ],
    }
