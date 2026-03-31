"""
(8)  한국 시황 요약 조회 — dispatcher 의도: korea_summary → get_market_summary(type="korea")      → format_korea_summary()
(9)  미국 시황 요약 조회 — dispatcher 의도: us_summary    → get_market_summary(type="us")         → format_us_summary()
(10) 종목별 뉴스 요약    — dispatcher 의도: stock_news    → get_market_summary(type="stock_news")  → format_stock_news()

데이터 소스: MongoDB sollite DB
  sollite.news            — 한국(KOSDAQ)/미국(NASDAQ) 시황 (published_at 최신 1건)
  sollite.stock_news      — 종목별 뉴스 요약 (해당 stock_code 최신 3건)
  Oracle instruments      — 한글 종목명 → stock_code 변환 (resolve_stock_code)
"""
import re
from typing import Literal
from app.db.mongo import get_sollite_news_collection, get_sollite_stock_news_collection
from app.db.oracle import resolve_stock_code


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

def _is_valid_stock_code(stock_code: str) -> bool:
    return bool(re.match(r'^[A-Z0-9]{1,10}(\.[A-Z0-9]{1,2})?$', stock_code))


def _fetch_stock_news_summary(stock_code: str | None) -> dict:
    if not stock_code:
        return {
            "stock_code": None,
            "stock_name": None,
            "news": [],
            "error": "stock_code가 필요합니다. (예: 국내 005930, 해외 AAPL.O)",
        }

    if not _is_valid_stock_code(stock_code):
        resolved = resolve_stock_code(stock_code)
        if not resolved:
            return {
                "stock_code": stock_code,
                "stock_name": None,
                "news": [],
                "error": f"'{stock_code}'에 해당하는 종목을 찾을 수 없습니다. 종목명을 정확히 입력해 주세요.",
            }
        stock_code = resolved

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

    # stock_name이 없거나 코드/티커 형태인 경우 → CSV에서 한글 종목명 조회
    if not stock_name or re.match(r'^[A-Z0-9]{1,10}(\.[A-Z0-9]{1,2})?$', stock_name):
        from app.stock_ref import resolve_name_from_code
        stock_name = resolve_name_from_code(stock_code) or stock_name or stock_code

    news = [
        {
            "title":        doc.get("title"),
            "summary":      doc.get("summary"),
            "published_at": _fmt_date(doc.get("published_at")),
        }
        for doc in docs
    ]
    return {"stock_code": stock_code, "stock_name": stock_name, "news": news}
