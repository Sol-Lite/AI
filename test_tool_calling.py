"""
챗봇 Tool Calling 통합 테스트 러너
각 그룹 파일을 모두 실행하고 전체 요약을 출력합니다.

사전 조건:
    - Ollama 실행 중
    - Oracle DB에 setup_dummy_data.py로 더미 데이터 삽입 완료
    - Spring API 실행 중 (balance/balance_detail, get_market_data, execute_order 테스트에 필요)

실행:
    python test_tool_calling.py              # 기본 그룹 (Ollama + Oracle만 필요)
    python test_tool_calling.py all          # 전체 그룹 실행 (Spring API 필요)
    python test_tool_calling.py market       # get_market_summary 그룹만
    python test_tool_calling.py db           # get_db_data 그룹만
    python test_tool_calling.py mdata        # get_market_data 그룹만
    python test_tool_calling.py order        # execute_order 그룹만

그룹별 단독 실행:
    python test_market_summary.py
    python test_db_data.py
    python test_market_data.py
    python test_execute_order.py
"""
import sys
from test_base import run_group, print_summary

from test_market_summary import TEST_CASES as MARKET_SUMMARY_CASES
from test_db_data        import TEST_CASES as DB_DATA_CASES
from test_market_data    import TEST_CASES as MARKET_DATA_CASES
from test_execute_order  import TEST_CASES as EXECUTE_ORDER_CASES

# Ollama + Oracle만 필요한 그룹 (Spring API 없이 실행 가능)
DEFAULT_CASES = MARKET_SUMMARY_CASES + DB_DATA_CASES

ALIAS = {
    "market": MARKET_SUMMARY_CASES,
    "db":     DB_DATA_CASES,
    "mdata":  MARKET_DATA_CASES,
    "order":  EXECUTE_ORDER_CASES,
    "all":    MARKET_SUMMARY_CASES + DB_DATA_CASES + MARKET_DATA_CASES + EXECUTE_ORDER_CASES,
}


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else None

    if arg is None:
        print("※ 기본 실행: get_market_summary + get_db_data 그룹만 실행합니다.")
        print("  전체 실행: python test_tool_calling.py all")
        print()
        cases = DEFAULT_CASES
    elif arg in ALIAS:
        cases = ALIAS[arg]
    else:
        print(f"[ERROR] 알 수 없는 인자: '{arg}'")
        print(f"  사용 가능: {list(ALIAS.keys())}")
        sys.exit(1)

    results = run_group(cases)
    print_summary(results)


if __name__ == "__main__":
    main()
