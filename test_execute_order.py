"""
execute_order 전체 흐름 테스트
  사용자 입력 → llm.chat() → Ollama LLM → tool_calls → execute_order() → Spring POST /api/orders

사전 조건:
    - Ollama 실행 중
    - Spring 서버 실행 중
    - .env에 TEST_JWT_TOKEN=<유효한 JWT> 설정

실행:
    python test_execute_order.py
"""
from test_base import run_group, print_summary

TEST_CASES = [
    # ── buy: 국내 시장가 ───────────────────────────────────────────────────────
    {
        "group":         "execute_order / buy",
        "message":       "삼성전자 1주 사줘",
        "expected_tool": "execute_order",
        "expected_type": "buy",
        "expected_args": {"quantity": 1},
        "desc":          "매수 - 국내 시장가 (수량 1주)",
    },
    {
        "group":         "execute_order / buy",
        "message":       "삼성전자 10주 매수해줘",
        "expected_tool": "execute_order",
        "expected_type": "buy",
        "expected_args": {"quantity": 10},
        "desc":          "매수 - 국내 시장가 (수량 10주)",
    },
    # ── buy: 국내 지정가 ───────────────────────────────────────────────────────
    {
        "group":         "execute_order / buy",
        "message":       "삼성전자 1주 190000원에 사줘",
        "expected_tool": "execute_order",
        "expected_type": "buy",
        "expected_args": {"quantity": 1},
        "desc":          "매수 - 국내 지정가",
    },
    # ── buy: 해외 ─────────────────────────────────────────────────────────────
    {
        "group":         "execute_order / buy",
        "message":       "애플 1주 사줘",
        "expected_tool": "execute_order",
        "expected_type": "buy",
        "expected_args": {"quantity": 1},
        "desc":          "매수 - 해외 (애플)",
    },
    # ── sell ──────────────────────────────────────────────────────────────────
    {
        "group":         "execute_order / sell",
        "message":       "삼성전자 1주 팔아줘",
        "expected_tool": "execute_order",
        "expected_type": "sell",
        "expected_args": {"quantity": 1},
        "desc":          "매도 - 국내 시장가",
    },
    {
        "group":         "execute_order / sell",
        "message":       "삼성전자 1주 190000원에 팔아줘",
        "expected_tool": "execute_order",
        "expected_type": "sell",
        "expected_args": {"quantity": 1},
        "desc":          "매도 - 국내 지정가",
    },
    # ── 미호출: 종목 누락 ─────────────────────────────────────────────────────
    {
        "group":         "execute_order / 미호출",
        "message":       "주식 10주 팔아줘",
        "expected_tool": None,
        "expected_type": None,
        "expected_args": None,
        "desc":          "매도 - 종목명 없음 → tool 호출 금지",
    },
    {
        "group":         "execute_order / 미호출",
        "message":       "사줘",
        "expected_tool": None,
        "expected_type": None,
        "expected_args": None,
        "desc":          "매수 - 종목·수량 모두 없음 → tool 호출 금지",
    },
    # ── exchange ──────────────────────────────────────────────────────────────
    {
        "group":         "execute_order / exchange",
        "message":       "100만원 달러로 환전해줘",
        "expected_tool": "execute_order",
        "expected_type": "exchange",
        "expected_args": None,
        "desc":          "환전 - 원화→달러 금액 명시",
    },
    {
        "group":         "execute_order / 미호출",
        "message":       "달러로 환전해줘",
        "expected_tool": None,
        "expected_type": None,
        "expected_args": None,
        "desc":          "환전 - 금액 누락 → tool 호출 금지",
    },
]


if __name__ == "__main__":
    results = run_group(TEST_CASES)
    print_summary(results)
