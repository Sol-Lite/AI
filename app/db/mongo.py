from pymongo import MongoClient
from app.core.config import settings

_client = None


def get_mongo_client():
    global _client
    if _client is None:
        _client = MongoClient(settings.MONGO_URI)
    return _client


def get_database():
    client = get_mongo_client()
    return client[settings.MONGO_DB]


def get_news_collection():
    db = get_database()
    return db["news"]