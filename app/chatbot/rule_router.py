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
from app.chatbot.stock_resolver import resolve_from_csv

# ── 의도별 키워드 패턴 ──────────────────────────────────────────────────────────
_PATTERNS: dict[str, list[str]] = {
    # (6) 매수 — 반드시 ranking/index 등보다 먼저 검사
    "buy_intent": [
        r"매수",
        r"사고\s*싶",
        r"살게",
        r"구매하고\s*싶",
        r"주식\s*사",
        r"살래",
        r"사줘",
        r"구매",
    ],
    # (6) 매도
    "sell_intent": [
        r"매도",
        r"팔고\s*싶",
        r"팔게",
        r"판매하고\s*싶",
        r"주식\s*팔",
        r"팔래",
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
        r"원화로\s*바꿔",
        r"달러\s*환전",
        r"원화\s*환전",
        r"환전"
    ],
    # (5) 잔고 조회
    "balance": [
        r"잔고",
        r"예수금",
        r"보유\s*현금",
        r"현금\s*잔액",
        r"내\s*계좌",
        r"계좌\s*잔액",
    ],
    # (10) 종목별 뉴스 — chart_price 보다 먼저 검사
    "stock_news": [
        r"뉴스",
        r"기사",
        r"소식",
        r"뉴스\s*요약",
    ],
    # (4) 차트+시세
    "chart_price": [
        r"차트",
        r"시세",
        r"주가",
        r"현재가",
        r"얼마",
    ],
    # (3) 주식 순위
    "ranking": [
        r"순위",
        r"랭킹",
        r"상위\s*종목",
        r"상승주",
        r"하락주",
        r"거래량\s*순",
        r"거래대금\s*순",
        r"시가총액\s*순",
    ],
    # (8+9) 한국+미국 시황 동시 조회 — korea_summary/us_summary 보다 먼저 검사
    "market_summary": [
        r"시황",
        r"시장",
        r"시황\s*요약",
        r"전체\s*시황",
        r"전체\s*시장",
        r"오늘\s*시장",
        r"오늘\s*시황",
        r"시장\s*요약",
    ],
    # (8) 한국 시황 — index 보다 먼저 검사
    "korea_summary": [
        r"한국\s*시장",
        r"한국\s*시황",
        r"국내\s*시황",
        r"국내\s*시장",
        r"한국장",
        r"국장",
        r"코스피\s*시황",
        r"코스닥\s*시황",
        r"코스피\s*시장",
        r"코스닥\s*시장",
        
    ],
    # (9) 미국 시황
    "us_summary": [
        r"미국\s*시황",
        r"미국\s*시장",
        r"미국장",
        r"미장",
        r"나스닥\s*시황",
        r"해외\s*시황",
        r"해외\s*시장",
        r"월가",
    ],
    # (1) 지수 조회
    "index": [
        r"지수",
        r"코스피",
        r"코스닥",
        r"나스닥",
        r"s&p",
        r"에스앤피",
        r"다우",
        r"닛케이",
        r"항셍",
        r"미장지수",
        r"미장\s*지수",
        r"국장지수",
        r"국장\s*지수",
    ],
    # (2) 환율 조회
    "exchange_rate": [
        r"환율",
        r"달러\s*환율",
        r"원달러",
        r"달러\s*얼마",
        r"유로\s*환율",
        r"엔화\s*환율",
        r"엔\s*환율",
    ],
}

# 의도 검사 우선순위 (앞에 있을수록 먼저 검사)
_PRIORITY = [
    "buy_intent",
    "sell_intent",
    "exchange_order",
    "balance",
    "stock_news",
    "chart_price",
    "ranking",
    "index",
    "market_summary",
    "korea_summary",
    "us_summary",
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

    for intent in _PRIORITY:
        for pattern in _PATTERNS[intent]:
            if re.search(pattern, msg, re.IGNORECASE):
                params = _extract_params(intent, msg)
                return intent, params

    return "unknown", {}


# ── 파라미터 추출 헬퍼 ─────────────────────────────────────────────────────────

def _extract_stock(message: str) -> tuple[str | None, str | None]:
    """
    메시지에서 (종목코드, 종목명)을 추출합니다.

    우선순위:
      1. 6자리 숫자          → 국내 종목코드 (예: 005930), 종목명 None
      2. 2~5자리 영문 대문자 → 미국 티커     (예: AAPL),   종목명 = 티커
      3. CSV 종목명 매칭     → kospi200_targets.csv / NASDAQ100.csv에서 한글 종목명 검색
    """
    # 1. 국내 종목코드: 6자리 숫자
    m = re.search(r'\b(\d{6})\b', message)
    if m:
        return m.group(1), None

    # 2. 미국 티커: 2~5자리 영문 대문자
    m = re.search(r'\b([A-Z]{2,5})\b', message)
    if m:
        ticker = m.group(1)
        return ticker, ticker

    # 3. CSV에서 한글 종목명 → 종목코드 변환 (긴 이름 우선 매칭)
    code, name = resolve_from_csv(message)
    if code:
        return code, name

    return None, None


def _extract_ranking_type(message: str) -> str:
    if re.search(r"거래대금", message):
        return "trading-value"
    if re.search(r"거래량", message):
        return "trading-volume"
    if re.search(r"상승", message):
        return "rising"
    if re.search(r"하락", message):
        return "falling"
    if re.search(r"시가총액", message):
        return "market-cap"
    return "trading-volume"  # 기본값


def _extract_market(message: str) -> str:
    if re.search(r"해외|미국|나스닥|뉴욕|NYSE|NASDAQ", message, re.IGNORECASE):
        return "overseas"
    return "domestic"


def _extract_currency_pair(message: str) -> str:
    if re.search(r"유로|EUR", message, re.IGNORECASE):
        return "EURKRW"
    if re.search(r"엔화|엔|JPY|일본", message, re.IGNORECASE):
        return "JPYKRW"
    if re.search(r"파운드|GBP|영국", message, re.IGNORECASE):
        return "GBPKRW"
    return "USDKRW"  # 기본값: 달러/원


def _extract_params(intent: str, message: str) -> dict:
    if intent in ("chart_price", "stock_news", "buy_intent", "sell_intent"):
        code, name = _extract_stock(message)
        return {"stock_code": code, "stock_name": name}

    if intent == "ranking":
        return {
            "ranking_type": _extract_ranking_type(message),
            "market": _extract_market(message),
        }

    if intent == "exchange_rate":
        return {"currency_pair": _extract_currency_pair(message)}

    return {}
