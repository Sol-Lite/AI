"""
get_db_data - 내부 DB 조회 (잔고 / 거래내역 / 포트폴리오 분석)
"""
from typing import Literal
from app.db.oracle import fetch_one, fetch_all
from AI.app.hardcoding.get_market_data import get_market_data
import requests
def get_db_data(
    type: Literal["balance", "trades", "portfolio", "balance_detail", "trades_detail", "portfolio_detail"],
    user_context: dict,
    limit: int = 3,
) -> dict:
    """
    내부 DB에서 사용자 데이터를 조회합니다.

    Args:
        type: 전체 조회(템플릿 반환) — "balance" | "trades" | "portfolio"
              세부 질문(LLM 답변) — "balance_detail" | "trades_detail" | "portfolio_detail"
        user_context: 세션에서 주입된 {"user_id": ..., "account_id": ...}
        limit: trades 조회 시 최근 건수 (기본값 3)

    Returns:
        type별 상이한 딕셔너리
    """
    account_id = user_context["account_id"]

    if type in ("balance", "balance_detail"):
        return _query_balance(account_id)
    elif type in ("trades", "trades_detail"):
        return _query_trades(account_id, limit)
    elif type in ("portfolio", "portfolio_detail"):
        return _query_portfolio(account_id)
    else:
        raise ValueError(f"Unknown type: {type}")

SPRING_BASE_URL = "http://localhost:8080"

def _call_spring_api(path: str, params: dict | None = None):
    try:
        url = f"{SPRING_BASE_URL}{path}"
        res = requests.get(url, params=params, timeout=3)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        return {
            "success": False,
            "error": "SPRING_API_ERROR",
            "message": str(e)
        }



# ── balance: 잔고 ──────────────────────────────────────────────────────────────────
# def _query_balance(account_id: str) -> dict:
#     sql = """
#         SELECT
#             cb.currency_code,
#             SUM(cb.available_amount) AS available_amount,
#             SUM(cb.total_amount) AS total_amount
#         FROM cash_balances cb
#         WHERE cb.account_id = :account_id
#         GROUP BY cb.currency_code
#     """

#     rows = fetch_all(sql, {"account_id": account_id}) or []

#     # 기본값 세팅
#     result = {
#         "krw_available": 0,
#         "krw_total": 0,
#         "usd_available": 0,
#         "usd_total": 0,
#         "total_eval": 0,
#     }
#     for currency_code, available, total in rows:
#         ccy = (currency_code or "").strip().upper()
#         if ccy == "KRW":
#             result["krw_available"] = float(available or 0)
#             result["krw_total"] = float(total or 0)
#         elif ccy == "USD":
#             result["usd_available"] = float(available or 0)
#             result["usd_total"] = float(total or 0)
#     return result

def _query_balance(account_id: str) -> dict:
    return _call_spring_api("/api/balance/cash")