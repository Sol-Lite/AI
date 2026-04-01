"""
미국 시황(오늘장 미리보기) 즉시 크롤링 스크립트

nasdaq_crawler.py의 08:40 스케줄과 관계없이 지금 당장 실행합니다.
이미 DB에 저장된 기사라도 최신 요약으로 덮어씁니다.

실행 방법:
    python -m app.crawlers.fetch_us_news_now
"""

import re
from datetime import datetime

from app.crawlers.nasdaq_crawler import (
    fetch_today_article_meta,
    fetch_article_content,
    summarize_with_ollama,
    collection,
)


def run() -> None:
    print(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}] 미국 시황 즉시 크롤링 시작")

    meta = fetch_today_article_meta()
    if not meta:
        print("  오늘 날짜 기사를 찾을 수 없습니다.")
        return

    print(f"  기사: {meta['title'][:60]}")
    print(f"  URL : {meta['url']}")

    content = fetch_article_content(meta["url"])
    if len(content) < 50:
        print("  본문 없음 — 종료")
        return
    print(f"  본문 길이: {len(content)}자")

    print("  요약 중... (Ollama 호출, 최대 3분 소요)")
    summary = summarize_with_ollama(content, meta.get("published_at"))
    if not summary or not summary.get("one_line_summary"):
        print("  요약 실패 — 저장 건너뜀")
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

    collection.update_one(
        {"news_id": meta["news_id"]},
        {"$set": doc},
        upsert=True,
    )
    print(f"  저장 완료: {meta['title'][:60]}")
    print(f"  한줄 요약: {summary.get('one_line_summary', '')}")


if __name__ == "__main__":
    run()