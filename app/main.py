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
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from pydantic import BaseModel
from app.core.auth import get_user_context
from app.chatbot.router import detect
from app.chatbot.dispatcher import dispatch
from app import crawlers as crawler

# 조합되지 않은 한글 자모 감지 (오타/IME 미완성 입력)
_JAMO_RE = re.compile(r"[ㄱ-ㅎㅏ-ㅣ]")

# 종목명 only 패턴 — 의도 키워드 없이 종목명(+조사)만 있는 경우
_STOCK_ONLY_STRIP_RE = re.compile(r"[?은는이가도요\s]+$")
_INTENT_KW = {
    "현재가", "시세", "주가", "차트", "뉴스", "기사", "소식", "순위", "랭킹",
    "환율", "잔고", "지수", "시황", "매수", "매도", "환전", "얼마", "가격",
}
# 직전 tool → (intent, 처리 함수) 매핑
_SHORTCUT_TOOLS = {"get_stock_price", "get_stock_news"}


def _try_stock_shortcut(message: str, account_id: str, session_since: float | None = None) -> dict | None:
    """
    종목명만 있는 짧은 메시지 + 직전 응답이 price/news/order인 경우
    LLM 없이 바로 해당 동작을 재실행하고 반환합니다.

    예) "삼전 현재가" → "SK하닉은?" → get_stock_price(SK하이닉스) 직접 실행
        "삼전 매수"   → "SK하닉은?" → order(SK하이닉스) 직접 반환
    """
    msg = message.strip()

    # 빠른 사전 필터: 명확한 의도 키워드가 있으면 패스 (router가 처리)
    if any(kw in msg for kw in _INTENT_KW):
        return None

    # 종목명 해석: 원본 먼저 시도 → 실패 시 조사 제거 후 재시도
    # (예: "카카오페이" → 조사 제거 시 "카카오페"가 되므로 원본 우선)
    from app.chatbot.resolver import resolve_from_csv, _normalize_message
    code, name = resolve_from_csv(_normalize_message(msg))
    if not code:
        base = _STOCK_ONLY_STRIP_RE.sub("", msg)
        if not base:
            return None
        code, name = resolve_from_csv(_normalize_message(base))
    if not code:
        return None

    # 종목명 외 다른 내용이 있으면 숏컷 bypass → router/agent가 처리
    # synonym 적용 후 비교 (예: base="현차", name="현대차" → synonym 적용 → "현대차" → remaining="")
    from app.chatbot.resolver import _apply_synonyms
    msg_expanded = _apply_synonyms(_normalize_message(msg))
    # 조사 제거 후 비교 (예: "카카오페이는" → "카카오페이" → remaining="")
    msg_stripped = _STOCK_ONLY_STRIP_RE.sub("", msg_expanded)
    remaining = msg_stripped.lower().replace(name.lower(), "").strip()
    if remaining:
        return None

    # 직전 응답 확인 (최근 4턴, 현재 세션만)
    try:
        from app.db.mongo import get_chat_history
        history = get_chat_history(account_id, limit=4, since=session_since)
    except Exception:
        return None

    # 세션 내 tool_call 없음 → 의도를 알 수 없으므로 안내문구
    # (인사말만 오간 경우도 포함)
    has_tool_call = any(m.get("tool_calls") for m in history)
    if not has_tool_call:
        return {
            "reply": (
                f"**{name}**에 대해 어떤 정보를 원하시나요?\n"
                f"예) {name} 현재가  /  {name} 뉴스  /  {name} 매수"
            )
        }

    # ── buy/sell 주문 단축키: 직전 assistant가 "주문 정보를 입력하세요:" 형태 ──
    for m in reversed(history):
        if m.get("role") == "assistant":
            content = m.get("content", "")
            if "주문 정보를 입력하세요:" in content:
                return {
                    "type":       "order",
                    "reply":      f"**{name}** 주문 정보를 입력하세요:",
                    "stock_code": code,
                }
            break  # assistant 메시지 하나만 확인

    # ── price/news tool 단축키: 직전 tool_calls 확인 ──
    last_tool = None
    for m in reversed(history):
        if m.get("role") == "assistant" and m.get("tool_calls"):
            last_tool = m["tool_calls"][0].get("function", {}).get("name")
            break

    if last_tool not in _SHORTCUT_TOOLS:
        return None

    from app.chatbot.dispatcher import _get_tool_context

    if last_tool == "get_stock_price":
        from app.data.market import get_market_data
        from app.templates.chart_price import format_chart_price
        data = get_market_data(type="price", stock_code=code)
        if isinstance(data, dict) and data.get("error"):
            return None
        tool_ctx = _get_tool_context("get_stock_price", {"stock_code": code}, data)
        return {"reply": format_chart_price(data), "_tool_context": tool_ctx, "_is_template": True}

    if last_tool == "get_stock_news":
        from app.data.news import get_market_summary
        from app.templates.stock_news import format_stock_news
        data = get_market_summary(type="stock_news", stock_code=code)
        if isinstance(data, dict) and data.get("error"):
            return None
        # stock_name이 없으면 이미 알고 있는 한글 종목명 주입
        if not data.get("stock_name"):
            data = {**data, "stock_name": name}
        tool_ctx = _get_tool_context("get_stock_news", {"stock_code": code}, data)
        reply = format_stock_news(data)
        has_news = bool(data.get("news"))
        return {"reply": reply, "_tool_context": tool_ctx, "_is_template": has_news}

    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    crawler.start()   # 서버 시작 시 크롤러 백그라운드 스레드 실행
    yield
    crawler.stop()    # 서버 종료 시 크롤러 정상 종료


app = FastAPI(title="Investment Chatbot", lifespan=lifespan)

# 이전 대화 맥락이 있어야 의미가 명확해지는 모호한 패턴
_AMBIGUOUS_RE = re.compile(
    r"(제일|가장|젤)\s*(많이\s*(오른|내린|상승|하락)|수익|손해|위험|좋은|나쁜)"
    r"|"
    r"(수익률|손익|비중|비율)\s*(이|가|은|는)?\s*(얼마|어때|어떻게|높|낮)"
)

# 이전에 조회한 종목끼리 비교하는 패턴 (종목 수 무관)
_COMPARISON_RE = re.compile(
    r"(두|세|네|여러|그|이)\s*(종목|주식|회사)\s*(중|에서|가운데)"
    r"|"
    r"(둘|셋|넷)\s*중"
    r"|"
    r"어느\s*(쪽|게|것|종목|주식)\s*(이|가)?\s*(더|많이)"
    r"|"
    r"(두|세|여러|이)\s*(종목|주식)\s*(비교|차이)"
    r"|"
    r"(가장|제일|젤)\s*(많이)?\s*(오른|내린|상승|하락)"
    r"|"
    r"더\s*(많이|크게)?\s*(오른|내린|올랐|내렸)"
)

# 종목명과 함께 와도 포트폴리오 도구가 필요한 키워드 — chart_price 오라우팅 방지
_PORTFOLIO_KW_RE = re.compile(r"손익|평가손익|실현손익|수익금|손실금|평가액")

# "보유 종목 중 가장 많이 오른 건?" 처럼 포트폴리오 대상 비교 — 항상 agent로
_PORTFOLIO_COMPARISON_RE = re.compile(
    r"보유\s*(종목|주식|중|한).*?(가장|제일|젤|많이|오른|내린|올랐|내렸|수익|손해|높|낮)"
    r"|"
    r"(가장|제일|젤|더)\s*(많이)?\s*(오른|내린|올랐|내렸|수익|손실).*보유"
)

# 직전 대화에서 포트폴리오/거래 관련 tool을 사용했는지 확인
_PORTFOLIO_TOOLS = {"get_portfolio_info", "get_trade_history"}
_PRICE_TOOLS = {"get_stock_price", "get_stock_news"}


def _last_tool_was_portfolio(account_id: str, session_since: float | None = None) -> bool:
    """최근 대화에서 포트폴리오/거래 tool을 사용했으면 True"""
    try:
        from app.db.mongo import get_chat_history
        history = get_chat_history(account_id, limit=6, since=session_since)
        for msg in reversed(history):
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                tool_name = msg["tool_calls"][0].get("function", {}).get("name", "")
                return tool_name in _PORTFOLIO_TOOLS
    except Exception:
        pass
    return False


def _has_recent_price_context(account_id: str, session_since: float | None = None) -> bool:
    """최근 대화에서 가격/뉴스 tool을 2회 이상 사용했으면 True (특정 종목 비교 맥락)"""
    try:
        from app.db.mongo import get_chat_history
        history = get_chat_history(account_id, limit=8, since=session_since)
        count = sum(
            1 for msg in history
            if msg.get("role") == "assistant" and msg.get("tool_calls")
            and msg["tool_calls"][0].get("function", {}).get("name") in _PRICE_TOOLS
        )
        return count >= 2
    except Exception:
        pass
    return False


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
        if _stripped not in _INTENT_KW:
            from app.chatbot.resolver import resolve_from_csv, _normalize_message as _nm
            _code, _ = resolve_from_csv(_nm(_stripped))
            if not _code:
                from app.templates.guide import _GUIDE_MESSAGE
                return ChatResponse(reply=_GUIDE_MESSAGE)

    # 종목명만 있는 follow-up + 직전 tool 재사용 → LLM 없이 직접 처리
    shortcut = _try_stock_shortcut(req.message, account_id, session_since)
    if shortcut:
        result = shortcut
    else:
        result = None

    if result is None:
        intent, params = detect(req.message)

        # 손익/평가손익 키워드 → chart_price로 잘못 라우팅되는 것을 방지, 항상 agent로
        if intent == "chart_price" and _PORTFOLIO_KW_RE.search(req.message):
            intent = "unknown"

        # 모호한 질문 + 직전에 포트폴리오 tool 사용 → agent로 위임
        if intent in ("ranking", "chart_price", "unknown") and _AMBIGUOUS_RE.search(req.message):
            if _last_tool_was_portfolio(account_id, session_since):
                intent = "unknown"

        # "보유 종목 중 가장 많이 오른 건?" → 포트폴리오 대상 비교이므로 항상 agent로
        if intent in ("ranking", "chart_price", "unknown") and _PORTFOLIO_COMPARISON_RE.search(req.message):
            intent = "unknown"

        # 종목 비교 질문 + 직전에 가격 조회 2회 이상 → agent로 위임
        if intent in ("ranking", "chart_price", "unknown") and _COMPARISON_RE.search(req.message):
            if _has_recent_price_context(account_id, session_since):
                intent = "unknown"

        # 시세/뉴스 intent인데 종목 미지정 → 이번 세션 맥락에서 종목 추출 시도
        if intent in ("chart_price", "stock_news") and not params.get("stock_code"):
            try:
                from app.db.mongo import get_chat_history
                from app.agent.llm_agent import _extract_last_stock
                _hist = get_chat_history(account_id, limit=6, since=session_since)
                _last_stock = _extract_last_stock(_hist)
                if _last_stock:
                    params["stock_code"] = _last_stock
                # 종목 못 찾으면 항상 dispatcher 안내문구 (agent 위임 안 함)
            except Exception:
                pass  # intent 유지 → dispatcher 안내문구

        # unknown인데 세션 내 tool call 없으면 → 전체 기능 안내
        # 단, 포트폴리오/비교 등 명확한 키워드가 있으면 agent로 위임
        _has_clear_intent = (
            _PORTFOLIO_KW_RE.search(req.message)
            or _PORTFOLIO_COMPARISON_RE.search(req.message)
            or _COMPARISON_RE.search(req.message)
        )
        if intent == "unknown" and not _has_clear_intent:
            try:
                from app.db.mongo import get_chat_history
                from app.templates.guide import _GUIDE_MESSAGE
                _hist = get_chat_history(account_id, limit=6, since=session_since)
                has_tool = any(m.get("tool_calls") for m in _hist)
                if not has_tool:
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
        reply = result.get("reply", "")
        saved_reply = "조회한 데이터를 보여드렸어요." if result.get("_is_template") else reply
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