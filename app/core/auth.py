import httpx
import time
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import SPRING_BASE_URL

_bearer = HTTPBearer()
_TOKEN_CACHE_TTL_SECONDS = 1800
_token_context_cache: dict[str, dict] = {}


def get_user_context(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    """
    Authorization: Bearer {accessToken} 헤더를 받아
    Spring `/api/users/me`를 통해 user_id, account_id를 조회합니다.

    - FastAPI는 JWT를 직접 검증하지 않습니다.
    - 같은 access token으로 반복 요청이 오면 토큰 단위 캐시를 사용합니다.
    """
    token = credentials.credentials
    now = time.time()
    cached = _token_context_cache.get(token)
    if cached and cached["expires_at"] > now:
        return {
            "user_id": cached["user_id"],
            "account_id": cached["account_id"],
            "token": token,
            "session_since": cached["session_since"],
        }

    try:
        with httpx.Client(timeout=3) as client:
            resp = client.get(
                f"{SPRING_BASE_URL}/api/users/me",
                headers={"Authorization": f"Bearer {token}"},
            )
        if resp.status_code == 401:
            raise HTTPException(status_code=401, detail="토큰이 만료되었습니다.")
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="사용자 정보 조회 실패")

        data = resp.json()
        user_id = data.get("userId")
        account_id = data.get("accountId")
        if user_id is None or account_id is None:
            raise HTTPException(status_code=403, detail="계좌가 없는 사용자입니다.")

        if len(_token_context_cache) >= 512:
            _evict_expired_cache_entries(now)

        _token_context_cache[token] = {
            "user_id": int(user_id),
            "account_id": int(account_id),
            "expires_at": now + _TOKEN_CACHE_TTL_SECONDS,
            "session_since": now,   # 토큰 최초 등록 시각 = 로그인 시각
        }
        return {
            "user_id": int(user_id),
            "account_id": int(account_id),
            "token": token,
            "session_since": now,
        }

    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Spring 서버 연결 실패: {e}")


def _evict_expired_cache_entries(now: float) -> None:
    expired_tokens = [
        token for token, cached in _token_context_cache.items()
        if cached["expires_at"] <= now
    ]
    for token in expired_tokens:
        _token_context_cache.pop(token, None)
