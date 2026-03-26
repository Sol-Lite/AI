from pymongo import MongoClient
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