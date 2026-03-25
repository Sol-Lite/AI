"""
챗봇 Tool Calling 통합 테스트 러너
각 그룹 파일을 모두 실행하고 전체 요약을 출력합니다.

사전 조건:
    - Ollama 실행 중
    - Oracle DB에 setup_dummy_data.py로 더미 데이터 삽입 완료
    - Spring API 실행 중 (balance/balance_detail, get_market_data, execute_order 테스트에 필요)

실행:
    python test_tool_calling.py                      # 전체 그룹 실행
    python test_tool_calling.py get_market_summary   # 특정 그룹만 실행
    python test_market_summary.py                    # 그룹별 단독 실행도 가능
"""
import sys
from test_base import run_group, print_summary

from test_market_summary import TEST_CASES as MARKET_SUMMARY_CASES
from test_db_data        import TEST_CASES as DB_DATA_CASES
from test_market_data    import TEST_CASES as MARKET_DATA_CASES
from test_execute_order  import TEST_CASES as EXECUTE_ORDER_CASES

ALL_CASES = (
    MARKET_SUMMARY_CASES
    + DB_DATA_CASES
    + MARKET_DATA_CASES
    + EXECUTE_ORDER_CASES
)

# 기본으로 실행할 그룹 (Spring API 없이도 실행 가능한 그룹)
DEFAULT_GROUPS = {"get_market_summary", "get_db_data"}


def main():
    target_group = sys.argv[1] if len(sys.argv) > 1 else None

    if target_group:
        cases = [c for c in ALL_CASES if c["group"] == target_group]
        if not cases:
            print(f"[ERROR] 그룹 '{target_group}'을 찾을 수 없습니다.")
            print(f"  사용 가능한 그룹: {sorted({c['group'] for c in ALL_CASES})}")
            sys.exit(1)
    else:
        # 인자 없이 실행 시 기본 그룹(Ollama + Oracle만 필요한 그룹)만 실행
        cases = [c for c in ALL_CASES if c["group"] in DEFAULT_GROUPS]
        print("※ Spring API가 필요한 그룹(get_market_data, execute_order)은 기본 실행에서 제외됩니다.")
        print("  전체 실행: python test_tool_calling.py all")

    if target_group == "all":
        cases = ALL_CASES

    results = run_group(cases)
    print_summary(results)


if __name__ == "__main__":
    main()
