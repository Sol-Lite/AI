# main.py
import re
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from pydantic import BaseModel
from app.core.auth import get_user_context
from app.chatbot.router import detect
from app.chatbot.dispatcher import (
    dispatch, try_shortcut, pre_dispatch,
    INTENT_KW, _PORTFOLIO_KW_RE, _PORTFOLIO_COMPARISON_RE, _COMPARISON_RE,
)
from app import crawlers as crawler

# 조합되지 않은 한글 자모 감지 (오타/IME 미완성 입력) — HTTP 입력 검증 전용
_JAMO_RE = re.compile(r"[ㄱ-ㅎㅏ-ㅣ]")

@asynccontextmanager
async def lifespan(app: FastAPI):
    crawler.start()   # 서버 시작 시 크롤러 백그라운드 스레드 실행
    yield
    crawler.stop()    # 서버 종료 시 크롤러 정상 종료


app = FastAPI(title="Investment Chatbot", lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    type: str = "text"          # "text" | "order" | "exchange" | "stock_price" | "ranking" | "index" | "balance" | "exchange_rate"
    reply: str
    stock_code: str | None = None   # type="order" 일 때 프론트가 현재가 조회에 사용
    data: dict | None = None        # 카드 렌더링용 구조화 데이터


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    req: ChatRequest,
    user_context: dict = Depends(get_user_context),
) -> ChatResponse:
    account_id    = str(user_context.get("account_id", ""))
    session_since = user_context.get("session_since")   # 로그인 시각 (epoch float)

    # 조합되지 않은 한글 자모(ㄱ,ㄴ,ㅏ,ㅑ 등) 포함 → 오타/IME 미완성 입력
    if _JAMO_RE.search(req.message):
        return ChatResponse(reply="입력이 완성되지 않은 것 같아요. 다시 입력해 주세요.\n예) 삼성전자 현재가")

    # 짧은 단답 → 의도 키워드 또는 종목명이면 통과, 아닌 경우만 안내문구
    _stripped = req.message.strip()
    if len(_stripped) <= 2 and re.fullmatch(r"[가-힣a-zA-Z0-9]{1,2}", _stripped):
        if _stripped not in INTENT_KW:
            from app.stock_ref import resolve_from_csv, _normalize_message as _nm
            _code, _ = resolve_from_csv(_nm(_stripped))
            if not _code:
                from app.templates.guide import _GUIDE_MESSAGE
                return ChatResponse(reply=_GUIDE_MESSAGE)

    # 종목명만 있는 follow-up + 직전 tool 재사용 → LLM 없이 직접 처리
    result = try_shortcut(req.message, account_id, session_since)

    if result is None:
        intent, params = detect(req.message)

        # 문맥 기반 intent 보정 (손익 키워드, 비교 패턴, 종목 미지정 등)
        intent, params = pre_dispatch(intent, params, req.message, account_id, session_since)

        # unknown인데 세션 내 tool call 없으면 → 전체 기능 안내
        # 단, 명확한 키워드(포트폴리오/비교 등)가 있으면 agent로 위임
        if intent == "unknown":
            try:
                from app.db.mongo import get_chat_history
                from app.templates.guide import _GUIDE_MESSAGE
                _hist = get_chat_history(account_id, limit=6, since=session_since)
                has_tool = any(m.get("tool_calls") for m in _hist)
                has_clear_intent = (
                    _PORTFOLIO_KW_RE.search(req.message)
                    or _PORTFOLIO_COMPARISON_RE.search(req.message)
                    or _COMPARISON_RE.search(req.message)
                )
                if not has_tool and not has_clear_intent:
                    result = {"reply": _GUIDE_MESSAGE}
            except Exception:
                pass

        if result is None:
            result = dispatch(intent, params, user_context, original_message=req.message)

    # user + tool_context(있으면) + assistant 를 한 턴으로 저장
    try:
        from app.db.mongo import save_conversation_turn
        turn_messages = [{"role": "user", "content": req.message}]
        turn_messages.extend(result.get("_tool_context") or [])

        # 템플릿 응답은 전체 텍스트 대신 짧은 요약을 저장
        # → llama가 이전 assistant 메시지 형식을 따라 복사하는 것을 방지
        # 실제 데이터는 tool_context(tool 메시지)에 이미 저장되어 있음
        saved_reply = "조회한 데이터를 보여드렸어요." if result.get("_is_template") else result.get("reply", "")
        turn_messages.append({"role": "assistant", "content": saved_reply})
        save_conversation_turn(account_id, turn_messages)
    except Exception:
        pass

    return ChatResponse(
        type=result.get("type", "text"),
        reply=result.get("reply", ""),
        stock_code=result.get("stock_code"),
        data=result.get("data"),
    )
