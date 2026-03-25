"""
get_market_data 도구 선택 정확도 테스트
(주식순위 / 지수조회 / 주가차트 / 환율조회 유즈케이스)

사전 조건:
    - Ollama 실행 중
    - Spring API 실행 중 (모든 케이스에 필요)

참고:
    - chart 타입(분봉)은 현재 주석 처리됨 → 해당 케이스 제외
    - period_chart 타입은 정상 지원

실행:
    python test_market_data.py
"""
from test_base import run_group, print_summary

TEST_CASES = [
    # ── ranking: 거래량 ────────────────────────────────────────────────────────
    # {
    #     "group":         "get_market_data / ranking",
    #     "message":       "거래량 순위 알려줘",
    #     "expected_tool": "get_market_data",
    #     "expected_type": "ranking",
    #     "expected_args": {"ranking_type": "trading-volume"},
    #     "desc":          "랭킹 - 거래량 (국내 기본)",
    # },
    # {
    #     "group":         "get_market_data / ranking",
    #     "message":       "시가총액 순위 알려줘",
    #     "expected_tool": "get_market_data",
    #     "expected_type": "ranking",
    #     "expected_args": {"ranking_type": "market-cap"},
    #     "desc":          "랭킹 - 시가총액 (국내 기본)",
    # },
    # {
    #     "group":         "get_market_data / ranking",
    #     "message":       "오늘 거래 많은 주식",
    #     "expected_tool": "get_market_data",
    #     "expected_type": "ranking",
    #     "expected_args": {"ranking_type": "trading-volume"},
    #     "desc":          "랭킹 - 거래량 많은 종목",
    # },
    # {
    #     "group":         "get_market_data / ranking",
    #     "message":       "해외 거래량 순위",
    #     "expected_tool": "get_market_data",
    #     "expected_type": "ranking",
    #     "expected_args": {"ranking_type": "trading-volume"},
    #     "desc":          "랭킹 - 해외 거래량",
    # },
    # ── ranking: 상승률 ────────────────────────────────────────────────────────
    # {
    #     "group":         "get_market_data / ranking",
    #     "message":       "오늘 많이 오른 주식",
    #     "expected_tool": "get_market_data",
    #     "expected_type": "ranking",
    #     "expected_args": {"ranking_type": "rising"},
    #     "desc":          "랭킹 - 상승률 상위",
    # },
    # {
    #     "group":         "get_market_data / ranking",
    #     "message":       "급등주 알려줘",
    #     "expected_tool": "get_market_data",
    #     "expected_type": "ranking",
    #     "expected_args": {"ranking_type": "rising"},
    #     "desc":          "랭킹 - 급등주",
    # },
    # {
    #     "group":         "get_market_data / ranking",
    #     "message":       "나스닥 급등주",
    #     "expected_tool": "get_market_data",
    #     "expected_type": "ranking",
    #     "expected_args": {"ranking_type": "rising"},
    #     "desc":          "랭킹 - 나스닥 급등주 (해외)",
    # },
    # # ── ranking: 하락률 ────────────────────────────────────────────────────────
    # {
    #     "group":         "get_market_data / ranking",
    #     "message":       "오늘 많이 내린 주식",
    #     "expected_tool": "get_market_data",
    #     "expected_type": "ranking",
    #     "expected_args": {"ranking_type": "falling"},
    #     "desc":          "랭킹 - 하락률 상위",
    # },
    # {
    #     "group":         "get_market_data / ranking",
    #     "message":       "급락주 보여줘",
    #     "expected_tool": "get_market_data",
    #     "expected_type": "ranking",
    #     "expected_args": {"ranking_type": "falling"},
    #     "desc":          "랭킹 - 급락주",
    # },
    # ── ranking: 시가총액 ──────────────────────────────────────────────────────
    # {
    #     "group":         "get_market_data / ranking",
    #     "message":       "시가총액 순위",
    #     "expected_tool": "get_market_data",
    #     "expected_type": "ranking",
    #     "expected_args": {"ranking_type": "market-cap"},
    #     "desc":          "랭킹 - 시가총액",
    # },
    # {
    #     "group":         "get_market_data / ranking",
    #     "message":       "거래대금 많은 주식",
    #     "expected_tool": "get_market_data",
    #     "expected_type": "ranking",
    #     "expected_args": {"ranking_type": "trading-value"},
    #     "desc":          "랭킹 - 거래대금",
    # },
    # ── index: 국내 ────────────────────────────────────────────────────────────
    {
        "group":         "get_market_data / index",
        "message":       "코스피 지금 얼마야",
        "expected_tool": "get_market_data",
        "expected_type": "index",
        "expected_args": None,
        "desc":          "지수 - 코스피",
    },
    {
        "group":         "get_market_data / index",
        "message":       "코스닥 지수 알려줘",
        "expected_tool": "get_market_data",
        "expected_type": "index",
        "expected_args": None,
        "desc":          "지수 - 코스닥",
    },
    {
        "group":         "get_market_data / index",
        "message":       "코스피 코스닥 둘 다 알려줘",
        "expected_tool": "get_market_data",
        "expected_type": "index",
        "expected_args": None,
        "desc":          "지수 - 코스피 + 코스닥",
    },
    # # ── index: 해외 ────────────────────────────────────────────────────────────
    {
        "group":         "get_market_data / index",
        "message":       "나스닥 지금 얼마야",
        "expected_tool": "get_market_data",
        "expected_type": "index",
        "expected_args": None,
        "desc":          "지수 - 나스닥 (수치 조회)",
    },
    {
        "group":         "get_market_data / index",
        "message":       "다우존스 지수",
        "expected_tool": "get_market_data",
        "expected_type": "index",
        "expected_args": None,
        "desc":          "지수 - 다우존스",
    },
    {
        "group":         "get_market_data / index",
        "message":       "닛케이 지수",
        "expected_tool": "get_market_data",
        "expected_type": "index",
        "expected_args": None,
        "desc":          "지수 - 닛케이",
    },
    # # ── price: 국내 ────────────────────────────────────────────────────────────
    # {
    #     "group":         "get_market_data / price",
    #     "message":       "삼성전자 주가 얼마야?",
    #     "expected_tool": "get_market_data",
    #     "expected_type": "price",
    #     "expected_args": None,
    #     "desc":          "현재가 - 삼성전자 (국내)",
    # },
    # {
    #     "group":         "get_market_data / price",
    #     "message":       "SK하이닉스 주가 알려줘",
    #     "expected_tool": "get_market_data",
    #     "expected_type": "price",
    #     "expected_args": None,
    #     "desc":          "현재가 - SK하이닉스",
    # },
    # {
    #     "group":         "get_market_data / price",
    #     "message":       "카카오 지금 주가",
    #     "expected_tool": "get_market_data",
    #     "expected_type": "price",
    #     "expected_args": None,
    #     "desc":          "현재가 - 카카오",
    # },
    # # ── price: 해외 ────────────────────────────────────────────────────────────
    # {
    #     "group":         "get_market_data / price",
    #     "message":       "엔비디아 주가 얼마야?",
    #     "expected_tool": "get_market_data",
    #     "expected_type": "price",
    #     "expected_args": None,
    #     "desc":          "현재가 - 엔비디아 (해외)",
    # },
    # {
    #     "group":         "get_market_data / price",
    #     "message":       "애플 지금 얼마야",
    #     "expected_tool": "get_market_data",
    #     "expected_type": "price",
    #     "expected_args": None,
    #     "desc":          "현재가 - 애플",
    # },
    # {
    #     "group":         "get_market_data / price",
    #     "message":       "테슬라 주가 알려줘",
    #     "expected_tool": "get_market_data",
    #     "expected_type": "price",
    #     "expected_args": None,
    #     "desc":          "현재가 - 테슬라",
    # },
    # # ── daily ──────────────────────────────────────────────────────────────────
    # {
    #     "group":         "get_market_data / daily",
    #     "message":       "삼성전자 오늘 고가 저가 알려줘",
    #     "expected_tool": "get_market_data",
    #     "expected_type": "daily",
    #     "expected_args": None,
    #     "desc":          "일별 시세 - 고가/저가",
    # },
    # {
    #     "group":         "get_market_data / daily",
    #     "message":       "카카오 오늘 시가 얼마야?",
    #     "expected_tool": "get_market_data",
    #     "expected_type": "daily",
    #     "expected_args": None,
    #     "desc":          "일별 시세 - 시가",
    # },
    # {
    #     "group":         "get_market_data / daily",
    #     "message":       "SK하이닉스 오늘 종가",
    #     "expected_tool": "get_market_data",
    #     "expected_type": "daily",
    #     "expected_args": None,
    #     "desc":          "일별 시세 - 종가",
    # },
    # # ── period_chart ───────────────────────────────────────────────────────────
    # # ※ chart 타입(분봉)은 주석 처리됨 — period_chart(일봉/기간) 만 테스트
    # {
    #     "group":         "get_market_data / period_chart",
    #     "message":       "삼성전자 일봉 차트",
    #     "expected_tool": "get_market_data",
    #     "expected_type": "period_chart",
    #     "expected_args": None,
    #     "desc":          "기간 차트 - 삼성전자 일봉",
    # },
    # {
    #     "group":         "get_market_data / period_chart",
    #     "message":       "삼성전자 최근 한 달 주가 흐름",
    #     "expected_tool": "get_market_data",
    #     "expected_type": "period_chart",
    #     "expected_args": None,
    #     "desc":          "기간 차트 - 한 달 흐름",
    # },
    # {
    #     "group":         "get_market_data / period_chart",
    #     "message":       "SK하이닉스 지난 3개월 차트",
    #     "expected_tool": "get_market_data",
    #     "expected_type": "period_chart",
    #     "expected_args": None,
    #     "desc":          "기간 차트 - 3개월",
    # },
    # {
    #     "group":         "get_market_data / period_chart",
    #     "message":       "엔비디아 차트 보여줘",
    #     "expected_tool": "get_market_data",
    #     "expected_type": "period_chart",
    #     "expected_args": None,
    #     "desc":          "기간 차트 - 엔비디아",
    # },
    # # ── exchange ───────────────────────────────────────────────────────────────
    # {
    #     "group":         "get_market_data / exchange",
    #     "message":       "달러 환율 얼마야",
    #     "expected_tool": "get_market_data",
    #     "expected_type": "exchange",
    #     "expected_args": None,
    #     "desc":          "환율 - USD/KRW 기본",
    # },
    # {
    #     "group":         "get_market_data / exchange",
    #     "message":       "원달러 환율",
    #     "expected_tool": "get_market_data",
    #     "expected_type": "exchange",
    #     "expected_args": None,
    #     "desc":          "환율 - 원달러",
    # },
    # {
    #     "group":         "get_market_data / exchange",
    #     "message":       "유로 환율",
    #     "expected_tool": "get_market_data",
    #     "expected_type": "exchange",
    #     "expected_args": None,
    #     "desc":          "환율 - 유로",
    # },
    # {
    #     "group":         "get_market_data / exchange",
    #     "message":       "엔화 환율 알려줘",
    #     "expected_tool": "get_market_data",
    #     "expected_type": "exchange",
    #     "expected_args": None,
    #     "desc":          "환율 - 엔화",
    # },
    # {
    #     "group":         "get_market_data / exchange",
    #     "message":       "100달러 원화로 얼마야",
    #     "expected_tool": "get_market_data",
    #     "expected_type": "exchange",
    #     "expected_args": None,
    #     "desc":          "환율 - 단순 환산 조회 (실행 아님)",
    # },
    # {
    #     "group":         "get_market_data / exchange",
    #     "message":       "달러 환전하면 얼마야",
    #     "expected_tool": "get_market_data",
    #     "expected_type": "exchange",
    #     "expected_args": None,
    #     "desc":          "환율 - 환전 금액 문의 (실행 아님)",
    # },
]


if __name__ == "__main__":
    results = run_group(TEST_CASES)
    print_summary(results)
