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
│   │                                  # 모호한 follow-up 감지 + 맥락 기반 intent 재분류
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
│   │   ├── router.py                  # 키워드 기반 의도 감지 + follow-up 대명사 감지
│   │   ├── dispatcher.py              # 의도 → 도구 호출 → 템플릿 포맷
│   │   └── resolver.py                # 종목명 → 종목코드 변환 (CSV 캐싱)
│   │
│   ├── agent/                         # 단일 LLM 에이전트
│   │   └── llm_agent.py               # ReAct 에이전트 (5개 도구, 대화 기록, 맥락 보강)
│   │
│   ├── data/                          # 외부 데이터 조회
│   │   ├── market.py                  # 시세·차트·순위·지수·환율 (Spring API)
│   │   ├── news.py                    # 한국/미국 시황, 종목 뉴스 (MongoDB)
│   │   ├── account.py                 # 잔고 조회 (Spring API)
│   │   ├── portfolio.py               # 포트폴리오 분석 (Oracle DB + Spring API)
│   │   └── trades.py                  # 거래내역 조회 (Oracle DB)
│   │
│   └── templates/                     # 응답 포맷 함수 모음
│       ├── index.py                   # format_index()
│       ├── exchange_rate.py           # format_exchange_rate()
│       ├── ranking.py                 # format_ranking()
│       ├── chart_price.py             # format_chart_price()
│       ├── account.py                 # format_balance(balance_type)
│       ├── stock_news.py              # format_korea_summary() / format_us_summary() / format_stock_news() / format_holdings_news()
│       ├── order.py                   # format_order()
│       ├── trades.py                  # format_trades() / format_trades_by_date()
│       ├── portfolio.py               # format_portfolio() / format_portfolio_analysis(metric_type)
│       └── guide.py                   # _GUIDE_MESSAGE / _FALLBACK_MESSAGE
│
├── test_scenarios.md                  # 챗봇 기능별 테스트 시나리오
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
      │  → follow-up 감지: 모호한 질문 + 직전 포트폴리오 tool → intent = unknown
      │  → 종목 미지정 시세/뉴스 질문 → intent = unknown (agent로 위임)
      ▼
router.detect(message)
      │  키워드 패턴 매칭 → intent, params 반환
      │  대명사("그 종목", "아까" 등) 감지 시 → unknown 반환
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
      ├── trades          → 단순 조회 → format_trades()
      │                     날짜 조회 → format_trades_by_date()
      │                     매수/매도 비교 → 직접 계산 (환각 방지)
      │                     세부 질문 → LLM 에이전트
      ├── portfolio       → 단순 조회 → format_portfolio()
      │                     보유 종목 뉴스 → 전용 핸들러 (rule-based)
      │                     지표별 질문 → format_portfolio_analysis(metric_type)
      │                     크로스도메인 질문 → LLM 에이전트
      └── unknown         → 섹터 키워드 감지 시 안내 / LLM 에이전트
      │
      ▼
MongoDB에 턴 단위 저장
  { messages: [user, tool_calls, tool_result, assistant] }
  (템플릿 응답은 "조회한 데이터를 보여드렸어요."로 단축 저장 — LLM 템플릿 모방 방지)
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
| 종목 미지정 시 | intent = unknown → LLM 에이전트 (이전 맥락에서 종목 추출)                   |

---

### (5) 잔고 조회

| 항목          | 내용                                           |
| ------------- | ---------------------------------------------- |
| 트리거 키워드 | 잔고, 잔액, 예수금, 총 자산, 현금, 내 계좌     |
| 데이터 소스   | Spring API `GET /api/balance/summary`          |
| 파라미터      | balance_type: total_assets / cash / summary    |
| 응답 포맷     | `format_balance(balance_type)`                 |

---

### (6) 매수·매도 버튼 연동

| 항목        | 내용                                                  |
| ----------- | ----------------------------------------------------- |
| 매수 트리거 | 매수, 사고 싶어, 살게, 구매 (단, "매수가/매수는" 등 조사 붙은 경우 제외) |
| 매도 트리거 | 매도, 팔고 싶어, 팔게, 판매 (단, "매도가/매도는" 등 조사 붙은 경우 제외) |
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
| 종목 미지정 시 | intent = unknown → LLM 에이전트 (이전 맥락에서 종목 추출) |

섹터 키워드 (`_SECTOR_KEYWORDS`): 바이오, 반도체, 제약, 화학, 자동차, IT, 금융, 에너지, 헬스케어, 게임, 엔터, 식품, 건설, 철강, 전기차, 배터리, 2차전지, 항공, 조선, 보험, 은행, 유통, 통신, 방산

---

### (11) 거래내역 조회 — AI agent

| 항목              | 내용                                                   |
| ----------------- | ------------------------------------------------------ |
| 트리거 키워드     | 거래내역, 매매 내역, 체결 내역, 최근 거래              |
| 단순 조회         | `format_trades()` / `format_trades_by_date()` 직접 반환 |
| 매수/매도 비교    | 직접 계산 후 반환 (LLM 비교 환각 방지)                 |
| 세부 질문         | LLM 에이전트 → `get_trade_history` 도구 호출           |

---

### (12) 포트폴리오 분석 — AI agent

| 항목              | 내용                                                |
| ----------------- | --------------------------------------------------- |
| 트리거 키워드     | 포트폴리오, 포폴, 수익률, 손익, 보유 종목           |
| 단순 조회         | `format_portfolio()` 직접 반환                      |
| 보유 종목 뉴스    | 전용 rule-based 핸들러 (보유 종목별 뉴스 1건씩)     |
| 지표별 질문       | `format_portfolio_analysis(metric_type)` — 수익률/섹터/리스크/거래통계 포커스 뷰 |
| 세부/복합 질문    | LLM 에이전트 → `get_portfolio_info` 도구 호출       |

지표 타입 (`metric_type`):

| 키워드 예시                    | metric_type |
| ------------------------------ | ----------- |
| 수익률, 1개월, 6개월           | `returns`   |
| 섹터, 업종, 비중, 국내/해외    | `sector`    |
| 리스크, MDD, 변동성, 낙폭      | `risk`      |
| 승률, 손익비, 거래 통계        | `stats`     |
| 보유 종목, 종목 수             | `holdings`  |

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

### LLM 숫자 환각 방지

tool 결과를 LLM에 전달하기 전에 raw 숫자를 포맷된 문자열로 변환합니다.

| 도구                              | 변환 내용                                              |
| --------------------------------- | ------------------------------------------------------ |
| `get_stock_price`                 | `current_price: 922000` → `"922,000원"` 등 문자열화   |
| `get_portfolio_info` (holdings)   | `return_rate: -0.003` → `"-0.49%"` 등 포맷            |
| `get_portfolio_info` (returns)    | 수익률·MDD → `"+3.2%"` 형식                            |
| `get_portfolio_info` (risk)       | 손익·MDD → 포맷된 문자열                               |
| `get_trade_history` (by_stock)    | 거래 목록 → `"2026-03-27 매도 1주 @ 179,700원"` 형식  |
| `get_trade_history` (recent)      | 매수/매도 비교 결과 → `"매수(5건)가 매도(1건)보다 많습니다."` |

### 대화 맥락 처리 (맥락 보강)

에이전트 호출 전 `_enrich_with_context()`가 메시지를 보강합니다.

| 입력 패턴                     | 변환 결과                          | 처리 방식                     |
| ----------------------------- | ---------------------------------- | ----------------------------- |
| `"그 종목 현재가"`            | `"현대차 현재가"`                  | 대명사 → 직전 종목명 치환     |
| `"현재가 어때"` (종목 없음)   | `"현대차 현재가 어때"`             | 직전 언급 종목 주입            |
| `"하닉은?"`                   | `"하닉 뉴스"` 또는 `"하닉 현재가"` | 직전 도구 타입 주입            |

직전 종목 추출 우선순위:
1. 최근 `get_stock_price` / `get_stock_news` tool_call 인자
2. 최근 `get_trade_history(by_stock)` tool_call 인자
3. 최근 assistant 텍스트 첫 줄에서 종목명 파싱

MongoDB 히스토리는 최근 6턴만 로드해 이전 세션 오염을 방지합니다.

---

## MongoDB 채팅 기록 구조

한 턴의 모든 메시지를 단일 document로 저장합니다.

```json
{
  "account_id": "1",
  "timestamp": "2026-03-30T...",
  "messages": [
    {"role": "user",      "content": "삼성전자 뉴스"},
    {"role": "assistant", "tool_calls": [{"function": {"name": "get_stock_news", "arguments": {"stock_code": "005930"}}}]},
    {"role": "tool",      "name": "get_stock_news", "content": "{...}"},
    {"role": "assistant", "content": "삼성전자 최신 뉴스입니다..."}
  ]
}
```

> 템플릿 경로(단순 조회) 응답은 `"조회한 데이터를 보여드렸어요."`로 단축 저장합니다.
> LLM이 긴 마크다운 템플릿 형식을 모방하는 것을 방지하기 위함입니다.

---

## 프론트엔드 위젯 연동 검색어

채팅 입력창에서 아래 키워드를 입력하면 해당 위젯이 활성화됩니다.

| 위젯 | 검색어 예시 |
| ---- | ----------- |
| 계좌 잔고 | 잔고, 계좌, 자산, 평가자산, 내계좌, 예수금, 투자자산, 계좌현황 |
| 환율 | 환율, 달러, 엔, 유로, usd, jpy, eur, 원달러, 환전, 외화, 파운드, 위안 |
| 실시간 순위 | 순위, 랭킹, 거래대금, 상승률, 거래량, 급등, 상한가, 인기종목, 하락률 |
| 주요 지수 | 지수, 코스피, 코스닥, 나스닥, kospi, kosdaq, nasdaq, 다우, s&p, 에센피, 뉴욕, 증시 |
| 오늘의 시황 | 시황, 시장, 헤드라인, 뉴스, 증시뉴스, 장세, 오늘증시, 코스피, 코스닥, 나스닥, 에센피, s&p, nasdaq, kospi, kosdaq, 다우, 뉴욕 |
| 포트폴리오 | 포트폴리오, 포트, 비중, 보유종목, 보유주식, 내주식, 수익률, 손익, 평가손익, 자산배분 |
| 관심종목 | 관심, 관심종목, 즐겨찾기, 찜, 위시 |
| 거래내역 | 거래내역, 매매, 주문내역, 체결, 내역, 거래기록, 주문, 체결내역, 매수내역, 매도내역 |
| 주가/차트 (종목명 자동) | 삼성전자, SK하이닉스 등 종목명 검색 → `{종목명} 주가` |
| 종목별 뉴스 (종목명 자동) | 위와 동일 → `{종목명} 뉴스` |

---

## 의도 감지 우선순위 (router)

```
1.  greeting       (인사 / 도움말)
2.  buy_intent     (매수 — "매수가/매수는" 등 조사 붙은 경우 제외)
3.  sell_intent    (매도 — "매도가/매도는" 등 조사 붙은 경우 제외)
4.  exchange_order (환전 주문)
5.  balance        (잔고)
6.  portfolio      (포트폴리오 — 보유종목+뉴스 복합 패턴 우선)
7.  stock_news     (종목 뉴스)
8.  korea_summary  (한국 시황)
9.  us_summary     (미국 시황)
10. market_summary (통합 시황)
11. index          (지수)
12. chart_price    (시세·차트)
13. ranking        (주식 순위)
14. exchange_rate  (환율)
15. trades         (거래내역)
```

> follow-up 대명사("그 종목", "아까", "방금" 등) 감지 시 intent = unknown으로 직행합니다.

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
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000  
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
