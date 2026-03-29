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
import re
from fastapi import FastAPI, Depends
from pydantic import BaseModel
from app.core.auth import get_user_context
from app.chatbot.router import detect
from app.chatbot.dispatcher import dispatch

app = FastAPI(title="Investment Chatbot")

# 이전 대화 맥락이 있어야 의미가 명확해지는 모호한 패턴
_AMBIGUOUS_RE = re.compile(
    r"(제일|가장|젤)\s*(많이\s*(오른|내린|상승|하락)|수익|손해|위험|좋은|나쁜)"
    r"|"
    r"(수익률|손익|비중|비율)\s*(이|가|은|는)?\s*(얼마|어때|어떻게|높|낮)"
)

# 직전 대화에서 포트폴리오/거래 관련 tool을 사용했는지 확인
_PORTFOLIO_TOOLS = {"get_portfolio_info", "get_trade_history"}


def _last_tool_was_portfolio(account_id: str) -> bool:
    """최근 대화에서 포트폴리오/거래 tool을 사용했으면 True"""
    try:
        from app.db.mongo import get_chat_history
        history = get_chat_history(account_id, limit=6)
        for msg in reversed(history):
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                tool_name = msg["tool_calls"][0].get("function", {}).get("name", "")
                return tool_name in _PORTFOLIO_TOOLS
    except Exception:
        pass
    return False


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    type: str = "text"          # "text" | "order" | "exchange"
    reply: str
    stock_code: str | None = None   # type="order" 일 때 프론트가 현재가 조회에 사용


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    req: ChatRequest,
    user_context: dict = Depends(get_user_context),
) -> ChatResponse:
    account_id = str(user_context.get("account_id", ""))

    intent, params = detect(req.message)

    # 모호한 질문 + 직전에 포트폴리오 tool 사용 → agent로 위임
    if intent in ("ranking", "chart_price", "unknown") and _AMBIGUOUS_RE.search(req.message):
        if _last_tool_was_portfolio(account_id):
            intent = "unknown"

    # 시세/뉴스 intent인데 종목 미지정 → 이전 맥락 기반 follow-up → agent로 위임
    if intent in ("chart_price", "stock_news") and not params.get("stock_code"):
        intent = "unknown"

    result = dispatch(intent, params, user_context, original_message=req.message)

    # user + tool_context(있으면) + assistant 를 한 턴으로 저장
    try:
        from app.db.mongo import save_conversation_turn
        turn_messages = [{"role": "user", "content": req.message}]
        turn_messages.extend(result.get("_tool_context") or [])

        # 템플릿 응답은 전체 마크다운 대신 짧은 요약을 저장
        # → llama가 이전 assistant 메시지의 긴 템플릿 형식을 따라 복사하는 것을 방지
        # 실제 데이터는 tool_context(tool 메시지)에 이미 저장되어 있음
        reply = result.get("reply", "")
        saved_reply = "조회한 데이터를 보여드렸어요." if "━" in reply else reply
        turn_messages.append({"role": "assistant", "content": saved_reply})
        save_conversation_turn(account_id, turn_messages)
    except Exception:
        pass

    return ChatResponse(
        type=result.get("type", "text"),
        reply=result.get("reply", ""),
        stock_code=result.get("stock_code"),
    )