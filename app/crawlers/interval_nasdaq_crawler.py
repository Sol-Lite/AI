"""
한국경제 '[뉴욕 증시 브리핑]' 인터벌 크롤러
- 2분마다 날짜를 하루씩 거슬러 올라가며 해당 날짜 기사 1건씩 처리
  (1회차: 오늘, 2회차: 어제, 3회차: 그제, ...)
- 이미 저장된 기사는 건너뛰고 다음 날짜로 이동
- MongoDB sollite.news 저장 (중복 시 upsert)

실행: python -m app.crawlers.interval_nasdaq_crawler
"""

import re
import threading
import time
from datetime import datetime, timezone, timedelta, date as date_type
from urllib.parse import parse_qs, urlparse

import certifi
import requests
from bs4 import BeautifulSoup
from pymongo import MongoClient

from app.core.config import MONGO_URI
from app.crawlers.nasdaq_crawler import (
    fetch_article_content,
    summarize_with_ollama,
    clean_text,
)

# ── 설정 ─────────────────────────────────────────────────────────
INTERVAL_SECONDS = 120
SEARCH_URL       = "https://search.hankyung.com/search/total"
SEARCH_QUERY     = "[뉴욕 증시 브리핑]"
ARTICLE_BASE     = "https://www.hankyung.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://search.hankyung.com/",
}

KST = timezone(timedelta(hours=9))

# ── MongoDB 연결 ─────────────────────────────────────────────────
def _build_mongo_client(uri: str) -> MongoClient:
    tls_value = parse_qs(urlparse(uri).query).get("tls", [None])[0]
    if tls_value and tls_value.lower() == "false":
        return MongoClient(uri)
    return MongoClient(uri, tlsCAFile=certifi.where())


_client     = _build_mongo_client(MONGO_URI)
_collection = _client["sollite"]["news"]


# ═══════════════════════════════════════════════════════════════
# 특정 날짜의 기사 메타 수집
# ═══════════════════════════════════════════════════════════════
def fetch_article_meta_for_date(target_date: date_type) -> dict | None:
    """target_date 날짜의 뉴욕 증시 브리핑 기사를 최신 1건 반환. 없으면 None."""
    date_str = target_date.strftime("%Y.%m.%d")

    try:
        r = requests.get(
            SEARCH_URL,
            params={"query": SEARCH_QUERY},
            headers=HEADERS,
            timeout=15,
        )
        r.raise_for_status()
    except Exception as e:
        print(f"  검색 페이지 요청 실패: {e}")
        return None

    soup  = BeautifulSoup(r.text, "html.parser")
    items = soup.select("ul.article > li")

    if not items:
        print("  검색 결과 없음")
        return None

    for item in items:
        date_tag = item.select_one(".date, span[class*='date'], time")
        if not date_tag:
            continue
        date_text = date_tag.get_text(strip=True)
        if date_str not in date_text:
            continue

        a_tag = item.select_one("a[href*='/article/']")
        if not a_tag:
            continue
        url = a_tag.get("href", "")
        if not url.startswith("http"):
            url = ARTICLE_BASE + url

        tit_tag = item.select_one(".tit, h2, h3")
        title   = tit_tag.get_text(strip=True) if tit_tag else a_tag.get_text(strip=True)
        news_id = url.rstrip("/").split("/")[-1]

        published_at = datetime.now(KST).replace(tzinfo=None)
        try:
            published_at = datetime.strptime(date_text.strip(), "%Y.%m.%d %H:%M")
        except ValueError:
            pass

        return {
            "news_id":      news_id,
            "title":        title,
            "url":          url,
            "published_at": published_at,
        }

    print(f"  {date_str} 날짜 기사 없음")
    return None


# ═══════════════════════════════════════════════════════════════
# 기사 1건 처리 — 본문 수집 → 요약 → MongoDB upsert
# ═══════════════════════════════════════════════════════════════
def _process_one(meta: dict) -> None:
    print(f"  처리 중: {meta['title'][:50]}")
    print(f"  URL : {meta['url']}")

    content = fetch_article_content(meta["url"])
    if len(content) < 50:
        print("  본문 없음 — 건너뜀")
        return

    summary = summarize_with_ollama(content, meta.get("published_at"))
    if not summary:
        print("  유효한 요약이 없어 저장 건너뜀")
        return

    clean_title = re.sub(r'\[뉴욕\s*증시\s*브리핑\]\s*', '', meta["title"]).strip()

    doc = {
        "news_id":      meta["news_id"],
        "title":        clean_title,
        "content":      content,
        "summary":      summary,
        "source":       "hankyung",
        "stock_index":  "NASDAQ",
        "source_url":   meta["url"],
        "published_at": meta["published_at"],
        "fetched_at":   datetime.now(),
    }
    _collection.update_one(
        {"news_id": doc["news_id"]},
        {"$set": doc},
        upsert=True,
    )
    print(f"  저장 완료: {clean_title[:50]}")


# ═══════════════════════════════════════════════════════════════
# 메인 루프
# ═══════════════════════════════════════════════════════════════
def run(stop_event: threading.Event | None = None) -> None:
    if stop_event is None:
        stop_event = threading.Event()

    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 나스닥 인터벌 크롤러 시작 (간격: {INTERVAL_SECONDS // 60}분)")

    day_offset = 0  # 0=오늘, 1=어제, 2=그제, ...

    while not stop_event.is_set():
        target_date = datetime.now(KST).date() - timedelta(days=day_offset)
        print(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}] {target_date} 기사 수집 중...")

        meta = fetch_article_meta_for_date(target_date)

        if not meta:
            print(f"  {target_date} 기사 없음 — 다음 날짜로 이동")
            day_offset += 1
            stop_event.wait(INTERVAL_SECONDS)
            continue

        if _collection.find_one({"news_id": meta["news_id"]}):
            print(f"  이미 저장된 기사 — 다음 날짜로 이동")
            day_offset += 1
            stop_event.wait(INTERVAL_SECONDS)
            continue

        try:
            _process_one(meta)
        except Exception as e:
            print(f"  처리 실패: {e}")

        day_offset += 1
        stop_event.wait(INTERVAL_SECONDS)


if __name__ == "__main__":
    run()
