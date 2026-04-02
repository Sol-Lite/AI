import threading
from datetime import datetime

from app.crawlers.scheduled_crawler import run_job as _run_stock_job, load_kospi200, load_nasdaq100, SCHEDULE_INTERVAL
from app.crawlers.kosdaq_crawler import run_job as _run_kosdaq_job
from app.crawlers.nasdaq_crawler import run_job as _run_nasdaq_job
# TODO: interval 크롤러 파일 삭제 시 아래 두 줄 제거
from app.crawlers.interval_news_crawler import run as _run_interval_news
from app.crawlers.interval_nasdaq_crawler import run as _run_interval_nasdaq

import os as _os

_KOSPI_CSV  = _os.path.join(_os.path.dirname(__file__), "..", "..", "kospi200_targets.csv")
_NASDAQ_CSV = _os.path.join(_os.path.dirname(__file__), "..", "..", "NASDAQ100.csv")

_stop_event = threading.Event()
_threads: list[threading.Thread] = []


# ── 종목 뉴스 크롤러 (30분 주기) ──────────────────────────────
def _stock_loop():
    try:
        stocks = load_kospi200(_KOSPI_CSV) + load_nasdaq100(_NASDAQ_CSV)
    except Exception as e:
        print(f"[crawler/stock] 종목 파일 로드 실패: {e}")
        stocks = []

    while not _stop_event.is_set():
        try:
            _run_stock_job(stocks)
        except Exception as e:
            print(f"[crawler/stock] 사이클 오류: {e}")
        _stop_event.wait(SCHEDULE_INTERVAL)


# ── KOSDAQ 마감시황 크롤러 (매일 16:30) ───────────────────────
def _kosdaq_loop():
    _fired_today: str | None = None

    while not _stop_event.is_set():
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")

        if now.hour == 16 and now.minute >= 30 and _fired_today != today:
            try:
                _run_kosdaq_job()
            except Exception as e:
                print(f"[crawler/kosdaq] 오류: {e}")
            _fired_today = today

        _stop_event.wait(60)  # 1분마다 체크


# ── NASDAQ 오늘장 미리보기 크롤러 (매일 08:40) ────────────────
def _nasdaq_loop():
    _fired_today: str | None = None

    while not _stop_event.is_set():
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")

        if now.hour == 8 and now.minute >= 40 and _fired_today != today:
            try:
                _run_nasdaq_job()
            except Exception as e:
                print(f"[crawler/nasdaq] 오류: {e}")
            _fired_today = today

        _stop_event.wait(60)  # 1분마다 체크


def start():
    _stop_event.clear()
    _threads.clear()

    for target, name in [
        (_stock_loop,          "crawler-stock"),
        (_kosdaq_loop,         "crawler-kosdaq"),
        (_nasdaq_loop,         "crawler-nasdaq"),
        # TODO: interval 크롤러 파일 삭제 시 아래 두 줄 제거
        (lambda: _run_interval_news(_stop_event),   "crawler-interval-news"),
        (lambda: _run_interval_nasdaq(_stop_event), "crawler-interval-nasdaq"),
    ]:
        t = threading.Thread(target=target, daemon=True, name=name)
        t.start()
        _threads.append(t)

    # TODO: interval 크롤러 파일 삭제 시 → 5개를 3개로, 괄호 안 이름도 정리
    print("[crawler] 백그라운드 크롤러 5개 시작 (stock/kosdaq/nasdaq/interval-news/interval-nasdaq)")


def stop():
    _stop_event.set()
    for t in _threads:
        t.join(timeout=15)
    print("[crawler] 크롤러 종료")
