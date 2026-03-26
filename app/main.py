# from fastapi import FastAPI, Depends, HTTPException
# from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
# from pydantic import BaseModel
# from app.services.llm import chat

# app = FastAPI(title="Investment Chatbot")
# _bearer = HTTPBearer()


# class ChatRequest(BaseModel):
#     message: str


# class ChatResponse(BaseModel):
#     reply: str


# def get_user_context(credentials: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict:
#     """
#     JWT 토큰에서 user_id, account_id를 추출합니다.
#     TODO: 실제 JWT 검증 및 디코딩으로 교체 (예: python-jose)
#     """
#     token = credentials.credentials
#     if not token:
#         raise HTTPException(status_code=401, detail="인증 토큰이 필요합니다.")

#     # TODO: jwt.decode(token, SECRET_KEY, algorithms=["HS256"]) 로 교체
#     return {
#         "user_id":    1,
#         "account_id": 1,
#     }


# @app.post("/chat", response_model=ChatResponse)
# async def chat_endpoint(
#     req: ChatRequest,
#     user_context: dict = Depends(get_user_context),
# ) -> ChatResponse:
#     reply = chat(req.message, user_context)
#     return ChatResponse(reply=reply)

# main.py
from fastapi import FastAPI, Depends
from pydantic import BaseModel
from typing import Any
from app.core.auth import get_user_context
from app.chatbot.rule_router import detect
from app.chatbot.dispatcher import dispatch

app = FastAPI(title="Investment Chatbot")


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    action: str | None = None
    # 프론트엔드 액션 파라미터
    # activate_buy / activate_sell: {"stock_code": str}
    # activate_exchange: {}
    action_params: dict[str, Any] | None = None


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    req: ChatRequest,
    user_context: dict = Depends(get_user_context),
) -> ChatResponse:
    intent, params = detect(req.message)
    result = dispatch(intent, params, user_context, original_message=req.message)
    return ChatResponse(
        reply=result.get("reply", ""),
        action=result.get("action"),
        action_params=result.get("action_params"),
    )