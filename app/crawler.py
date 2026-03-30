"""
백그라운드 크롤러 — FastAPI lifespan 에서 호출.
app/crawlers/scheduled_crawler.py 의 run_job을 별도 스레드에서 30분 주기로 실행.
"""
import os
import threading

from app.crawlers.scheduled_crawler import (
    run_job,
    load_kospi200,
    load_nasdaq100,
    SCHEDULE_INTERVAL,
)

_CSV_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crawlers")

_stop_event = threading.Event()
_thread: threading.Thread | None = None


def _loop() -> None:
    kospi  = load_kospi200(os.path.join(_CSV_DIR, "kospi200_targets.csv"))
    nasdaq = load_nasdaq100(os.path.join(_CSV_DIR, "NASDAQ100.csv"))
    stocks = kospi + nasdaq
    print(f"[crawler] KOSPI {len(kospi)} + NASDAQ {len(nasdaq)} = 총 {len(stocks)}종목 크롤링 시작")

    while not _stop_event.is_set():
        try:
            run_job(stocks)
        except Exception as e:
            print(f"[crawler] 에러: {e}")
        # SCHEDULE_INTERVAL 동안 대기 (stop 시 즉시 깨어남)
        _stop_event.wait(SCHEDULE_INTERVAL)


def start() -> None:
    global _thread
    _stop_event.clear()
    _thread = threading.Thread(target=_loop, name="news-crawler", daemon=True)
    _thread.start()
    print("[crawler] 백그라운드 스레드 시작")


def stop() -> None:
    _stop_event.set()
    if _thread:
        _thread.join(timeout=15)
    print("[crawler] 중지")
