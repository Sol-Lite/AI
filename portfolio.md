# _query_portfolio 상세 문서

`app/tools/get_db_data.py` 내 `_query_portfolio(account_id)` 함수에 대한 상세 설명입니다.

---

## 개요

사용자의 포트폴리오 전체를 분석하여 반환하는 함수입니다.
Oracle DB, Spring API(실시간 시세/환율)를 조합해 아래 6개 영역의 데이터를 수집·계산합니다.

| 영역 | 데이터 출처 |
|------|------------|
| 스냅샷 (기간별 수익률, MDD, 변동성) | `portfolio_snapshots` |
| 보유 종목 (평가액, 집중도, 손익) | `holdings` + `instruments` + Spring API |
| 현금 잔고 | `cash_balances` |
| 환율 | Spring API (`/api/market/exchange`) |
| 거래 통계 | `executions` |
| 실현손익 | `executions` |

---

## 사용 테이블

### 1. `portfolio_snapshots` (추가 예정)

일별 1건씩 저장되는 포트폴리오 스냅샷 테이블입니다.

| 컬럼 | 타입 | 설명 | 사용 여부 |
|------|------|------|----------|
| `snapshot_id` | PK | 고유 식별자 | - |
| `account_id` | FK | 계좌 식별자 | 필터 조건 |
| `simulation_round_id` | FK | 시뮬레이션 회차 연결 | - |
| `snapshot_date` | DATE | 스냅샷 날짜 (일별 1건) | 정렬, 기간 필터 |
| `total_value` | NUMBER | 당일 총 평가금액 (현금 + 보유주식) | 기간별 수익률, MDD, yesterday_total |
| `daily_return` | NUMBER | 전일 대비 수익률 (%) | daily_return |
| `cash_krw` | NUMBER | 원화 현금 | 미사용 (cash_balances 직접 조회) |
| `cash_usd` | NUMBER | 달러 현금 | 미사용 (cash_balances 직접 조회) |
| `holdings_value_krw` | NUMBER | 보유주식 평가액 (원화 환산) | 미사용 (실시간 계산) |
| `created_at` | TIMESTAMP | 생성일시 | - |

> `cash_krw`, `cash_usd`, `holdings_value_krw`는 현재 코드에서 사용하지 않습니다.
> `cash_balances`에서 직접 조회하고 평가액은 실시간으로 계산하기 때문입니다.
> 단, 히스토리 분석(특정 날짜의 자산 구성 추적) 목적으로 테이블에는 유지합니다.

---

### 2. `holdings`

현재 보유 중인 종목 정보를 저장하는 테이블입니다.

| 컬럼 | 설명 | 사용 목적 |
|------|------|----------|
| `account_id` | 계좌 식별자 | 필터 조건 |
| `instrument_id` | 종목 식별자 (instruments 연결) | JOIN 키 |
| `holding_quantity` | 보유 수량 | 평가액 계산 |
| `avg_buy_price` | 평균 매수가 | 수익률, 미실현손익 계산 |

> `holding_quantity > 0` 조건으로 실제 보유 중인 종목만 조회합니다.

---

### 3. `instruments`

종목 메타 정보 테이블입니다.

| 컬럼 | 설명 | 사용 목적 |
|------|------|----------|
| `instrument_id` | 종목 식별자 | JOIN 키 |
| `stock_code` | 종목 코드 | Spring API 시세 조회 |
| `stock_name` | 종목명 | best/worst stock, 집중도 표시 |
| `sector` | 섹터 | 섹터 집중도 계산 |
| `market_type` | 시장 구분 (`domestic` / `overseas`) | 국내/해외 분리, 환율 환산 여부 결정 |

---

### 4. `cash_balances`

통화별 현금 잔고 테이블입니다.

| 컬럼 | 설명 | 사용 목적 |
|------|------|----------|
| `account_id` | 계좌 식별자 | 필터 조건 |
| `currency_code` | 통화 코드 (`KRW` / `USD`) | KRW/USD 분리 |
| `total_amount` | 총 잔고 | 실시간 총평가금액 계산에 포함 |

---

### 5. `executions`

체결 내역 테이블입니다. 거래 통계와 실현손익 계산에 사용합니다.

| 컬럼 | 설명 | 사용 목적 |
|------|------|----------|
| `account_id` | 계좌 식별자 | 필터 조건 |
| `order_side` | 매수/매도 구분 (`buy` / `sell`) | 거래 통계 분류 |
| `net_amount` | 순 체결금액 (수수료/세금 차감 후) | 실현손익, 승/패 판단 |

---

## 반환 지표 상세

### 실시간 총평가금액

| 키 | 설명 | 계산 방식 |
|----|------|----------|
| `current_total_krw` | 실시간 총평가금액 (원화) | 국내주식 평가액 + 해외주식 평가액(KRW 환산) + 현금KRW + 현금USD × USDKRW |
| `current_total_usd` | 실시간 총평가금액 (달러) | (국내주식 평가액 + 현금KRW) ÷ USDKRW + 해외주식 평가액(USD) + 현금USD |
| `usdkrw` | 적용 환율 | Spring API 실시간 조회 |

> `portfolio_snapshots.total_value`는 일별 스냅샷이므로 당일 실시간값이 아닙니다.
> 실시간 총평가금액은 Spring API 시세와 환율을 조합해 직접 계산합니다.

---

### 국내/해외 자산 분리

| 키 | 설명 |
|----|------|
| `domestic_value` | 국내주식 실시간 평가액 (KRW, 현재가 × 수량) |
| `domestic_cost` | 국내주식 매수금액 (평균매수가 × 수량) |
| `overseas_value_usd` | 해외주식 실시간 평가액 (USD) |
| `overseas_value_krw` | 해외주식 실시간 평가액 (KRW 환산, USD × USDKRW) |
| `overseas_cost` | 해외주식 매수금액 |
| `cash_krw` | 보유 원화 현금 |
| `cash_usd` | 보유 달러 현금 |

---

### 기간별 수익률

스냅샷의 `total_value`를 기준 시점과 비교해 계산합니다.

| 키 | 기준 시점 | 계산식 |
|----|----------|-------|
| `yesterday_total` | 전일 스냅샷 | - |
| `daily_return` | 전일 대비 | 스냅샷의 `daily_return` 컬럼 직접 사용 |
| `return_1m` | 30일 전 스냅샷 | (오늘 total_value - 30일전 total_value) / 30일전 × 100 |
| `return_3m` | 90일 전 스냅샷 | (오늘 total_value - 90일전 total_value) / 90일전 × 100 |
| `return_6m` | 180일 전 스냅샷 | (오늘 total_value - 180일전 total_value) / 180일전 × 100 |

> 기준 시점 스냅샷이 없을 경우 해당 수익률은 0으로 반환됩니다.

---

### 손익

| 키 | 설명 | 계산 방식 |
|----|------|----------|
| `unrealized_pnl` | 미실현손익 (보유 중 종목) | (현재가 - 평균매수가) × 수량, 종목별 합산 |
| `realized_pnl` | 실현손익 (매도 완료 종목) | `executions`의 매도 체결 `net_amount` 전체 합산 |

> `net_amount`는 수수료와 세금이 차감된 순 금액입니다.

---

### 섹터/종목 집중도

**실시간 평가액 기준**으로 계산합니다. (매수금액 기준이 아님)

| 키 | 설명 |
|----|------|
| `sector_concentration` | 섹터별 비중 리스트 `[{"sector": "반도체", "weight": 42.1}, ...]` |
| `stock_concentration` | 종목별 비중 리스트 `[{"stock": "삼성전자", "weight": 35.2}, ...]` |
| `domestic_ratio` | 국내주식 비중 (%) — 매수금액 기준 |
| `foreign_ratio` | 해외주식 비중 (%) — 매수금액 기준 |

> 섹터/종목 집중도: `현재가 × 수량 (KRW 환산)` / 전체 보유주식 평가액 합계 × 100
> 해외주식은 `현재가(USD) × 수량 × USDKRW`로 KRW 환산 후 집계합니다.
> `domestic_ratio` / `foreign_ratio`는 매수금액 기준으로, 실제 투자 의도 비중을 나타냅니다.

---

### 리스크 지표

| 키 | 설명 | 계산 방식 |
|----|------|----------|
| `mdd` | 최대 낙폭 (Maximum Drawdown, %) | 누적 최고점 대비 최저점의 하락률. `MIN((total_value - peak) / peak × 100)` |
| `recovery_needed` | MDD 회복 필요 수익률 (%) | `|MDD| / (100 - |MDD|) × 100` |
| `volatility` | 변동성 | 최근 30일 `daily_return`의 표준편차 (`STDDEV`) |

**MDD 예시:**
- 포트폴리오 최고점 10,000,000원 → 최저점 9,170,000원이면 MDD = -8.3%
- 이 경우 회복 필요 수익률 = 8.3 / (100 - 8.3) × 100 ≈ **9.05%**

**MDD 계산 SQL 원리:**
```sql
MAX(total_value) OVER (ORDER BY snapshot_date ROWS UNBOUNDED PRECEDING)
```
날짜 순으로 누적 최고점을 구한 뒤, `(현재값 - 누적최고점) / 누적최고점 × 100` 중 최솟값이 MDD입니다.

---

### 종목별 최고/최저 수익 종목

| 키 | 설명 | 계산 방식 |
|----|------|----------|
| `best_stock` | 수익률 최고 종목 | `{"name": "삼성전자", "return": 18.2}` |
| `worst_stock` | 수익률 최저 종목 | `{"name": "NAVER", "return": -3.1}` |

> **현재가 기반 수익률** = (현재가 - 평균매수가) / 평균매수가 × 100
> Spring API에서 실시간 현재가를 조회해 계산하므로 실시간 기준입니다.
> 보유 중인 종목만 대상이며, 이미 매도한 종목은 포함되지 않습니다.

---

### 거래 통계

| 키 | 설명 |
|----|------|
| `total_trades` | 전체 체결 건수 |
| `buy_count` | 매수 체결 건수 |
| `sell_count` | 매도 체결 건수 |
| `win_count` | 수익 매도 건수 (`net_amount > 0`) |
| `loss_count` | 손실 매도 건수 (`net_amount < 0`) |
| `avg_win` | 수익 매도 평균 금액 |
| `avg_loss` | 손실 매도 평균 금액 |
| `profit_factor` | 손익비 = `avg_win / |avg_loss|` |

**profit_factor 해석:**
- `> 1.0` : 평균 수익이 평균 손실보다 큼 (유리한 구조)
- `= 1.0` : 수익과 손실이 동일
- `< 1.0` : 평균 손실이 평균 수익보다 큼 (불리한 구조)

---

## 실시간 vs 스냅샷 기준 정리

| 지표 | 기준 | 이유 |
|------|------|------|
| 총평가금액 | 실시간 (Spring API) | 현재 자산 파악이 목적 |
| 국내/해외 평가액 | 실시간 (Spring API) | 현재 자산 파악이 목적 |
| 섹터/종목 집중도 | 실시간 (Spring API) | 현재 포트폴리오 구성 반영 |
| 미실현손익 | 실시간 (Spring API) | 현재 손익 파악이 목적 |
| 기간별 수익률 | 스냅샷 | 일별 종가 기준 수익률이 표준 |
| MDD | 스냅샷 | 일별 종가 기준 낙폭 계산이 표준 |
| 변동성 | 스냅샷 | 30일 일별 수익률 표준편차 |
| 실현손익 | DB (executions) | 체결 완료 데이터 |
| 거래 통계 | DB (executions) | 체결 완료 데이터 |
