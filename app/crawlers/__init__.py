import threading

from app.crawlers.scheduled_crawler import run_job, load_kospi200, load_nasdaq100, SCHEDULE_INTERVAL

import os as _os

_KOSPI_CSV  = _os.path.join(_os.path.dirname(__file__), "..", "..", "kospi200_targets.csv")
_NASDAQ_CSV = _os.path.join(_os.path.dirname(__file__), "..", "..", "NASDAQ100.csv")

_stop_event = threading.Event()
_thread: threading.Thread | None = None


def _loop():
    try:
        stocks = load_kospi200(_KOSPI_CSV) + load_nasdaq100(_NASDAQ_CSV)
    except Exception as e:
        print(f"[crawler] 종목 파일 로드 실패: {e}")
        stocks = []

    while not _stop_event.is_set():
        try:
            run_job(stocks)
        except Exception as e:
            print(f"[crawler] 사이클 오류: {e}")
        _stop_event.wait(SCHEDULE_INTERVAL)


def start():
    global _thread
    _stop_event.clear()
    _thread = threading.Thread(target=_loop, daemon=True, name="crawler")
    _thread.start()
    print("[crawler] 백그라운드 크롤러 시작")


def stop():
    _stop_event.set()
    if _thread:
        _thread.join(timeout=15)
    print("[crawler] 크롤러 종료")
