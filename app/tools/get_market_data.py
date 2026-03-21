"""
도구 3: get_market_data - LS증권 API 연동 (실시간 시장 데이터: 시세/차트/랭킹/지수/환율)
"""
from typing import Literal
import requests
from datetime import date as date_type


# 시세 조회, 차트, 랭킹, 지수, 환율 등 시장 데이터 조회를 위한 도구 함수
def get_market_data(type: str, **kwargs):
    if type == "price":
        return _fetch_price(kwargs.get("stock_code"), kwargs.get("market"))

    elif type == "chart":
        return _fetch_chart(kwargs.get("stock_code"), kwargs.get("market"))

    elif type == "daily":
        return _fetch_daily(kwargs.get("stock_code"), kwargs.get("date"))

    elif type == "period_chart":
        return _fetch_period_chart(
            kwargs.get("stock_code"),
            kwargs.get("start_date"),
            kwargs.get("end_date"),
        )
    elif type == "ranking":
        return _fetch_ranking(kwargs.get("market"), kwargs.get("ranking_type"))

    elif type == "exchange":
        return _fetch_exchange(kwargs.get("currency_pair"))

    else:
        raise ValueError(f"Unknown type: {type}")

SPRING_BASE_URL = "http://localhost:8080"

def _call_spring_api(path: str, params: dict | None = None):
    try:
        url = f"{SPRING_BASE_URL}{path}"
        res = requests.get(url, params=params, timeout=3)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        return {
            "success": False,
            "error": "SPRING_API_ERROR",
            "message": str(e)
        }

# ── price ─────────────────────────────────────────────────────────────────────
# 시세 조회 템플릿을 위한 함수 병합
def _fetch_price(stock_code: str | None, market: str | None) -> dict:
    if not stock_code:
        return {"error": "stock_code is required"}

    price_data = _call_spring_api(
        f"/api/market/stocks/{stock_code}/price",
        {
            "stockCode": stock_code,
            "market": market,
        },
    )
    if price_data.get("error"):
        return price_data

    daily_data = _call_spring_api(
        f"/api/market/stocks/{stock_code}/daily",
        {"date": str(date_type.today())},
    )
    if daily_data.get("error"):
        daily_data = {}

    return {
        "stock_name": stock_code,
        "stock_code": price_data.get("stockCode", stock_code),
        "current_price": price_data.get("currentPrice", 0),
        "change": price_data.get("changeAmount", 0),
        "change_rate": price_data.get("changeRate", 0.0),
        "open": daily_data.get("openPrice", 0),
        "high": daily_data.get("highPrice", 0),
        "low": daily_data.get("lowPrice", 0),
        "volume": price_data.get("volume", 0),
    }


# ── chart ─────────────────────────────────────────────────────────────────────


#종목 분봉 차트
def _fetch_chart(stock_code: str | None, market: str | None) -> dict:
    if not stock_code:
        return {"error": "stock_code is required"}

    return _call_spring_api(
        f"/api/market/stocks/{stock_code}/minute-chart",
        {"ncnt": 1}  # 1분봉
    )

#종목 기간별 차트(일/주/월/년)
def _fetch_period_chart(stock_code: str, start_date: str, end_date: str) -> dict:
    return _call_spring_api(
        f"/api/market/stocks/{stock_code}/chart",
        {
            "period": "DAILY",
            "startDate": start_date,
            "endDate": end_date
        }
    )

# 저가,고가,종가 등등 
def _fetch_daily(stock_code: str, date: str) -> dict:
    return _call_spring_api(
        f"/api/market/stocks/{stock_code}/daily",
        {"date": date}
    )


# ── ranking ───────────────────────────────────────────────────────────────────

_MOCK_RANKINGS: dict[str, list[dict]] = {
    "volume": [
        {"rank": 1, "stock_name": "삼성전자",  "value": 15_000_000},
        {"rank": 2, "stock_name": "POSCO홀딩스","value":  9_800_000},
        {"rank": 3, "stock_name": "SK하이닉스","value":  5_000_000},
    ],
    "change_rate": [
        {"rank": 1, "stock_name": "에코프로",  "value": 8.7},
        {"rank": 2, "stock_name": "포스코DX",  "value": 7.3},
        {"rank": 3, "stock_name": "삼성SDI",   "value": 5.1},
    ],
    "foreign_buy": [
        {"rank": 1, "stock_name": "삼성전자",  "value": 3_200_000_000},
        {"rank": 2, "stock_name": "SK하이닉스","value": 1_500_000_000},
        {"rank": 3, "stock_name": "LG에너지솔루션","value": 800_000_000},
    ],
}

def _fetch_ranking(market: str | None, ranking_type: str | None) -> dict:
    # TODO: LS증권 API t1463/t1464(국내)/해외랭킹 API 호출로 교체
    items = _MOCK_RANKINGS.get(ranking_type or "volume", [])
    return {
        "ranking_type": ranking_type,
        "market": market,
        "items": items,
    }


# ── index ─────────────────────────────────────────────────────────────────────

_MOCK_INDEXES = {
    "KOSPI":  {"current": 2_650.3, "change":  12.5, "change_rate":  0.47},
    "NASDAQ": {"current": 18_350.2,"change": -45.8, "change_rate": -0.25},
}

def _fetch_index(index_code: str | None) -> dict:
    # TODO: LS증권 API t1511(국내지수)/해외지수 API 호출로 교체
    base = _MOCK_INDEXES.get(index_code or "KOSPI", {"current": 0, "change": 0, "change_rate": 0.0})
    return {"index_code": index_code, **base}


# ── exchange ──────────────────────────────────────────────────────────────────

def _fetch_exchange(currency_pair: str | None) -> dict:
    # TODO: Spring API 환율 엔드포인트 확정 시 path 교체
    pair = currency_pair or "USDKRW"
    data = _call_spring_api(
        "/api/market/exchange",
        {"currencyPair": pair},
    )
    if data.get("error"):
        return {"currency_pair": pair, "rate": 0.0, "change": 0.0}
    return {
        "currency_pair": pair,
        "rate":   data.get("rate", 0.0),
        "change": data.get("change", 0.0),
    }
