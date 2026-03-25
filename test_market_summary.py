"""
get_market_summary 도구 선택 정확도 테스트 (뉴스조회 유즈케이스)

사전 조건:
    - Ollama 실행 중

실행:
    python test_market_summary.py
"""
from test_base import run_group, print_summary

TEST_CASES = [
    # ── korea ──────────────────────────────────────────────────────────────────
    {
        "group":         "get_market_summary / korea",
        "message":       "오늘 한국 증시 어때?",
        "expected_tool": "get_market_summary",
        "expected_type": "korea",
        "expected_args": None,
        "desc":          "한국 시황 - 직접 질문",
    },
    {
        "group":         "get_market_summary / korea",
        "message":       "국내 증시 지금 어떻게 돼?",
        "expected_tool": "get_market_summary",
        "expected_type": "korea",
        "expected_args": None,
        "desc":          "한국 시황 - 국내 키워드",
    },
    {
        "group":         "get_market_summary / korea",
        "message":       "한국 증시 요약해줘",
        "expected_tool": "get_market_summary",
        "expected_type": "korea",
        "expected_args": None,
        "desc":          "한국 시황 - 요약 키워드",
    },
    {
        "group":         "get_market_summary / korea",
        "message":       "오늘 한국 시장 요약 정리해줘",
        "expected_tool": "get_market_summary",
        "expected_type": "korea",
        "expected_args": None,
        "desc":          "한국 시황 - 요약 정리",
    },
    {
        "group":         "get_market_summary / korea",
        "message":       "오늘 장 마감 후 리뷰 해줘",
        "expected_tool": "get_market_summary",
        "expected_type": "korea",
        "expected_args": None,
        "desc":          "한국 시황 - 장 마감 리뷰",
    },
    # ── us ─────────────────────────────────────────────────────────────────────
    {
        "group":         "get_market_summary / us",
        "message":       "미국 증시 어때?",
        "expected_tool": "get_market_summary",
        "expected_type": "us",
        "expected_args": None,
        "desc":          "미국 시황 - 직접 질문",
    },
    {
        "group":         "get_market_summary / us",
        "message":       "월스트리트 오늘 분위기?",
        "expected_tool": "get_market_summary",
        "expected_type": "us",
        "expected_args": None,
        "desc":          "미국 시황 - 월스트리트",
    },
    {
        "group":         "get_market_summary / us",
        "message":       "뉴욕 증시 현황 알려줘",
        "expected_tool": "get_market_summary",
        "expected_type": "us",
        "expected_args": None,
        "desc":          "미국 시황 - 뉴욕 증시",
    },
    {
        "group":         "get_market_summary / us",
        "message":       "미국 마감 결과 알려줘",
        "expected_tool": "get_market_summary",
        "expected_type": "us",
        "expected_args": None,
        "desc":          "미국 시황 - 마감 결과",
    },
    {
        "group":         "get_market_summary / us",
        "message":       "나스닥 지금 어떻게 돼?",
        "expected_tool": "get_market_summary",
        "expected_type": "us",
        "expected_args": None,
        "desc":          "미국 시황 - 나스닥 분위기",
    },
    # ── stock_news ─────────────────────────────────────────────────────────────
    {
        "group":         "get_market_summary / stock_news",
        "message":       "삼성전자 오늘 뉴스 있어?",
        "expected_tool": "get_market_summary",
        "expected_type": "stock_news",
        "expected_args": None,
        "desc":          "종목 뉴스 - 삼성전자",
    },
    {
        "group":         "get_market_summary / stock_news",
        "message":       "SK하이닉스 최근 소식 알려줘",
        "expected_tool": "get_market_summary",
        "expected_type": "stock_news",
        "expected_args": None,
        "desc":          "종목 뉴스 - SK하이닉스",
    },
    {
        "group":         "get_market_summary / stock_news",
        "message":       "카카오 뉴스 뭐 있어?",
        "expected_tool": "get_market_summary",
        "expected_type": "stock_news",
        "expected_args": None,
        "desc":          "종목 뉴스 - 카카오",
    },
    {
        "group":         "get_market_summary / stock_news",
        "message":       "엔비디아 오늘 뉴스 뭐야?",
        "expected_tool": "get_market_summary",
        "expected_type": "stock_news",
        "expected_args": None,
        "desc":          "종목 뉴스 - 엔비디아",
    },
    {
        "group":         "get_market_summary / stock_news",
        "message":       "삼성전자 관련 뉴스 알려줘",
        "expected_tool": "get_market_summary",
        "expected_type": "stock_news",
        "expected_args": None,
        "desc":          "종목 뉴스 - 삼성전자 관련",
    },
    # ── 미호출: 정보 누락 → 되묻기 ────────────────────────────────────────────
    {
        "group":         "get_market_summary / 미호출",
        "message":       "시황",
        "expected_tool": None,
        "expected_type": None,
        "expected_args": None,
        "desc":          "모호한 입력 - 시장 미지정 → 되묻기",
    },
    {
        "group":         "get_market_summary / 미호출",
        "message":       "뉴스 알려줘",
        "expected_tool": None,
        "expected_type": None,
        "expected_args": None,
        "desc":          "종목 미지정 뉴스 → 종목 되묻기",
    },
    {
        "group":         "get_market_summary / 미호출",
        "message":       "바이오 주식 뉴스 뭐 있어?",
        "expected_tool": None,
        "expected_type": None,
        "expected_args": None,
        "desc":          "섹터 뉴스 (종목명 없음) → 종목 되묻기",
    },
]


if __name__ == "__main__":
    results = run_group(TEST_CASES)
    print_summary(results)
