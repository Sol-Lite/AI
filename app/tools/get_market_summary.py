"""
도구 1: get_market_summary - 시황 요약
TODO: kobart 연동 시 _fetch_news_and_summarize() 내부를 실제 구현으로 교체
"""
from datetime import date as date_type, datetime, time, timedelta
from app.db.mongo import get_news_collection

_NEWS_LIMIT = 5
_NEWS_PROJECTION = {"title": 1, "summary": 1, "_id": 0}


def _published_at_day_filter(date_str: str) -> dict:
    """DB는 `date` 문자열이 아니라 `published_at`(naive datetime)으로 저장됨."""
    d = date_type.fromisoformat(date_str)
    start = datetime.combine(d, time.min)
    end = datetime.combine(d + timedelta(days=1), time.min)
    return {"published_at": {"$gte": start, "$lt": end}}


def get_market_summary(date: str | None = None) -> dict:
    """
    주어진 날짜의 시황 요약을 반환합니다.

    Args:
        date: 조회 날짜 (YYYY-MM-DD). 생략 시 오늘 날짜.

    Returns:
        {
            "date": "2026-03-17",
            "title": ["...", ...],
            "summary": ["...", ...],
            "count": 5,
            "source": "..."
        }
    """
    if date is None:
        date = str(date_type.today())
    col = get_news_collection()

    docs = list(
        col.find(_published_at_day_filter(date), _NEWS_PROJECTION)
        .sort("published_at", -1)
        .limit(_NEWS_LIMIT)
    )

    titles: list[str] = []
    summaries: list[str] = []
    print(titles)
    print(summaries)
    for doc in docs:
        titles.append((doc.get("title") or "").strip())
        summaries.append((doc.get("summary") or "").strip())

    return {
        "date": date,
        "title": titles,
        "summary": summaries,
        "count": len(docs),
        "source": "db-test",
    }


if __name__ == "__main__":
    result = get_market_summary("2026-03-19")
    print(result)
