"""
(5) 잔고 조회 — Spring API
dispatcher 의도: balance
호출: dispatcher._handle_balance() → get_db_data(type="balance") → format_balance()
"""
import requests
from app.core.config import SPRING_BASE_URL, HTTP_TIMEOUT_SECONDS


def get_db_data(type: str, user_context: dict, **kwargs) -> dict:
    """
    잔고를 Spring API에서 조회합니다.

    Args:
        type:         "balance"
        user_context: {"user_id": ..., "account_id": ..., "token": ...}
    """
    token = user_context.get("token", "")
    if type in ("balance", "balance_detail"):
        return _query_balance(token)
    raise ValueError(f"Unknown type: {type}")


# ── Spring API 호출 ────────────────────────────────────────────────────────────

def _call_spring_api(path: str, token: str = "", params: dict | None = None) -> dict:
    try:
        url     = f"{SPRING_BASE_URL}{path}"
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        res     = requests.get(url, params=params, headers=headers, timeout=HTTP_TIMEOUT_SECONDS)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        return {"success": False, "error": "SPRING_API_ERROR", "message": str(e)}


# ── balance: 잔고 ──────────────────────────────────────────────────────────────

def _query_balance(token: str) -> dict:
    return _call_spring_api("/api/balance/summary", token=token)
