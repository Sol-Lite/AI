# 투자 챗봇 개발 진행상황

최종 업데이트: 2026-03-18

---

## 완료된 작업

### 1. 프로젝트 구조 생성

```
MidProject/
├── app/
│   ├── main.py                      ✅
│   ├── core/
│   │   └── config.py                ✅
│   ├── services/
│   │   └── llm.py                   ✅
│   └── tools/
│       ├── __init__.py              ✅
│       ├── get_market_summary.py    ✅
│       ├── get_db_data.py           ✅
│       ├── get_market_data.py       ✅
│       └── execute_order.py         ✅
├── .env                             ✅
└── requirements.txt                 ✅
```

---

### 2. 도구 4개 mock 구현

| 도구                 | 파일                          | 상태      |
| -------------------- | ----------------------------- | --------- |
| `get_market_summary` | `tools/get_market_summary.py` | mock 완료 |
| `get_db_data`        | `tools/get_db_data.py`        | mock 완료 |
| `get_market_data`    | `tools/get_market_data.py`    | mock 완료 |
| `execute_order`      | `tools/execute_order.py`      | mock 완료 |

각 도구 파일 내 `# TODO:` 주석으로 실제 연동 교체 위치 표시

#### get_market_summary

- 입력: `date` (생략 시 오늘)
- 출력: `{ date, title[], summary[], count, source }`
- TODO: `_fetch_news_and_summarize()` → 뉴스 크롤링 + llama

#### get_db_data

- 입력: `type` (balance / trades / portfolio), `limit`
- 출력: 잔고 / 거래내역 / 포트폴리오 분석 딕셔너리
- TODO: `_query_balance/trades/portfolio(account_id)` → Oracle SELECT + Redis 캐시

#### get_market_data

- 입력: `type` (price / chart / ranking / index / exchange) + 타입별 파라미터
- 출력: 시세 / 차트 캔들 / 랭킹 / 지수 / 환율 딕셔너리
- TODO: `_fetch_*()` → LS증권 API + Redis 캐시

#### execute_order

- 입력: `type` (buy / sell / exchange) + 타입별 파라미터
- 출력: 주문 접수 결과 / 환전 완료 결과 딕셔너리
- TODO: `_place_stock_order/fx_order(account_id)` → LS증권 API

---

### 3. llama tool calling 루프 (`services/llm.py`)

- Ollama `/api/chat` 호출 (모델: llama3.1:8b)
- 도구 4개 JSON 스키마 정의 (LLM에 노출)
- tool_calls 파싱 → `_dispatch()` → 결과를 tool 메시지로 추가 → 루프 반복
- llm이 tool_calls 없는 응답 반환 시 루프 종료

---

### 4. FastAPI 엔드포인트 (`main.py`)

- `POST /chat` — `{ "message": "..." }` 입력, `{ "reply": "..." }` 출력
- `HTTPBearer` 의존성으로 JWT 파싱 → `user_context` 추출

---

### 5. 세션 기반 user_context 설계

**핵심 원칙**: `user_id` / `account_id`는 LLM 스키마에 노출하지 않음

흐름:

```
JWT → get_user_context() → user_context dict
                              ↓
               chat(message, user_context)
                              ↓
            _dispatch() 시 코드가 직접 주입
            (get_db_data, execute_order 에만)
```

- `get_market_summary`, `get_market_data`는 공용 데이터 → user_context 불필요
- `get_db_data`, `execute_order`는 계정 데이터 → `account_id` 주입

---

## 남은 작업

| 순서 | 항목                                            | 비고                   |
| ---- | ----------------------------------------------- | ---------------------- |
| 1    | LS증권 API 연동 (`services/ls_api.py`)          | Access Token 발급 필요 |
| 2    | Oracle 연동 (`db/oracle.py`)                    | cx_Oracle 설치 필요    |
| 3    | MongoDB 연동 (`db/mongo.py`)                    | 채팅 이력 저장용       |
| 4    | Redis 연동 (`db/redis.py`)                      | 시세 캐시, 세션 캐시   |
| 5    | JWT 실제 검증 (`main.py` `get_user_context`)    | python-jose 사용       |
| 6    | kobart 요약 모델 연동 (`get_market_summary.py`) | —                      |
| 7    | 프론트 채팅창 연결                              | —                      |

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
| `LS_APP_KEY` / `LS_APP_SECRET`                   | LS증권 Open API 인증                     |
| `ORACLE_DSN` / `ORACLE_USER` / `ORACLE_PASSWORD` | Oracle DB                                |
| `MONGO_URI` / `MONGO_DB`                         | MongoDB                                  |
| `REDIS_HOST` / `REDIS_PORT`                      | Redis                                    |
