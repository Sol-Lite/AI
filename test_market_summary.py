"""
get_market_summary 도구 선택 정확도 테스트

사전 조건:
    - Ollama 실행 중

실행:
    python test_market_summary.py
"""
from test_base import run_group, print_summary

TEST_CASES = [
    # ── korea ──────────────────────────────────────────────────────────────────
    {
        "group":         "get_market_summary",
        "message":       "오늘 한국 증시 어때?",
        "expected_tool": "get_market_summary",
        "expected_type": "korea",
        "expected_args": None,
        "desc":          "한국 시황 - 직접 질문",
    },
    {
        "group":         "get_market_summary",
        "message":       "오늘 주식 시장 현황 알려줘",
        "expected_tool": "get_market_summary",
        "expected_type": "korea",
        "expected_args": None,
        "desc":          "한국 시황 - 시장 현황",
    },
    {
        "group":         "get_market_summary",
        "message":       "국내 증시 지금 어떻게 돼?",
        "expected_tool": "get_market_summary",
        "expected_type": "korea",
        "expected_args": None,
        "desc":          "한국 시황 - 국내 키워드",
    },
    {
        "group":         "get_market_summary",
        "message":       "오늘 시장 분위기 어때?",
        "expected_tool": "get_market_summary",
        "expected_type": "korea",
        "expected_args": None,
        "desc":          "한국 시황 - 분위기 질문",
    },
    # ── us ─────────────────────────────────────────────────────────────────────
    {
        "group":         "get_market_summary",
        "message":       "나스닥 지금 어떻게 돼?",
        "expected_tool": "get_market_summary",
        "expected_type": "us",
        "expected_args": None,
        "desc":          "미국 시황 - 나스닥 분위기",
    },
    # ── stock_news ─────────────────────────────────────────────────────────────
    {
        "group":         "get_market_summary",
        "message":       "삼성전자 관련 뉴스 알려줘",
        "expected_tool": "get_market_summary",
        "expected_type": "stock_news",
        "expected_args": None,
        "desc":          "종목 뉴스 - 종목명 포함",
    },
]


if __name__ == "__main__":
    results = run_group(TEST_CASES)
    print_summary(results)
