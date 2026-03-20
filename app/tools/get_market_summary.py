"""
도구 1: get_market_summary - 시황 요약 및 종목별 뉴스 요약
"""
from typing import Literal
from app.db.mongo import get_sollite_news_collection


def get_market_summary(
    type: Literal["korea", "us", "stock_news"],
    stock_code: str | None = None,
) -> dict:
    """
    시황 요약 및 종목별 뉴스 요약을 반환합니다.

    Args:
        type: "korea" | "us" | "stock_news"
        stock_code: 종목 코드 (stock_news 시 필요, 예: "005930")
    """
    if type == "korea":
        return _fetch_korea_summary()
    elif type == "us":
        return _fetch_us_summary()
    elif type == "stock_news":
        return _fetch_stock_news_summary(stock_code)
    else:
        raise ValueError(f"Unknown type: {type}")


# ── korea ─────────────────────────────────────────────────────────────────────

def _fetch_korea_summary() -> dict:
    col = get_sollite_news_collection()
    doc = col.find_one(
        {"stock_index": "KOSDAQ"},
        {"summary": 1, "_id": 0},
        sort=[("published_at", -1)],
    )
    return {"stock_index": "KOSDAQ", "summary": doc.get("summary") if doc else None}


# ── us ────────────────────────────────────────────────────────────────────────

def _fetch_us_summary() -> dict:
    col = get_sollite_news_collection()
    doc = col.find_one(
        {"stock_index": "NASDAQ"},
        {"summary": 1, "_id": 0},
        sort=[("published_at", -1)],
    )
    return {"stock_index": "NASDAQ", "summary": doc.get("summary") if doc else None}


# ── stock_news ────────────────────────────────────────────────────────────────

def _fetch_stock_news_summary(stock_code: str | None) -> dict:
    col = get_sollite_news_collection()
    docs = list(
        col.find(
            {"stock_code": stock_code},
            {"title": 1, "summary": 1, "_id": 0},
        )
        .sort("published_at", -1)
        .limit(3)
    )
    news = [{"title": doc.get("title"), "summary": doc.get("summary")} for doc in docs]
    return {"stock_code": stock_code, "news": news}


if __name__ == "__main__":
    print(get_market_summary("korea"))
    print(get_market_summary("us"))
    print(get_market_summary("stock_news", stock_code="005930"))
