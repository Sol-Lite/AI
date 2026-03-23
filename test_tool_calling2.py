"""
챗봇 Tool Calling 정확도 테스트 — usecase 기반
chatbot_usecase.xlsx 의 8개 시트를 전부 커버합니다.

사전 조건:
    - Ollama 실행 중 (llama3.1:8b 이상)
    - Oracle DB 더미 데이터 삽입 완료
    - Spring API(get_market_data) 실행 중

실행:
    python test_tool_calling_usecase.py                      # 전체
    python test_tool_calling_usecase.py 주식순위             # 특정 시트만
    python test_tool_calling_usecase.py --retry 2            # 실패 시 재시도
    python test_tool_calling_usecase.py --report             # JSON 리포트 저장
    python test_tool_calling_usecase.py --only-fail          # FAIL/ERROR 케이스만 출력
"""
import sys
import json
import time
import argparse
from datetime import datetime
from unittest.mock import patch
import app.services.llm as llm_module

USER_CONTEXT = {"user_id": "user-001", "account_id": "acc-001"}

# ── 실패 원인 분류 ─────────────────────────────────────────────────────────────
FAIL_REASON = {
    "WRONG_TOOL":      "잘못된 tool 선택",
    "WRONG_TYPE":      "tool 맞으나 type 불일치",
    "WRONG_ARGS":      "tool/type 맞으나 args 불일치",
    "TOOL_CALLED":     "미호출 기대인데 호출됨 (오발주 위험)",
    "TOOL_NOT_CALLED": "호출 기대인데 미호출 (기능 누락)",
    "MULTI_TOOL":      "tool 2회 이상 호출",
    "ERROR":           "예외 발생",
    "NONE":            "",
}

# ── 테스트 케이스 ─────────────────────────────────────────────────────────────
# severity: "critical" = 오발주 등 실제 피해 가능, "normal" = 일반 정확도
# expected_tool=None → tool 미호출 기대 (되묻기)
# expected_args=None → type까지만 검증

TEST_CASES = [

    # ════════════════════════════════════════════════════════
    # 시트 1: 주식순위 — get_market_data / type=ranking
    # ════════════════════════════════════════════════════════

    # ── 거래량 순위 ───────────────────────────────────────────
    {"sheet": "주식순위", "no": 1,  "message": "거래량 순위 알려줘",
     "expected_tool": "get_market_data", "expected_type": "ranking",
     "expected_args": {"ranking_type": "volume"},
     "desc": "거래량 순위 - 기본", "severity": "normal"},

    {"sheet": "주식순위", "no": 2,  "message": "오늘 거래 많은 주식",
     "expected_tool": "get_market_data", "expected_type": "ranking",
     "expected_args": {"ranking_type": "volume"},
     "desc": "거래량 순위 - 표현 변형", "severity": "normal"},

    {"sheet": "주식순위", "no": 6,  "message": "해외 거래량 순위",
     "expected_tool": "get_market_data", "expected_type": "ranking",
     "expected_args": {"ranking_type": "volume"},
     "desc": "거래량 순위 - 해외", "severity": "normal"},

    # ── 상승률 순위 ───────────────────────────────────────────
    {"sheet": "주식순위", "no": 11, "message": "오늘 많이 오른 주식",
     "expected_tool": "get_market_data", "expected_type": "ranking",
     "expected_args": {"ranking_type": "change_rate_asc"},
     "desc": "상승률 순위 - 국내", "severity": "normal"},

    {"sheet": "주식순위", "no": 12, "message": "급등주 알려줘",
     "expected_tool": "get_market_data", "expected_type": "ranking",
     "expected_args": {"ranking_type": "change_rate_asc"},
     "desc": "상승률 순위 - 급등주", "severity": "normal"},

    {"sheet": "주식순위", "no": 16, "message": "해외 많이 오른 종목",
     "expected_tool": "get_market_data", "expected_type": "ranking",
     "expected_args": {"ranking_type": "change_rate_asc"},
     "desc": "상승률 순위 - 해외", "severity": "normal"},

    # ── 하락률 순위 ───────────────────────────────────────────
    {"sheet": "주식순위", "no": 18, "message": "오늘 많이 내린 주식",
     "expected_tool": "get_market_data", "expected_type": "ranking",
     "expected_args": {"ranking_type": "change_rate_desc"},
     "desc": "하락률 순위 - 국내", "severity": "normal"},

    {"sheet": "주식순위", "no": 19, "message": "급락주 보여줘",
     "expected_tool": "get_market_data", "expected_type": "ranking",
     "expected_args": {"ranking_type": "change_rate_desc"},
     "desc": "하락률 순위 - 급락", "severity": "normal"},

    # ── 외국인/기관 ───────────────────────────────────────────
    {"sheet": "주식순위", "no": 23, "message": "외국인이 많이 사는 주식",
     "expected_tool": "get_market_data", "expected_type": "ranking",
     "expected_args": {"ranking_type": "foreign_buy"},
     "desc": "외국인 순매수", "severity": "normal"},

    {"sheet": "주식순위", "no": 25, "message": "외국인이 많이 파는 종목",
     "expected_tool": "get_market_data", "expected_type": "ranking",
     "expected_args": {"ranking_type": "foreign_sell"},
     "desc": "외국인 순매도", "severity": "normal"},

    {"sheet": "주식순위", "no": 27, "message": "기관 순매수 순위",
     "expected_tool": "get_market_data", "expected_type": "ranking",
     "expected_args": {"ranking_type": "institution_buy"},
     "desc": "기관 순매수", "severity": "normal"},

    # ── 시가총액/거래대금 ─────────────────────────────────────
    {"sheet": "주식순위", "no": 31, "message": "시가총액 순위",
     "expected_tool": "get_market_data", "expected_type": "ranking",
     "expected_args": {"ranking_type": "market_cap"},
     "desc": "시가총액 순위", "severity": "normal"},

    {"sheet": "주식순위", "no": 34, "message": "거래대금 많은 주식",
     "expected_tool": "get_market_data", "expected_type": "ranking",
     "expected_args": {"ranking_type": "trade_value"},
     "desc": "거래대금 순위", "severity": "normal"},

    # ── 에러/예외 ─────────────────────────────────────────────
    {"sheet": "주식순위", "no": 39, "message": "주식 순위",
     "expected_tool": None, "expected_type": None, "expected_args": None,
     "desc": "랭킹 타입 불명확 → 되묻기", "severity": "normal"},

    # ════════════════════════════════════════════════════════
    # 시트 2: 지수조회 — get_market_data / type=index
    # ════════════════════════════════════════════════════════

    # ── 국내 지수 ─────────────────────────────────────────────
    {"sheet": "지수조회", "no": 1, "message": "코스피 지금 얼마야",
     "expected_tool": "get_market_data", "expected_type": "index",
     "expected_args": {"index_code": "KOSPI"},
     "desc": "코스피 지수", "severity": "normal"},

    {"sheet": "지수조회", "no": 4, "message": "코스닥 지수 알려줘",
     "expected_tool": "get_market_data", "expected_type": "index",
     "expected_args": {"index_code": "KOSDAQ"},
     "desc": "코스닥 지수", "severity": "normal"},

    # ── 미국 지수 ─────────────────────────────────────────────
    {"sheet": "지수조회", "no": 10, "message": "나스닥 지금 얼마야",
     "expected_tool": "get_market_data", "expected_type": "index",
     "expected_args": {"index_code": "NASDAQ"},
     "desc": "나스닥 지수", "severity": "normal"},

    {"sheet": "지수조회", "no": 12, "message": "S&P500 확인",
     "expected_tool": "get_market_data", "expected_type": "index",
     "expected_args": {"index_code": "SP500"},
     "desc": "S&P500 지수", "severity": "normal"},

    {"sheet": "지수조회", "no": 14, "message": "다우존스 지수",
     "expected_tool": "get_market_data", "expected_type": "index",
     "expected_args": {"index_code": "DOW"},
     "desc": "다우존스 지수", "severity": "normal"},

    {"sheet": "지수조회", "no": 13, "message": "에스앤피 얼마야",
     "expected_tool": "get_market_data", "expected_type": "index",
     "expected_args": {"index_code": "SP500"},
     "desc": "S&P500 - 한글 표기", "severity": "normal"},

    # ── 아시아/유럽 지수 ──────────────────────────────────────
    {"sheet": "지수조회", "no": 20, "message": "닛케이 지수",
     "expected_tool": "get_market_data", "expected_type": "index",
     "expected_args": {"index_code": "NIKKEI"},
     "desc": "닛케이 지수", "severity": "normal"},

    {"sheet": "지수조회", "no": 22, "message": "상해 증시",
     "expected_tool": "get_market_data", "expected_type": "index",
     "expected_args": {"index_code": "SSE"},
     "desc": "상해종합 지수", "severity": "normal"},

    # ── 에러/예외 ─────────────────────────────────────────────
    {"sheet": "지수조회", "no": 32, "message": "지수 알려줘",
     "expected_tool": None, "expected_type": None, "expected_args": None,
     "desc": "index_code 불명확 → 되묻기", "severity": "normal"},

    # ════════════════════════════════════════════════════════
    # 시트 3: 뉴스조회 — get_market_summary
    # ════════════════════════════════════════════════════════

    # ── 국내 시황 ─────────────────────────────────────────────
    {"sheet": "뉴스조회", "no": 1, "message": "오늘 한국 증시 어때?",
     "expected_tool": "get_market_summary", "expected_type": "korea",
     "expected_args": None,
     "desc": "국내 시황 조회", "severity": "normal"},

    {"sheet": "뉴스조회", "no": 3, "message": "국내 증시 지금 어떻게 돼?",
     "expected_tool": "get_market_summary", "expected_type": "korea",
     "expected_args": None,
     "desc": "국내 시황 - 표현 변형", "severity": "normal"},

    # ── 미국 시황 ─────────────────────────────────────────────
    {"sheet": "뉴스조회", "no": 11, "message": "미국 증시 어때?",
     "expected_tool": "get_market_summary", "expected_type": "us",
     "expected_args": None,
     "desc": "미국 시황 조회", "severity": "normal"},

    {"sheet": "뉴스조회", "no": 13, "message": "뉴욕 증시 현황 알려줘",
     "expected_tool": "get_market_summary", "expected_type": "us",
     "expected_args": None,
     "desc": "미국 시황 - 뉴욕 표현", "severity": "normal"},

    {"sheet": "뉴스조회", "no": 12, "message": "월스트리트 오늘 분위기?",
     "expected_tool": "get_market_summary", "expected_type": "us",
     "expected_args": None,
     "desc": "미국 시황 - 월스트리트 표현", "severity": "normal"},

    # ── 종목 뉴스 ─────────────────────────────────────────────
    {"sheet": "뉴스조회", "no": 22, "message": "삼성전자 오늘 뉴스 있어?",
     "expected_tool": "get_market_summary", "expected_type": "stock_news",
     "expected_args": {"stock_code": "005930"},
     "desc": "종목 뉴스 - 삼성전자", "severity": "normal"},

    {"sheet": "뉴스조회", "no": 23, "message": "SK하이닉스 최근 소식 알려줘",
     "expected_tool": "get_market_summary", "expected_type": "stock_news",
     "expected_args": {"stock_code": "000660"},
     "desc": "종목 뉴스 - SK하이닉스", "severity": "normal"},

    {"sheet": "뉴스조회", "no": 25, "message": "엔비디아 오늘 뉴스 뭐야?",
     "expected_tool": "get_market_summary", "expected_type": "stock_news",
     "expected_args": {"stock_code": "NVDA"},
     "desc": "종목 뉴스 - NVDA 해외", "severity": "normal"},

    # ── 에러/예외 ─────────────────────────────────────────────
    {"sheet": "뉴스조회", "no": 35, "message": "뉴스 알려줘",
     "expected_tool": None, "expected_type": None, "expected_args": None,
     "desc": "종목 불명확 → 되묻기", "severity": "normal"},

    # ════════════════════════════════════════════════════════
    # 시트 4: 주가차트 — get_market_data / type=price|chart|daily|period_chart
    # ════════════════════════════════════════════════════════

    # ── 현재가 (국내) ─────────────────────────────────────────
    {"sheet": "주가차트", "no": 1, "message": "삼성전자 주가 얼마야?",
     "expected_tool": "get_market_data", "expected_type": "price",
     "expected_args": {"stock_code": "005930"},
     "desc": "현재가 - 삼성전자", "severity": "normal"},

    {"sheet": "주가차트", "no": 3, "message": "SK하이닉스 주가 알려줘",
     "expected_tool": "get_market_data", "expected_type": "price",
     "expected_args": {"stock_code": "000660"},
     "desc": "현재가 - SK하이닉스", "severity": "normal"},

    {"sheet": "주가차트", "no": 4, "message": "카카오 지금 주가",
     "expected_tool": "get_market_data", "expected_type": "price",
     "expected_args": {"stock_code": "035720"},
     "desc": "현재가 - 카카오", "severity": "normal"},

    # ── 현재가 (해외) ─────────────────────────────────────────
    {"sheet": "주가차트", "no": 7, "message": "엔비디아 주가 얼마야?",
     "expected_tool": "get_market_data", "expected_type": "price",
     "expected_args": {"stock_code": "NVDA"},
     "desc": "현재가 - NVDA 해외", "severity": "normal"},

    {"sheet": "주가차트", "no": 8, "message": "애플 지금 얼마야",
     "expected_tool": "get_market_data", "expected_type": "price",
     "expected_args": {"stock_code": "AAPL"},
     "desc": "현재가 - AAPL 해외", "severity": "normal"},

    {"sheet": "주가차트", "no": 9, "message": "테슬라 주가 알려줘",
     "expected_tool": "get_market_data", "expected_type": "price",
     "expected_args": {"stock_code": "TSLA"},
     "desc": "현재가 - TSLA 해외", "severity": "normal"},

    # ── 당일시세 ─────────────────────────────────────────────
    {"sheet": "주가차트", "no": 11, "message": "삼성전자 오늘 고가 저가 알려줘",
     "expected_tool": "get_market_data", "expected_type": "daily",
     "expected_args": {"stock_code": "005930"},
     "desc": "당일시세 - 고가/저가", "severity": "normal"},

    {"sheet": "주가차트", "no": 12, "message": "카카오 오늘 시가 얼마야?",
     "expected_tool": "get_market_data", "expected_type": "daily",
     "expected_args": {"stock_code": "035720"},
     "desc": "당일시세 - 시가", "severity": "normal"},

    # ── 분봉차트 ─────────────────────────────────────────────
    {"sheet": "주가차트", "no": 15, "message": "삼성전자 분봉 차트 보여줘",
     "expected_tool": "get_market_data", "expected_type": "chart",
     "expected_args": {"stock_code": "005930"},
     "desc": "분봉차트 - 삼성전자", "severity": "normal"},

    {"sheet": "주가차트", "no": 18, "message": "엔비디아 차트 보여줘",
     "expected_tool": "get_market_data", "expected_type": "chart",
     "expected_args": {"stock_code": "NVDA"},
     "desc": "분봉차트 - 해외", "severity": "normal"},

    # ── 기간별 차트 ───────────────────────────────────────────
    {"sheet": "주가차트", "no": 19, "message": "삼성전자 일봉 차트",
     "expected_tool": "get_market_data", "expected_type": "period_chart",
     "expected_args": {"stock_code": "005930"},
     "desc": "기간차트 - 일봉", "severity": "normal"},

    {"sheet": "주가차트", "no": 20, "message": "삼성전자 최근 한 달 주가 흐름",
     "expected_tool": "get_market_data", "expected_type": "period_chart",
     "expected_args": {"stock_code": "005930"},
     "desc": "기간차트 - 1개월", "severity": "normal"},

    # ── 에러/예외 ─────────────────────────────────────────────
    {"sheet": "주가차트", "no": 28, "message": "주가 알려줘",
     "expected_tool": None, "expected_type": None, "expected_args": None,
     "desc": "종목 누락 → 되묻기", "severity": "normal"},

    # ════════════════════════════════════════════════════════
    # 시트 5: 잔고조회 — get_db_data / type=balance|balance_detail
    # ════════════════════════════════════════════════════════

    {"sheet": "잔고조회", "no": 1, "message": "내 잔고 얼마야?",
     "expected_tool": "get_db_data", "expected_type": "balance",
     "expected_args": None,
     "desc": "잔고 전체 조회", "severity": "normal"},

    {"sheet": "잔고조회", "no": 2, "message": "지금 내 계좌 잔고 알려줘",
     "expected_tool": "get_db_data", "expected_type": "balance",
     "expected_args": None,
     "desc": "잔고 - 표현 변형", "severity": "normal"},

    {"sheet": "잔고조회", "no": 6, "message": "주문 가능한 돈 얼마야?",
     "expected_tool": "get_db_data", "expected_type": "balance_detail",
     "expected_args": None,
     "desc": "잔고 세부 - 주문가능금액", "severity": "normal"},

    {"sheet": "잔고조회", "no": 7, "message": "출금 가능 금액 알려줘",
     "expected_tool": "get_db_data", "expected_type": "balance_detail",
     "expected_args": None,
     "desc": "잔고 세부 - 출금가능", "severity": "normal"},

    {"sheet": "잔고조회", "no": 8, "message": "총 자산이 얼마야?",
     "expected_tool": "get_db_data", "expected_type": "balance_detail",
     "expected_args": None,
     "desc": "잔고 세부 - 총자산", "severity": "normal"},

    # ════════════════════════════════════════════════════════
    # 시트 6: 환율조회 — get_market_data / type=exchange
    # ════════════════════════════════════════════════════════

    {"sheet": "환율조회", "no": 1, "message": "달러 환율 얼마야",
     "expected_tool": "get_market_data", "expected_type": "exchange",
     "expected_args": {"currency_pair": "USDKRW"},
     "desc": "달러 환율", "severity": "normal"},

    {"sheet": "환율조회", "no": 3, "message": "원달러 환율",
     "expected_tool": "get_market_data", "expected_type": "exchange",
     "expected_args": {"currency_pair": "USDKRW"},
     "desc": "달러 환율 - 원달러 표현", "severity": "normal"},

    {"sheet": "환율조회", "no": 12, "message": "유로 환율",
     "expected_tool": "get_market_data", "expected_type": "exchange",
     "expected_args": {"currency_pair": "EURKRW"},
     "desc": "유로 환율", "severity": "normal"},

    {"sheet": "환율조회", "no": 14, "message": "엔화 환율 알려줘",
     "expected_tool": "get_market_data", "expected_type": "exchange",
     "expected_args": {"currency_pair": "JPYKRW"},
     "desc": "엔화 환율", "severity": "normal"},

    {"sheet": "환율조회", "no": 17, "message": "위안화 환율",
     "expected_tool": "get_market_data", "expected_type": "exchange",
     "expected_args": {"currency_pair": "CNYKRW"},
     "desc": "위안화 환율", "severity": "normal"},

    # 환율 조회 vs 환전 실행 구분
    {"sheet": "환율조회", "no": 27, "message": "달러 환율이 얼마야",
     "expected_tool": "get_market_data", "expected_type": "exchange",
     "expected_args": None,
     "desc": "환율 조회 (execute_order 아님)", "severity": "critical"},

    # ── 에러/예외 ─────────────────────────────────────────────
    {"sheet": "환율조회", "no": 31, "message": "환율 알려줘",
     "expected_tool": None, "expected_type": None, "expected_args": None,
     "desc": "통화 불명확 → 되묻기", "severity": "normal"},

    # ════════════════════════════════════════════════════════
    # 시트 7: 거래내역 — get_db_data / type=trades|trades_detail
    # ════════════════════════════════════════════════════════

    {"sheet": "거래내역", "no": 1, "message": "내 거래내역 보여줘",
     "expected_tool": "get_db_data", "expected_type": "trades",
     "expected_args": None,
     "desc": "거래내역 전체", "severity": "normal"},

    {"sheet": "거래내역", "no": 3, "message": "내가 뭐 샀어?",
     "expected_tool": "get_db_data", "expected_type": "trades",
     "expected_args": None,
     "desc": "거래내역 - 매수 위주", "severity": "normal"},

    {"sheet": "거래내역", "no": 5, "message": "거래 몇 번 했어?",
     "expected_tool": "get_db_data", "expected_type": "trades",
     "expected_args": None,
     "desc": "거래내역 - 총 횟수", "severity": "normal"},

    {"sheet": "거래내역", "no": 6, "message": "최근 거래 5건 보여줘",
     "expected_tool": "get_db_data", "expected_type": "trades_detail",
     "expected_args": None,
     "desc": "거래내역 세부 - N건", "severity": "normal"},

    {"sheet": "거래내역", "no": 7, "message": "삼성전자 거래내역 있어?",
     "expected_tool": "get_db_data", "expected_type": "trades_detail",
     "expected_args": None,
     "desc": "거래내역 세부 - 특정 종목", "severity": "normal"},

    {"sheet": "거래내역", "no": 8, "message": "오늘 거래한 거 있어?",
     "expected_tool": "get_db_data", "expected_type": "trades_detail",
     "expected_args": None,
     "desc": "거래내역 세부 - 당일", "severity": "normal"},

    {"sheet": "거래내역", "no": 10, "message": "내가 제일 많이 산 종목이 뭐야?",
     "expected_tool": "get_db_data", "expected_type": "trades_detail",
     "expected_args": None,
     "desc": "거래내역 세부 - 최다 매수", "severity": "normal"},

    # ════════════════════════════════════════════════════════
    # 시트 8-1: 포트폴리오 — get_db_data / type=portfolio|portfolio_detail
    # ════════════════════════════════════════════════════════

    {"sheet": "포트폴리오", "no": 1, "message": "내 포트폴리오 분석해줘",
     "expected_tool": "get_db_data", "expected_type": "portfolio",
     "expected_args": None,
     "desc": "포트폴리오 전체 조회", "severity": "normal"},

    {"sheet": "포트폴리오", "no": 2, "message": "내 투자 현황 알려줘",
     "expected_tool": "get_db_data", "expected_type": "portfolio",
     "expected_args": None,
     "desc": "포트폴리오 - 표현 변형", "severity": "normal"},

    {"sheet": "포트폴리오", "no": 4, "message": "내 수익률 얼마야?",
     "expected_tool": "get_db_data", "expected_type": "portfolio_detail",
     "expected_args": None,
     "desc": "포트폴리오 세부 - 수익률", "severity": "normal"},

    {"sheet": "포트폴리오", "no": 5, "message": "지금 얼마 벌었어?",
     "expected_tool": "get_db_data", "expected_type": "portfolio_detail",
     "expected_args": None,
     "desc": "포트폴리오 세부 - 평가손익", "severity": "normal"},

    {"sheet": "포트폴리오", "no": 7, "message": "제일 많이 오른 종목이 뭐야?",
     "expected_tool": "get_db_data", "expected_type": "portfolio_detail",
     "expected_args": None,
     "desc": "포트폴리오 세부 - 최고수익종목", "severity": "normal"},

    {"sheet": "포트폴리오", "no": 9, "message": "내 포트폴리오 국내/해외 비율이 어떻게 돼?",
     "expected_tool": "get_db_data", "expected_type": "portfolio_detail",
     "expected_args": None,
     "desc": "포트폴리오 세부 - 국내해외비율", "severity": "normal"},

    {"sheet": "포트폴리오", "no": 13, "message": "내 포트폴리오 위험한가요?",
     "expected_tool": "get_db_data", "expected_type": "portfolio_detail",
     "expected_args": None,
     "desc": "포트폴리오 세부 - 리스크", "severity": "normal"},

    {"sheet": "포트폴리오", "no": 14, "message": "MDD가 얼마야?",
     "expected_tool": "get_db_data", "expected_type": "portfolio_detail",
     "expected_args": None,
     "desc": "포트폴리오 세부 - MDD", "severity": "normal"},

    {"sheet": "포트폴리오", "no": 15, "message": "승률이 어떻게 돼?",
     "expected_tool": "get_db_data", "expected_type": "portfolio_detail",
     "expected_args": None,
     "desc": "포트폴리오 세부 - 승률", "severity": "normal"},

    # ════════════════════════════════════════════════════════
    # 시트 8-2: 매수/매도 — execute_order / type=buy|sell
    # ════════════════════════════════════════════════════════

    # ── 매수 (수량 지정) ──────────────────────────────────────
    {"sheet": "매수매도", "no": 1, "message": "삼성전자 10주 사줘",
     "expected_tool": "execute_order", "expected_type": "buy",
     "expected_args": {"stock_code": "005930", "quantity": 10},
     "desc": "매수 - 수량 지정", "severity": "normal"},

    {"sheet": "매수매도", "no": 4, "message": "삼성전자 10주 75000원에 사줘",
     "expected_tool": "execute_order", "expected_type": "buy",
     "expected_args": {"stock_code": "005930", "quantity": 10, "price": 75000},
     "desc": "매수 - 지정가", "severity": "normal"},

    {"sheet": "매수매도", "no": 6, "message": "SK하이닉스 5주 매수",
     "expected_tool": "execute_order", "expected_type": "buy",
     "expected_args": {"stock_code": "000660", "quantity": 5},
     "desc": "매수 - SK하이닉스", "severity": "normal"},

    # ── 매수 (약칭) ───────────────────────────────────────────
    {"sheet": "매수매도", "no": 13, "message": "삼전 10주 사줘",
     "expected_tool": "execute_order", "expected_type": "buy",
     "expected_args": {"quantity": 10},
     "desc": "매수 - 삼전 약칭", "severity": "normal"},

    {"sheet": "매수매도", "no": 14, "message": "하이닉스 5주 매수",
     "expected_tool": "execute_order", "expected_type": "buy",
     "expected_args": {"quantity": 5},
     "desc": "매수 - 하이닉스 약칭", "severity": "normal"},

    # ── 매수 (해외) ───────────────────────────────────────────
    {"sheet": "매수매도", "no": 18, "message": "애플 3주 사줘",
     "expected_tool": "execute_order", "expected_type": "buy",
     "expected_args": {"stock_code": "AAPL", "quantity": 3},
     "desc": "매수 - 해외 애플", "severity": "normal"},

    {"sheet": "매수매도", "no": 19, "message": "엔비디아 1주 매수",
     "expected_tool": "execute_order", "expected_type": "buy",
     "expected_args": {"stock_code": "NVDA", "quantity": 1},
     "desc": "매수 - 해외 NVDA", "severity": "normal"},

    # ── 매도 ─────────────────────────────────────────────────
    {"sheet": "매수매도", "no": 23, "message": "삼성전자 5주 팔아줘",
     "expected_tool": "execute_order", "expected_type": "sell",
     "expected_args": {"stock_code": "005930", "quantity": 5},
     "desc": "매도 - 수량 지정", "severity": "normal"},

    {"sheet": "매수매도", "no": 25, "message": "삼성전자 5주 75500원에 팔아줘",
     "expected_tool": "execute_order", "expected_type": "sell",
     "expected_args": {"stock_code": "005930", "quantity": 5, "price": 75500},
     "desc": "매도 - 지정가", "severity": "normal"},

    # ── 에러/예외 (CRITICAL: 오발주 방지) ─────────────────────
    {"sheet": "매수매도", "no": 32, "message": "삼성전자 사줘",
     "expected_tool": None, "expected_type": None, "expected_args": None,
     "desc": "매수 - 수량 누락 → 되묻기", "severity": "critical"},

    {"sheet": "매수매도", "no": 33, "message": "사줘",
     "expected_tool": None, "expected_type": None, "expected_args": None,
     "desc": "매수 - 종목+수량 누락 → 되묻기", "severity": "critical"},

    {"sheet": "매수매도", "no": 33, "message": "주식 10주 팔아줘",
     "expected_tool": None, "expected_type": None, "expected_args": None,
     "desc": "매도 - 종목 누락 → 되묻기", "severity": "critical"},

    {"sheet": "매수매도", "no": 33, "message": "다 팔아줘",
     "expected_tool": None, "expected_type": None, "expected_args": None,
     "desc": "매도 - 종목 불명확 → 되묻기", "severity": "critical"},

    {"sheet": "매수매도", "no": 38, "message": "삼성전자 0주 사줘",
     "expected_tool": None, "expected_type": None, "expected_args": None,
     "desc": "매수 - 수량 0 → 되묻기/거부", "severity": "critical"},

    # ════════════════════════════════════════════════════════
    # 시트 8-3: 환전실행 — execute_order / type=exchange
    # ════════════════════════════════════════════════════════

    {"sheet": "환전실행", "no": 1, "message": "달러로 환전해줘 100만원",
     "expected_tool": "execute_order", "expected_type": "exchange",
     "expected_args": None,
     "desc": "환전 실행 - KRW→USD", "severity": "normal"},

    {"sheet": "환전실행", "no": 2, "message": "50만원 달러로 바꿔줘",
     "expected_tool": "execute_order", "expected_type": "exchange",
     "expected_args": None,
     "desc": "환전 실행 - 바꿔줘 표현", "severity": "normal"},

    {"sheet": "환전실행", "no": 8, "message": "달러 500달러 원화로 환전해줘",
     "expected_tool": "execute_order", "expected_type": "exchange",
     "expected_args": None,
     "desc": "환전 실행 - USD→KRW", "severity": "normal"},

    # 환전 vs 환율 조회 구분 (CRITICAL)
    {"sheet": "환전실행", "no": 17, "message": "달러 얼마야",
     "expected_tool": "get_market_data", "expected_type": "exchange",
     "expected_args": None,
     "desc": "환율 조회 (환전 실행 아님)", "severity": "critical"},

    # ── 에러/예외 ─────────────────────────────────────────────
    {"sheet": "환전실행", "no": 20, "message": "달러로 환전해줘",
     "expected_tool": None, "expected_type": None, "expected_args": None,
     "desc": "환전 - 금액 누락 → 되묻기", "severity": "critical"},

    {"sheet": "환전실행", "no": 25, "message": "환전",
     "expected_tool": None, "expected_type": None, "expected_args": None,
     "desc": "환전 - 완전 불명확 → 되묻기", "severity": "normal"},
]


# ── 실패 원인 분류 ─────────────────────────────────────────────────────────────

def classify_fail(case, actual_tool, actual_type, actual_args, captured) -> str:
    if len(captured) > 1:
        return "MULTI_TOOL"
    expected_tool = case["expected_tool"]
    if expected_tool is None:
        return "TOOL_CALLED"
    if actual_tool is None:
        return "TOOL_NOT_CALLED"
    if actual_tool != expected_tool:
        return "WRONG_TOOL"
    if actual_type != case["expected_type"]:
        return "WRONG_TYPE"
    if case.get("expected_args"):
        for k, v in case["expected_args"].items():
            if actual_args.get(k) != v:
                return "WRONG_ARGS"
    return "NONE"


# ── 단일 실행 ─────────────────────────────────────────────────────────────────

def run_single(case: dict) -> dict:
    captured = []
    original_dispatch = llm_module._dispatch

    def spy(fn_name, fn_args, user_context):
        captured.append({"tool": fn_name, "args": fn_args})
        return original_dispatch(fn_name, fn_args, user_context)

    reply = ""
    error = ""
    with patch.object(llm_module, "_dispatch", side_effect=spy):
        try:
            reply = llm_module.chat(case["message"], USER_CONTEXT)
        except Exception as e:
            error = str(e)

    actual_tool = captured[0]["tool"] if captured else None
    actual_args = captured[0]["args"] if captured else {}
    actual_type = actual_args.get("type") if actual_args else None

    if error:
        return {
            "status": "ERROR", "error": error, "fail_reason": "ERROR",
            "actual_tool": actual_tool, "actual_type": actual_type,
            "actual_args": actual_args, "reply": reply, "captured": captured, "attempts": 1,
        }

    expected_tool = case["expected_tool"]
    if expected_tool is None:
        ok = (actual_tool is None)
    else:
        tool_ok = (actual_tool == expected_tool)
        type_ok = (actual_type == case["expected_type"])
        args_ok = True
        if case.get("expected_args"):
            args_ok = all(actual_args.get(k) == v for k, v in case["expected_args"].items())
        ok = tool_ok and type_ok and args_ok

    fail_reason = "NONE" if ok else classify_fail(case, actual_tool, actual_type, actual_args, captured)
    return {
        "status": "PASS" if ok else "FAIL", "error": "", "fail_reason": fail_reason,
        "actual_tool": actual_tool, "actual_type": actual_type,
        "actual_args": actual_args, "reply": reply, "captured": captured, "attempts": 1,
    }


def run_test(case: dict, max_retry: int = 0) -> dict:
    result = run_single(case)
    for attempt in range(1, max_retry + 1):
        if result["status"] == "PASS":
            break
        time.sleep(0.5)
        result = run_single(case)
        result["attempts"] = attempt + 1
    return result


# ── 출력 ──────────────────────────────────────────────────────────────────────

def print_result(case: dict, res: dict, only_fail: bool = False):
    if only_fail and res["status"] == "PASS":
        return

    exp_str = (f"{case['expected_tool']} / type={case['expected_type']}"
               if case["expected_tool"] else "tool 미호출")
    act_str = (f"{res['actual_tool']} / type={res['actual_type']}"
               if res["actual_tool"] else "tool 미호출")

    print(f"\n  [{case['no']:>2}] {case['message']}")
    print(f"       ({case['desc']})")
    print(f"       기대: {exp_str}")
    print(f"       실제: {act_str}")

    if case.get("expected_args") and res["actual_args"]:
        for k, v in case["expected_args"].items():
            actual_v = res["actual_args"].get(k)
            mark = "✓" if actual_v == v else "✗"
            print(f"       args.{k}: 기대={v}, 실제={actual_v} {mark}")

    status = res["status"]
    severity = case.get("severity", "normal")
    attempts = res.get("attempts", 1)

    if status == "PASS":
        label = "[PASS]" + (f" (재시도 {attempts}회)" if attempts > 1 else "")
    elif status == "FAIL":
        reason_str = FAIL_REASON.get(res["fail_reason"], res["fail_reason"])
        crit = " ⚠️  CRITICAL" if severity == "critical" else ""
        label = f"[FAIL] {reason_str}{crit}"
    else:
        label = f"[ERROR] {res.get('error', '')}"

    print(f"       {label}")

    if len(res.get("captured", [])) > 1:
        print(f"       ⚠️  {len(res['captured'])}회 호출: "
              + ", ".join(c["tool"] for c in res["captured"]))

    if res.get("reply"):
        preview = res["reply"][:200]
        print(f"       💬 {preview}" + ("..." if len(res["reply"]) > 200 else ""))


# ── 메인 ──────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("sheet", nargs="?", default=None, help="특정 시트만 실행")
    p.add_argument("--retry", type=int, default=0, metavar="N")
    p.add_argument("--report", action="store_true")
    p.add_argument("--only-fail", action="store_true", help="FAIL/ERROR 케이스만 출력")
    return p.parse_args()


def main():
    args = parse_args()
    target_sheet = args.sheet
    max_retry = args.retry
    only_fail = args.only_fail

    cases = [c for c in TEST_CASES
             if target_sheet is None or c["sheet"] == target_sheet]

    if not cases:
        print(f"시트 '{target_sheet}'를 찾을 수 없습니다.")
        print("사용 가능한 시트:", sorted({c["sheet"] for c in TEST_CASES}))
        return

    if max_retry:
        print(f"  ※ FAIL/ERROR 시 최대 {max_retry}회 재시도\n")

    results = []
    current_sheet = None

    for case in cases:
        if case["sheet"] != current_sheet:
            current_sheet = case["sheet"]
            print(f"\n{'━'*60}")
            print(f"  📋 {current_sheet}")
            print(f"{'━'*60}")

        res = run_test(case, max_retry=max_retry)
        print_result(case, res, only_fail=only_fail)
        results.append({**case, **res})

    # ── 요약 ──────────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  결과 요약")
    print(f"{'='*60}")

    sheets: dict[str, list] = {}
    for r in results:
        sheets.setdefault(r["sheet"], []).append(r)

    total_pass = total_fail = total_error = total_critical_fail = 0

    for sheet, items in sheets.items():
        p  = sum(1 for i in items if i["status"] == "PASS")
        f  = sum(1 for i in items if i["status"] == "FAIL")
        e  = sum(1 for i in items if i["status"] == "ERROR")
        cf = sum(1 for i in items if i["status"] == "FAIL" and i.get("severity") == "critical")
        total_pass += p; total_fail += f; total_error += e; total_critical_fail += cf
        line = f"  {sheet:<12} PASS {p}/{len(items)}"
        if f:  line += f"  FAIL {f}"
        if cf: line += f"  (CRITICAL {cf})"
        if e:  line += f"  ERROR {e}"
        print(line)

    # 실패 원인 집계
    fail_counter: dict[str, int] = {}
    for r in results:
        if r["status"] in ("FAIL", "ERROR"):
            reason = r.get("fail_reason", "ERROR")
            fail_counter[reason] = fail_counter.get(reason, 0) + 1

    print(f"{'─'*60}")
    total = len(results)
    print(f"  전체: PASS {total_pass}/{total}  FAIL {total_fail}  ERROR {total_error}")
    if total_critical_fail:
        print(f"  ⚠️  CRITICAL FAIL: {total_critical_fail}건 (오발주 위험)")

    if fail_counter:
        print(f"\n  실패 원인 분류:")
        for reason, count in sorted(fail_counter.items(), key=lambda x: -x[1]):
            print(f"    {FAIL_REASON.get(reason, reason):<22} {count}건")

    # ── JSON 리포트 ────────────────────────────────────────────────────────────
    if args.report:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"test_report_usecase_{ts}.json"
        report = {
            "timestamp": ts, "total": total,
            "pass": total_pass, "fail": total_fail,
            "error": total_error, "critical_fail": total_critical_fail,
            "fail_reasons": fail_counter,
            "cases": [
                {
                    "sheet": r["sheet"], "no": r["no"], "desc": r["desc"],
                    "message": r["message"], "severity": r.get("severity", "normal"),
                    "status": r["status"], "fail_reason": r.get("fail_reason", ""),
                    "expected_tool": r["expected_tool"], "expected_type": r["expected_type"],
                    "actual_tool": r.get("actual_tool"), "actual_type": r.get("actual_type"),
                    "actual_args": r.get("actual_args", {}),
                    "attempts": r.get("attempts", 1),
                    "reply_preview": r.get("reply", "")[:200],
                }
                for r in results
            ],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n  📄 리포트 저장: {path}")


if __name__ == "__main__":
    main()
