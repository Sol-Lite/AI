# 투자 챗봇 개발 진행상황

최종 업데이트: 2026-03-21

---

## 프로젝트 구조

```
MidProject/
├── app/
│   ├── main.py                          ✅  FastAPI 엔드포인트
│   ├── core/
│   │   └── config.py                    ✅  환경변수 로드
│   ├── db/
│   │   ├── oracle.py                    ✅  Oracle 연결 (oracledb)
│   │   └── mongo.py                     ✅  MongoDB 연결 (sollite.news)
│   ├── services/
│   │   └── llm.py                       ✅  Ollama tool calling 루프 + 템플릿 디스패치
│   ├── tools/
│   │   ├── __init__.py                  ✅
│   │   ├── get_market_summary.py        ✅  MongoDB 실제 연동
│   │   ├── get_db_data.py               ✅  Oracle 실제 연동 (잔고/거래내역/포트폴리오)
│   │   ├── get_market_data.py           ✅  Spring API 실제 연동 (시세/차트/환율), 랭킹/지수 mock
│   │   └── execute_order.py             ⏳  mock (LS증권 API 연동 필요)
│   └── templates/
│       ├── account.py                   ✅  잔고
│       ├── trades.py                    ✅  거래내역
│       ├── portfolio.py                 ✅  포트폴리오 분석
│       ├── market.py                    ✅  한국/미국 시황, 종목 뉴스
│       └── order.py                     ✅  주문 완료 메시지 템플릿
├── portfolio.md                         ✅  _query_portfolio 상세 설계 문서
├── .env                                 ✅
└── requirements.txt                     ✅
```

---

## 완료된 작업

### 1. FastAPI 엔드포인트 (`main.py`)

- `POST /chat` — `{ "message": "..." }` 입력, `{ "reply": "..." }` 출력
- `HTTPBearer` 의존성으로 JWT 파싱 → `user_context` 추출
- JWT 실제 검증은 TODO (현재 하드코딩)

---

### 2. LLM Tool Calling 루프 (`services/llm.py`)

- Ollama `/api/chat` 호출 (모델: llama3.1:8b)
- 도구 4개 JSON 스키마 정의
- **system prompt**: 매 요청마다 주입, LLM의 툴 선택 라우팅 규칙 명시
- **`_TEMPLATE_DISPATCH`**: `(tool_name, type)` → 템플릿 함수 매핑
  - 템플릿이 등록된 경우 LLM 응답 생성 없이 즉시 반환
  - 등록되지 않은 경우 tool 결과를 LLM에 재전달하여 자연어 응답 생성

**LLM 제어 역할 분리:**

| 구분             | 역할                              | 이유                                                                 |
| ---------------- | --------------------------------- | -------------------------------------------------------------------- |
| system prompt    | 툴 선택 라우팅 규칙               | 여러 툴에 걸친 선택 기준은 한 곳에 모아야 LLM이 일관되게 판단 가능. 작은 모델(llama3.1:8b)은 tool description만으로 놓치는 케이스가 생김. 테스트 중 실패 케이스 발견 시 system prompt만 수정하면 됨 |
| tool description | 툴 목적 및 파라미터 의미          | 툴 자체가 무엇을 하는지 간결하게 기술. 라우팅 규칙까지 담으면 불필요하게 길어짐 |

**_TEMPLATE_DISPATCH 등록 현황:**

| (tool_name, type)                   | 템플릿 함수            |
| ----------------------------------- | ---------------------- |
| `get_db_data` / `balance`           | `format_balance`       |
| `get_db_data` / `trades`            | `format_trades`        |
| `get_db_data` / `portfolio`         | `format_portfolio`     |
| `get_market_summary` / `korea`      | `format_korea_summary` |
| `get_market_summary` / `us`         | `format_us_summary`    |
| `get_market_summary` / `stock_news` | `format_stock_news`    |
| `execute_order` / `buy`             | `format_order`         |
| `execute_order` / `sell`            | `format_order`         |
| `execute_order` / `exchange`        | `format_order`         |

---

### 3. 도구 구현

#### get_market_summary (MongoDB 실제 연동)

- `type`: `korea` | `us` | `stock_news`
- `sollite.news` 컬렉션에서 최신 문서 조회
- `published_at` 날짜 포맷: `YYYY년 MM월 DD일`
- `stock_news`: `stock_name` 포함 반환 (종목명 표시용)

#### get_db_data (Oracle 연동)

전체 조회(템플릿 반환) / 세부 질문(LLM 자연어 응답) 두 가지 타입으로 분리:

| type               | 응답 방식        | 설명                        |
| ------------------ | ---------------- | --------------------------- |
| `balance`          | 템플릿 즉시 반환 | KRW/USD 잔고 전체 리포트    |
| `trades`           | 템플릿 즉시 반환 | 거래내역 전체 리포트        |
| `portfolio`        | 템플릿 즉시 반환 | 포트폴리오 전체 분석 리포트 |
| `balance_detail`   | LLM 자연어 응답  | 특정 잔고 항목 질문         |
| `trades_detail`    | LLM 자연어 응답  | 특정 거래 항목 질문         |
| `portfolio_detail` | LLM 자연어 응답  | 특정 포트폴리오 항목 질문   |

- `balance/balance_detail`: `cash_balances` 테이블에서 KRW/USD 잔고 조회 (동일 쿼리)
- `trades/trades_detail`: `executions` + `instruments` JOIN, 매수/매도 최근 N건 CTE (동일 쿼리)
- `portfolio/portfolio_detail`: 6개 쿼리 + Spring API 실시간 시세/환율 조합 (동일 쿼리)
  - `portfolio_snapshots`: 기간별 수익률(1M/3M/6M), MDD, 변동성
  - `holdings` + Spring API: 실시간 평가액(`domestic_stock_value`), 섹터/종목 집중도, 미실현손익
  - `cash_balances`: 현금 잔고
  - `executions`: 거래 통계, 실현손익
  - 반환값에 `stock_returns` 포함 (종목별 수익률 전체 리스트 — "삼성전자 수익률" 같은 세부 질문 대응)

#### get_market_data (Spring API 실제 연동)

| type           | 연동 상태 | 엔드포인트                               |
| -------------- | --------- | ---------------------------------------- |
| `price`        | ✅ 실제   | `/api/market/stocks/{code}/price`        |
| `chart`        | ✅ 실제   | `/api/market/stocks/{code}/minute-chart` |
| `daily`        | ✅ 실제   | `/api/market/stocks/{code}/daily`        |
| `period_chart` | ✅ 실제   | `/api/market/stocks/{code}/chart`        |
| `exchange`     | ✅ 실제   | `/api/market/exchange`                   |
| `ranking`      | ⏳ mock   | LS증권 API 연동 필요                     |
| `index`        | ⏳ mock   | LS증권 API 연동 필요                     |

#### execute_order (mock)

- `buy` / `sell` / `exchange` 모두 mock 데이터 반환
- LS증권 API 연동 필요

---

### 4. 응답 템플릿

LLM이 텍스트를 생성하는 대신, 도구 결과를 직접 포맷팅하여 채팅 메시지로 반환합니다.

| 파일                     | 함수                   | 출력 내용                                  |
| ------------------------ | ---------------------- | ------------------------------------------ |
| `templates/account.py`   | `format_balance`       | KRW/USD 잔고, 주문/출금 가능 금액          |
| `templates/trades.py`    | `format_trades`        | 매수/매도 건수 요약 + 최근 체결 내역       |
| `templates/portfolio.py` | `format_portfolio`     | 수익률 / 집중도 / 리스크 3섹션 리포트      |
| `templates/market.py`    | `format_korea_summary` | 한국 시황 (이슈·섹터·종목)                 |
| `templates/market.py`    | `format_us_summary`    | 미국 시황 (이슈·시장심리)                  |
| `templates/market.py`    | `format_stock_news`    | 종목 뉴스 (종목명·기사제목·요약, 최대 3건) |
| `templates/order.py`     | `format_order`         | 매수/매도/환전 주문 완료 메시지             |

---

### 5. DB 연결

| DB      | 파일           | 상태 | 비고                              |
| ------- | -------------- | ---- | --------------------------------- |
| Oracle  | `db/oracle.py` | ✅   | `oracledb`, fetch_one/all/execute |
| MongoDB | `db/mongo.py`  | ✅   | `sollite.news` 컬렉션             |

---

## 남은 작업

| 구분 | 항목                                            | 비고                            |
| ---- | ----------------------------------------------- | ------------------------------- |
| 1    | `portfolio_snapshots` 테이블 Oracle에 생성      | DDL은 portfolio.md 참고         |
| 2    | JWT 실제 검증 (`main.py` `get_user_context`)    | python-jose 사용 예정           |
| 3    | `execute_order` LS증권 API 연동                 | CSPAT00601 (국내), 해외주문 API |
| 4    | `get_market_data` ranking/index LS증권 API 연동 | t1463/t1464, t1511              |
| ~~5~~ | ~~`templates/order.py` 작성~~                  | ~~완료~~                                    |
| 7    | 프론트엔드 채팅창 연결                          | `/chat` API 연결                |

---

## 실행 방법

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

```bash
# 테스트
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"message": "내 잔고 알려줘"}'
```

---

## 환경변수 (.env)

| 키                                               | 용도                                     |
| ------------------------------------------------ | ---------------------------------------- |
| `OLLAMA_BASE_URL`                                | Ollama 서버 주소 (기본: localhost:11434) |
| `OLLAMA_MODEL`                                   | LLM 모델명 (기본: llama3.1:8b)           |
| `ORACLE_DSN` / `ORACLE_USER` / `ORACLE_PASSWORD` | Oracle DB                                |
| `MONGO_URI` / `MONGO_DB`                         | MongoDB                                  |
| `REDIS_HOST` / `REDIS_PORT`                      | Redis                                    |
| `SPRING_BASE_URL`                                | Spring API (기본: localhost:8080)        |
