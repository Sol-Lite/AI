"""
(5) 잔고 조회 — Spring API
dispatcher 의도: balance
호출: dispatcher._handle_balance() → get_db_data(type="balance") → format_balance()
"""
import requests

SPRING_BASE_URL = "http://localhost:8080"


def get_db_data(type: str, user_context: dict, **kwargs) -> dict:
    """
    잔고를 Spring API에서 조회합니다.

    Args:
        type:         "balance"
        user_context: {"user_id": ..., "account_id": ..., "token": ...}

    Returns:
        {
            "krw_available": float,
            "krw_total":     float,
            "usd_available": float,
            "usd_total":     float,
        }
    """
    if type in ("balance", "balance_detail"):
        return _query_balance(user_context["account_id"])
    raise ValueError(f"Unknown type: {type}")


# ── Spring API 호출 ────────────────────────────────────────────────────────────

def _call_spring_api(path: str, params: dict | None = None) -> dict:
    try:
        url = f"{SPRING_BASE_URL}{path}"
        res = requests.get(url, params=params, timeout=3)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        return {"success": False, "error": "SPRING_API_ERROR", "message": str(e)}


# ── balance: 잔고 ──────────────────────────────────────────────────────────────
# Spring API GET /api/balance/cash
# 반환 키: krw_available, krw_total, usd_available, usd_total

def _query_balance(account_id: str) -> dict:
    return _call_spring_api("/api/balance/cash")
