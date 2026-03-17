"""
도구 1: get_market_summary - 시황 요약
TODO: kobart 연동 시 _fetch_news_and_summarize() 내부를 실제 구현으로 교체
"""
from datetime import date as date_type


def get_market_summary(date: str | None = None) -> dict:
    """
    주어진 날짜의 시황 요약을 반환합니다.

    Args:
        date: 조회 날짜 (YYYY-MM-DD). 생략 시 오늘 날짜.

    Returns:
        {
            "date": "2026-03-17",
            "summary": "...",
            "source": "..."
        }
    """
    if date is None:
        date = str(date_type.today())

    # TODO: 실제 뉴스 수집 후 EbanLee/kobart-summary-v3 모델로 요약
    summary_text = _fetch_news_and_summarize(date)

    return {
        "date": date,
        "summary": summary_text,
        "source": "mock",
    }


def _fetch_news_and_summarize(date: str) -> str:
    # TODO: 뉴스 크롤링 → kobart 모델 요약으로 교체
    return (
        f"{date} 기준 시황: 코스피는 전일 대비 0.5% 상승한 2,650포인트를 기록했습니다. "
        "미국 연준의 금리 동결 기조 유지 발표에 따라 외국인 순매수가 이어지며 반도체 업종이 강세를 보였습니다. "
        "삼성전자가 2% 이상 오르며 지수 상승을 이끌었고, 코스닥도 동반 상승했습니다."
    )
