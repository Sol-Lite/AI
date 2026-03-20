import redis
from app.core.config import settings

def get_redis_client():
    """
    Redis 클라이언트 반환
    TODO: 실제 서버 연결 정보로 교체
    """
    # TODO: 실제 구현
    # return redis.Redis(
    #     host=settings.REDIS_HOST,
    #     port=settings.REDIS_PORT,
    #     db=0,
    #     decode_responses=True
    # )
    return None


def get_cache(key: str):
    """캐시 조회"""
    # TODO: 실제 구현
    # client = get_redis_client()
    # return client.get(key)
    return None


def set_cache(key: str, value: str, ttl: int = 60):
    """캐시 저장"""
    # TODO: 실제 구현
    # client = get_redis_client()
    # client.setex(key, ttl, value)
    pass


def delete_cache(key: str):
    """캐시 삭제"""
    # TODO: 실제 구현
    # client = get_redis_client()
    # client.delete(key)
    pass