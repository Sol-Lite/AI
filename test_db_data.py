"""
get_db_data 도구 선택 정확도 테스트

사전 조건:
    - Ollama 실행 중
    - Oracle DB에 setup_dummy_data.py로 더미 데이터 삽입 완료
    - Spring API 실행 중 (balance / balance_detail 조회에 필요)

실행:
    python test_db_data.py
"""
from test_base import run_group, print_summary

TEST_CASES = [
    # ── balance: 전체 조회 ─────────────────────────────────────────────────────
    {
        "group":         "get_db_data",
        "message":       "내 잔고 보여줘",
        "expected_tool": "get_db_data",
        "expected_type": "balance",
        "expected_args": None,
        "desc":          "잔고 전체 조회",
    },
    # ── trades: 전체 조회 ──────────────────────────────────────────────────────
    {
        "group":         "get_db_data",
        "message":       "거래내역 보여줘",
        "expected_tool": "get_db_data",
        "expected_type": "trades",
        "expected_args": None,
        "desc":          "거래내역 전체 조회",
    },
    # ── portfolio: 전체 조회 ───────────────────────────────────────────────────
    {
        "group":         "get_db_data",
        "message":       "내 포트폴리오 분석해줘",
        "expected_tool": "get_db_data",
        "expected_type": "portfolio",
        "expected_args": None,
        "desc":          "포트폴리오 전체 조회",
    },
    # ── balance_detail ─────────────────────────────────────────────────────────
    {
        "group":         "get_db_data",
        "message":       "원화 잔고 얼마야?",
        "expected_tool": "get_db_data",
        "expected_type": "balance_detail",
        "expected_args": None,
        "desc":          "잔고 세부 - 원화",
    },
    {
        "group":         "get_db_data",
        "message":       "출금 가능 금액 알려줘",
        "expected_tool": "get_db_data",
        "expected_type": "balance_detail",
        "expected_args": None,
        "desc":          "잔고 세부 - 출금 가능",
    },
    # ── trades_detail ──────────────────────────────────────────────────────────
    {
        "group":         "get_db_data",
        "message":       "매수 몇 번 했어?",
        "expected_tool": "get_db_data",
        "expected_type": "trades_detail",
        "expected_args": None,
        "desc":          "거래내역 세부 - 매수 횟수",
    },
    {
        "group":         "get_db_data",
        "message":       "최근에 뭐 샀어?",
        "expected_tool": "get_db_data",
        "expected_type": "trades_detail",
        "expected_args": None,
        "desc":          "거래내역 세부 - 최근 매수",
    },
    # ── portfolio_detail ───────────────────────────────────────────────────────
    {
        "group":         "get_db_data",
        "message":       "MDD 얼마야?",
        "expected_tool": "get_db_data",
        "expected_type": "portfolio_detail",
        "expected_args": None,
        "desc":          "포트폴리오 세부 - MDD",
    },
    {
        "group":         "get_db_data",
        "message":       "삼성전자 수익률 어떻게 돼?",
        "expected_tool": "get_db_data",
        "expected_type": "portfolio_detail",
        "expected_args": None,
        "desc":          "포트폴리오 세부 - 종목 수익률",
    },
    {
        "group":         "get_db_data",
        "message":       "내 총 평가금액 알려줘",
        "expected_tool": "get_db_data",
        "expected_type": "portfolio_detail",
        "expected_args": None,
        "desc":          "포트폴리오 세부 - 총 평가금액",
    },
]


if __name__ == "__main__":
    results = run_group(TEST_CASES)
    print_summary(results)
