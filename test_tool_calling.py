"""
챗봇 Tool Calling 선택 정확도 테스트
실제 chat() 함수를 실행하면서 _dispatch를 spy로 래핑하여
어떤 tool이 어떤 type으로 호출됐는지 검증합니다.

사전 조건:
    - Ollama 실행 중
    - Oracle DB에 setup_dummy_data.py로 더미 데이터 삽입 완료
    - Spring API(get_market_data) 실행 중

실행:
    python test_tool_calling.py              # 전체 테스트
    python test_tool_calling.py get_db_data  # 특정 tool 그룹만
"""
import sys
from unittest.mock import patch
import app.services.llm as llm_module

USER_CONTEXT = {"user_id": "user-001", "account_id": "acc-001"}

# ── 테스트 케이스 정의 ─────────────────────────────────────────────────────────
# (질문, 기대 tool, 기대 type, 기대 추가 args(부분 일치), 설명)
# expected_args=None 이면 type만 검증
# expected_tool=None 이면 "tool 미호출" 기대 (LLM이 되묻기 응답해야 하는 케이스)

TEST_CASES = [
    # ── get_market_summary ─────────────────────────────────────────────────────
    {
        "group":        "get_market_summary",
        "message":      "오늘 한국 증시 어때?",
        "expected_tool": "get_market_summary",
        "expected_type": "korea",
        "expected_args": None,
        "desc":         "한국 시황 조회",
    },
    {
        "group":        "get_market_summary",
        "message":      "나스닥 지금 어떻게 돼?",
        "expected_tool": "get_market_summary",
        "expected_type": "us",
        "expected_args": None,
        "desc":         "미국 시황 조회",
    },
    {
        "group":        "get_market_summary",
        "message":      "삼성전자 관련 뉴스 알려줘",
        "expected_tool": "get_market_summary",
        "expected_type": "stock_news",
        "expected_args": None,
        "desc":         "종목 뉴스 조회",
    },

    # ── get_db_data: 전체 조회 ─────────────────────────────────────────────────
    {
        "group":        "get_db_data",
        "message":      "내 잔고 보여줘",
        "expected_tool": "get_db_data",
        "expected_type": "balance",
        "expected_args": None,
        "desc":         "잔고 전체 조회",
    },
    {
        "group":        "get_db_data",
        "message":      "거래내역 보여줘",
        "expected_tool": "get_db_data",
        "expected_type": "trades",
        "expected_args": None,
        "desc":         "거래내역 전체 조회",
    },
    {
        "group":        "get_db_data",
        "message":      "내 포트폴리오 분석해줘",
        "expected_tool": "get_db_data",
        "expected_type": "portfolio",
        "expected_args": None,
        "desc":         "포트폴리오 전체 조회",
    },

    # ── get_db_data: 세부 질문 ─────────────────────────────────────────────────
    {
        "group":        "get_db_data",
        "message":      "원화 잔고 얼마야?",
        "expected_tool": "get_db_data",
        "expected_type": "balance_detail",
        "expected_args": None,
        "desc":         "잔고 세부 - 원화",
    },
    {
        "group":        "get_db_data",
        "message":      "출금 가능 금액 알려줘",
        "expected_tool": "get_db_data",
        "expected_type": "balance_detail",
        "expected_args": None,
        "desc":         "잔고 세부 - 출금 가능",
    },
    {
        "group":        "get_db_data",
        "message":      "매수 몇 번 했어?",
        "expected_tool": "get_db_data",
        "expected_type": "trades_detail",
        "expected_args": None,
        "desc":         "거래내역 세부 - 매수 횟수",
    },
    {
        "group":        "get_db_data",
        "message":      "최근에 뭐 샀어?",
        "expected_tool": "get_db_data",
        "expected_type": "trades_detail",
        "expected_args": None,
        "desc":         "거래내역 세부 - 최근 매수",
    },
    {
        "group":        "get_db_data",
        "message":      "MDD 얼마야?",
        "expected_tool": "get_db_data",
        "expected_type": "portfolio_detail",
        "expected_args": None,
        "desc":         "포트폴리오 세부 - MDD",
    },
    {
        "group":        "get_db_data",
        "message":      "삼성전자 수익률 어떻게 돼?",
        "expected_tool": "get_db_data",
        "expected_type": "portfolio_detail",
        "expected_args": None,
        "desc":         "포트폴리오 세부 - 종목 수익률",
    },
    {
        "group":        "get_db_data",
        "message":      "내 총 평가금액 알려줘",
        "expected_tool": "get_db_data",
        "expected_type": "portfolio_detail",
        "expected_args": None,
        "desc":         "포트폴리오 세부 - 총 평가금액",
    },

    # ── get_market_data ────────────────────────────────────────────────────────
    {
        "group":        "get_market_data",
        "message":      "삼성전자 지금 얼마야?",
        "expected_tool": "get_market_data",
        "expected_type": "price",
        "expected_args": None,
        "desc":         "종목 현재가 조회",
    },
    {
        "group":        "get_market_data",
        "message":      "코스피 지수 알려줘",
        "expected_tool": "get_market_data",
        "expected_type": "index",
        "expected_args": {"index_code": "KOSPI"},
        "desc":         "지수 조회 - 코스피",
    },
    {
        "group":        "get_market_data",
        "message":      "달러 환율 얼마야?",
        "expected_tool": "get_market_data",
        "expected_type": "exchange",
        "expected_args": None,
        "desc":         "환율 조회",
    },
    {
        "group":        "get_market_data",
        "message":      "거래량 많은 종목 알려줘",
        "expected_tool": "get_market_data",
        "expected_type": "ranking",
        "expected_args": {"ranking_type": "volume"},
        "desc":         "랭킹 조회 - 거래량",
    },
    {
        "group":        "get_market_data",
        "message":      "오늘 많이 오른 종목 뭐야?",
        "expected_tool": "get_market_data",
        "expected_type": "ranking",
        "expected_args": {"ranking_type": "change_rate"},
        "desc":         "랭킹 조회 - 등락률",
    },

    # ── execute_order ──────────────────────────────────────────────────────────
    {
        "group":        "execute_order",
        "message":      "삼성전자 10주 사줘",
        "expected_tool": "execute_order",
        "expected_type": "buy",
        "expected_args": {"quantity": 10},
        "desc":         "매수 주문",
    },
    {
        "group":        "execute_order",
        "message":      "SK하이닉스 5주 팔아줘",
        "expected_tool": "execute_order",
        "expected_type": "sell",
        "expected_args": {"quantity": 5},
        "desc":         "매도 주문",
    },
    {
        "group":        "execute_order",
        "message":      "100만원 달러로 환전해줘",
        "expected_tool": "execute_order",
        "expected_type": "exchange",
        "expected_args": None,
        "desc":         "환전 주문",
    },

    # ── 불완전 정보 → tool 미호출 기대 ─────────────────────────────────────────
    {
        "group":        "execute_order(미호출)",
        "message":      "삼성전자 사줘",   # 수량 누락
        "expected_tool": None,
        "expected_type": None,
        "expected_args": None,
        "desc":         "매수 - 수량 누락 → 되묻기",
    },
    {
        "group":        "execute_order(미호출)",
        "message":      "주식 10주 팔아줘",  # 종목 누락
        "expected_tool": None,
        "expected_type": None,
        "expected_args": None,
        "desc":         "매도 - 종목 누락 → 되묻기",
    },
]


# ── 테스트 실행 ────────────────────────────────────────────────────────────────

def run_test(case: dict) -> dict:
    captured = []
    original_dispatch = llm_module._dispatch

    def spy_dispatch(fn_name, fn_args, user_context):
        captured.append({"tool": fn_name, "args": fn_args})
        return original_dispatch(fn_name, fn_args, user_context)

    with patch.object(llm_module, "_dispatch", side_effect=spy_dispatch):
        try:
            reply = llm_module.chat(case["message"], USER_CONTEXT)
        except Exception as e:
            return {"status": "ERROR", "error": str(e), "captured": captured, "reply": ""}

    actual_tool = captured[0]["tool"] if captured else None
    actual_args = captured[0]["args"] if captured else {}
    actual_type = actual_args.get("type") if captured else None

    # 판정
    if case["expected_tool"] is None:
        # tool이 호출되지 않아야 하는 케이스
        ok = actual_tool is None
    else:
        tool_ok = (actual_tool == case["expected_tool"])
        type_ok = (actual_type == case["expected_type"])
        args_ok = True
        if case["expected_args"]:
            args_ok = all(actual_args.get(k) == v for k, v in case["expected_args"].items())
        ok = tool_ok and type_ok and args_ok

    return {
        "status":      "PASS" if ok else "FAIL",
        "actual_tool": actual_tool,
        "actual_type": actual_type,
        "actual_args": actual_args,
        "reply":       reply if "reply" in dir() else "",
        "captured":    captured,
    }


def main():
    target_group = sys.argv[1] if len(sys.argv) > 1 else None
    cases = [c for c in TEST_CASES if target_group is None or c["group"] == target_group]

    results = []
    current_group = None

    for case in cases:
        if case["group"] != current_group:
            current_group = case["group"]
            print(f"\n{'━'*60}")
            print(f"  {current_group}")
            print(f"{'━'*60}")

        print(f"\n  Q: {case['message']}")
        print(f"     ({case['desc']})")

        res = run_test(case)

        exp_str = f"{case['expected_tool']} / type={case['expected_type']}" \
                  if case["expected_tool"] else "tool 미호출"
        act_str = f"{res['actual_tool']} / type={res['actual_type']}" \
                  if res["actual_tool"] else "tool 미호출"

        print(f"     기대: {exp_str}")
        print(f"     실제: {act_str}")

        if case["expected_args"] and res["actual_args"]:
            for k, v in case["expected_args"].items():
                actual_v = res["actual_args"].get(k)
                match = "✓" if actual_v == v else "✗"
                print(f"     args.{k}: 기대={v}, 실제={actual_v} {match}")

        status_mark = "PASS" if res["status"] == "PASS" else "FAIL" if res["status"] == "FAIL" else "ERROR"
        print(f"     [{status_mark}]", end="")
        if res["status"] == "ERROR":
            print(f" {res['error']}", end="")
        print()

        # 챗봇 답변 출력
        if res.get("reply"):
            print(f"     💬 답변: {res['reply'][:300]}"
                  + ("..." if len(res.get("reply","")) > 300 else ""))

        results.append({**case, **res})

    # ── 요약 ──────────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  결과 요약")
    print(f"{'='*60}")

    groups: dict[str, list] = {}
    for r in results:
        groups.setdefault(r["group"], []).append(r)

    total_pass = total_fail = total_error = 0
    for group, items in groups.items():
        p = sum(1 for i in items if i["status"] == "PASS")
        f = sum(1 for i in items if i["status"] == "FAIL")
        e = sum(1 for i in items if i["status"] == "ERROR")
        total_pass += p; total_fail += f; total_error += e
        print(f"  {group:<30} PASS {p}/{len(items)}", end="")
        if f: print(f"  FAIL {f}", end="")
        if e: print(f"  ERROR {e}", end="")
        print()

    print(f"{'─'*60}")
    total = len(results)
    print(f"  전체: PASS {total_pass}/{total}  FAIL {total_fail}  ERROR {total_error}")


if __name__ == "__main__":
    main()
