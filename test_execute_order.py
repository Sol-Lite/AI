"""
execute_order 도구 선택 정확도 테스트 (매수매도 / 환전실행 유즈케이스)

사전 조건:
    - Ollama 실행 중
    - Spring API 실행 중 (주문 실행에 필요)

실행:
    python test_execute_order.py
"""
from test_base import run_group, print_summary

TEST_CASES = [
    # ── buy: 수량 지정 (국내) ──────────────────────────────────────────────────
    # {
    #     "group":         "execute_order / buy",
    #     "message":       "삼성전자 사줘",
    #     "expected_tool": "execute_order",
    #     "expected_type": "buy",
    #     "expected_args": None,
    #     "desc":          "매수 - 종목만 있고 수량 없음 (tool은 호출, 수량은 되묻기 가능)",
    # },
    # {
    #     "group":         "execute_order / buy",
    #     "message":       "삼성전자 10주 사줘",
    #     "expected_tool": "execute_order",
    #     "expected_type": "buy",
    #     "expected_args": {"quantity": 10},
    #     "desc":          "매수 - 종목 + 수량 (시장가)",
    # },
    # {
    #     "group":         "execute_order / buy",
    #     "message":       "삼성전자 10주 매수해줘",
    #     "expected_tool": "execute_order",
    #     "expected_type": "buy",
    #     "expected_args": {"quantity": 10},
    #     "desc":          "매수 - 매수해줘 키워드",
    # },
    # {
    #     "group":         "execute_order / buy",
    #     "message":       "SK하이닉스 5주 매수",
    #     "expected_tool": "execute_order",
    #     "expected_type": "buy",
    #     "expected_args": {"quantity": 5},
    #     "desc":          "매수 - SK하이닉스",
    # },
    # {
    #     "group":         "execute_order / buy",
    #     "message":       "카카오 3주 사줘",
    #     "expected_tool": "execute_order",
    #     "expected_type": "buy",
    #     "expected_args": {"quantity": 3},
    #     "desc":          "매수 - 카카오",
    # },
    # {
    #     "group":         "execute_order / buy",
    #     "message":       "삼성전자 10주 75000원에 사줘",
    #     "expected_tool": "execute_order",
    #     "expected_type": "buy",
    #     "expected_args": {"quantity": 10},
    #     "desc":          "매수 - 지정가",
    # },
    # # ── buy: 해외 ──────────────────────────────────────────────────────────────
    # {
    #     "group":         "execute_order / buy",
    #     "message":       "애플 3주 사줘",
    #     "expected_tool": "execute_order",
    #     "expected_type": "buy",
    #     "expected_args": {"quantity": 3},
    #     "desc":          "매수 - 해외 (애플)",
    # },
    # {
    #     "group":         "execute_order / buy",
    #     "message":       "엔비디아 1주 매수",
    #     "expected_tool": "execute_order",
    #     "expected_type": "buy",
    #     "expected_args": {"quantity": 1},
    #     "desc":          "매수 - 해외 (엔비디아)",
    # },
    # # ── sell ───────────────────────────────────────────────────────────────────
    # {
    #     "group":         "execute_order / sell",
    #     "message":       "삼성전자 5주 팔아줘",
    #     "expected_tool": "execute_order",
    #     "expected_type": "sell",
    #     "expected_args": {"quantity": 5},
    #     "desc":          "매도 - 종목 + 수량 (시장가)",
    # },
    # {
    #     "group":         "execute_order / sell",
    #     "message":       "삼성전자 5주 매도",
    #     "expected_tool": "execute_order",
    #     "expected_type": "sell",
    #     "expected_args": {"quantity": 5},
    #     "desc":          "매도 - 매도 키워드",
    # },
    {
        "group":         "execute_order / sell",
        "message":       "신투 5주 75500원에 팔아줘",
        "expected_tool": "execute_order",
        "expected_type": "sell",
        "expected_args": {"quantity": 5},
        "desc":          "매도 - 지정가",
    },
    {
        "group":         "execute_order / sell",
        "message":       "SK하이닉스 5주 팔아줘",
        "expected_tool": "execute_order",
        "expected_type": "sell",
        "expected_args": {"quantity": 5},
        "desc":          "매도 - SK하이닉스",
    },
    # # ── exchange: 실행 ─────────────────────────────────────────────────────────
    # {
    #     "group":         "execute_order / exchange",
    #     "message":       "달러로 환전해줘 100만원",
    #     "expected_tool": "execute_order",
    #     "expected_type": "exchange",
    #     "expected_args": None,
    #     "desc":          "환전 - 원화→달러 금액 명시",
    # },
    # {
    #     "group":         "execute_order / exchange",
    #     "message":       "50만원 달러로 바꿔줘",
    #     "expected_tool": "execute_order",
    #     "expected_type": "exchange",
    #     "expected_args": None,
    #     "desc":          "환전 - 바꿔줘 키워드",
    # },
    # {
    #     "group":         "execute_order / exchange",
    #     "message":       "원화 200만원 달러로",
    #     "expected_tool": "execute_order",
    #     "expected_type": "exchange",
    #     "expected_args": None,
    #     "desc":          "환전 - 원화→달러 간결한 표현",
    # },
    # {
    #     "group":         "execute_order / exchange",
    #     "message":       "100달러 원화로 환전해줘",
    #     "expected_tool": "execute_order",
    #     "expected_type": "exchange",
    #     "expected_args": None,
    #     "desc":          "환전 - 달러→원화",
    # },
    # # ── 미호출: 매수/매도 정보 누락 ───────────────────────────────────────────
    # {
    #     "group":         "execute_order / 미호출",
    #     "message":       "주식 10주 팔아줘",
    #     "expected_tool": None,
    #     "expected_type": None,
    #     "expected_args": None,
    #     "desc":          "매도 - 종목 누락 → 되묻기",
    # },
    # {
    #     "group":         "execute_order / 미호출",
    #     "message":       "사줘",
    #     "expected_tool": None,
    #     "expected_type": None,
    #     "expected_args": None,
    #     "desc":          "매수 - 종목 + 수량 모두 누락",
    # },
    # # ── 미호출: 환전 정보 누락 ────────────────────────────────────────────────
    # {
    #     "group":         "execute_order / 미호출",
    #     "message":       "달러로 환전해줘",
    #     "expected_tool": None,
    #     "expected_type": None,
    #     "expected_args": None,
    #     "desc":          "환전 - 기준통화/금액 누락 → 되묻기",
    # },
    # {
    #     "group":         "execute_order / 미호출",
    #     "message":       "달러로 바꿔줘",
    #     "expected_tool": None,
    #     "expected_type": None,
    #     "expected_args": None,
    #     "desc":          "환전 - 금액 누락 → 되묻기",
    # },
]


if __name__ == "__main__":
    results = run_group(TEST_CASES)
    print_summary(results)
