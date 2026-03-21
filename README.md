# 투자 챗봇 (Investment Chatbot)

개인 투자 계좌와 연동된 AI 기반 투자 어시스턴트입니다.
사용자가 자연어로 질문하면 LLM이 적절한 도구를 선택하고, 실시간 데이터를 조회해 포맷된 응답을 반환합니다.

---

## 기술 스택

| 분류        | 기술                                         |
|-------------|----------------------------------------------|
| API 서버    | FastAPI                                      |
| LLM         | Ollama (llama3.1:8b) — tool calling          |
| 계좌 DB     | Oracle DB (`oracledb`)                       |
| 뉴스 DB     | MongoDB (`sollite.news` 컬렉션)              |
| 시장 데이터 | Spring API (`localhost:8080`) / LS증권 API   |
| 인증        | JWT (HTTPBearer)                             |

---

## 아키텍처

```
사용자 메시지
      │
      ▼
POST /chat  (FastAPI)
      │  JWT → user_context { user_id, account_id }
      ▼
chat(message, user_context)  (services/llm.py)
      │
      ▼
Ollama /api/chat  ──► LLM이 tool_calls 결정
      │
      ▼
_dispatch(tool_name, fn_args, user_context)
      │
      ├── get_market_summary  → MongoDB
      ├── get_db_data         → Oracle DB + Spring API
      ├── get_market_data     → Spring API / LS증권 API
      └── execute_order       → LS증권 API (매수/매도/환전)
      │
      ▼
_TEMPLATE_DISPATCH[(tool_name, type)]
      │
      ├── 템플릿 있음 → 포맷된 문자열 즉시 반환 (LLM 재호출 없음)
      └── 템플릿 없음 → tool 결과를 LLM에 전달 → 자연어 응답 생성
      │
      ▼
{ "reply": "..." }  (ChatResponse)
```

> **핵심 설계**: `user_id` / `account_id`는 LLM 스키마에 노출하지 않고 코드가 직접 주입합니다.
> `get_market_summary`, `get_market_data`는 공용 데이터이므로 user_context 불필요.

---

## 프로젝트 구조

```
MidProject/
├── app/
│   ├── main.py                    # FastAPI 앱, /chat 엔드포인트, JWT 파싱
│   ├── core/
│   │   └── config.py              # 환경변수 로드
│   ├── db/
│   │   ├── oracle.py              # Oracle 연결 (fetch_one / fetch_all / execute)
│   │   └── mongo.py               # MongoDB 연결 (get_sollite_news_collection)
│   ├── services/
│   │   └── llm.py                 # Ollama tool calling 루프, 템플릿 디스패치
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── get_market_summary.py  # 한국/미국 시황, 종목 뉴스 (MongoDB)
│   │   ├── get_db_data.py         # 잔고/거래내역/포트폴리오 (Oracle + Spring API)
│   │   ├── get_market_data.py     # 시세/차트/랭킹/지수/환율 (Spring API)
│   │   └── execute_order.py       # 매수/매도/환전 주문 (mock → LS증권 API)
│   └── templates/
│       ├── account.py             # format_balance  — 잔고
│       ├── trades.py              # format_trades   — 거래내역
│       ├── portfolio.py           # format_portfolio — 포트폴리오 분석
│       ├── market.py              # format_korea_summary / format_us_summary / format_stock_news
│       ├── order.py               # (미구현) 주문 결과 템플릿
│       └── guide.py               # (미구현) 안내 메시지 템플릿
├── portfolio.md                   # _query_portfolio 상세 설계 문서
├── progress.md                    # 개발 진행상황
├── .env                           # 환경변수
├── .gitignore
└── requirements.txt
```

---

## 도구 (Tools)

LLM이 사용자 의도에 맞게 아래 4개 도구 중 하나를 선택해 호출합니다.

### 1. `get_market_summary` — 시황 및 종목 뉴스

| type         | 설명                              | 데이터 소스  |
|--------------|-----------------------------------|--------------|
| `korea`      | 한국 시황 (KOSDAQ 기준)           | MongoDB      |
| `us`         | 미국 시황 (NASDAQ 기준)           | MongoDB      |
| `stock_news` | 종목별 뉴스 요약 (최근 3건)       | MongoDB      |

```python
get_market_summary(type="stock_news", stock_code="005930")
```

### 2. `get_db_data` — 계좌 데이터 조회

| type        | 설명                              | 데이터 소스              |
|-------------|-----------------------------------|--------------------------|
| `balance`   | KRW/USD 잔고, 주문/출금 가능 금액 | Oracle (`cash_balances`) |
| `trades`    | 매수/매도 건수 + 최근 체결 내역   | Oracle (`executions`)    |
| `portfolio` | 수익률·집중도·리스크 분석 리포트  | Oracle + Spring API      |

**portfolio 분석 항목:**

| 영역   | 주요 지표                                             |
|--------|-------------------------------------------------------|
| 수익률 | 평가손익, 실현손익, 1M/3M/6M 수익률, 최고/최저 종목  |
| 집중도 | 섹터별·종목별 비중, 국내/해외 비율                    |
| 리스크 | MDD, 회복 필요 수익률, 변동성, 거래통계, 손익비       |

> 자세한 계산 방식은 [portfolio.md](./portfolio.md) 참고

### 3. `get_market_data` — 실시간 시장 데이터

| type           | 설명                              | 상태             |
|----------------|-----------------------------------|------------------|
| `price`        | 현재가, 등락, 거래량              | Spring API 연동  |
| `chart`        | 분봉 차트                         | Spring API 연동  |
| `daily`        | 당일 고/저/시/종가                | Spring API 연동  |
| `period_chart` | 기간별 차트 (일/주/월)            | Spring API 연동  |
| `exchange`     | 환율 (USDKRW, EURKRW)            | Spring API 연동  |
| `ranking`      | 거래량/등락률/외국인 순매수 랭킹  | mock (연동 예정) |
| `index`        | KOSPI / NASDAQ 지수               | mock (연동 예정) |

### 4. `execute_order` — 주문 실행

| type       | 설명                      | 상태             |
|------------|---------------------------|------------------|
| `buy`      | 주식 매수 (시장가/지정가) | mock (연동 예정) |
| `sell`     | 주식 매도                 | mock (연동 예정) |
| `exchange` | 환전                      | mock (연동 예정) |

---

## 응답 템플릿

LLM이 텍스트를 직접 생성하는 대신, 코드가 포맷된 문자열을 만들어 채팅 응답으로 반환합니다.
`_TEMPLATE_DISPATCH[(tool_name, type)]`에 등록된 경우 LLM 재호출 없이 즉시 응답합니다.

**포트폴리오 분석 예시:**
```
포트폴리오 분석 리포트
────────────────────────
수익률
  평가손익   +1,250,000원
  실현손익   +320,000원
  1개월 +3.2%   3개월 +8.7%   6개월 +12.4%
  최고  삼성전자  +18.2%
  최저  NAVER  -3.1%
────────────────────────
집중도
  국내 72.0%   해외 28.0%
  섹터
    반도체      42.1%
    2차전지     28.3%
  종목
    삼성전자    35.2%
    SK하이닉스  18.9%
────────────────────────
리스크
  최대 낙폭    -8.3%
  회복 필요    +9.05%
  일간 변동폭  1.24%
  거래 47회   수익 28회 / 손실 19회
  평균 수익  +182,000원
  평균 손실  -95,000원
  손익비     1.91배
────────────────────────
```

**종목 뉴스 예시:**
```
삼성전자 종목 뉴스
────────────────────────
1. 기사제목: 삼성전자, 2분기 실적 가이던스 상향  (2026년 03월 21일)
   요약: HBM 수요 증가로 반도체 부문 이익률 개선 전망

2. 기사제목: 삼성전자 파운드리 수주 확대  (2026년 03월 19일)
   요약: TSMC 대비 가격 경쟁력으로 고객사 확대 중

────────────────────────
```

---

## 설치 및 실행

### 환경변수 설정 (`.env`)

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b

ORACLE_DSN=<host>:<port>/<service>
ORACLE_USER=<user>
ORACLE_PASSWORD=<password>

MONGO_URI=mongodb://localhost:27017
MONGO_DB=sollite

REDIS_HOST=localhost
REDIS_PORT=6379

SPRING_BASE_URL=http://localhost:8080
```

### 실행

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### API 호출

```bash
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer <JWT>" \
  -H "Content-Type: application/json" \
  -d '{"message": "내 포트폴리오 분석해줘"}'
```

**응답:**
```json
{ "reply": "포트폴리오 분석 리포트\n────────..." }
```

---

## 사용 예시

| 사용자 입력               | LLM 선택 도구                          | 응답 방식        |
|---------------------------|----------------------------------------|------------------|
| "내 잔고 알려줘"          | `get_db_data(type=balance)`            | 템플릿 즉시 반환 |
| "최근 거래내역 보여줘"    | `get_db_data(type=trades)`             | 템플릿 즉시 반환 |
| "포트폴리오 분석해줘"     | `get_db_data(type=portfolio)`          | 템플릿 즉시 반환 |
| "오늘 한국 증시 어때?"    | `get_market_summary(type=korea)`       | 템플릿 즉시 반환 |
| "미국 장 어떻게 됐어?"    | `get_market_summary(type=us)`          | 템플릿 즉시 반환 |
| "삼성전자 뉴스 알려줘"    | `get_market_summary(type=stock_news)`  | 템플릿 즉시 반환 |
| "삼성전자 현재가 얼마야?" | `get_market_data(type=price)`          | LLM 자연어 응답  |
| "삼성전자 10주 매수해줘"  | `execute_order(type=buy)`              | LLM 자연어 응답  |
