"""
도구 3: get_market_data - LS증권 API 연동 (실시간 시장 데이터: 시세/차트/랭킹/지수/환율)
"""
from typing import Literal
import requests
from datetime import date as date_type

VALID_CHART_PERIODS = {"DAILY", "WEEKLY", "MONTHLY", "YEARLY"}


# 시세 조회, 차트, 랭킹, 지수, 환율 등 시장 데이터 조회를 위한 도구 함수
def get_market_data(type: str, **kwargs):
    if type == "price":
        return _fetch_price(kwargs.get("stock_code"), kwargs.get("market"))

    # elif type == "chart":
    #     return _fetch_chart(kwargs.get("stock_code"), kwargs.get("market"))

    elif type == "daily":
        return _fetch_daily(kwargs.get("stock_code"), kwargs.get("date"))

    elif type == "period_chart":
        return _fetch_period_chart(
            kwargs.get("stock_code"),
            kwargs.get("period"),
            kwargs.get("start_date"),
            kwargs.get("end_date"),
    
        )
    elif type == "ranking":
        return _fetch_ranking(kwargs.get("ranking_type"), kwargs.get("market"))

    elif type == "exchange":
        return _fetch_exchange(kwargs.get("currency_pair"))
    elif type=="index":
        return _fetch_index()

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
# def _fetch_chart(stock_code: str | None, market: str | None) -> dict:
#     if not stock_code:
#         return {"error": "stock_code is required"}

#     return _call_spring_api(
#         f"/api/market/stocks/{stock_code}/minute-chart",
#         {"ncnt": 1}  # 1분봉
#     )

#종목 기간별 차트(일/주/월/년)
def _fetch_period_chart(stock_code: str, period: str, start_date: str, end_date: str | None = None) -> dict:
    if not stock_code:
        return {"error": "stock_code is required"}
    if not start_date:
        return {"error": "start_date is required"}
    if not end_date:
        return {"error": "end_date is required"}

    normalized_period = (period or "DAILY").upper()
    if normalized_period not in VALID_CHART_PERIODS:
        return {
            "error": "invalid period",
            "message": f"period must be one of {sorted(VALID_CHART_PERIODS)}",
        }

    return _call_spring_api(
        f"/api/market/stocks/{stock_code}/chart",
        {
            "period": normalized_period,
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

def _fetch_ranking(ranking_type: str, market: str) -> dict:
    return _call_spring_api(
        "/api/market/stocks/ranking",
        {"type": ranking_type or "trading-value", "market": market or "all"}
    )

# ── index ─────────────────────────────────────────────────────────────────────

def _fetch_index():
    return _call_spring_api("/api/market/indices")


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
