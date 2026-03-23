"""
도구 1: get_market_summary - 내부 DB 조회 (시황 요약 및 종목별 뉴스 요약)
"""
from typing import Literal
from app.db.mongo import get_sollite_news_collection, get_sollite_stock_news_collection


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

def _fmt_date(published_at) -> str | None:
    if not published_at:
        return None
    return published_at.strftime("%Y년 %m월 %d일")


def _fetch_korea_summary() -> dict:
    col = get_sollite_news_collection()
    doc = col.find_one(
        {"stock_index": "KOSDAQ"},
        {"summary": 1, "published_at": 1, "_id": 0},
        sort=[("published_at", -1)],
    )
    if not doc:
        return {"stock_index": "KOSDAQ", "summary": None, "published_at": None}
    return {
        "stock_index":  "KOSDAQ",
        "summary":      doc.get("summary"),
        "published_at": _fmt_date(doc.get("published_at")),
    }


# ── us ────────────────────────────────────────────────────────────────────────

def _fetch_us_summary() -> dict:
    col = get_sollite_news_collection()
    doc = col.find_one(
        {"stock_index": "NASDAQ"},
        {"summary": 1, "published_at": 1, "_id": 0},
        sort=[("published_at", -1)],
    )
    if not doc:
        return {"stock_index": "NASDAQ", "summary": None, "published_at": None}
    return {
        "stock_index":  "NASDAQ",
        "summary":      doc.get("summary"),
        "published_at": _fmt_date(doc.get("published_at")),
    }


# ── stock_news ────────────────────────────────────────────────────────────────

# def _fetch_stock_news_summary(stock_code: str | None) -> dict:
#     col = get_sollite_stock_news_collection()
#     docs = list( 
#         col.find(
#             {"stock_code": stock_code},
#             {"title": 1, "summary": 1, "published_at": 1, "stock_name": 1, "_id": 0},
#         )
#         .sort("published_at", -1)
#         .limit(3)
#     )
#     stock_name = docs[0].get("stock_name") if docs else None
#     news = [
#         {
#             "title":        doc.get("title"),
#             "summary":      doc.get("summary"),
#             "published_at": _fmt_date(doc.get("published_at")),
#         }
#         for doc in docs
#     ]
#     return {"stock_code": stock_code, "stock_name": stock_name, "news": news}


# 종목 코드 유효성 검증 함수 분리
def _is_valid_stock_code(stock_code: str) -> bool:
    """
    유효한 종목 코드 형식 검증
    - 국내: 6자리 숫자 (005930)
    - 해외: 영문+숫자 조합, 점(.) 허용 (AAPL.O, TSLA, MSFT)
    """
    import re
    return bool(re.match(r'^[A-Z0-9]{1,10}(\.[A-Z0-9]{1,2})?$', stock_code))


def _fetch_stock_news_summary(stock_code: str | None) -> dict:
    # stock_code 누락 방어
    if not stock_code:
        return {
            "stock_code": None,
            "stock_name": None,
            "news": [],
            "error": "stock_code가 필요합니다. (예: 국내 005930, 해외 AAPL.O)",
        }

    # 종목명이 한글로 그대로 넘어온 경우 방어
    if not _is_valid_stock_code(stock_code):
        return {
            "stock_code": stock_code,
            "stock_name": None,
            "news": [],
            "error": f"'{stock_code}'는 유효한 종목 코드가 아닙니다. (예: 국내 005930, 해외 AAPL.O)",
        }

    col = get_sollite_stock_news_collection()
    docs = list(
        col.find(
            {"stock_code": stock_code},
            {
                "title": 1,
                "summary": 1,
                "published_at": 1,
                "stock_name": 1,
                "_id": 0,
            },
        )
        .sort("published_at", -1)
        .limit(3)
    )

    stock_name = docs[0].get("stock_name") if docs else None
    news = [
        {
            "title":        doc.get("title"),
            "summary":      doc.get("summary"),
            "published_at": _fmt_date(doc.get("published_at")),
        }
        for doc in docs
    ]
    return {"stock_code": stock_code, "stock_name": stock_name, "news": news}