# 더미 데이터 구조 및 DB 조회·출력 가이드

> `setup_dummy_data.py` 기준 (account_id = 1, simulation_round_id = 1)

---

## 1. 더미 데이터 구조

### 1-1. instruments (종목)

| instrument_id | market_type | stock_code | stock_name | currency | sector |
| ------------- | ----------- | ---------- | ---------- | -------- | ------ |
| 1             | domestic    | 005930     | 삼성전자   | KRW      | IT     |
| 2             | domestic    | 000660     | SK하이닉스 | KRW      | 반도체 |
| 3             | domestic    | 035420     | NAVER      | KRW      | IT     |
| 4             | overseas    | AAPL       | Apple      | USD      | IT     |
| 5             | overseas    | NVDA       | NVIDIA     | USD      | 반도체 |

### 1-2. cash_balances (현금 잔고)

| currency | available_amount (주문/출금 가능) | total_amount (총잔고) |
| -------- | --------------------------------- | --------------------- |
| KRW      | 3,000,000 원                      | 5,000,000 원          |
| USD      | 1,000 USD                         | 1,500 USD             |

> `_query_balance()`는 Spring API(`/api/balance/cash`)를 호출해 위 값을 반환합니다.

### 1-3. holdings (보유 종목)

| 종목       | 보유수량 | 평균매수가        | 총 매수금액  |
| ---------- | -------- | ----------------- | ------------ |
| 삼성전자   | 50주     | 70,000 KRW        | 3,500,000 원 |
| SK하이닉스 | 20주     | 180,000 KRW       | 3,600,000 원 |
| NAVER      | 10주     | 200,000 KRW       | 2,000,000 원 |
| Apple      | 5주      | $200 (환율 1,380) | $1,000       |
| NVIDIA     | 3주      | $800 (환율 1,380) | $2,400       |

### 1-4. executions (체결 내역)

| execution_id | 종목       | 매수/매도 | 체결가  | 수량 | 체결금액  | 수수료 | 세금   | 순손익     | 체결일  |
| ------------ | ---------- | --------- | ------- | ---- | --------- | ------ | ------ | ---------- | ------- |
| 1            | 삼성전자   | 매수      | 70,000  | 50주 | 3,500,000 | 3,500  | -      | -3,503,500 | 30일 전 |
| 2            | SK하이닉스 | 매수      | 180,000 | 20주 | 3,600,000 | 3,600  | -      | -3,603,600 | 25일 전 |
| 3            | NAVER      | 매수      | 200,000 | 10주 | 2,000,000 | 2,000  | -      | -2,002,000 | 20일 전 |
| 4            | Apple      | 매수      | $200    | 5주  | $1,000    | $100   | -      | -$1,100    | 15일 전 |
| 5            | NVIDIA     | 매수      | $800    | 3주  | $2,400    | $100   | -      | -$2,500    | 10일 전 |
| 6            | 삼성전자   | 매도      | 75,000  | 10주 | 750,000   | 3,750  | 11,250 | +735,000   | 5일 전  |
| 7            | SK하이닉스 | 매도      | 200,000 | 5주  | 1,000,000 | 5,000  | 15,000 | +980,000   | 3일 전  |
| 8            | NAVER      | 매도      | 190,000 | 3주  | 570,000   | 2,850  | 8,550  | +558,600   | 1일 전  |

**실현손익 합계**: 735,000 + 980,000 + 558,600 = **2,273,600 원**

### 1-5. portfolio_snapshots (포트폴리오 스냅샷)

총 33개 스냅샷 (오늘 기준):

| 기준          | snapshot_date | total_value |
| ------------- | ------------- | ----------- |
| 오늘 (rn=1)   | SYSDATE       | 12,000,000  |
| 어제 (rn=2)   | SYSDATE-1     | 11,940,000  |
| 1개월 전 기준 | SYSDATE-31    | 11,000,000  |
| 3개월 전 기준 | SYSDATE-91    | 10,500,000  |
| 6개월 전 기준 | SYSDATE-181   | 9,800,000   |

---

## 2. 거래내역 조회 (`get_db_data / trades`)

### 2-1. SQL 쿼리 구조

```
COUNT 쿼리: total(8), buy_count(5), sell_count(3)

RECENT 쿼리 (limit=3):
  last_buy  = 최근 매수 3건: NVIDIA(10일전), Apple(15일전), NAVER(20일전)
  last_sell = 최근 매도 3건: NAVER(1일전), SK하이닉스(3일전), 삼성전자(5일전)
  UNION ALL → executed_at DESC 정렬
```

### 2-2. `_query_trades()` 반환값

```python
{
    "total":      8,
    "buy_count":  5,
    "sell_count": 3,
    "recent": [
        {"stock_name": "NAVER",      "side": "sell", "price": 190000, "quantity": 3,  "executed_at": "2026-03-22 ..."},
        {"stock_name": "SK하이닉스", "side": "sell", "price": 200000, "quantity": 5,  "executed_at": "2026-03-20 ..."},
        {"stock_name": "삼성전자",   "side": "sell", "price": 75000,  "quantity": 10, "executed_at": "2026-03-18 ..."},
        {"stock_name": "NVIDIA",     "side": "buy",  "price": 800,    "quantity": 3,  "executed_at": "2026-03-11 ..."},
        {"stock_name": "Apple",      "side": "buy",  "price": 200,    "quantity": 5,  "executed_at": "2026-03-07 ..."},
        {"stock_name": "NAVER",      "side": "buy",  "price": 200000, "quantity": 10, "executed_at": "2026-03-02 ..."},
    ]
}
```

> **주의**: `recent`는 매수 limit개 + 매도 limit개 UNION 구조입니다.
> 특정 종목 필터링 SQL이 없으므로 "삼성전자 거래내역 전체"는 조회 불가.
> recent 리스트 내에 포함된 경우에만 확인 가능합니다.

### 2-3. `format_trades()` 출력 예시

```
거래내역

총 거래 횟수: 8건  (매수 5건 / 매도 3건)

최근 거래내역

1. [매도] NAVER
   190,000원 × 3주 = 570,000원
   체결일: 2026-03-22 01:11:25

2. [매도] SK하이닉스
   200,000원 × 5주 = 1,000,000원
   체결일: 2026-03-20 01:11:25

3. [매도] 삼성전자
   75,000원 × 10주 = 750,000원
   체결일: 2026-03-18 01:11:25

4. [매수] NVIDIA
   800원 × 3주 = 2,400원
   체결일: 2026-03-11 01:11:25

5. [매수] Apple
   200원 × 5주 = 1,000원
   체결일: 2026-03-07 01:11:25

6. [매수] NAVER
   200,000원 × 10주 = 2,000,000원
   체결일: 2026-03-02 01:11:25

※ 안내: 최근 체결 기준 내역이며, 주문 상태/체결 수수료 반영 시점에 따라 앱 표시와 차이가 날 수 있습니다.
```

---

## 3. 포트폴리오 조회 (`get_db_data / portfolio`)

### 3-1. 쿼리 구조 (4개 SQL + Spring API 2회)

| 단계           | 출처      | 내용                                                   |
| -------------- | --------- | ------------------------------------------------------ |
| snapshot_sql   | Oracle DB | daily_return, return_1m/3m/6m, MDD 계산                |
| holdings_sql   | Oracle DB | 보유 종목 목록 (stock_code, avg_buy_price, quantity)   |
| Spring API × N | Spring    | 보유 종목별 현재가 (`/api/market/stocks/{code}/price`) |
| Spring API × 1 | Spring    | 환율 (`/api/market/exchange?currencyPair=USDKRW`)      |
| cash_sql       | Oracle DB | 현금 잔고 (krw, usd)                                   |
| trade_sql      | Oracle DB | 거래 통계 (승률, 평균 수익/손실)                       |
| realized_sql   | Oracle DB | 실현손익 합계                                          |
| volatility_sql | Oracle DB | 최근 30일 daily_return 표준편차                        |

### 3-2. 더미 데이터 기준 계산값

#### 수익률 (snapshot 기준)

```
1개월 수익률: (12,000,000 - 11,000,000) / 11,000,000 × 100 = +9.09%
3개월 수익률: (12,000,000 - 10,500,000) / 10,500,000 × 100 = +14.29%
6개월 수익률: (12,000,000 -  9,800,000) /  9,800,000 × 100 = +22.45%
MDD: portfolio_snapshots의 최대 낙폭 (더미에서는 거의 0에 가까움)
```

#### 실현손익

```
삼성전자 매도: +735,000 원
SK하이닉스 매도: +980,000 원
NAVER 매도: +558,600 원
합계: +2,273,600 원
```

#### 평가손익 (Spring API 현재가 기준, 실시간 변동)

```
holdings × 현재가 - holdings × 평균매수가
※ Spring API 연결 여부에 따라 값이 달라짐 (연결 안 되면 current_price=0)
```

#### 승률

```
win_count / sell_count × 100
더미: sell 3건 모두 net_amount > 0 → 승률 100% (단, 더미 집계에 따라 다를 수 있음)
```

#### 국내/해외 비율 (매수금액 기준)

```
국내: 삼성전자(3,500,000) + SK하이닉스(3,600,000) + NAVER(2,000,000) = 9,100,000
해외: Apple(1,000 USD) + NVIDIA(2,400 USD) = 3,400 USD
비율은 KRW 환산 후 계산
※ Spring API 환율이 0이면 해외 비율을 계산하지 못해 국내 100%로 표시될 수 있음
```

### 3-3. `_query_portfolio()` 주요 반환 필드

```python
{
    "current_total_krw": float,       # 실시간 총 평가금액 (KRW)
    "current_total_usd": float,       # 실시간 총 평가금액 (USD)
    "usdkrw": float,                  # 환율 (Spring API)
    "domestic_stock_value": float,    # 국내 주식 실시간 평가액
    "overseas_value_krw": float,      # 해외 주식 KRW 환산 평가액
    "cash_krw": float,                # 원화 현금 (5,000,000)
    "cash_usd": float,                # 달러 현금 (1,500)
    "daily_return": float,            # 일간 수익률 (오늘 스냅샷)
    "return_1m": float,               # 1개월 수익률
    "return_3m": float,               # 3개월 수익률
    "return_6m": float,               # 6개월 수익률
    "mdd": float,                     # 최대 낙폭 (%)
    "volatility": float,              # 30일 일간 변동성 (표준편차)
    "realized_pnl": float,            # 실현손익 = +2,273,600
    "unrealized_pnl": float,          # 평가손익 (실시간)
    "best_stock": {"name": str, "return": float},   # 최고 수익 종목
    "worst_stock": {"name": str, "return": float},  # 최저 수익 종목
    "stock_returns": [                # 보유 종목별 수익률 리스트
        {"name": str, "return_rate": float, "unrealized_pnl": float},
        ...
    ],
    "sector_concentration": [{"sector": str, "weight": float}, ...],
    "stock_concentration":  [{"stock": str,  "weight": float}, ...],
    "domestic_ratio": float,          # 국내 비율 (%)
    "foreign_ratio": float,           # 해외 비율 (%)
    "total_trades": int,              # 8
    "buy_count": int,                 # 5
    "sell_count": int,                # 3
    "win_count": int,                 # 수익 매도 건수
    "loss_count": int,                # 손실 매도 건수
    "avg_win": float,                 # 평균 수익 금액
    "avg_loss": float,                # 평균 손실 금액
    "profit_factor": float,           # 손익비 = avg_win / abs(avg_loss)
}
```

### 3-4. `format_portfolio()` 출력 예시

```
포트폴리오 분석 리포트
────────────────────────
수익률
  평가손익   +23,000,000원         ← Spring API 현재가 기반 (실시간 변동)
  실현손익   +2,273,600원          ← Oracle DB 고정값
  1개월 +9.09%   3개월 +14.29%   6개월 +22.45%
  최고  SK하이닉스  +470.0%        ← best_stock (현재가 기준)
  최저  NAVER  +8.75%             ← worst_stock (현재가 기준)
────────────────────────
집중도
  국내 100.0%   해외 0.0%         ← Spring API 환율 0이면 국내 100%로 표시
  섹터
    반도체       63.2%
    IT           36.8%
  종목
    SK하이닉스   63.2%
    삼성전자     ...
────────────────────────
리스크
  최대 낙폭    0.0%               ← 더미 스냅샷 단조증가 구조라 MDD≈0
  회복 필요    +0.0%
  일간 변동폭  0.28%              ← 최근 30일 daily_return 표준편차
  거래 8회   수익 3회 / 손실 0회
  평균 수익  +757,867원
  평균 손실  -0원
  손익비     0배
────────────────────────
```

---

## 4. Spring API 의존성 정리

| 데이터                     | 출처                                     | Spring 꺼지면                 |
| -------------------------- | ---------------------------------------- | ----------------------------- |
| 잔고 (balance)             | Spring `/api/balance/cash`               | SPRING_API_ERROR 반환         |
| 환율 (portfolio 내)        | Spring `/api/market/exchange`            | usdkrw=0 → 해외비율 계산 불가 |
| 종목 현재가 (portfolio 내) | Spring `/api/market/stocks/{code}/price` | current_price=0 → 평가손익=0  |
| 거래내역 (trades)          | Oracle DB 직접                           | Spring 불필요                 |
| 포트폴리오 스냅샷·거래통계 | Oracle DB 직접                           | Spring 불필요                 |

---

## 5. LLM 답변 가능 범위 정리

### trades / trades_detail

| 질문 유형               | 가능 여부 | 근거                                            |
| ----------------------- | --------- | ----------------------------------------------- |
| 총 거래 횟수            | 가능      | `total` = 8                                     |
| 매수/매도 횟수          | 가능      | `buy_count`=5, `sell_count`=3                   |
| 최근 거래 내역          | 가능      | `recent` 리스트 (최대 limit×2건)                |
| 특정 종목 전체 거래내역 | **불가**  | 종목 필터 SQL 없음. `recent`에 있으면 확인 가능 |
| 특정 날짜 거래          | **불가**  | 날짜 필터 SQL 없음                              |

### portfolio / portfolio_detail

| 질문 유형           | 가능 여부 | 근거                                     |
| ------------------- | --------- | ---------------------------------------- |
| 총 평가금액         | 가능      | `current_total_krw`                      |
| 기간별 수익률       | 가능      | `return_1m/3m/6m`                        |
| 특정 종목 수익률    | 가능      | `stock_returns` 리스트                   |
| 최고/최저 수익 종목 | 가능      | `best_stock`, `worst_stock`              |
| 손실 종목           | 가능      | `stock_returns`에서 return_rate < 0 필터 |
| 승률                | 가능      | `win_count / sell_count × 100`           |
| MDD                 | 가능      | `mdd` 필드 (더미에서 ≈ 0)                |
| 국내/해외 비율      | 가능      | `domestic_ratio`, `foreign_ratio`        |
| 섹터 비중           | 가능      | `sector_concentration`                   |
| 종목별 비중         | 가능      | `stock_concentration`                    |
| 일간 수익률         | 가능      | `daily_return` (스냅샷 기준)             |
