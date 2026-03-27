"""
테스트용 mock 데이터 — .env에 USE_MOCK=true 설정 시 Oracle DB 대신 사용
"""

MOCK_TRADE_SUMMARY = {
    "total":      42,
    "buy_count":  25,
    "sell_count": 17,
}

MOCK_RECENT_TRADES = {
    "trades": [
        {"stock_name": "삼성전자",   "side": "buy",  "price": 74200, "quantity": 10, "amount": 742000,  "executed_at": "2026-03-26 14:32:11"},
        {"stock_name": "SK하이닉스", "side": "sell", "price": 198000,"quantity": 5,  "amount": 990000,  "executed_at": "2026-03-25 10:15:44"},
        {"stock_name": "NVDA",       "side": "buy",  "price": 121.5, "quantity": 3,  "amount": 364.5,   "executed_at": "2026-03-24 22:01:09"},
        {"stock_name": "카카오",     "side": "sell", "price": 43500, "quantity": 20, "amount": 870000,  "executed_at": "2026-03-21 09:55:00"},
        {"stock_name": "AAPL",       "side": "buy",  "price": 218.3, "quantity": 2,  "amount": 436.6,   "executed_at": "2026-03-20 23:30:55"},
    ]
}

MOCK_HOLDINGS = {
    "holdings": [
        {"stock_code": "005930", "stock_name": "삼성전자",   "sector": "반도체", "market_type": "domestic",
         "quantity": 50, "avg_buy_price": 71000, "cost_basis": 3550000, "current_price": 74200, "current_value_krw": 3710000, "return_rate": 4.51},
        {"stock_code": "000660", "stock_name": "SK하이닉스", "sector": "반도체", "market_type": "domestic",
         "quantity": 15, "avg_buy_price": 210000,"cost_basis": 3150000, "current_price": 198000,"current_value_krw": 2970000, "return_rate": -5.71},
        {"stock_code": "NVDA",   "stock_name": "엔비디아",   "sector": "반도체", "market_type": "overseas",
         "quantity": 10, "avg_buy_price": 105.0, "cost_basis": 1050,    "current_price": 121.5,  "current_value_krw": 1755450,"return_rate": 15.71},
        {"stock_code": "035720", "stock_name": "카카오",     "sector": "인터넷", "market_type": "domestic",
         "quantity": 30, "avg_buy_price": 47000, "cost_basis": 1410000, "current_price": 43500,  "current_value_krw": 1305000,"return_rate": -7.45},
        {"stock_code": "AAPL",   "stock_name": "애플",       "sector": "IT",     "market_type": "overseas",
         "quantity": 5,  "avg_buy_price": 195.0, "cost_basis": 975,     "current_price": 218.3,  "current_value_krw": 1580171,"return_rate": 11.95},
    ],
    "total_count": 5,
    "total_cost":  10161025,
    "usdkrw":      1445.0,
}

MOCK_PORTFOLIO_RETURNS = {
    "daily_return": -0.82,
    "return_1m":     3.14,
    "return_3m":     7.28,
    "return_6m":    12.45,
    "mdd":          -11.23,
    "recovery_needed": 12.65,
}

MOCK_SECTOR_CONCENTRATION = {
    "sectors": [
        {"sector": "반도체", "market_type": "domestic", "weight": 58.3},
        {"sector": "반도체", "market_type": "overseas",  "weight": 15.7},
        {"sector": "인터넷", "market_type": "domestic",  "weight": 11.6},
        {"sector": "IT",     "market_type": "overseas",  "weight": 14.4},
    ],
    "domestic_weight": 69.9,
    "overseas_weight": 30.1,
}

MOCK_PORTFOLIO_RISK = {
    "volatility":      1.84,
    "mdd":            -11.23,
    "recovery_needed": 12.65,
    "best_stock":  {"name": "엔비디아", "return_rate": 15.71, "unrealized_pnl": 237075},
    "worst_stock": {"name": "카카오",   "return_rate": -7.45, "unrealized_pnl": -105000},
    "realized_pnl":   320000,
    "unrealized_pnl": 254621,
    "stock_returns": [
        {"name": "삼성전자",   "return_rate":  4.51, "unrealized_pnl":  160000},
        {"name": "SK하이닉스", "return_rate": -5.71, "unrealized_pnl": -180000},
        {"name": "엔비디아",   "return_rate": 15.71, "unrealized_pnl":  237075},
        {"name": "카카오",     "return_rate": -7.45, "unrealized_pnl": -105000},
        {"name": "애플",       "return_rate": 11.95, "unrealized_pnl":  142546},
    ],
}

MOCK_TRADE_STATS = {
    "total_trades":   42,
    "buy_count":      25,
    "sell_count":     17,
    "win_count":      11,
    "loss_count":      6,
    "win_rate":       64.7,
    "avg_win":       185000.0,
    "avg_loss":      -92000.0,
    "profit_factor":   2.01,
    "total_realized": 320000,
}
