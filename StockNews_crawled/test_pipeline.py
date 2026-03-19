"""
test_pipeline.py
KOSPI 1개 + NASDAQ 1개 종목으로 파이프라인 1회 실행 테스트
크롤링 → 전처리 → 중복체크 → 요약 → MongoDB 저장
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from naver_stock_news_scraper import (
    load_kospi200, load_nasdaq100,
    crawl_stock_news, deduplicate, collection,
)
from summarizer import summarize_articles

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TARGET = 3


def run_test():
    kospi = load_kospi200(os.path.join(BASE_DIR, "코스피200리스트.xlsx"))
    nasdaq = load_nasdaq100(os.path.join(BASE_DIR, "Nasdaq-100.xlsx"))
    test_stocks = [kospi[0], nasdaq[0]]

    print(f"테스트 종목: {[s['name'] for s in test_stocks]}")
    print(f"종목당 목표 기사: {TARGET}건\n")

    for stock in test_stocks:
        ticker, name = stock["ticker"], stock["name"]
        print(f"{'='*50}")
        print(f"[{ticker}] {name}")

        # 1. 크롤링 + 전처리
        candidates = crawl_stock_news(stock, target=TARGET)
        print(f"  크롤링: {len(candidates)}건")
        assert isinstance(candidates, list), "크롤링 결과가 list가 아님"

        if not candidates:
            print("  → 기사 없음, 스킵")
            continue

        # 2. 중복 체크
        new_articles = deduplicate(candidates)
        print(f"  중복 제거 후: {len(new_articles)}건")
        assert isinstance(new_articles, list), "중복체크 결과가 list가 아님"

        if not new_articles:
            print("  → 모두 중복, 스킵")
            continue

        # 3. 요약
        new_articles = summarize_articles(new_articles)
        assert all("summary" in a for a in new_articles), "summary 필드 누락"
        print(f"  요약 완료: {len(new_articles)}건")

        # 4. MongoDB 저장
        result = collection.insert_many(new_articles)
        assert len(result.inserted_ids) == len(new_articles), "저장 건수 불일치"
        print(f"  MongoDB 저장 완료: {len(result.inserted_ids)}건")

    print(f"\n{'='*50}")
    print("모든 테스트 통과")
    print(f"DB 전체 누적: {collection.count_documents({})}건")


if __name__ == "__main__":
    run_test()
