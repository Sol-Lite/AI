"""
get_db_data 도구 선택 정확도 테스트 (잔고조회 / 거래내역 / 포트폴리오 유즈케이스)

사전 조건:
    - Ollama 실행 중
    - Oracle DB에 setup_dummy_data.py로 더미 데이터 삽입 완료
    - Spring API 실행 중 (balance / balance_detail 조회에 필요)

실행:
    python test_db_data.py
"""
from test_base import run_group, print_summary

TEST_CASES = [
    # ── balance: 전체 리포트 필요 ──────────────────────────────────────────────
    {
        "group":         "get_db_data / balance",
        "message":       "지금 내 계좌 잔고 알려줘",
        "expected_tool": "get_db_data",
        "expected_type": "balance",
        "expected_args": None,
        "desc":          "잔고 전체 리포트 - 계좌 키워드",
    },
    {
        "group":         "get_db_data / balance",
        "message":       "잔고 확인해줘",
        "expected_tool": "get_db_data",
        "expected_type": "balance",
        "expected_args": None,
        "desc":          "잔고 전체 리포트 - 확인 키워드",
    },
    {
        "group":         "get_db_data / balance",
        "message":       "내 잔고 보여줘",
        "expected_tool": "get_db_data",
        "expected_type": "balance",
        "expected_args": None,
        "desc":          "잔고 전체 리포트 - 보여줘 키워드",
    },
    # ── balance_detail: 리포트 일부 정보만 필요 ────────────────────────────────
    {
        "group":         "get_db_data / balance_detail",
        "message":       "내 잔고 얼마야?",
        "expected_tool": "get_db_data",
        "expected_type": "balance_detail",
        "expected_args": None,
        "desc":          "잔고 세부 - 잔고 금액만",
    },
    {
        "group":         "get_db_data / balance_detail",
        "message":       "달러 잔고도 있어?",
        "expected_tool": "get_db_data",
        "expected_type": "balance_detail",
        "expected_args": None,
        "desc":          "잔고 세부 - 달러 보유 여부",
    },
    {
        "group":         "get_db_data / balance_detail",
        "message":       "내 계좌에 달러 얼마나 있어?",
        "expected_tool": "get_db_data",
        "expected_type": "balance_detail",
        "expected_args": None,
        "desc":          "잔고 세부 - 달러 금액",
    },
    {
        "group":         "get_db_data / balance_detail",
        "message":       "주문 가능한 돈 얼마야?",
        "expected_tool": "get_db_data",
        "expected_type": "balance_detail",
        "expected_args": None,
        "desc":          "잔고 세부 - 주문 가능 금액",
    },
    {
        "group":         "get_db_data / balance_detail",
        "message":       "출금 가능 금액 알려줘",
        "expected_tool": "get_db_data",
        "expected_type": "balance_detail",
        "expected_args": None,
        "desc":          "잔고 세부 - 출금 가능",
    },
    {
        "group":         "get_db_data / balance_detail",
        "message":       "총 자산이 얼마야?",
        "expected_tool": "get_db_data",
        "expected_type": "balance_detail",
        "expected_args": None,
        "desc":          "잔고 세부 - 총 자산",
    },
    {
        "group":         "get_db_data / balance_detail",
        "message":       "원화 잔고 얼마야?",
        "expected_tool": "get_db_data",
        "expected_type": "balance_detail",
        "expected_args": None,
        "desc":          "잔고 세부 - 원화 금액",
    },
    # ── trades ─────────────────────────────────────────────────────────────────
    {
        "group":         "get_db_data / trades",
        "message":       "내 거래내역 보여줘",
        "expected_tool": "get_db_data",
        "expected_type": "trades",
        "expected_args": None,
        "desc":          "거래내역 전체 조회 - 기본",
    },
    {
        "group":         "get_db_data / trades",
        "message":       "최근 거래 좀 알려줘",
        "expected_tool": "get_db_data",
        "expected_type": "trades",
        "expected_args": None,
        "desc":          "거래내역 전체 조회 - 최근 거래",
    },
    {
        "group":         "get_db_data / trades",
        "message":       "내가 뭐 샀어?",
        "expected_tool": "get_db_data",
        "expected_type": "trades",
        "expected_args": None,
        "desc":          "거래내역 전체 조회 - 매수 이력",
    },
    {
        "group":         "get_db_data / trades",
        "message":       "내가 뭐 팔았어?",
        "expected_tool": "get_db_data",
        "expected_type": "trades",
        "expected_args": None,
        "desc":          "거래내역 전체 조회 - 매도 이력",
    },
    # ── trades_detail ──────────────────────────────────────────────────────────
    {
        "group":         "get_db_data / trades_detail",
        "message":       "매수 몇 번 했어?",
        "expected_tool": "get_db_data",
        "expected_type": "trades_detail",
        "expected_args": None,
        "desc":          "거래내역 세부 - 매수 횟수",
    },
    {
        "group":         "get_db_data / trades_detail",
        "message":       "최근에 뭐 샀어?",
        "expected_tool": "get_db_data",
        "expected_type": "trades_detail",
        "expected_args": None,
        "desc":          "거래내역 세부 - 최근 매수",
    },
    {
        "group":         "get_db_data / trades_detail",
        "message":       "거래 몇 번 했어?",
        "expected_tool": "get_db_data",
        "expected_type": "trades_detail",
        "expected_args": None,
        "desc":          "거래내역 세부 - 총 거래 횟수",
    },
    {
        "group":         "get_db_data / trades_detail",
        "message":       "내가 제일 많이 산 종목이 뭐야?",
        "expected_tool": "get_db_data",
        "expected_type": "trades_detail",
        "expected_args": None,
        "desc":          "거래내역 세부 - 최다 매수 종목",
    },
    {
        "group":         "get_db_data / trades_detail",
        "message":       "삼성전자 거래내역 있어?",
        "expected_tool": "get_db_data",
        "expected_type": "trades_detail",
        "expected_args": None,
        "desc":          "거래내역 세부 - 종목별 조회",
    },
    # ── portfolio ──────────────────────────────────────────────────────────────
    {
        "group":         "get_db_data / portfolio",
        "message":       "내 포트폴리오 분석해줘",
        "expected_tool": "get_db_data",
        "expected_type": "portfolio",
        "expected_args": None,
        "desc":          "포트폴리오 전체 조회 - 기본",
    },
    {
        "group":         "get_db_data / portfolio",
        "message":       "포트폴리오 보여줘",
        "expected_tool": "get_db_data",
        "expected_type": "portfolio",
        "expected_args": None,
        "desc":          "포트폴리오 전체 조회 - 짧은 표현",
    },
    {
        "group":         "get_db_data / portfolio",
        "message":       "내 투자 현황 알려줘",
        "expected_tool": "get_db_data",
        "expected_type": "portfolio",
        "expected_args": None,
        "desc":          "포트폴리오 전체 조회 - 투자 현황",
    },
    # ── portfolio_detail ───────────────────────────────────────────────────────
    {
        "group":         "get_db_data / portfolio_detail",
        "message":       "내 수익률 얼마야?",
        "expected_tool": "get_db_data",
        "expected_type": "portfolio_detail",
        "expected_args": None,
        "desc":          "포트폴리오 세부 - 수익률",
    },
    {
        "group":         "get_db_data / portfolio_detail",
        "message":       "MDD가 얼마야?",
        "expected_tool": "get_db_data",
        "expected_type": "portfolio_detail",
        "expected_args": None,
        "desc":          "포트폴리오 세부 - MDD",
    },
    {
        "group":         "get_db_data / portfolio_detail",
        "message":       "삼성전자 수익률 어떻게 돼?",
        "expected_tool": "get_db_data",
        "expected_type": "portfolio_detail",
        "expected_args": None,
        "desc":          "포트폴리오 세부 - 종목 수익률",
    },
    {
        "group":         "get_db_data / portfolio_detail",
        "message":       "내 총 평가금액 알려줘",
        "expected_tool": "get_db_data",
        "expected_type": "portfolio_detail",
        "expected_args": None,
        "desc":          "포트폴리오 세부 - 총 평가금액",
    },
    {
        "group":         "get_db_data / portfolio_detail",
        "message":       "제일 많이 오른 종목이 뭐야?",
        "expected_tool": "get_db_data",
        "expected_type": "portfolio_detail",
        "expected_args": None,
        "desc":          "포트폴리오 세부 - 최고 수익 종목",
    },
    {
        "group":         "get_db_data / portfolio_detail",
        "message":       "손실 난 종목 있어?",
        "expected_tool": "get_db_data",
        "expected_type": "portfolio_detail",
        "expected_args": None,
        "desc":          "포트폴리오 세부 - 손실 종목",
    },
    {
        "group":         "get_db_data / portfolio_detail",
        "message":       "내 포트폴리오 국내/해외 비율이 어떻게 돼?",
        "expected_tool": "get_db_data",
        "expected_type": "portfolio_detail",
        "expected_args": None,
        "desc":          "포트폴리오 세부 - 국내/해외 비율",
    },
    {
        "group":         "get_db_data / portfolio_detail",
        "message":       "내 포트폴리오 위험한가요?",
        "expected_tool": "get_db_data",
        "expected_type": "portfolio_detail",
        "expected_args": None,
        "desc":          "포트폴리오 세부 - 리스크",
    },
    {
        "group":         "get_db_data / portfolio_detail",
        "message":       "승률이 어떻게 돼?",
        "expected_tool": "get_db_data",
        "expected_type": "portfolio_detail",
        "expected_args": None,
        "desc":          "포트폴리오 세부 - 거래 승률",
    },
]


if __name__ == "__main__":
    results = run_group(TEST_CASES)
    print_summary(results)
