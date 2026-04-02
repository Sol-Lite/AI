"""
news2day.co.kr 마감시황 인터벌 크롤러
- 5분마다 날짜를 하루씩 거슬러 올라가며 해당 날짜 기사 1건씩 처리
  (1회차: 오늘, 2회차: 어제, 3회차: 그제, ...)
- 이미 저장된 기사는 건너뛰고 다음 날짜로 이동
- MongoDB sollite.news 저장 (중복 시 upsert)

실행: python -m app.crawlers.interval_news_crawler
"""

import threading
import time
from datetime import datetime, timezone, timedelta, date as date_type

import certifi
import requests
from pymongo import MongoClient

from app.core.config import MONGO_URI
from app.crawlers.kosdaq_crawler import (
    parse_html_content,
    summarize_with_ollama,
)

# ── 설정 ─────────────────────────────────────────────────────────
INTERVAL_SECONDS = 120
SEARCH_API_URL   = "https://www.news2day.co.kr/rest/search"
ARTICLE_BASE_URL = "https://www.news2day.co.kr"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://www.news2day.co.kr/search?searchText=%EB%A7%88%EA%B0%90%EC%8B%9C%ED%99%A9",
}

KST = timezone(timedelta(hours=9))

# ── MongoDB 연결 ─────────────────────────────────────────────────
_client     = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
_collection = _client["sollite"]["news"]


# ═══════════════════════════════════════════════════════════════
# 특정 날짜의 기사 1건 수집
# ═══════════════════════════════════════════════════════════════
def fetch_article_for_date(target_date: date_type) -> dict | None:
    """target_date 날짜의 마감시황 기사를 최신 1건 반환. 없으면 None."""
    date_str = target_date.strftime("%Y-%m-%d")
    params = {
        "searchText": "마감시황",
        "searchType": "all",
        "from":       date_str,
        "to":         date_str,
        "page":       1,
        "sort":       "latest",
    }
    try:
        r = requests.get(SEARCH_API_URL, params=params, headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"  API 요청 실패 ({date_str}): {e}")
        return None

    items = data.get("list", [])
    if not items:
        return None

    # 첫 번째(최신) 기사 사용
    item             = items[0]
    article_id       = item.get("id", "")
    title            = item.get("title", "").replace("[마감시황]", "").replace("(마감시황)", "").strip()
    raw_html         = item.get("content", "")
    link             = item.get("link", "")
    release_date_str = item.get("releaseDate") or item.get("firstReleaseDate", "")

    published_at = datetime.now(KST).replace(tzinfo=None)
    if release_date_str:
        try:
            dt_utc       = datetime.strptime(release_date_str[:19], "%Y-%m-%dT%H:%M:%S")
            dt_utc       = dt_utc.replace(tzinfo=timezone.utc)
            published_at = dt_utc.astimezone(KST).replace(tzinfo=None)
        except ValueError:
            pass

    if not raw_html:
        return None
    content = parse_html_content(raw_html)
    if len(content) < 50:
        return None

    return {
        "news_id":      article_id,
        "title":        title,
        "content":      content,
        "source":       "news2day",
        "stock_index":  "KOSDAQ",
        "source_url":   ARTICLE_BASE_URL + link if link else "",
        "published_at": published_at,
    }


# ═══════════════════════════════════════════════════════════════
# 기사 1건 처리 — 요약 후 MongoDB upsert
# ═══════════════════════════════════════════════════════════════
def _process_one(article: dict) -> None:
    print(f"  처리 중: {article['title'][:50]}")
    summary = summarize_with_ollama(article["content"], article.get("published_at"))
    doc = {
        **article,
        "summary":    summary,
        "fetched_at": datetime.now(),
    }
    _collection.update_one(
        {"news_id": doc["news_id"]},
        {"$set": doc},
        upsert=True,
    )
    print(f"  저장 완료: {article['title'][:50]}")


# ═══════════════════════════════════════════════════════════════
# 메인 루프
# ═══════════════════════════════════════════════════════════════
def run(stop_event: threading.Event | None = None) -> None:
    if stop_event is None:
        stop_event = threading.Event()

    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 인터벌 크롤러 시작 (간격: {INTERVAL_SECONDS // 60}분)")

    day_offset = 0  # 0=오늘, 1=어제, 2=그제, ...

    while not stop_event.is_set():
        target_date = datetime.now(KST).date() - timedelta(days=day_offset)
        print(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}] {target_date} 기사 수집 중...")

        article = fetch_article_for_date(target_date)

        if not article:
            print(f"  {target_date} 기사 없음 — 다음 날짜로 이동")
            day_offset += 1
            stop_event.wait(INTERVAL_SECONDS)
            continue

        if _collection.find_one({"news_id": article["news_id"]}):
            print(f"  이미 저장된 기사 — 다음 날짜로 이동")
            day_offset += 1
            stop_event.wait(INTERVAL_SECONDS)
            continue

        try:
            _process_one(article)
        except Exception as e:
            print(f"  처리 실패: {e}")

        day_offset += 1
        stop_event.wait(INTERVAL_SECONDS)


if __name__ == "__main__":
    run()
