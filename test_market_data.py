"""
get_market_data 도구 선택 정확도 테스트

사전 조건:
    - Ollama 실행 중
    - Spring API 실행 중 (모든 케이스에 필요)

실행:
    python test_market_data.py
"""
from test_base import run_group, print_summary

TEST_CASES = [
    # ── price ──────────────────────────────────────────────────────────────────
    {
        "group":         "get_market_data",
        "message":       "삼성전자 지금 얼마야?",
        "expected_tool": "get_market_data",
        "expected_type": "price",
        "expected_args": None,
        "desc":          "종목 현재가 조회",
    },
    # ── index ──────────────────────────────────────────────────────────────────
    {
        "group":         "get_market_data",
        "message":       "코스피 지수 알려줘",
        "expected_tool": "get_market_data",
        "expected_type": "index",
        "expected_args": None,
        "desc":          "지수 조회 - 코스피",
    },
    # ── exchange ───────────────────────────────────────────────────────────────
    {
        "group":         "get_market_data",
        "message":       "달러 환율 얼마야?",
        "expected_tool": "get_market_data",
        "expected_type": "exchange",
        "expected_args": None,
        "desc":          "환율 조회",
    },
    # ── ranking ────────────────────────────────────────────────────────────────
    {
        "group":         "get_market_data",
        "message":       "거래량 많은 종목 알려줘",
        "expected_tool": "get_market_data",
        "expected_type": "ranking",
        "expected_args": {"ranking_type": "volume"},
        "desc":          "랭킹 조회 - 거래량",
    },
    {
        "group":         "get_market_data",
        "message":       "오늘 많이 오른 종목 뭐야?",
        "expected_tool": "get_market_data",
        "expected_type": "ranking",
        "expected_args": {"ranking_type": "change_rate"},
        "desc":          "랭킹 조회 - 등락률",
    },
    # ── period_chart ───────────────────────────────────────────────────────────
    {
        "group":         "get_market_data",
        "message":       "삼성전자 일봉 차트 보여줘",
        "expected_tool": "get_market_data",
        "expected_type": "period_chart",
        "expected_args": None,
        "desc":          "기간별 차트 - 일봉",
    },
]


if __name__ == "__main__":
    results = run_group(TEST_CASES)
    print_summary(results)
