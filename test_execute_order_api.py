"""
execute_order → Spring API 실제 연동 확인 테스트

사전 조건:
    - Spring 서버 실행 중 (http://localhost:8080)
    - .env에 TEST_JWT_TOKEN=<유효한 JWT> 추가

실행:
    python test_execute_order_api.py
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TEST_JWT_TOKEN")
if not TOKEN:
    print("\n[ERROR] .env에 TEST_JWT_TOKEN이 설정되지 않았습니다.")
    print("  예) TEST_JWT_TOKEN=eyJhbGci...\n")
    sys.exit(1)

from app.tools.execute_order import execute_order
from app.templates.order import format_order
from app.core.config import SPRING_BASE_URL

USER_CONTEXT = {"user_id": 202, "account_id": 1, "token": TOKEN}


# ── 개별 테스트 함수 ────────────────────────────────────────────────────────────

def case_buy_market():
    """국내 시장가 매수 — 삼성전자 1주"""
    result = execute_order(type="buy", user_context=USER_CONTEXT,
                           stock_code="005930", quantity=1)
    _assert_no_error(result)
    return result


def case_buy_limit():
    """국내 지정가 매수 — 삼성전자 1주 @ 60,000원"""
    result = execute_order(type="buy", user_context=USER_CONTEXT,
                           stock_code="005930", quantity=1, price=60_000)
    _assert_no_error(result)
    return result


def case_sell_market():
    """국내 시장가 매도 — 삼성전자 1주"""
    result = execute_order(type="sell", user_context=USER_CONTEXT,
                           stock_code="005930", quantity=1)
    _assert_no_error(result)
    return result


def case_sell_limit():
    """국내 지정가 매도 — 삼성전자 1주 @ 80,000원"""
    result = execute_order(type="sell", user_context=USER_CONTEXT,
                           stock_code="005930", quantity=1, price=80_000)
    _assert_no_error(result)
    return result


def case_foreign_buy():
    """해외 시장가 매수 — AAPL 1주"""
    result = execute_order(type="buy", user_context=USER_CONTEXT,
                           stock_code="AAPL", quantity=1)
    _assert_no_error(result)
    return result


def case_missing_stock_code():
    """stock_code 누락 → ValueError 발생 기대 (정상)"""
    try:
        execute_order(type="buy", user_context=USER_CONTEXT, quantity=1)
        raise AssertionError("ValueError가 발생해야 합니다.")
    except ValueError as e:
        return f"기대한 ValueError: {e}"


def case_missing_quantity():
    """quantity 누락 → ValueError 발생 기대 (정상)"""
    try:
        execute_order(type="buy", user_context=USER_CONTEXT, stock_code="005930")
        raise AssertionError("ValueError가 발생해야 합니다.")
    except ValueError as e:
        return f"기대한 ValueError: {e}"


def case_exchange_mock():
    """환전 목 데이터 — 원화 100만원 → 달러"""
    result = execute_order(type="exchange", user_context=USER_CONTEXT,
                           from_currency="KRW", to_currency="USD", amount=1_000_000)
    assert "fx_order_id" in result, "fx_order_id 없음"
    return result


# ── 헬퍼 ───────────────────────────────────────────────────────────────────────

def _assert_no_error(result: dict):
    if result.get("error"):
        raise AssertionError(result.get("message", "알 수 없는 오류"))


def _show_template(result):
    """dict 결과이면 format_order 템플릿 출력"""
    if isinstance(result, dict):
        print()
        for line in format_order(result).splitlines():
            print(f"     │ {line}")


# ── 실행기 ──────────────────────────────────────────────────────────────────────

CASES = [
    ("국내 시장가 매수  (삼성전자 1주)",           case_buy_market),
    ("국내 지정가 매수  (삼성전자 1주 @ 60,000원)", case_buy_limit),
    ("국내 시장가 매도  (삼성전자 1주)",           case_sell_market),
    ("국내 지정가 매도  (삼성전자 1주 @ 80,000원)", case_sell_limit),
    ("해외 시장가 매수  (AAPL 1주)",               case_foreign_buy),
    ("누락 검증        stock_code 없음",           case_missing_stock_code),
    ("누락 검증        quantity 없음",             case_missing_quantity),
    ("환전 목 데이터   원화 100만원 → 달러",        case_exchange_mock),
]


def main():
    print(f"\n{'━'*62}")
    print("  execute_order  Spring API 연동 테스트")
    print(f"{'━'*62}")
    print(f"  SPRING_BASE_URL : {SPRING_BASE_URL}")
    print(f"  TOKEN (앞 30자) : {TOKEN[:30]}...")

    pass_cnt = fail_cnt = error_cnt = 0

    for label, fn in CASES:
        print(f"\n  {'─'*58}")
        print(f"  {label}")
        try:
            result = fn()
            _show_template(result)
            if isinstance(result, dict):
                print(f"\n  raw : {result}")
            else:
                print(f"\n  raw : {result}")
            status = "PASS"
            pass_cnt += 1
        except AssertionError as e:
            print(f"\n  [FAIL] {e}")
            status = "FAIL"
            fail_cnt += 1
        except Exception as e:
            print(f"\n  [ERROR] {type(e).__name__}: {e}")
            status = "ERROR"
            error_cnt += 1

        print(f"  [{status}]")

    total = len(CASES)
    print(f"\n{'━'*62}")
    print(f"  전체 {total}건  |  PASS {pass_cnt}  FAIL {fail_cnt}  ERROR {error_cnt}")
    print(f"{'━'*62}\n")

    sys.exit(0 if fail_cnt == 0 and error_cnt == 0 else 1)


if __name__ == "__main__":
    main()
