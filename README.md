# 투자 챗봇 (Investment Chatbot)

개인 투자 계좌와 연동된 챗봇입니다.
룰 베이스 라우터가 의도를 감지하고, 단순 조회는 템플릿으로 응답하며 복잡한 자연어 질문은 단일 LLM 에이전트가 처리합니다.

---

## 기술 스택

| 분류        | 기술                                          |
| ----------- | --------------------------------------------- |
| API 서버    | FastAPI                                       |
| AI agent    | Ollama (`llama3.1:8b`) — 5개 도구 단일 에이전트 |
| 계좌 DB     | Oracle DB (`oracledb`)                        |
| 뉴스 DB     | MongoDB Atlas (`sollite` DB)                  |
| 채팅 기록   | MongoDB Atlas (`sollite.chat_history`)        |
| 시장 데이터 | Spring API (`localhost:8080`)                 |
| 인증        | JWT (HTTPBearer, HS384)                       |

---

## 폴더 구조

```
AI/
├── app/
│   ├── main.py                        # FastAPI 앱, POST /chat 엔드포인트
│   │
│   ├── core/
│   │   ├── auth.py                    # JWT 검증, user_context 추출
│   │   └── config.py                  # 환경변수 로드 (.env)
│   │
│   ├── db/
│   │   ├── oracle.py                  # Oracle 연결 (fetch_one / fetch_all / resolve_stock_code)
│   │   └── mongo.py                   # MongoDB 연결 + 채팅 기록 턴 기반 저장
│   │
│   ├── chatbot/                       # 룰 베이스 라우터
│   │   ├── rule_router.py             # 키워드 기반 의도 감지 + 파라미터 추출
│   │   ├── dispatcher.py              # 의도 → 도구 호출 → 템플릿 포맷
│   │   └── stock_resolver.py          # 종목명 → 종목코드 변환 (CSV 캐싱)
│   │
│   ├── agent/                         # 단일 LLM 에이전트
│   │   ├── trade_tools.py             # 거래내역 조회 도구 (Oracle DB)
│   │   ├── portfolio_tools.py         # 포트폴리오 분석 도구 (Oracle DB + Spring API)
│   │   └── llm_agent.py               # 단일 에이전트 (5개 도구, 대화 기록 포함)
│   │
│   ├── hardcoding/                    # 외부 API 조회
│   │   ├── get_market_data.py         # 시세·차트·순위·지수·환율 (Spring API)
│   │   ├── get_market_summary.py      # 한국/미국 시황, 종목 뉴스 (MongoDB)
│   │   ├── get_balance_data.py        # 잔고 조회 (Spring API)
│   │   └── execute_order.py           # 매수·매도·환전 주문 (Spring API)
│   │
│   └── templates/                     # 응답 포맷 함수 모음
│       ├── index.py                   # format_index()
│       ├── exchange_rate.py           # format_exchange_rate()
│       ├── ranking.py                 # format_ranking()
│       ├── chart_price.py             # format_chart_price()
│       ├── account.py                 # format_balance(balance_type)
│       ├── stock_news.py              # format_korea_summary() / format_us_summary() / format_stock_news()
│       ├── order.py                   # format_order()
│       ├── trades.py                  # format_trades() / format_trades_by_date()
│       ├── portfolio.py               # format_portfolio()
│       └── guide.py                   # _GUIDE_MESSAGE / _FALLBACK_MESSAGE
│
├── .env
├── .gitignore
├── requirements.txt
└── README.md
```

---

## 전체 처리 흐름

```
사용자 메시지
      │
      ▼
POST /chat  (main.py)
      │  Authorization: Bearer <JWT>
      │  → get_user_context() : user_id, account_id 추출
      ▼
rule_router.detect(message)
      │  키워드 패턴 매칭 → intent, params 반환
      ▼
dispatcher.dispatch(intent, params, user_context, message)
      │
      ├── greeting        → _GUIDE_MESSAGE (서비스 안내)
      ├── index           → get_market_data("index")           → format_index()
      ├── exchange_rate   → get_market_data("exchange")        → format_exchange_rate()
      ├── ranking         → get_market_data("ranking")         → format_ranking()
      ├── chart_price     → get_market_data("price")           → format_chart_price()
      ├── balance         → get_db_data("balance")             → format_balance(balance_type)
      ├── buy_intent      → type: "order", stock_code 반환
      ├── sell_intent     → type: "order", stock_code 반환
      ├── exchange_order  → type: "exchange"
      ├── korea_summary   → get_market_summary("korea")        → format_korea_summary()
      ├── us_summary      → get_market_summary("us")           → format_us_summary()
      ├── market_summary  → korea + us 동시 조회 → 통합 응답
      ├── stock_news      → 섹터 키워드 감지 시 안내 / get_market_summary("stock_news")
      ├── trades          → 단순 조회 → format_trades() / 세부 질문 → LLM 에이전트
      ├── portfolio       → 단순 조회 → format_portfolio() / 세부 질문 → LLM 에이전트
      └── unknown         → 섹터 키워드 감지 시 안내 / LLM 에이전트
      │
      ▼
MongoDB에 턴 단위 저장
  { messages: [user, tool_calls, tool_result, assistant] }
      │
      ▼
ChatResponse { type, reply, stock_code }
```

---

## 기능별 상세

### 인사 / 도움말

| 항목          | 내용                                         |
| ------------- | -------------------------------------------- |
| 트리거 키워드 | 안녕, hi, hello, 뭐 할 수 있어, 도움말, 기능 |
| 응답          | 서비스 목록 안내 (`_GUIDE_MESSAGE`)          |

---

### (1) 지수 조회

| 항목          | 내용                                                  |
| ------------- | ----------------------------------------------------- |
| 트리거 키워드 | 지수, 코스피, 코스닥, 나스닥, S&P, 다우, 닛케이, 항셍 |
| 데이터 소스   | Spring API `GET /api/market/indices`                  |
| 응답 포맷     | `format_index()`                                      |

---

### (2) 환율 조회

| 항목          | 내용                                                  |
| ------------- | ----------------------------------------------------- |
| 트리거 키워드 | 환율, 달러, 원달러, 유로, 엔화, 파운드                |
| 데이터 소스   | Spring API `GET /api/market/exchange`                 |
| 파라미터      | currency_pair: USDKRW / EURKRW / JPYKRW / GBPKRW     |
| 응답 포맷     | `format_exchange_rate()` — 통화별 이모지, 1000원 역환율, 엔화는 100엔 기준 |

---

### (3) 주식 순위 조회

| 항목          | 내용                                                          |
| ------------- | ------------------------------------------------------------- |
| 트리거 키워드 | 순위, 랭킹, 상승주, 하락주, 많이 오른, 많이 내린, 거래량 순  |
| 데이터 소스   | Spring API `GET /api/market/stocks/ranking`                   |
| 파라미터      | ranking_type: trading-value(기본) / trading-volume / rising / falling / market-cap |
| 응답 포맷     | `format_ranking()`                                            |

ranking_type 키워드 매핑:

| 키워드                         | ranking_type     |
| ------------------------------ | ---------------- |
| 거래대금                       | `trading-value`  |
| 거래량                         | `trading-volume` |
| 상승, 많이 오른, 급등, 올랐    | `rising`         |
| 하락, 많이 내린, 급락, 떨어졌  | `falling`        |
| 시가총액, 시총                 | `market-cap`     |

---

### (4) 차트+시세 조회

| 항목          | 내용                                                                          |
| ------------- | ----------------------------------------------------------------------------- |
| 트리거 키워드 | 차트, 시세, 주가, 현재가, 얼마야 + (종목명/코드)                              |
| 데이터 소스   | Spring API `GET /api/market/stocks/{code}/price`                              |
| 파라미터      | stock_code (6자리 → 국내, 영문 대문자 → 미국, 한글 → CSV 종목명 매칭)        |
| 응답 포맷     | `format_chart_price()`                                                        |

---

### (5) 잔고 조회

| 항목          | 내용                                           |
| ------------- | ---------------------------------------------- |
| 트리거 키워드 | 잔고, 잔액, 예수금, 총 자산, 현금, 내 계좌     |
| 데이터 소스   | Spring API `GET /api/balance/summary`          |
| 파라미터      | balance_type: total_assets / cash / summary    |
| 응답 포맷     | `format_balance(balance_type)`                 |

balance_type 분기:

| 질문 예시          | balance_type    | 응답              |
| ------------------ | --------------- | ----------------- |
| "총 자산 얼마야"   | `total_assets`  | 총 자산만 표시    |
| "현금 잔고"        | `cash`          | 현금 잔고만 표시  |
| "내 계좌", "잔액"  | `summary`       | 총 자산 + 현금    |

---

### (6) 매수·매도 버튼 연동

| 항목        | 내용                                                  |
| ----------- | ----------------------------------------------------- |
| 매수 트리거 | 매수, 사고 싶어, 살게, 구매                           |
| 매도 트리거 | 매도, 팔고 싶어, 팔게, 판매                           |
| 동작        | `type: "order"` + `stock_code` 로 프론트엔드에 전달  |

응답 예시:

```json
{
  "type": "order",
  "reply": "**삼성전자** 주문 정보를 입력하세요:",
  "stock_code": "005930"
}
```

---

### (7) 환전 버튼 연동

| 항목          | 내용                                          |
| ------------- | --------------------------------------------- |
| 트리거 키워드 | 환전해줘, 달러로 바꿔, 원화로 바꿔            |
| 동작          | `type: "exchange"` 로 프론트엔드 환전 화면 활성화 |

---

### (8) 한국 시황 / (9) 미국 시황 / (8-2) 통합 시황

| 의도             | 트리거 예시                        | 응답              |
| ---------------- | ---------------------------------- | ----------------- |
| `korea_summary`  | 한국 시황, 국내 시황, 국장         | 한국 시황만       |
| `us_summary`     | 미국 시황, 미장, 나스닥 시황       | 미국 시황만       |
| `market_summary` | 시황, 오늘 장 어때, 장 상황        | 한국 + 미국 통합  |

> 범용 키워드("시황", "장 어때")는 `market_summary`로 처리되어 두 시장 모두 표시됩니다.

---

### (10) 종목별 뉴스 요약

| 항목          | 내용                                              |
| ------------- | ------------------------------------------------- |
| 트리거 키워드 | 뉴스, 기사, 소식 + 종목명                         |
| 데이터 소스   | MongoDB `sollite.stock_news`                      |
| 섹터 감지     | 바이오/반도체 등 섹터 키워드 → 안내 메시지 반환  |

섹터 키워드 (`_SECTOR_KEYWORDS`): 바이오, 반도체, 제약, 화학, 자동차, IT, 금융, 에너지, 헬스케어, 게임, 엔터, 식품, 건설, 철강, 전기차, 배터리, 2차전지, 항공, 조선, 보험, 은행, 유통, 통신, 방산

---

### (11) 거래내역 조회 — AI agent

| 항목          | 내용                                                   |
| ------------- | ------------------------------------------------------ |
| 트리거 키워드 | 거래내역, 매매 내역, 체결 내역, 최근 거래              |
| 단순 조회     | `format_trades()` / `format_trades_by_date()` 직접 반환 |
| 세부 질문     | LLM 에이전트 → `get_trade_history` 도구 호출           |

---

### (12) 포트폴리오 분석 — AI agent

| 항목          | 내용                                                |
| ------------- | --------------------------------------------------- |
| 트리거 키워드 | 포트폴리오, 포폴, 수익률, 손익, 보유 종목           |
| 단순 조회     | `format_portfolio()` 직접 반환                      |
| 세부 질문     | LLM 에이전트 → `get_portfolio_info` 도구 호출       |

---

## 단일 LLM 에이전트 (llm_agent.py)

`unknown` / `portfolio` 세부 질문 / `trades` 세부 질문이 에이전트로 라우팅됩니다.

### 도구 목록

| 도구명                | 설명                     | 주요 파라미터                                              |
| --------------------- | ------------------------ | ---------------------------------------------------------- |
| `get_stock_price`     | 종목 현재가·등락률 조회  | `stock_code`                                               |
| `get_stock_news`      | 종목 최신 뉴스 조회      | `stock_code`                                               |
| `get_market_summary`  | 한국/미국 시황 조회      | `market`: korea / us                                       |
| `get_portfolio_info`  | 포트폴리오 정보 조회     | `info_type`: holdings / sector / returns / risk / stats    |
| `get_trade_history`   | 거래내역 조회            | `query_type`: recent / by_stock / by_date                  |

### 대화 맥락 처리

- MongoDB에서 최근 20개 턴을 불러와 LLM에 전달
- 짧은 팔로업 질문 (`"하닉은?"`) 은 이전 도구를 확인해 자동 보강 (`"하닉 뉴스"`)

---

## MongoDB 채팅 기록 구조

한 턴의 모든 메시지를 단일 document로 저장합니다.

```json
{
  "account_id": "1",
  "timestamp": "2026-03-28T...",
  "messages": [
    {"role": "user",      "content": "삼성전자 뉴스"},
    {"role": "assistant", "tool_calls": [{"function": {"name": "get_stock_news", "arguments": {"stock_code": "005930"}}}]},
    {"role": "tool",      "name": "get_stock_news", "content": "{...}"},
    {"role": "assistant", "content": "삼성전자 최신 뉴스입니다..."}
  ]
}
```

---

## 의도 감지 우선순위 (rule_router)

```
1.  greeting       (인사 / 도움말)
2.  buy_intent     (매수)
3.  sell_intent    (매도)
4.  exchange_order (환전 주문)
5.  balance        (잔고)
6.  stock_news     (종목 뉴스)
7.  korea_summary  (한국 시황)
8.  us_summary     (미국 시황)
9.  market_summary (통합 시황)
10. index          (지수)
11. chart_price    (시세·차트)
12. ranking        (주식 순위)
13. exchange_rate  (환율)
14. trades         (거래내역)
15. portfolio      (포트폴리오)
```

---

## API 명세

### `POST /chat`

**Request:**

```json
{
  "message": "삼성전자 시세 알려줘"
}
```

**Headers:**

```
Authorization: Bearer <JWT>
Content-Type: application/json
```

**Response:**

```json
{
  "type": "text",
  "reply": "삼성전자 현재가는 75,400원입니다...",
  "stock_code": null
}
```

**주문 응답 (매수/매도 요청 시):**

```json
{
  "type": "order",
  "reply": "**삼성전자** 주문 정보를 입력하세요:",
  "stock_code": "005930"
}
```

**환전 응답:**

```json
{
  "type": "exchange",
  "reply": "환전 정보를 입력하세요:",
  "stock_code": null
}
```

| type 값      | 프론트엔드 동작                          |
| ------------ | ---------------------------------------- |
| `text`       | 일반 텍스트 응답                         |
| `order`      | 주문 폼 활성화, `stock_code` 자동 입력   |
| `exchange`   | 환전 화면 활성화                         |

---

## 설치 및 실행

### 환경변수 설정 (`.env`)

```env
JWT_SECRET_KEY=<secret>

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b

ORACLE_DSN=<host>:<port>/<service>
ORACLE_USER=<user>
ORACLE_PASSWORD=<password>

MONGO_URI=mongodb+srv://...
MONGO_DB=sollite

SPRING_BASE_URL=http://localhost:8080
```

### 실행

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### 호출 예시

```bash
# 지수 조회
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer <JWT>" \
  -H "Content-Type: application/json" \
  -d '{"message": "오늘 코스피 어때?"}'

# 종목 시세
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer <JWT>" \
  -H "Content-Type: application/json" \
  -d '{"message": "삼성전자 현재가 알려줘"}'

# 매수 버튼 활성화
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer <JWT>" \
  -H "Content-Type: application/json" \
  -d '{"message": "삼성전자 매수하고 싶어"}'

# 포트폴리오 세부 질문 (LLM 에이전트)
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer <JWT>" \
  -H "Content-Type: application/json" \
  -d '{"message": "내 포트폴리오에서 수익률 가장 좋은 종목은?"}'
```
