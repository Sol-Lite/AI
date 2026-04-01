"""
코스닥 마감시황 즉시 크롤링 스크립트

kosdaq_crawler.py의 스케줄과 관계없이 지금 당장 실행합니다.
이미 DB에 저장된 기사라도 최신 요약으로 덮어씁니다.

실행 방법:
    python -m app.crawlers.fetch_kosdaq_news_now
"""

from datetime import datetime

from app.crawlers.kosdaq_crawler import run_job


if __name__ == "__main__":
    run_job()
