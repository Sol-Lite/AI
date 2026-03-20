import oracledb
from app.core.config import settings

def get_oracle_connection():
    """
    Oracle DB 연결 반환
    TODO: 실제 서버 연결 정보로 교체
    """
    # TODO: 실제 구현
    # conn = oracledb.connect(
    #     user=settings.ORACLE_USER,
    #     password=settings.ORACLE_PASSWORD,
    #     dsn=f"{settings.ORACLE_HOST}:{settings.ORACLE_PORT}/{settings.ORACLE_SID}"
    # )
    # return conn
    return None  # 현재는 None 반환


def fetch_one(query: str, params: dict = None):
    """단건 조회"""
    # TODO: 실제 구현
    # conn = get_oracle_connection()
    # cursor = conn.cursor()
    # cursor.execute(query, params or {})
    # return cursor.fetchone()
    return None


def fetch_all(query: str, params: dict = None):
    """다건 조회"""
    # TODO: 실제 구현
    # conn = get_oracle_connection()
    # cursor = conn.cursor()
    # cursor.execute(query, params or {})
    # return cursor.fetchall()
    return []


def execute(query: str, params: dict = None):
    """INSERT/UPDATE/DELETE"""
    # TODO: 실제 구현
    # conn = get_oracle_connection()
    # cursor = conn.cursor()
    # cursor.execute(query, params or {})
    # conn.commit()
    pass