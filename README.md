# 투자 챗봇 (Investment Chatbot)

개인 투자 계좌와 연동된 챗봇입니다.
**(1)~(10)** 은 룰 베이스 챗봇이 처리하고, **(11)~(12)** 는 llama AI agent가 처리합니다.

---

## 기술 스택

| 분류        | 기술                                        |
|-------------|---------------------------------------------|
| API 서버    | FastAPI                                     |
| AI agent    | Ollama (`llama3.1:8b`) — (11), (12) 전용    |
| 계좌 DB     | Oracle DB (`oracledb`)                      |
| 뉴스 DB     | MongoDB (`sollite.news` 컬렉션)             |
| 시장 데이터 | Spring API (`localhost:8080`)               |
| 인증        | JWT (HTTPBearer, HS384)                     |

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
│   │   └── mongo.py                   # MongoDB 연결 (get_sollite_news_collection 등)
│   │
│   │
│   ├── chatbot/                       # 룰 베이스 챗봇 (1)~(10)
│   │   ├── __init__.py
│   │   ├── rule_router.py             # 키워드 기반 의도 감지 + 파라미터 추출
│   │   └── dispatcher.py             # 의도 → 도구 호출 → 템플릿 포맷
│   │
│   ├── agent/                         # AI agent (11)~(12)
│   │   ├── trade_tool.py              # 거래내역 조회 (Oracle DB)
│   │   ├── portfolio_tool.py          # 포트폴리오 분석 (Oracle DB + Spring API)
│   │   └── llm_agent.py              # llama 호출 래퍼 (ask_trades / ask_portfolio)
│   │
│   ├── hardcoding/                    # 외부 API 조회 도구
│   │   ├── get_market_data.py         # 시세·차트·순위·지수·환율 (Spring API)
│   │   ├── get_market_summary.py      # 한국/미국 시황, 종목 뉴스 (MongoDB)
│   │   ├── get_balance_data.py        # 잔고 조회 (Spring API)
│   │   └── execute_order.py           # 매수·매도·환전 주문 (Spring API)
│   │
│   └── templates/                     # 응답 포맷 함수 모음
│       ├── index.py                   # format_index()        — 지수
│       ├── exchange_rate.py           # format_exchange_rate() — 환율
│       ├── ranking.py                 # format_ranking()      — 주식 순위
│       ├── chart_price.py             # format_chart_price()  — 차트+시세
│       ├── account.py                 # format_balance()      — 잔고
│       ├── stock_news.py              # format_korea_summary() / format_us_summary() / format_stock_news()
│       ├── order.py                   # format_order()        — 주문 완료
│       ├── trades.py                  # format_trades()       — 거래내역
│       └── portfolio.py               # format_portfolio()    — 포트폴리오 분석
│
├── .env                               # 환경변수
├── .gitignore
├── requirements.txt
├── portfolio.md                       # 포트폴리오 분석 상세 설계
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
      │  → get_user_context() : user_id, account_id, token 추출
      ▼
rule_router.detect(message)
      │  키워드 패턴 매칭 → intent, params 반환
      │  예) "삼성전자 시세" → ("chart_price", {"stock_code": "삼성전자"})
      ▼
dispatcher.dispatch(intent, params, user_context, message)
      │
      ├── (1)  index          → get_market_data("index")           → format_index()
      ├── (2)  exchange_rate  → get_market_data("exchange")        → format_exchange_rate()
      ├── (3)  ranking        → get_market_data("ranking")         → format_ranking()
      ├── (4)  chart_price    → get_market_data("price")           → format_chart_price()
      ├── (5)  balance        → get_db_data("balance")             → format_balance()
      ├── (6)  buy_intent     → action: "activate_buy"
      ├── (6)  sell_intent    → action: "activate_sell"
      ├── (7)  exchange_order → action: "activate_exchange"
      ├── (8)  korea_summary  → get_market_summary("korea")        → format_korea_summary()
      ├── (9)  us_summary     → get_market_summary("us")           → format_us_summary()
      ├── (10) stock_news     → get_market_summary("stock_news")   → format_stock_news()
      ├── (11) trades         → get_trade_data()  ─┬─ 단순 조회 → format_trades()
      │                                            └─ 세부 질문 → llama (ask_trades)
      └── (12) portfolio      → get_portfolio_data() ─┬─ 단순 조회 → format_portfolio()
                                                      └─ 세부 질문 → llama (ask_portfolio)
      │
      ▼
ChatResponse
  {
    "reply":         "...",          # 채팅 응답 텍스트
    "action":        "activate_buy", # 프론트엔드 버튼 활성화 (없으면 null)
    "action_params": {"stock_code": "005930"}  # 액션 파라미터 (없으면 null)
  }
```

---

## 기능별 상세

### (1) 지수 조회

| 항목 | 내용 |
|------|------|
| 트리거 키워드 | 지수, 코스피, 코스닥, 나스닥, S&P, 다우, 닛케이, 항셍 |
| 데이터 소스 | Spring API `GET /api/market/indices` |
| 파라미터 추출 | 없음 (전체 지수 반환 후 메시지 기준 필터링) |
| 응답 포맷 | `format_index()` |

```
■ 주요 지수
────────────────────────
  KOSPI:   2,680.45  ▲12.30 (+0.46%)
  KOSDAQ:  855.12    ▲3.45  (+0.40%)
  NASDAQ:  17,245.30 ▲85.60 (+0.50%)
```

---

### (2) 환율 조회

| 항목 | 내용 |
|------|------|
| 트리거 키워드 | 환율, 달러 환율, 원달러, 유로, 엔화 |
| 데이터 소스 | Spring API `GET /api/market/exchange` |
| 파라미터 추출 | currency_pair (달러→USDKRW, 유로→EURKRW, 엔→JPYKRW) |
| 응답 포맷 | `format_exchange_rate()` |

```
■ 환율  달러/원 (USD/KRW)
────────────────────────
  현재    1,385.50원
  등락   ▲2.30원
```

---

### (3) 주식 순위 조회

| 항목 | 내용 |
|------|------|
| 트리거 키워드 | 순위, 랭킹, 상승주, 하락주, 거래량 순, 시가총액 순 |
| 데이터 소스 | Spring API `GET /api/market/stocks/ranking` |
| 파라미터 추출 | ranking_type (거래량/거래대금/상승/하락/시가총액), market (국내/해외) |
| 응답 포맷 | `format_ranking()` |

ranking_type 매핑:

| 키워드 | API 파라미터 |
|--------|-------------|
| 거래량 | `trading-volume` |
| 거래대금 | `trading-value` |
| 상승 | `rising` |
| 하락 | `falling` |
| 시가총액 | `market-cap` |

---

### (4) 차트+시세 조회

| 항목 | 내용 |
|------|------|
| 트리거 키워드 | 차트, 시세, 주가, 현재가, 얼마 + (종목명/코드) |
| 데이터 소스 | Spring API `GET /api/market/stocks/{code}/price` + `/daily` |
| 파라미터 추출 | stock_code (6자리 숫자 → 국내, 영문 대문자 → 미국, 한글 → Oracle 종목명 조회) |
| 응답 포맷 | `format_chart_price()` |

```
■ 삼성전자 시세
────────────────────────
  현재가       75,400원
  등락    ▲400원  (▲0.53%)
────────────────────────
  시가         75,000원
  고가         75,600원
  저가         74,800원
────────────────────────
  거래량    12,345,678주
```

---

### (5) 잔고 조회

| 항목 | 내용 |
|------|------|
| 트리거 키워드 | 잔고, 예수금, 보유 현금, 내 계좌 |
| 데이터 소스 | Spring API `GET /api/balance/cash` |
| 응답 포맷 | `format_balance()` |

```
계좌잔고

원화 (KRW)
  • 총 자산:            5,000,000 원
  • 주문/출금 가능:     4,800,000 원

달러 (USD)
  • 총 자산:               500.00 USD
  • 주문/출금 가능:         480.00 USD
```

---

### (6) 매수·매도 버튼 연동

| 항목 | 내용 |
|------|------|
| 매수 트리거 | 매수, 사고 싶어, 살게, 구매하고 싶어 |
| 매도 트리거 | 매도, 팔고 싶어, 팔게, 판매하고 싶어 |
| 동작 | 주문을 직접 실행하지 않고 `action` 필드로 프론트엔드에 신호 전달 |

응답 예시:
```json
{
  "reply": "005930 매수 주문 화면을 활성화합니다.",
  "action": "activate_buy",
  "action_params": { "stock_code": "005930" }
}
```

프론트엔드는 `action` 값에 따라 매수/매도 모달을 열고,
`action_params.stock_code`로 종목을 자동 입력합니다.

---

### (7) 환전 버튼 연동

| 항목 | 내용 |
|------|------|
| 트리거 키워드 | 환전하고 싶어, 환전해줘, 달러로 바꿔, 원화로 바꿔 |
| 동작 | `action: "activate_exchange"` 로 프론트엔드 환전 화면 활성화 |

응답 예시:
```json
{
  "reply": "환전 화면을 활성화합니다.",
  "action": "activate_exchange",
  "action_params": {}
}
```

---

### (8) 한국 시황 요약

| 항목 | 내용 |
|------|------|
| 트리거 키워드 | 한국 시황, 국내 시황, 한국장, 코스피 시황, 오늘 시황 |
| 데이터 소스 | MongoDB `sollite.news` (stock_index: "KOSDAQ", 최신 1건) |
| 응답 포맷 | `format_korea_summary()` |

```
한국 시황  2026년 03월 25일
────────────────────────
반도체 업황 개선 기대로 코스피 반등

주요 이슈
  · 미 연준 금리 동결 발표로 외국인 매수세 유입
  · 삼성전자 HBM 수주 소식에 반도체 섹터 강세

상승 섹터
  KOSPI   반도체(+2.1%)  ·  자동차(+1.3%)
  KOSDAQ  바이오(+1.8%)  ·  2차전지(+0.9%)

주요 종목
  KOSPI   ▲ 삼성전자(+1.2%)  ·  SK하이닉스(+2.3%)
              ▼ LG에너지솔루션(-0.5%)
────────────────────────
```

---

### (9) 미국 시황 요약

| 항목 | 내용 |
|------|------|
| 트리거 키워드 | 미국 시황, 미국장, 나스닥 시황, 해외 시황 |
| 데이터 소스 | MongoDB `sollite.news` (stock_index: "NASDAQ", 최신 1건) |
| 응답 포맷 | `format_us_summary()` |

---

### (10) 종목별 뉴스 요약

| 항목 | 내용 |
|------|------|
| 트리거 키워드 | 뉴스, 기사, 소식 + (종목명/코드) |
| 데이터 소스 | MongoDB `sollite.stock_news` (해당 종목 최신 3건) |
| 파라미터 추출 | stock_code (한글이면 Oracle `instruments` 테이블에서 코드 조회) |
| 응답 포맷 | `format_stock_news()` |

```
삼성전자 종목 뉴스
────────────────────────
1. 기사제목: 삼성전자 2분기 실적 가이던스 상향  (2026년 03월 25일)
   요약: HBM 수요 증가로 반도체 부문 이익률 개선 전망

2. 기사제목: 삼성전자 파운드리 수주 확대  (2026년 03월 23일)
   요약: TSMC 대비 가격 경쟁력으로 고객사 확대 중
────────────────────────
```

---

### (11) 거래내역 조회 — AI agent

| 항목 | 내용 |
|------|------|
| 트리거 키워드 | 거래내역, 거래 내역, 매매 내역, 체결 내역, 주문 내역 |
| 데이터 소스 | Oracle DB (`executions`, `instruments` 테이블) |
| 단순 조회 | `format_trades()` 템플릿 직접 반환 |
| 세부 질문 | 데이터 + 질문을 llama에 전달 → 자연어 응답 |

**단순 조회 vs 세부 질문 판단:**
메시지에 아래 키워드가 포함되면 세부 질문으로 분류해 llama로 라우팅합니다.

```
가장, 왜, 어떤, 얼마나, 비교, 최고, 최저, 몇, 언제, 어느, 분석, 추천, 평균, 합계, 총
```

| 입력 예시 | 분류 | 처리 |
|-----------|------|------|
| "거래내역 보여줘" | 단순 조회 | `format_trades()` |
| "최근 거래내역" | 단순 조회 | `format_trades()` |
| "가장 많이 거래한 종목은?" | 세부 질문 | llama |
| "삼성전자 몇 번 샀어?" | 세부 질문 | llama |
| "평균 체결가 얼마야?" | 세부 질문 | llama |

llama에게는 거래 데이터 전체를 JSON으로 제공하고 답변을 요청합니다:
```
[System] 아래 거래 데이터를 바탕으로 질문에 답하세요.
         데이터: { "total": 47, "buy_count": 28, ... }
[User]   가장 많이 거래한 종목은?
```

---

### (12) 포트폴리오 분석 조회 — AI agent

| 항목 | 내용 |
|------|------|
| 트리거 키워드 | 포트폴리오, 포폴, 자산 분석, 수익률 분석, 투자 분석 |
| 데이터 소스 | Oracle DB + Spring API 실시간 시세 |
| 단순 조회 | `format_portfolio()` 템플릿 직접 반환 |
| 세부 질문 | 데이터 + 질문을 llama에 전달 → 자연어 응답 |

포트폴리오 분석 항목:

| 영역 | 지표 |
|------|------|
| 수익률 | 평가손익, 실현손익, 1M/3M/6M 수익률, 최고/최저 종목 |
| 집중도 | 섹터별 비중, 종목별 비중, 국내/해외 비율 |
| 리스크 | MDD, 회복 필요 수익률, 일간 변동폭, 거래통계, 손익비 |

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

---

## 의도 감지 우선순위 (rule_router)

의도 충돌 방지를 위해 아래 순서로 패턴을 검사합니다.

```
1. buy_intent     (매수)
2. sell_intent    (매도)
3. exchange_order (환전 주문)
4. balance        (잔고)
5. trades         (거래내역)
6. portfolio      (포트폴리오)
7. stock_news     (종목 뉴스)
8. chart_price    (시세·차트)
9. ranking        (주식 순위)
10. korea_summary (한국 시황)
11. us_summary    (미국 시황)
12. index         (지수)
13. exchange_rate (환율)
```

> 매수/매도를 가장 먼저 검사하는 이유: "삼성전자 매수 순위 알려줘" 같은 메시지에서
> `ranking` 보다 `buy_intent` 가 우선 매칭되는 것을 방지하기 위함입니다.

---

## 파라미터 추출 (rule_router)

### 종목 코드 추출 우선순위

```
1. 6자리 숫자        → 국내 종목코드  (예: 005930)
2. 2~5자리 영문 대문자 → 미국 티커     (예: AAPL, TSLA)
3. 한글 단어         → Oracle DB instruments 테이블에서 종목명으로 코드 조회
```

### ranking_type 추출

| 키워드 | API 값 |
|--------|--------|
| 거래대금 | `trading-value` |
| 거래량 | `trading-volume` (기본값) |
| 상승 | `rising` |
| 하락 | `falling` |
| 시가총액 | `market-cap` |

### currency_pair 추출

| 키워드 | API 값 |
|--------|--------|
| 달러 (기본값) | `USDKRW` |
| 유로 | `EURKRW` |
| 엔, 엔화, 일본 | `JPYKRW` |
| 파운드 | `GBPKRW` |

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
  "reply": "■ 삼성전자 시세\n────────────────────────\n  현재가       75,400원\n  ...",
  "action": null,
  "action_params": null
}
```

**action 응답 (매수/매도/환전 요청 시):**
```json
{
  "reply": "005930 매수 주문 화면을 활성화합니다.",
  "action": "activate_buy",
  "action_params": { "stock_code": "005930" }
}
```

| action 값 | 프론트엔드 동작 |
|-----------|----------------|
| `activate_buy` | 매수 주문 모달 오픈, `stock_code` 자동 입력 |
| `activate_sell` | 매도 주문 모달 오픈, `stock_code` 자동 입력 |
| `activate_exchange` | 환전 화면 오픈 |
| `null` | 일반 텍스트 응답 |

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

MONGO_URI=mongodb://localhost:27017
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

# 포트폴리오 세부 질문 (llama 응답)
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer <JWT>" \
  -H "Content-Type: application/json" \
  -d '{"message": "내 포트폴리오에서 가장 수익률 좋은 섹터 분석해줘"}'
```
