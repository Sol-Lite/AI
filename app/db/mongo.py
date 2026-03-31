from datetime import datetime
from pymongo import MongoClient, DESCENDING
from app.core.config import MONGO_URI, MONGO_DB

_client = None

def get_mongo_client():
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URI)
    return _client

def get_database():
    client = get_mongo_client()
    return client[MONGO_DB]

def get_sollite_news_collection():
    client = get_mongo_client()
    return client["sollite"]["news"]

def get_sollite_stock_news_collection():
    client = get_mongo_client()
    return client["sollite"]["stock_news"]


# ── 채팅 기록 ──────────────────────────────────────────────────────────────────

def get_chat_collection():
    db = get_database()
    return db["chat_history"]


def save_conversation_turn(account_id: str, messages: list[dict]) -> None:
    """
    한 턴의 모든 메시지를 단일 document로 저장합니다.
    messages 예시:
        [
            {"role": "user", "content": "현차 현재가"},
            {"role": "assistant", "tool_calls": [...]},
            {"role": "tool", "name": "get_stock_price", "content": "..."},
            {"role": "assistant", "content": "현대차 현재가는 495,000원입니다."},
        ]
    """
    if not messages:
        return
    col = get_chat_collection()
    col.insert_one({
        "account_id": str(account_id),
        "timestamp":  datetime.utcnow(),
        "messages":   messages,
    })


def get_chat_history(account_id: str, limit: int = 20, since: datetime | None = None) -> list[dict]:
    """
    최근 N개 턴을 조회하고 messages를 펼쳐서 Ollama messages 형식으로 반환합니다.
    tool_call 메시지도 포함되어 LLM이 이전 도구 선택 맥락을 파악할 수 있습니다.

    since: 이 시각 이후의 메시지만 반환 (로그인 세션 분리에 사용)
    """
    col = get_chat_collection()
    query: dict = {"account_id": str(account_id), "messages": {"$exists": True}}
    if since is not None:
        since_dt = datetime.utcfromtimestamp(since) if isinstance(since, (int, float)) else since
        query["timestamp"] = {"$gte": since_dt}
    turns = list(
        col.find(
            query,
            {"_id": 0, "account_id": 0, "timestamp": 0},
        ).sort("timestamp", DESCENDING).limit(limit)
    )
    turns.reverse()

    flattened = []
    for turn in turns:
        for msg in turn.get("messages", []):
            flattened.append(msg)
    return flattened
