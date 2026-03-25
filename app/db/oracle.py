import oracledb
from app.core.config import ORACLE_DSN, ORACLE_USER, ORACLE_PASSWORD


def get_oracle_connection():
    """Oracle DB 연결 반환"""
    return oracledb.connect(
        user=ORACLE_USER,
        password=ORACLE_PASSWORD,
        dsn=ORACLE_DSN,
        ssl_server_dn_match=False,
    )


def fetch_one(query: str, params: dict = None):
    """단건 조회"""
    with get_oracle_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, params or {})
            return cursor.fetchone()


def fetch_all(query: str, params: dict = None):
    """다건 조회"""
    with get_oracle_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, params or {})
            return cursor.fetchall()


def execute(query: str, params: dict = None):
    """INSERT/UPDATE/DELETE"""
    with get_oracle_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, params or {})
        conn.commit()


def resolve_stock_code(name: str) -> str | None:
    """
    종목명으로 instruments 테이블에서 STOCK_CODE를 조회합니다.
    STOCK_NAME(한글), STOCK_NAME_EN(영문) 두 열을 LIKE로 검색하며,
    정확히 일치하는 결과를 우선 반환합니다.

    Args:
        name: 종목명 (예: "삼성전자", "SK하이닉스", "Apple")
    Returns:
        STOCK_CODE 문자열 또는 None (매칭 없을 때)
    """
    row = fetch_one(
        """
        SELECT STOCK_CODE FROM instruments
        WHERE UPPER(TRIM(STOCK_NAME))    LIKE UPPER(:pattern)
           OR UPPER(TRIM(STOCK_NAME_EN)) LIKE UPPER(:pattern)
        ORDER BY
            CASE
                WHEN UPPER(TRIM(STOCK_NAME))    = UPPER(:name) THEN 0
                WHEN UPPER(TRIM(STOCK_NAME_EN)) = UPPER(:name) THEN 1
                ELSE 2
            END
        FETCH FIRST 1 ROWS ONLY
        """,
        {"pattern": f"%{name.strip()}%", "name": name.strip()},
    )
    return row[0] if row else None
