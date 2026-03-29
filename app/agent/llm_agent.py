"""
단일 agent — 4개 도구로 모든 질문 처리

도구:
    get_stock_price(stock_code)              — 종목 시세
    get_stock_news(stock_code)               — 종목별 뉴스
    get_portfolio_info(info_type)            — 포트폴리오 (holdings/sector/returns/risk/stats)
    get_trade_history(query_type, ...)       — 거래내역 (recent/by_stock/by_date)

흐름:
    1. MongoDB에서 대화 기록 조회
    2. system + history + user message → llama
    3. tool_calls → 실행 → 결과 추가 → 재전송 (최대 MAX_TURNS)
    4. 최종 content 반환
"""
import json
import re
import httpx
from app.core.config import OLLAMA_BASE_URL, OLLAMA_MODEL

MAX_TURNS = 5


# ── 도구 정의 ─────────────────────────────────────────────────────────────────

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_stock_price",
            "description": (
                "특정 종목의 현재가, 등락률, 거래량을 조회합니다. "
                "주가/시세/현재가 질문이나 종목명만 언급한 경우에 사용합니다. "
                "예) '하닉은?', '삼성전자 얼마야?', '현차 시세'"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "stock_code": {
                        "type": "string",
                        "description": "종목 코드 또는 종목명 (예: 005930, 삼성전자, AAPL, SK하이닉스)",
                    }
                },
                "required": ["stock_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_news",
            "description": "특정 종목의 최신 뉴스/기사를 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "stock_code": {
                        "type": "string",
                        "description": "종목 코드 또는 종목명 (예: 005930, 삼성전자, AAPL)",
                    }
                },
                "required": ["stock_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_portfolio_info",
            "description": "사용자의 포트폴리오 정보를 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "info_type": {
                        "type": "string",
                        "enum": ["holdings", "sector", "returns", "risk", "stats"],
                        "description": (
                            "조회할 정보 유형:\n"
                            "- holdings: 보유 종목 목록, 종목별 비중, 특정 종목 보유 여부\n"
                            "- sector: 섹터(업종)별 비중\n"
                            "- returns: 기간별 수익률 (일간, 1개월, 3개월, 6개월)\n"
                            "- risk: 평가손익, 실현손익, 변동성, MDD, 최고/최저 수익 종목\n"
                            "- stats: 승률, 손익비, 평균 수익금/손실금 등 거래 통계"
                        ),
                    }
                },
                "required": ["info_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_summary",
            "description": "한국 또는 미국 시장의 시황 요약을 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "market": {
                        "type": "string",
                        "enum": ["korea", "us"],
                        "description": "조회할 시장: korea(한국/코스피/코스닥), us(미국/나스닥/S&P500)",
                    }
                },
                "required": ["market"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_trade_history",
            "description": "사용자의 거래내역을 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query_type": {
                        "type": "string",
                        "enum": ["recent", "by_stock", "by_date"],
                        "description": (
                            "조회 유형:\n"
                            "- recent: 최근 거래내역 및 전체 거래 요약\n"
                            "- by_stock: 특정 종목의 전체 거래내역\n"
                            "- by_date: 특정 날짜의 거래내역"
                        ),
                    },
                    "stock_code": {
                        "type": "string",
                        "description": "query_type=by_stock일 때 종목 코드 또는 종목명",
                    },
                    "date": {
                        "type": "string",
                        "description": "query_type=by_date일 때 날짜 (예: 2026-03-27, 3월 27일)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "query_type=recent일 때 조회 건수 (기본값: 10)",
                    },
                },
                "required": ["query_type"],
            },
        },
    },
]


# ── 도구 실행기 ───────────────────────────────────────────────────────────────

def _fmt_rate(v: float) -> str:
    """수익률/등락률 float → 부호 포함 문자열. -0.00 방지"""
    if abs(v) < 0.005:
        return "0.00%"
    sign = "+" if v > 0 else ""
    return f"{sign}{v:.2f}%"


def _fmt_krw(v: float) -> str:
    return f"{int(v):,}원"


def _fmt_portfolio(info_type: str, data: dict) -> dict:
    """LLM 숫자 환각 방지: 포트폴리오 raw 수치를 포맷된 문자열로 교체"""
    if not isinstance(data, dict):
        return data

    if info_type == "holdings":
        for h in data.get("holdings", []):
            h["return_rate"]    = _fmt_rate(h.get("return_rate", 0))
            h["avg_buy_price"]  = _fmt_krw(h.get("avg_buy_price", 0))
            h["current_price"]  = _fmt_krw(h.get("current_price", 0))
        return data

    if info_type == "returns":
        for key in ("daily_return", "return_1m", "return_3m", "return_6m", "mdd"):
            if key in data:
                data[key] = _fmt_rate(data[key])
        return data

    if info_type == "risk":
        for key in ("mdd", "volatility"):
            if key in data:
                data[key] = _fmt_rate(data[key])
        for key in ("realized_pnl", "unrealized_pnl"):
            if key in data:
                data[key] = _fmt_krw(data[key])
        for stock_key in ("best_stock", "worst_stock"):
            s = data.get(stock_key)
            if s and isinstance(s, dict):
                s["return_rate"]    = _fmt_rate(s.get("return_rate", 0))
                s["unrealized_pnl"] = _fmt_krw(s.get("unrealized_pnl", 0))
        return data

    if info_type == "stats":
        for key in ("avg_win", "avg_loss", "total_realized"):
            if key in data:
                data[key] = _fmt_krw(data[key])
        return data

    return data


def _make_executor(account_id: str):
    def execute(name: str, args: dict) -> str:
        try:
            result = _execute(name, args, account_id)
        except Exception as e:
            result = {"error": str(e)}
        result_str = json.dumps(result, ensure_ascii=False)
        try:
            from app.db.mongo import save_tool_log
            save_tool_log(account_id, name, args, result_str)
        except Exception:
            pass
        return result_str
    return execute


def _resolve_stock(stock_input: str) -> str:
    """줄임말/동의어를 종목코드로 변환합니다. 예) '하닉' → '000660'"""
    from app.chatbot.resolver import resolve_from_csv
    code, _ = resolve_from_csv(stock_input)
    return code or stock_input


def _execute(name: str, args: dict, account_id: str) -> dict:
    if name == "get_stock_price":
        from app.data.market import get_market_data
        stock_code = _resolve_stock(args["stock_code"])
        data = get_market_data(type="price", stock_code=stock_code)
        # LLM 숫자 환각 방지: 원시 숫자 제거 후 포맷된 문자열만 전달
        if isinstance(data, dict) and "current_price" in data:
            price  = int(data.get("current_price") or 0)
            change = int(data.get("change") or 0)
            rate   = float(data.get("change_rate") or 0.0)
            c_sign = "+" if change >= 0 else ""
            r_sign = "+" if rate   >= 0 else ""
            return {
                "stock_name":    data.get("stock_name", stock_code),
                "stock_code":    data.get("stock_code", stock_code),
                "current_price": f"{price:,}원",
                "change":        f"{c_sign}{change:,}원",
                "change_rate":   f"{r_sign}{rate:.2f}%",
                "volume":        f"{int(data.get('volume') or 0):,}주",
            }
        return data

    if name == "get_market_summary":
        from app.data.news import get_market_summary
        market = args.get("market", "korea")
        return get_market_summary(type=market)

    if name == "get_stock_news":
        from app.data.news import get_market_summary
        stock_code = _resolve_stock(args.get("stock_code", ""))
        return get_market_summary(type="stock_news", stock_code=stock_code)

    if name == "get_portfolio_info":
        from app.data.portfolio import (
            get_holdings, get_sector_concentration,
            get_portfolio_returns, get_portfolio_risk, get_trade_stats,
        )
        info_type = args.get("info_type", "holdings")
        dispatch = {
            "holdings": lambda: get_holdings(account_id),
            "sector":   lambda: get_sector_concentration(account_id),
            "returns":  lambda: get_portfolio_returns(account_id),
            "risk":     lambda: get_portfolio_risk(account_id),
            "stats":    lambda: get_trade_stats(account_id),
        }
        fn = dispatch.get(info_type)
        result = fn() if fn else {"error": f"Unknown info_type: {info_type}"}
        return _fmt_portfolio(info_type, result)

    if name == "get_trade_history":
        from app.data.trades import (
            get_trade_summary, get_recent_trades,
            get_trades_by_stock, get_trades_by_date,
        )
        query_type = args.get("query_type", "recent")
        if query_type == "recent":
            summary = get_trade_summary(account_id)
            recent  = get_recent_trades(account_id, limit=args.get("limit", 10))
            result  = {**summary, "trades": recent["trades"]}
            # LLM 비교 환각 방지: 미리 계산된 비교 결과 주입
            buy_count  = int(result.get("buy_count",  0))
            sell_count = int(result.get("sell_count", 0))
            if buy_count > sell_count:
                result["매수_매도_비교"] = f"매수({buy_count}건)가 매도({sell_count}건)보다 많습니다."
            elif sell_count > buy_count:
                result["매수_매도_비교"] = f"매도({sell_count}건)가 매수({buy_count}건)보다 많습니다."
            else:
                result["매수_매도_비교"] = f"매수와 매도가 각각 {buy_count}건으로 같습니다."
            return result
        if query_type == "by_stock":
            stock_code = _resolve_stock(args["stock_code"])
            result = get_trades_by_stock(account_id, stock_code=stock_code)
            # LLM이 수량·가격을 따로 묻지 않도록 요약 문장 미리 생성
            trades = result.get("trades", [])
            summaries = []
            for t in trades[:5]:
                side  = "매도" if str(t.get("side", "")).upper() in ("SELL", "sell") else "매수"
                qty   = int(t.get("quantity") or 0)
                price = int(t.get("price") or 0)
                at    = str(t.get("executed_at", ""))[:10]
                summaries.append(f"{at} {side} {qty:,}주 @ {price:,}원")
            if summaries:
                result["거래_요약"] = " | ".join(summaries)
            return result
        if query_type == "by_date":
            return get_trades_by_date(account_id, date=args["date"])
        return {"error": f"Unknown query_type: {query_type}"}

    return {"error": f"Unknown tool: {name}"}


# ── 시스템 프롬프트 ───────────────────────────────────────────────────────────

def _build_system() -> str:
    from datetime import date
    today = date.today()
    weekday_map = ["월", "화", "수", "목", "금", "토", "일"]
    weekday = weekday_map[today.weekday()]
    return f"""당신은 친근한 주식 투자 어시스턴트입니다.
오늘 날짜: {today} ({weekday}요일). 상대적 날짜("저번주 토요일", "지난주 금요일" 등)는 이 날짜 기준으로 계산하세요.""" + """
한국어와 영어만 사용하세요. 다른 언어(러시아어 등)는 절대 사용하지 마세요.
자연스러운 한국어 구어체로 간결하게 답하세요.
투자와 전혀 무관한 질문에는 "투자 관련 질문만 답변드릴 수 있어요."라고 안내하세요.
섹터/업종 뉴스를 요청하면 "섹터별 뉴스는 제공하지 않아요. 종목별 뉴스(예: 삼성전자 뉴스)나 한국/미국 시황 뉴스를 이용해 주세요."라고 안내하세요.

[도구 호출 규칙 - 반드시 준수]
- 수치(가격, 수량, 날짜, 수익률 등)가 포함된 답변은 반드시 도구를 먼저 호출하세요.
- 도구를 호출하지 않고 수치를 생성하는 것은 절대 금지입니다.
- 도구 결과에 없는 정보는 답변에 절대 포함하지 마세요.
- 도구 결과의 값은 반드시 그대로 복사하세요. 숫자를 다시 계산하거나 포맷을 바꾸는 것은 절대 금지입니다.
- get_stock_price 결과가 있으면 반드시 이 형식으로 답하세요: "{stock_name} 현재가는 {current_price}이고, 전일 대비 {change} ({change_rate})입니다."
- 도구 결과가 비어있거나 오류면 "데이터를 불러올 수 없어요."라고 답하세요.

이전 대화 맥락을 반드시 활용하세요.
직전에 사용한 도구와 동일한 도구를 사용하세요.
종목명만 언급한 짧은 질문("하닉은?", "현차는?", "삼성은?")은 반드시 이전 대화의 도구를 따르세요. 예시:
- 이전에 get_stock_price 사용 → "하닉은?" → get_stock_price(SK하이닉스)
- 이전에 get_stock_news 사용 → "하닉은?" → get_stock_news(SK하이닉스)
- 이전에 get_stock_news 사용 → "현차는?" → get_stock_news(현대차)
- 이전에 get_market_summary(korea) 사용 → "미국은?" → get_market_summary(us)
- 이전에 get_trade_history 사용 → "삼성은?" → get_trade_history(by_stock, 삼성전자)

[이전 대화 기반 질문 처리 - 핵심]
이전 대화에 도구 결과(tool 메시지)가 있으면 그 데이터를 직접 참조해서 답하세요.
새로 도구를 호출하지 않아도 되는 경우:
- "그 중에 제일 오른 게 뭐야?" → 이전 포트폴리오/주가 데이터에서 찾아 답변
- "아까 말한 종목 수익률이 얼마였지?" → 이전 tool 결과에서 수치 추출
- "방금 본 거 기준으로 리스크가 큰 게 뭐야?" → 이전 데이터 해석
- "IT 비중이 너무 높은 거 아니야?" → 이전 포트폴리오 구성 데이터 참조
이전 데이터로 답할 수 있으면 도구를 다시 호출하지 말고 바로 답하세요.

[후속 질문 응답 규칙 - 반드시 준수]
후속 질문("제일 많이 오른 게?", "그 중에 뭐가 좋아?", "비중은?")에는 반드시 한두 문장으로 짧게 답하세요.
이전 대화에 포트폴리오 분석 결과가 있어도 전체를 다시 출력하지 마세요.
예시:
- "제일 많이 오른 종목이 뭐야?" → "SK하이닉스가 +0.49%로 가장 많이 올랐어요."
- "그 종목 비중은?" → "SK하이닉스 비중은 78.8%예요."
- "IT 비중이 높지 않아?" → "현재 섹터 데이터에 IT 섹터는 없고, 기타 100%로 분류되어 있어요."
이전 assistant 메시지가 긴 템플릿 형식이었어도 후속 답변은 반드시 짧게 유지하세요.

도구 선택 기준:
- 특정 종목 현재가/주가/시세, 또는 종목명만 언급 → get_stock_price
- 종목 뉴스/기사 → get_stock_news
- 한국/미국 시장 시황 요약 → get_market_summary (market 선택)
- 포트폴리오 질문 → get_portfolio_info (info_type 선택)
- 거래내역 질문 → get_trade_history (query_type 선택)

포트폴리오 info_type 선택:
- 보유 종목, 종목 비중, 보유 여부 → holdings
- 섹터/업종 비중 → sector
- 기간별 수익률 → returns
- 평가손익, 실현손익, MDD, 변동성, 최고/최저 수익 종목 → risk
- 승률, 손익비, 거래 통계 → stats

거래내역 query_type 선택:
- 최근 거래, 전체 거래 요약, 거래 횟수 → recent
- 특정 종목의 거래 이력 → by_stock
- 특정 날짜의 거래 → by_date

거래내역 답변 규칙:
- "언제" 질문 → executed_at 날짜/시간만 답하세요. 예) "삼성전자 2026-03-27 16:12에 1주를 179,700원에 매도했어요."
- "얼마에" 질문 → 가격과 수량을 함께 답하세요. 예) "삼성전자 2026-03-27 16:12에 1주를 179,700원에 매도했어요." (거래_요약 필드 활용)

보유 종목 응답 규칙:
- 보유 중: "네, X 종목 Y주 보유 중이에요." (다른 종목 나열 금지)
- 미보유: "X 종목은 현재 보유하고 있지 않아요." (보유 종목 나열 금지)

포트폴리오 분석 응답 규칙:
- 도구 결과의 수치만 그대로 해석하세요. 예) "1개월 수익률은 +3.2%입니다.", "MDD는 -8.5%입니다."
- "양호", "우수", "위험", "안정적" 등 주관적 평가 표현 금지
- 투자 의견, 매수/매도 권유, 포트폴리오 조정 권유 금지
- 수치 간 비교는 허용. 예) "A 종목이 B 종목보다 수익률이 높습니다."

출력 금지:
- "volatility", "mdd", "best_stock", "unrealized_pnl" 등 영어 변수명
- 투자 조언이나 포트폴리오 조정 권유
- 증권사 이름(미래에셋, 키움 등)"""


# ── ReAct 루프 ────────────────────────────────────────────────────────────────

def _run_agent(
    user_message: str,
    tools: list,
    execute_tool,
    history: list,
) -> tuple[str, list]:
    """
    Returns:
        (response_text, intermediate_messages)
        intermediate_messages: tool_call + tool_result 메시지 목록
                               다음 대화 맥락 파악을 위해 MongoDB에 저장됩니다.
    """
    messages = [{"role": "system", "content": _build_system()}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})
    turn_start = len(messages)  # tool 메시지가 추가되기 시작하는 인덱스

    with httpx.Client(timeout=120) as client:
        for _ in range(MAX_TURNS):
            payload = {
                "model":    OLLAMA_MODEL,
                "messages": messages,
                "tools":    tools,
                "stream":   False,
                "options":  {"temperature": 0},
            }
            try:
                resp = client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
                resp.raise_for_status()
            except httpx.TimeoutException:
                return "응답 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.", []
            except Exception as e:
                return f"AI 응답 오류: {e}", []

            data       = resp.json()
            message    = data.get("message", {})
            tool_calls = message.get("tool_calls") or []

            if not tool_calls:
                intermediate = messages[turn_start:]
                return message.get("content", "답변을 생성하지 못했습니다."), intermediate

            messages.append({"role": "assistant", "tool_calls": tool_calls})
            for call in tool_calls:
                fn   = call.get("function", {})
                name = fn.get("name", "")
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                try:
                    tool_result = execute_tool(name, args)
                except Exception as e:
                    tool_result = json.dumps({"error": str(e)}, ensure_ascii=False)
                messages.append({"role": "tool", "name": name, "content": tool_result})

    return "처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.", []


# ── 맥락 보강 ─────────────────────────────────────────────────────────────────

_INTENT_KEYWORDS = ["뉴스", "기사", "주가", "시세", "현재가", "차트", "거래", "수익", "포트폴리오", "시황"]
_TOOL_SUFFIX = {
    "get_stock_news":    "뉴스",
    "get_stock_price":   "현재가",
    "get_trade_history": "거래내역",
}

# "그 종목", "그거", "그 주식" 등 직전 맥락 종목을 가리키는 패턴
_THAT_STOCK_RE = re.compile(r"그\s*(종목|거|주식|애|놈)")


def _extract_last_stock(history: list) -> str | None:
    """
    최근 히스토리(최대 6개 메시지)에서 가장 마지막으로 언급된 종목명을 추출합니다.

    우선순위:
      1. get_stock_price / get_stock_news / get_trade_history(by_stock) tool_call 인자
      2. assistant 텍스트 응답의 첫 번째 종목명 ("현대차가 ...")
    """
    recent = history[-6:] if len(history) > 6 else history

    # 1. 가장 최근 tool_call 인자에서 stock_code 추출
    _STOCK_TOOLS = {"get_stock_price", "get_stock_news"}
    for msg in reversed(recent):
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            for call in msg["tool_calls"]:
                fn   = call.get("function", {})
                name = fn.get("name", "")
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                # get_stock_price / get_stock_news
                if name in _STOCK_TOOLS:
                    stock = args.get("stock_code", "")
                    if stock:
                        return stock
                # get_trade_history(by_stock) → stock_code 인자
                if name == "get_trade_history" and args.get("query_type") == "by_stock":
                    stock = args.get("stock_code", "")
                    if stock:
                        return stock

    # 2. assistant 텍스트 첫 줄에서 "종목명 + 조사" 패턴 추출
    #    예) "현대차가 -0.49%로", "SK하이닉스는 922,000원"
    _STOCK_IN_TEXT_RE = re.compile(
        r"^([\uAC00-\uD7A3A-Za-z0-9&·\s]{2,12}?)\s*(?:가|이|는|은|의|을|를)\s"
    )
    _SKIP_WORDS = {"현재", "비중", "수익률", "해당", "보유", "이전", "직전", "다음", "해외", "국내"}
    for msg in reversed(recent):
        if msg.get("role") == "assistant" and msg.get("content"):
            first_line = msg["content"].strip().split("\n")[0]
            m = _STOCK_IN_TEXT_RE.match(first_line)
            if m:
                candidate = m.group(1).strip()
                if len(candidate) >= 2 and candidate not in _SKIP_WORDS:
                    return candidate

    return None


_PRICE_NEWS_KW = {
    "현재가", "시세", "주가", "뉴스", "기사", "소식", "얼마", "가격",
    # 거래 follow-up: "몇 주 샀지", "얼마에 팔았지" 등
    "샀지", "팔았지", "매수했", "매도했", "거래했", "체결했",
    "몇 주", "수량", "몇 개",
}


def _has_stock_in_msg(msg: str) -> bool:
    """메시지에 종목명/코드가 포함되어 있는지 확인합니다."""
    from app.chatbot.resolver import resolve_from_csv, _normalize_message
    code, _ = resolve_from_csv(_normalize_message(msg))
    if code:
        return True
    if re.search(r'\b\d{6}\b', msg):
        return True
    if re.search(r'\b[A-Z]{2,5}\b', msg):
        return True
    return False


def _enrich_with_context(user_message: str, history: list) -> str:
    """
    메시지 맥락을 보강합니다.

    1. "그 종목 현재가" → "현대차 현재가"   (대명사 해소)
    2. "현재가 어때" (종목 없음) → "현대차 현재가 어때"  (follow-up 종목 주입)
    3. "하닉은?" (짧은 종목명) → "하닉 뉴스"  (직전 도구 타입 주입)
    """
    msg = user_message.strip()

    # ── 1. "그 종목 X" → "종목명 X" ──────────────────────────────────────────
    if _THAT_STOCK_RE.search(msg):
        stock = _extract_last_stock(history)
        if stock:
            return _THAT_STOCK_RE.sub(stock, msg)

    # ── 2. 가격/뉴스/거래 키워드 있는데 종목명 없음 → 직전 종목 주입 ─────────
    if any(kw in msg for kw in _PRICE_NEWS_KW) and not _has_stock_in_msg(msg):
        stock = _extract_last_stock(history)
        if stock:
            # "몇 주?" 는 거래 맥락에서만 "몇 주(株) 거래했어?"로 명확화
            if msg in ("몇 주?", "몇 주", "몇주?", "몇주"):
                return f"{stock} 몇 주 거래했어?"
            return f"{stock} {msg}"

    # ── 3. 짧은 종목명 + 이전 도구 타입 주입 ────────────────────────────────
    if len(msg) > 10 or any(kw in msg for kw in _INTENT_KEYWORDS):
        return user_message

    last_tool = None
    for m in reversed(history):
        if m.get("role") == "assistant" and m.get("tool_calls"):
            fn = m["tool_calls"][0].get("function", {})
            last_tool = fn.get("name")
            break

    suffix = _TOOL_SUFFIX.get(last_tool)
    if suffix:
        base = re.sub(r"[?은는이가도요\s]+$", "", msg)
        return f"{base} {suffix}"

    return user_message


# ── 공개 API ──────────────────────────────────────────────────────────────────

def ask_general(user_context: dict, user_message: str) -> tuple[str, list]:
    """
    단일 agent — 대화 기록 포함해 모든 질문을 처리합니다.

    Returns:
        (response_text, tool_context)
        tool_context: tool_call + tool_result 메시지 목록 (저장은 호출자가 담당)
    """
    account_id = str(user_context.get("account_id", ""))

    try:
        from app.db.mongo import get_chat_history
        history = get_chat_history(account_id, limit=6)
    except Exception:
        history = []

    enriched_message = _enrich_with_context(user_message, history)
    execute_tool = _make_executor(account_id)
    response, tool_context = _run_agent(enriched_message, _TOOLS, execute_tool, history)
    return response, tool_context
