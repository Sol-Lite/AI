import oracledb
from app.core.config import ORACLE_DSN, ORACLE_USER, ORACLE_PASSWORD


def get_oracle_connection():
    """Oracle DB 연결 반환"""
    return oracledb.connect(
        user=ORACLE_USER,
        password=ORACLE_PASSWORD,
        dsn=ORACLE_DSN,
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
