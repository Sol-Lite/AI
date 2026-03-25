# 코드 수정 사항 (merge 후 발견된 버그)

## 1. `app/services/llm.py` — TOOLS 스키마 중복 키 (심각)

### 문제
`get_market_data` 툴 파라미터에 `market`과 `ranking_type`이 **두 번씩 선언**되어 있음.
Python dict는 중복 키의 마지막 값만 유지하므로, 실제로 LLM에 전달되는 스키마는 아래와 같음:

```
# 의도한 값 (첫 번째 선언, 무시됨)
"market": {"enum": ["all", "kospi", "kosdaq"]}

# 실제 적용된 값 (두 번째 선언이 덮어씀)
"market": {"enum": ["domestic", "overseas"]}   ← 잘못된 값!
```

**결과:** LLM이 ranking 호출 시 `market=domestic` 또는 `market=overseas`를 넘기고,
Spring API는 `all/kospi/kosdaq`만 받으므로 502 에러 발생.

### 수정
- 중복된 `market` 선언 제거 → `["all", "kospi", "kosdaq"]` 하나만 유지
- 중복된 `ranking_type` 선언 제거

---

## 2. `app/services/llm.py` — 시스템 프롬프트 ranking 섹션 누락

### 문제
ranking 시스템 프롬프트에 `market` 파라미터 값 안내가 없어,
LLM이 market을 어떤 값으로 채워야 할지 알 수 없음.

### 수정
ranking 섹션에 market 선택 규칙 추가:
```
market 결정 규칙:
  all    : 전체 (기본값, 시장 미특정 시)
  kospi  : 코스피, 유가증권시장
  kosdaq : 코스닥
```

---

## 3. `app/tools/get_market_data.py` — `_fetch_price`의 불필요한 market 파라미터

### 문제
`_fetch_price`에서 `market` 값을 Spring `/api/market/stocks/{code}/price`에 쿼리 파라미터로 전달.
- price API는 종목코드로 조회하므로 market 필터가 의미 없음
- market 값이 `all/kospi/kosdaq`으로 바뀐 뒤에도 그대로 넘어가면 Spring이 의도치 않게 동작할 수 있음

### 수정
`_fetch_price` 내 `_call_spring_api` 호출 시 `market` 파라미터 제거

---

## Spring 백엔드 미구현 (코드 수정 불가, Spring 팀 요청 필요)

테스트(`python test_market_data_api.py`) 결과 아래 조합이 502/500 반환:

| API | 파라미터 | 에러 |
|-----|----------|------|
| `/api/market/stocks/{code}/daily` | 모든 종목 | 500 |
| `/api/market/stocks/{code}/chart` | 모든 종목 | 500 |
| `/api/market/stocks/ranking` | `market=kosdaq` 전체 | 502 |
| `/api/market/stocks/ranking` | `type=falling` 전체 | 502 |
| `/api/market/exchange` | 모든 통화쌍 | 응답은 오나 `rate=0.0` |
