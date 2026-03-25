"""
execute_order 도구 선택 정확도 테스트 (정상 케이스 + 미호출 케이스)

사전 조건:
    - Ollama 실행 중
    - Spring API 실행 중 (주문 실행에 필요)

실행:
    python test_execute_order.py
"""
from test_base import run_group, print_summary

TEST_CASES = [
    # ── buy ────────────────────────────────────────────────────────────────────
    {
        "group":         "execute_order",
        "message":       "삼성전자 10주 사줘",
        "expected_tool": "execute_order",
        "expected_type": "buy",
        "expected_args": {"quantity": 10},
        "desc":          "매수 주문 - 종목 + 수량 정상",
    },
    # ── sell ───────────────────────────────────────────────────────────────────
    {
        "group":         "execute_order",
        "message":       "SK하이닉스 5주 팔아줘",
        "expected_tool": "execute_order",
        "expected_type": "sell",
        "expected_args": {"quantity": 5},
        "desc":          "매도 주문 - 종목 + 수량 정상",
    },
    # ── exchange ───────────────────────────────────────────────────────────────
    {
        "group":         "execute_order",
        "message":       "원화 100만원 달러로 환전해줘",
        "expected_tool": "execute_order",
        "expected_type": "exchange",
        "expected_args": None,
        "desc":          "환전 주문 - 기준통화 + 표시통화 + 환전 키워드 정상",
    },
    # ── 미호출: 정보 누락 → 되묻기 ────────────────────────────────────────────
    {
        "group":         "execute_order(미호출)",
        "message":       "삼성전자 사줘",
        "expected_tool": None,
        "expected_type": None,
        "expected_args": None,
        "desc":          "매수 - 수량 누락 → 되묻기",
    },
    {
        "group":         "execute_order(미호출)",
        "message":       "주식 10주 팔아줘",
        "expected_tool": None,
        "expected_type": None,
        "expected_args": None,
        "desc":          "매도 - 종목 누락 → 되묻기",
    },
    {
        "group":         "execute_order(미호출)",
        "message":       "달러로 환전해줘",
        "expected_tool": None,
        "expected_type": None,
        "expected_args": None,
        "desc":          "환전 - 기준통화 누락 → 되묻기",
    },
]


if __name__ == "__main__":
    results = run_group(TEST_CASES)
    print_summary(results)
