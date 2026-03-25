# app/core/auth.py
import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.config import JWT_SECRET_KEY, JWT_ALGORITHM, SPRING_BASE_URL

_bearer = HTTPBearer()
_account_id_cache: dict[int, int] = {}  # user_id → account_id


def get_user_context(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    """
    Authorization: Bearer {accessToken} 헤더에서 user_id, account_id를 추출합니다.

    1. JWT 시크릿으로 토큰 검증 (Spring과 동일한 HS256 키 사용)
    2. sub 클레임에서 user_id 추출  ← JwtTokenProvider.createAccessToken() 확인
    3. account_id는 user_id 기준으로 캐싱해서 Spring API 중복 호출 방지
    """
    token = credentials.credentials
    user_id = _verify_jwt(token)
    account_id = _fetch_account_id_cached(user_id, token)
    return {"user_id": user_id, "account_id": account_id}


# ── JWT 검증 ───────────────────────────────────────────────────────────────────

def _verify_jwt(token: str) -> int:
    """
    Spring JwtTokenProvider와 동일한 방식으로 토큰을 검증합니다.
    - 서명 알고리즘: HS256
    - subject 클레임: userId (문자열)
    - 만료 시간(exp): jwt.decode()가 자동으로 검증
    """
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
        )
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="토큰에 사용자 정보가 없습니다.")
        return int(user_id)
    except JWTError:
        raise HTTPException(status_code=401, detail="유효하지 않거나 만료된 토큰입니다.")


# ── account_id 조회 (user_id 기준 캐싱) ───────────────────────────────────────

def _fetch_account_id_cached(user_id: int, token: str) -> int:
    """
    account_id는 사용자별로 변하지 않으므로 user_id만 키로 캐싱합니다.
    토큰이 갱신돼도 동일 user_id라면 Spring API를 재호출하지 않습니다.
    """
    if user_id in _account_id_cache:
        return _account_id_cache[user_id]

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
        account_id = data.get("accountId")
        if account_id is None:
            raise HTTPException(status_code=403, detail="계좌가 없는 사용자입니다.")

        _account_id_cache[user_id] = account_id
        return account_id

    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Spring 서버 연결 실패: {e}")