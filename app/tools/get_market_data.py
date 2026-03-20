"""
도구 3: get_market_data - 실시간 시장 데이터 (시세/차트/랭킹/지수/환율)
TODO: LS증권 API 연동 시 _fetch_*() 내부를 실제 호출로 교체
"""
from typing import Literal


def get_market_data(
    type: Literal["price", "chart", "ranking", "index", "exchange"],
    stock_code: str | None = None,
    market: Literal["domestic", "overseas"] | None = None,
    ranking_type: Literal["volume", "change_rate", "foreign_buy"] | None = None,
    index_code: Literal["KOSPI", "NASDAQ"] | None = None,
    currency_pair: Literal["USDKRW", "EURKRW"] | None = None,
) -> dict:
    """
    실시간 시장 데이터를 반환합니다.

    Args:
        type: "price" | "chart" | "ranking" | "index" | "exchange"
        stock_code: 종목코드 (price/chart 시 필요)
        market: "domestic" | "overseas" (price/chart/ranking 시)
        ranking_type: "volume" | "change_rate" | "foreign_buy" (ranking 시)
        index_code: "KOSPI" | "NASDAQ" (index 시)
        currency_pair: "USDKRW" | "EURKRW" (exchange 시)
    """
    if type == "price":
        return _fetch_price(stock_code, market)
    elif type == "chart":
        return _fetch_chart(stock_code, market)
    elif type == "ranking":
        return _fetch_ranking(market, ranking_type)
    elif type == "index":
        return _fetch_index(index_code)
    elif type == "exchange":
        return _fetch_exchange(currency_pair)
    else:
        raise ValueError(f"Unknown type: {type}")


# ── price ─────────────────────────────────────────────────────────────────────

_MOCK_PRICES = {
    "005930": {"stock_name": "삼성전자",  "current_price": 75_000,  "change": 1_500,  "change_rate":  2.04, "open": 73_500, "high": 75_500, "low": 73_000, "volume": 15_000_000},
    "000660": {"stock_name": "SK하이닉스","current_price": 195_000, "change": -2_000, "change_rate": -1.02, "open": 197_000,"high": 197_500,"low": 194_000,"volume":  5_000_000},
    "035420": {"stock_name": "NAVER",    "current_price": 210_000, "change":  3_000,  "change_rate":  1.45, "open": 207_000,"high": 211_000,"low": 206_000,"volume":  2_500_000},
    # 해외
    "AAPL":   {"stock_name": "Apple",    "current_price": 225,     "change":    3.5,  "change_rate":  1.58, "open": 221,    "high": 226,    "low": 220,    "volume": 80_000_000},
    "NVDA":   {"stock_name": "NVIDIA",   "current_price": 875,     "change":  -12.0,  "change_rate": -1.35, "open": 887,    "high": 889,    "low": 872,    "volume": 40_000_000},
}

def _fetch_price(stock_code: str | None, market: str | None) -> dict:
    # TODO: LS증권 API t1102(국내)/HDFSCMUP0(해외) 호출로 교체
    if stock_code and stock_code in _MOCK_PRICES:
        return {"stock_code": stock_code, **_MOCK_PRICES[stock_code]}
    return {
        "stock_code": stock_code or "UNKNOWN",
        "stock_name": "알 수 없는 종목",
        "current_price": 0, "change": 0, "change_rate": 0.0,
        "open": 0, "high": 0, "low": 0, "volume": 0,
    }


# ── chart ─────────────────────────────────────────────────────────────────────

def _fetch_chart(stock_code: str | None, market: str | None) -> dict:
    # TODO: LS증권 API t8410(국내)/HDFSCHART(해외) 호출로 교체
    return {
        "stock_code": stock_code,
        "market": market,
        "candles": [
            {"date": "2026-03-17", "open": 73_500, "high": 75_500, "low": 73_000, "close": 75_000, "volume": 15_000_000},
            {"date": "2026-03-14", "open": 72_000, "high": 74_000, "low": 71_500, "close": 73_500, "volume": 12_000_000},
            {"date": "2026-03-13", "open": 70_500, "high": 72_500, "low": 70_000, "close": 72_000, "volume": 10_000_000},
        ],
    }


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

_MOCK_EXCHANGE = {
    "USDKRW": {"rate": 1_380.5, "change": -2.3},
    "EURKRW": {"rate": 1_490.2, "change":  5.1},
}

def _fetch_exchange(currency_pair: str | None) -> dict:
    # TODO: LS증권 API 또는 한국은행 API 환율 조회로 교체
    base = _MOCK_EXCHANGE.get(currency_pair or "USDKRW", {"rate": 0.0, "change": 0.0})
    return {"currency_pair": currency_pair, **base}
