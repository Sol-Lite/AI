"""
ranking API 연동 확인 스크립트
실행: python test_ranking_api.py
"""
import sys
import io
import json
import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SPRING_BASE_URL = "http://localhost:8080"
CASES = [
    ("trading-value",  "all"),
    ("trading-value",  "kospi"),
    ("trading-value",  "kosdaq"),
    ("trading-volume", "all"),
    ("trading-volume", "kospi"),
    ("rising",         "all"),
    ("rising",         "kospi"),
    ("falling",        "all"),
    ("falling",        "kosdaq"),
    ("market-cap",     "all"),
    ("market-cap",     "kospi"),
]


def fetch_ranking(ranking_type: str, market: str) -> dict | list:
    url = f"{SPRING_BASE_URL}/api/market/stocks/ranking"
    resp = requests.get(url, params={"type": ranking_type, "market": market}, timeout=5)
    resp.raise_for_status()
    return resp.json()


def print_result(ranking_type: str, market: str, data: dict | list):
    print(f"\n{'-'*60}")
    print(f"  type={ranking_type}  market={market}")
    print(f"{'-'*60}")

    if isinstance(data, dict) and data.get("error"):
        print(f"  [오류] {data}")
        return

    items = data if isinstance(data, list) else data.get("data", data)
    if not items:
        print("  (빈 응답)")
        return

    print(f"  총 {len(items)}건 — 상위 5개:")
    for item in items[:5]:
        rank        = item.get("rank", "-")
        name        = item.get("name", "")
        code        = item.get("stockCode", "")
        price       = item.get("price", 0)
        change_rate = item.get("changeRate", 0)
        volume      = item.get("volume", 0)
        buy_ratio   = item.get("buyRatio")

        line = f"  {rank:>2}. [{code}] {name:<12}  현재가={price:>10,}  등락률={change_rate:>6.2f}%  거래량={volume:>12,}"
        if buy_ratio is not None:
            line += f"  외국인비율={buy_ratio:.2f}%"
        print(line)


def main():
    ok, fail = 0, 0

    print("=" * 60)
    print("  ranking API 연동 테스트")
    print(f"  대상: {SPRING_BASE_URL}")
    print("=" * 60)

    for ranking_type, market in CASES:
        try:
            data = fetch_ranking(ranking_type, market)
            print_result(ranking_type, market, data)
            ok += 1
        except Exception as e:
            print(f"\n{'-'*60}")
            print(f"  type={ranking_type}  market={market}")
            print(f"{'-'*60}")
            print(f"  [실패] {type(e).__name__}: {e}")
            fail += 1

    print(f"\n{'='*60}")
    print(f"  결과: 성공 {ok}건 / 실패 {fail}건")
    print("=" * 60)
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
