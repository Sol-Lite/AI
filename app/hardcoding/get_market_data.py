"""
(1) 지수 조회      — dispatcher 의도: index         → get_market_data(type="index")         → format_index()
(2) 환율 조회      — dispatcher 의도: exchange_rate → get_market_data(type="exchange")       → format_exchange_rate()
(3) 주식 순위 조회 — dispatcher 의도: ranking       → get_market_data(type="ranking")        → format_ranking()
(4) 차트+시세 조회 — dispatcher 의도: chart_price   → get_market_data(type="price")          → format_chart_price()

데이터 소스: Spring API (localhost:8080)
  GET /api/market/indices                      — 지수
  GET /api/market/exchange                     — 환율
  GET /api/market/stocks/ranking               — 주식 순위
  GET /api/market/stocks/{code}/price          — 현재가
  GET /api/market/stocks/{code}/daily          — 당일 고/저/시/종가
  GET /api/market/stocks/{code}/chart          — 기간별 차트 (일/주/월/년)
"""
import re
import requests
from datetime import date as date_type
from app.db.oracle import resolve_stock_code

VALID_CHART_PERIODS = {"DAILY", "WEEKLY", "MONTHLY", "YEARLY"}

# stock_code가 필요한 type 목록
_STOCK_CODE_TYPES = {"price", "daily", "period_chart"}


def _is_valid_stock_code(code: str) -> bool:
    """국내(6자리 숫자) 또는 해외(영문+숫자, 점 허용) 종목 코드 형식 검증"""
    return bool(re.match(r'^[A-Z0-9]{1,10}(\.[A-Z0-9]{1,2})?$', code))


def _resolve(stock_code: str | None) -> tuple[str | None, dict | None]:
    """
    종목 코드를 검증하고 필요 시 DB에서 조회합니다.
    Returns:
        (resolved_code, None) 정상
        (None, error_dict)    실패
    """
    if not stock_code:
        return None, {"error": "stock_code is required"}
    if not _is_valid_stock_code(stock_code):
        resolved = resolve_stock_code(stock_code)
        if not resolved:
            return None, {
                "error": "not_found",
                "message": f"'{stock_code}'에 해당하는 종목을 찾을 수 없습니다.",
            }
        return resolved, None
    return stock_code, None


def get_market_data(type: str, **kwargs):
    # price / daily / period_chart 는 종목 코드 필요 → 한글 종목명이면 Oracle DB에서 코드 조회
    if type in _STOCK_CODE_TYPES:
        stock_code, err = _resolve(kwargs.get("stock_code"))
        if err:
            return err
        kwargs = {**kwargs, "stock_code": stock_code}

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
def _fetch_price(stock_code: str, market: str | None) -> dict:
    price_data = _call_spring_api(
        f"/api/market/stocks/{stock_code}/price",
        {"stockCode": stock_code},
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

_VALID_RANKING_TYPES = {"trading-volume", "trading-value", "rising", "falling", "market-cap"}


def _fetch_ranking(ranking_type: str | None, market: str | None = None) -> dict:  # noqa: ARG001
    is_default = ranking_type not in _VALID_RANKING_TYPES
    api_type = ranking_type if not is_default else "trading-volume"
    stocks = _call_spring_api(
        "/api/market/stocks/ranking",
        {"type": type, "market": market}
    )
    return {
        "type":       api_type,
        "is_default": is_default,
        "stocks":     stocks if isinstance(stocks, list) else [],
    }

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
