import oracledb
from app.core.config import ORACLE_DSN, ORACLE_USER, ORACLE_PASSWORD

_pool: oracledb.ConnectionPool | None = None


def _create_pool() -> oracledb.ConnectionPool:
    return oracledb.create_pool(
        user=ORACLE_USER,
        password=ORACLE_PASSWORD,
        dsn=ORACLE_DSN,
        ssl_server_dn_match=False,
        min=0,           # 유휴 커넥션 사전 생성 안 함 (서버 측 idle timeout 방지)
        max=10,
        increment=1,
        ping_interval=-1,  # acquire 시 항상 유효성 검증
    )


def _get_pool() -> oracledb.ConnectionPool:
    global _pool
    if _pool is None:
        _pool = _create_pool()
    return _pool


def get_oracle_connection():
    """커넥션 풀에서 연결 반환 (DPY-4011 시 풀 재생성 후 1회 재시도)"""
    global _pool
    try:
        return _get_pool().acquire()
    except oracledb.DatabaseError as e:
        if "DPY-4011" in str(e):
            try:
                if _pool is not None:
                    _pool.close(force=True)
            except Exception:
                pass
            _pool = None
            return _get_pool().acquire()
        raise


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
