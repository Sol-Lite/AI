"""
get_market_data.py API 연동 전체 테스트
실행: python test_market_data_api.py
"""
import sys
import io
from datetime import date, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from app.tools.get_market_data import (
    _fetch_price,
    _fetch_daily,
    _fetch_period_chart,
    _fetch_ranking,
    _fetch_index,
    _fetch_exchange,
)

TODAY = str(date.today())
MONTH_AGO = str(date.today() - timedelta(days=30))

CASES = [
    # (설명, 함수, args)
    # ── price ──────────────────────────────────────────────
    ("price / 삼성전자 (국내)",      _fetch_price,        ("005930", "domestic")),
    ("price / 애플 (해외)",          _fetch_price,        ("AAPL",   "overseas")),

    # ── daily ──────────────────────────────────────────────
    ("daily / 삼성전자 오늘",        _fetch_daily,        ("005930", TODAY)),
    ("daily / SK하이닉스 오늘",      _fetch_daily,        ("000660", TODAY)),

    # ── period_chart ───────────────────────────────────────
    ("period_chart / 삼성전자 일봉", _fetch_period_chart, ("005930", "DAILY",   MONTH_AGO, TODAY)),
    ("period_chart / 삼성전자 주봉", _fetch_period_chart, ("005930", "WEEKLY",  MONTH_AGO, TODAY)),
    ("period_chart / 삼성전자 월봉", _fetch_period_chart, ("005930", "MONTHLY", MONTH_AGO, TODAY)),

    # ── ranking ────────────────────────────────────────────
    ("ranking / 거래대금 전체",      _fetch_ranking,      ("trading-value",  "all")),
    ("ranking / 거래대금 코스피",    _fetch_ranking,      ("trading-value",  "kospi")),
    ("ranking / 거래대금 코스닥",    _fetch_ranking,      ("trading-value",  "kosdaq")),
    ("ranking / 거래량 전체",        _fetch_ranking,      ("trading-volume", "all")),
    ("ranking / 거래량 코스피",      _fetch_ranking,      ("trading-volume", "kospi")),
    ("ranking / 거래량 코스닥",      _fetch_ranking,      ("trading-volume", "kosdaq")),
    ("ranking / 상승률 전체",        _fetch_ranking,      ("rising",         "all")),
    ("ranking / 상승률 코스피",      _fetch_ranking,      ("rising",         "kospi")),
    ("ranking / 상승률 코스닥",      _fetch_ranking,      ("rising",         "kosdaq")),
    ("ranking / 하락률 전체",        _fetch_ranking,      ("falling",        "all")),
    ("ranking / 하락률 코스피",      _fetch_ranking,      ("falling",        "kospi")),
    ("ranking / 하락률 코스닥",      _fetch_ranking,      ("falling",        "kosdaq")),
    ("ranking / 시가총액 전체",      _fetch_ranking,      ("market-cap",     "all")),
    ("ranking / 시가총액 코스피",    _fetch_ranking,      ("market-cap",     "kospi")),
    ("ranking / 시가총액 코스닥",    _fetch_ranking,      ("market-cap",     "kosdaq")),

    # ── index ──────────────────────────────────────────────
    ("index / 전체 지수",            _fetch_index,        ()),

    # ── exchange ───────────────────────────────────────────
    ("exchange / 원달러",            _fetch_exchange,     ("USDKRW",)),
    ("exchange / 유로원",            _fetch_exchange,     ("EURKRW",)),
]


def _summarize(label: str, data):
    if isinstance(data, dict):
        if data.get("error") or data.get("success") is False:
            return f"[오류] {data}"
        keys = list(data.keys())[:6]
        vals = {k: data[k] for k in keys}
        return str(vals)
    if isinstance(data, list):
        count = len(data)
        first = data[0] if data else {}
        keys = list(first.keys())[:4]
        sample = {k: first.get(k) for k in keys}
        return f"{count}건  예시: {sample}"
    return str(data)


def main():
    ok, fail = 0, 0
    failures = []

    print("=" * 65)
    print("  get_market_data API 연동 전체 테스트")
    print("=" * 65)

    for label, fn, args in CASES:
        try:
            result = fn(*args)
            is_error = (
                isinstance(result, dict)
                and (result.get("error") or result.get("success") is False)
            )
            if is_error:
                status = "FAIL"
                fail += 1
                failures.append((label, str(result)))
            else:
                status = "OK  "
                ok += 1
            summary = _summarize(label, result)
            print(f"  [{status}] {label}")
            print(f"         {summary}")
        except Exception as e:
            fail += 1
            failures.append((label, str(e)))
            print(f"  [FAIL] {label}")
            print(f"         {type(e).__name__}: {e}")

    print()
    print("=" * 65)
    print(f"  결과: 성공 {ok}건 / 실패 {fail}건")
    if failures:
        print()
        print("  실패 목록:")
        for label, msg in failures:
            print(f"    - {label}: {msg}")
    print("=" * 65)
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
