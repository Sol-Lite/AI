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

def get_news_collection():
    db = get_database()
    return db["news"]

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


def get_chat_history(account_id: str, limit: int = 20) -> list[dict]:
    """
    최근 N개 턴을 조회하고 messages를 펼쳐서 Ollama messages 형식으로 반환합니다.
    tool_call 메시지도 포함되어 LLM이 이전 도구 선택 맥락을 파악할 수 있습니다.
    """
    col = get_chat_collection()
    turns = list(
        col.find(
            {"account_id": str(account_id), "messages": {"$exists": True}},
            {"_id": 0, "account_id": 0, "timestamp": 0},
        ).sort("timestamp", DESCENDING).limit(limit)
    )
    turns.reverse()

    flattened = []
    for turn in turns:
        for msg in turn.get("messages", []):
            flattened.append(msg)
    return flattened


# ── 도구 호출 로그 ─────────────────────────────────────────────────────────────

def get_tool_log_collection():
    db = get_database()
    return db["tool_logs"]


def save_tool_log(account_id: str, tool_name: str, args: dict, result: str) -> None:
    """agent가 호출한 도구와 결과를 저장합니다. 환각 여부 디버깅에 활용합니다."""
    col = get_tool_log_collection()
    col.insert_one({
        "account_id": str(account_id),
        "tool_name":  tool_name,
        "args":       args,
        "result":     result,
        "timestamp":  datetime.utcnow(),
    })
