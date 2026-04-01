"""
룰 베이스 의도 감지 (Intent Detection) 모듈

지원 의도(intent):
    index           - (1) 지수 조회
    exchange_rate   - (2) 환율 조회
    ranking         - (3) 주식 순위 조회
    chart_price     - (4) 차트+시세 조회
    balance         - (5) 잔고 조회
    buy_intent      - (6) 매수 버튼 활성화
    sell_intent     - (6) 매도 버튼 활성화
    exchange_order  - (7) 환전 버튼 활성화
    korea_summary   - (8) 한국 시황 요약
    us_summary      - (9) 미국 시황 요약
    stock_news      - (10) 종목별 뉴스 요약
    trades          - (11) 거래내역 조회  [AI agent]
    portfolio       - (12) 포트폴리오 분석 [AI agent]
    unknown         - 인식 불가
"""
import re
from app.stock_ref import resolve_from_csv, resolve_all_from_csv, _normalize_message

# ── 의도별 키워드 패턴 ──────────────────────────────────────────────────────────
_PATTERNS: dict[str, list[str]] = {
    # 인사 / 시작
    "greeting": [
        r"^안녕",
        r"^hi$",
        r"^hello$",
        r"^헬로",
        r"^반가",
        r"^처음\s*왔",
        r"^뭐\s*할\s*수\s*있",
        r"^뭐\s*돼",
        r"^도움말",
        r"^기능",
        r"^사용법",
    ],
    # (6) 매수 — 반드시 ranking/index 등보다 먼저 검사
    "buy_intent": [
        r"매수(?!\s*(한|했|하였|내역|기록|이력|가|이|는|은|량|비중|수))",
        r"사고\s*싶",
        r"(?<![가-힣])사(?=[줘요\s]|$)",
        r"살게",
        r"살래",
        r"사려고",
        r"사보려고",
        r"살까",
        r"사\s*줘",
        r"사볼까",
        r"구매하고\s*싶",
        r"구매\s*할게",
        r"주식\s*사",
        r"살래",
        r"사줘",
        r"구매",
        r"매입",
        r"매매",
        r"주문",
    ],
    # (6) 매도
    "sell_intent": [
        r"매도(?!\s*(한|했|하였|내역|기록|이력|가|이|는|은|량|비중|수))",
        r"팔고\s*싶",
        r"팔게",
        r"팔아보려고",
        r"팔아",
        r"팔래",
        r"팔까",
        r"팔자",
        r"팔아\s*줘",
        r"판매하고\s*싶",
        r"주식\s*팔",
        r"팔려고",
        r"팔래",
        r"팔래요",
        r"팔아줘",
        r"구매",
    ],
    # (7) 환전 주문 — 환율 조회보다 먼저 검사
    "exchange_order": [
        r"환전\s*하고\s*싶",
        r"환전\s*해\s*줘",
        r"환전\s*할게",
        r"환전\s*할래",
        r"환전\s*하자",
        r"환전\s*해",
        r"환전\s*하려",
        r"달러로\s*바꿔",
        r"달러로\s*환전",
        r"(달러|엔화|엔|유로|파운드|원화|외화|위안)\s*(로|으로)?\s*(바꾸고\s*싶|바꿔\s*줘|바꿔\s*주세요|바꿀게|바꿀래|바꾸고\s*싶어|바꾸려고|바꾸자)",
        r"(달러|엔화|엔|유로|파운드|원화|외화|위안)\s*(로|으로)?\s*(교환|환전)",
        r"(달러|엔화|엔|유로|파운드|원화|외화|위안)\s*(을|를)?\s*(사고\s*싶|살게|살래|사줘|사려고|사자)",
        r"원화로\s*바꿔",
        r"원화로\s*환전",
        r"달러\s*환전",
        r"원화\s*환전",
        r"환전"
    ],
    # (5) 잔고 조회
    "balance": [
        r"잔고",
        r"잔액",
        r"예수금",
        r"보유\s*현금",
        r"현금\s*잔액",
        r"내\s*계좌",
        r"계좌\s*잔액",
        r"보유\s*금액",
        r"투자\s*가능\s*금액",
        r"가용\s*금액",
        r"총\s*자산",
        r"현금\s*잔고",
        r"내\s*자산(?!\s*(분석|수익률|현황|비중))",
        r"보유\s*원화",
        r"보유\s*달러",
    ],
    # (10) 종목별 뉴스 — chart_price 보다 먼저 검사
    "stock_news": [
        r"뉴스",
        r"기사",
        r"소식",
        r"뉴스\s*요약",
        r"최신\s*뉴스",
        r"관련\s*뉴스",
        r"기사\s*요약",
        r"최신\s*기사",
        r"관련\s*기사",
    ],
    # (4) 차트+시세
    "chart_price": [
        r"차트",
        r"시세",
        r"주가",
        r"현재가",
        r"현재\s*가격",
        r"고가",
        r"시가(?!총액)",   # "시가총액"은 ranking에서 처리
        r"종가",
        r"저가",
        r"최고가",
        r"최저가",
        r"상한가",
        r"하한가",
        r"가격\s*알려",
        r"가격\s*조회",
        r"얼마야",
        r"얼마에요",
        r"얼마예요",
        r"얼마임",
    ],
    # (3) 주식 순위
    "ranking": [
        r"순위",
        r"랭킹",
        r"상위\s*종목",
        r"인기\s*종목",
        r"핫한\s*종목",
        r"상승주",
        r"하락주",
        r"많이\s*오른",
        r"많이\s*내린",
        r"상승률\s*높",
        r"하락률\s*높",
        r"거래량\s*순",
        r"거래량\s*기준",
        r"거래량\s*으로",
        r"거래량\s*많",
        r"거래대금\s*순",
        r"거래대금\s*으로",
        r"거래대금\s*기준",
        r"거래대금\s*많",
        r"시가총액\s*순",
        r"시총\s*순",
        r"시총\s*으로",
        r"시가총액\s*기준",
        r"시가총액\s*으로",
        r"시총\s*기준",
        r"시총",
        r"급상승",
        r"급하락",
    ],
    # (8) 한국 시황 — 한국/코스피 특정 키워드만
    "korea_summary": [
        r"한국\s*시황",
        r"국내\s*시황",
        r"한국장",
        r"코스피\s*시황",
        r"코스닥\s*시황",
        r"한국\s*시장",
        r"국내\s*시장",
        r"국장",
        r"코스피\s*시장",
        r"코스닥\s*시장",
        r"국내\s*증시",
        r"한국\s*증시",
    ],
    # (8-2) 한국+미국 시황 동시 — 범용 키워드 (korea/us_summary 보다 나중에 검사)
    "market_summary": [
        r"시황",
        r"시장",
        r"시장\s*어때",
        r"오늘\s*시황",
        r"오늘\s*시장",
        r"오늘\s*장",
        r"장\s*어때",
        r"장\s*상황",
        r"증시\s*어때",
    ],
    # (9) 미국 시황
    "us_summary": [
        r"미국\s*시황",
        r"미국장",
        r"미장",
        r"미국\s*시장",
        r"나스닥\s*시장",
        r"해외\s*시장",
        r"나스닥\s*시황",
        r"해외\s*시황",
        r"월가",
        r"뉴욕\s*증시",
        r"뉴욕증시",
        r"미국\s*증시",
        r"미국\s*주식\s*시장",
    ],
    # (1) 지수 조회
    "index": [
        r"지수",
        r"한국\s*지수",
        r"미국\s*지수",
        r"코스피",
        r"코스닥",
        r"나스닥",
        r"s&p",
        r"sp\s*500",
        r"에스앤피",
        r"에스엔피",
        r"다우",
        r"다우\s*존스",
        r"닛케이",
        r"닉케이",
        r"항셍",
    ],
    # (2) 환율 조회
    "exchange_rate": [
        r"환율",
        r"달러\s*환율",
        r"달러\s*얼마",
        r"달러\s*가격",
        r"달러\s*시세",
        r"달러",
        r"달러값",
        r"원달러",
        r"달러원",
        r"오늘\s*환율",
        r"현재\s*환율",
        r"유로\s*환율",
        r"유로\s*얼마",
        r"엔화\s*환율",
        r"엔화\s*얼마",
        r"엔\s*환율",
    ],
    # (11) 거래내역 [AI agent]
    "trades": [
        r"거래\s*내역",
        r"거래내역",
        r"매매\s*내역",
        r"체결\s*내역",
        r"거래\s*기록",
        r"거래\s*이력",
        r"내\s*거래",
        r"주문\s*내역",
        r"최근\s*거래",
        r"매수\s*내역",
        r"매도\s*내역",
        r"투자\s*내역",
        # 시점 + 과거형 매수/매도/거래/주문 — "언제 샀지?", "어제 팔았어?", "최근에 매수했나?"
        r"(언제|어제|최근에?|지난번에?|며칠|몇\s*일)\s*(샀|팔았|매수했|매도했|체결했|거래했|주문했)",
        r"(샀|팔았|매수했|매도했|체결했|거래했|주문했)(지|나|니|어|요|나요|지요|었나|었지|었어)",
    ],
    # (12) 포트폴리오 분석 [AI agent]
    "portfolio": [
        r"포트폴리오",
        r"포폴",
        r"자산\s*분석",
        r"수익률\s*분석",
        r"투자\s*분석",
        r"내\s*주식\s*분석",
        r"내\s*수익률",
        r"보유\s*한?\s*(주식|종목)",
        r"내\s*가?\s*보유",
        r"보유\s*(중|해|하고|있어|있나|있어요|하고\s*있)",
        r"내\s*자산",
        r"\bMDD\b",
        r"\bMDd\b",
        r"\bMdD\b",
        r"\bmDD\b",
        r"\bMdd\b",
        r"\bmdD\b",
        r"\bmdd\b",
        r"\bmDd\b",
        r"변동성",
        r"최대\s*낙폭",
        r"승률",
        r"손익비",
        r"평가\s*손익",
        r"실현\s*손익",
        r"거래\s*통계",
        r"매매\s*통계",
        r"투자\s*통계",
        r"거래\s*성과",
        r"평균\s*(수익금|손실금)",
    ],
}

# 의도 검사 우선순위 (앞에 있을수록 먼저 검사)
_PRIORITY = [
    "greeting",
    "trades",         # 시점+과거형 매수/매도 패턴을 buy_intent보다 먼저 잡음
    "exchange_order", # 화폐 바꾸기 패턴이 buy_intent보다 먼저 잡혀야 함
    "buy_intent",
    "sell_intent",
    "balance",
    "portfolio",      # 크로스도메인 복합 패턴 우선 (보유종목+뉴스/시세 등)
    "stock_news",
    "korea_summary",
    "us_summary",
    "market_summary", # 범용 시황 — 한국/미국 특정 키워드가 없을 때
    "index",          # chart_price보다 먼저: "코스피 얼마야" 등이 chart_price로 잘못 잡히는 문제 방지
    "chart_price",
    "ranking",
    "exchange_rate",
]

# 파라미터 추출 시 무시할 한글 단어 목록
_IGNORE_WORDS = frozenset({
    "차트", "시세", "주가", "현재가", "얼마", "뉴스", "기사", "소식",
    "매수", "매도", "잔고", "환율", "지수", "순위", "랭킹", "조회",
    "알려", "알아", "보여", "보고", "싶어", "줘", "해줘",
    "오늘", "지금", "현재", "최근", "최신", "종목", "주식",
    "해주세요", "해줘요", "볼게요", "볼께요",
})


# ── 메인 API ──────────────────────────────────────────────────────────────────

def detect(message: str) -> tuple[str, dict]:
    """
    사용자 메시지에서 의도(intent)와 파라미터를 추출합니다.

    Returns:
        (intent, params)
        예) ("chart_price", {"stock_code": "삼성전자"})
            ("ranking",     {"ranking_type": "rising", "market": "domestic"})
            ("unknown",     {})
    """
    msg = message.strip()

    # 대화 지시어가 있으면 이전 맥락 기반 질문 → agent로 직행
    if _is_followup(msg):
        return "unknown", {}

    for intent in _PRIORITY:
        for pattern in _PATTERNS[intent]:
            if re.search(pattern, msg, re.IGNORECASE):
                params = _extract_params(intent, msg)
                return intent, params

    return "unknown", {}


# 이전 대화를 가리키는 지시어 패턴
_FOLLOWUP_RE = re.compile(
    r"^(그\s*(중|종목|거|게|건|쪽|애|놈|분)|저\s*(중|종목|거)|아까|방금|앞에서|이전에|위에서|해당\s*(종목|주식|거))"
    r"|그\s*(중에|종목은|종목이|거는|게|건데|게요|종목의)"
    r"|해당\s*(종목|주식)",
    re.IGNORECASE,
)


def _is_followup(msg: str) -> bool:
    """이전 대화를 참조하는 follow-up 질문이면 True"""
    return bool(_FOLLOWUP_RE.search(msg))


# ── 파라미터 추출 헬퍼 ─────────────────────────────────────────────────────────

def _extract_stock(message: str) -> str | None:
    """
    메시지에서 종목코드를 추출합니다.

    우선순위:
      1. 6자리 숫자          → 국내 종목코드 (예: 005930)
      2. CSV 종목명 매칭     → kospi200_targets.csv / NASDAQ100.csv에서 한글 종목명 검색
      3. 2~5자리 영문 대문자 → 미국 티커     (예: AAPL)
    """
    # 영문-한글 경계 공백 제거 ("SK 하이닉스" → "SK하이닉스")
    normalized = _normalize_message(message)

    # 1. 국내 종목코드: 6자리 숫자
    m = re.search(r'\b(\d{6})\b', normalized)
    if m:
        return m.group(1)

    # 2. CSV에서 한글 종목명 → 종목코드 변환 (긴 이름 우선 매칭)
    #    ticker 검사보다 먼저: "SK하이닉스"가 "SK" 티커로 잡히는 문제 방지
    code, _ = resolve_from_csv(normalized)
    if code:
        return code

    # 3. 미국 티커: 2~5자리 영문 대문자
    m = re.search(r'\b([A-Z]{2,5})\b', normalized)
    if m:
        return m.group(1)

    return None


def _extract_ranking_type(message: str) -> str:
    if re.search(r"거래대금", message):
        return "trading-value"
    if re.search(r"거래량", message):
        return "trading-volume"
    if re.search(r"상승|많이\s*오른|많이\s*올랐|급등|올랐", message):
        return "rising"
    if re.search(r"하락|많이\s*내린|많이\s*떨어|급락|떨어졌", message):
        return "falling"
    if re.search(r"시가총액|시총", message):
        return "market-cap"
    return "trading-value"  # 기본값


def _extract_currency_pair(message: str) -> str:
    if re.search(r"유로|EUR", message, re.IGNORECASE):
        return "EURKRW"
    if re.search(r"엔화|엔|JPY|일본", message, re.IGNORECASE):
        return "JPYKRW"
    if re.search(r"파운드|GBP|영국", message, re.IGNORECASE):
        return "GBPKRW"
    return "USDKRW"  # 기본값: 달러/원


def _extract_balance_type(message: str) -> str:
    if re.search(r"총\s*자산", message):
        return "total_assets"
    if re.search(r"보유\s*달러|달러\s*(잔고|예수금|잔액)|USD\s*(잔고|예수금|잔액)", message):
        return "usd"
    if re.search(r"보유\s*원화|원화\s*(잔고|예수금|잔액)|KRW\s*(잔고|예수금|잔액)", message):
        return "krw"
    if re.search(r"현금|예수금|가용|투자\s*가능", message):
        return "cash"
    return "summary"  # "잔고" 단독 → 총 자산 + 현금 함께


def _extract_params(intent: str, message: str) -> dict:
    if intent == "chart_price":
        all_stocks = resolve_all_from_csv(_normalize_message(message))
        if len(all_stocks) > 1:
            return {"multi_stock": True}
        return {"stock_code": _extract_stock(message)}

    if intent == "stock_news":
        all_stocks = resolve_all_from_csv(_normalize_message(message))
        if len(all_stocks) > 1:
            return {"multi_stock": True}
        return {"stock_code": _extract_stock(message)}

    if intent in ("buy_intent", "sell_intent"):
        all_stocks = resolve_all_from_csv(_normalize_message(message))
        if len(all_stocks) > 1:
            return {"multi_stock": True}
        normalized = _normalize_message(message)
        code, name = resolve_from_csv(normalized)
        if not code:
            code = _extract_stock(message)
        return {"stock_code": code, "stock_name": name}

    if intent == "balance":
        return {"balance_type": _extract_balance_type(message)}

    if intent == "ranking":
        return {
            "ranking_type": _extract_ranking_type(message),
        }

    if intent == "exchange_rate":
        return {"currency_pair": _extract_currency_pair(message)}

    if intent == "trades":
        stock_code = _extract_stock(message)
        return {"stock_code": stock_code} if stock_code else {}

    return {}
