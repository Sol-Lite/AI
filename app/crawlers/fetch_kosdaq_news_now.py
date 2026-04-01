"""
코스닥 마감시황 즉시 크롤링 스크립트

kosdaq_crawler.py의 스케줄과 관계없이 지금 당장 실행합니다.
이미 DB에 저장된 기사라도 최신 요약으로 덮어씁니다.

실행 방법:
    python -m app.crawlers.fetch_kosdaq_news_now
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import app.crawlers.kosdaq_crawler as _crawler
from app.crawlers.kosdaq_crawler import run_job

KST = timezone(timedelta(hours=9))

if __name__ == "__main__":
    yesterday = datetime.now(KST) - timedelta(days=1)
    with patch.object(_crawler, "datetime") as mock_dt:
        mock_dt.now.return_value = yesterday
        mock_dt.strptime = datetime.strptime
        run_job()