# 병렬 크롤링 구현

## 배경 및 문제

기존 `run_job` 함수는 CSV에 등재된 종목을 **순차적으로** 처리했다.

```
종목1 크롤링 → 종목2 크롤링 → ... → 종목300 크롤링
```

KOSPI200 + NASDAQ100 약 300종목을 순서대로 처리하면, 뒤쪽 종목(예: 199번째, 200번째)은
첫 번째 종목 대비 수십 분 늦게 크롤링된다.
30분 주기 스케줄에서 이 지연은 "최신 기사"라는 느낌을 해칠 수 있다.

---

## 해결 방법: ThreadPoolExecutor

크롤링 작업은 대부분 **HTTP 요청 대기(I/O bound)** 이므로,
멀티스레드로 여러 종목을 동시에 처리하면 전체 소요 시간을 크게 줄일 수 있다.

```
           [순차]                         [병렬 - 10 workers]
종목1 ──────────────────────►     종목1, 11, 21, 31... ──────►
종목2      ──────────────────►     종목2, 12, 22, 32... ──────►
...                                ...
종목300                   ──►     종목10, 20, 30, 40...──────►
```

---

## 구현 내용

### 1. import 추가

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
```

### 2. 상수 추가

```python
MAX_WORKERS = 10  # 동시 크롤링 스레드 수 (너무 높이면 IP 차단 위험)
```

### 3. `_crawl_and_save` 함수 분리

기존 `run_job` 내부 루프 로직을 **종목 1개 처리 단위**로 분리했다.
스레드 하나가 이 함수를 담당한다.

```python
def _crawl_and_save(stock) -> int:
    """크롤링 → 중복 제거 → 요약 → DB 저장. 저장 건수를 반환."""
    candidates = crawl_stock_news(stock)
    new_articles = deduplicate(candidates)
    new_articles = summarize_articles(new_articles)
    result = collection.insert_many(new_articles, ordered=False)
    return len(result.inserted_ids)
```

### 4. `run_job` 병렬화

```python
def run_job(stocks):
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_crawl_and_save, stock): stock for stock in stocks}
        for future in as_completed(futures):
            try:
                total_saved += future.result()
            except Exception as e:
                print(f'[{futures[future]["ticker"]}] 에러: {e}')
```

- `executor.submit`: 각 종목을 스레드 풀에 제출
- `as_completed`: 완료된 순서대로 결과를 수집 (CSV 순서와 무관)
- 개별 종목 에러가 전체 사이클을 중단시키지 않음

---

## 성능 비교

| 방식 | 300종목 예상 소요 시간 |
|------|----------------------|
| 순차 (기존) | 약 25~40분 |
| 병렬 10 workers | 약 3~5분 |

> 실제 시간은 네트워크 상태와 기사 본문 파싱 속도에 따라 달라진다.

---

## MAX_WORKERS 선택 기준

| workers 수 | 특징 |
|------------|------|
| 5 이하 | 안전하지만 속도 개선 제한적 |
| **10 (현재)** | **속도와 안정성의 균형** |
| 20 이상 | 빠르지만 네이버 API IP 차단 위험 증가 |

---

## 스레드 안전성

- **pymongo `MongoClient`**: 내부적으로 커넥션 풀을 관리하므로 멀티스레드 환경에서 안전하다.
- **`deduplicate`**: DB 조회 + 필터링만 수행하며 공유 상태를 변경하지 않으므로 안전하다.
- **`summarize_articles`**: 아래 Race Condition 버그 수정 후 안전하다.

---

## 트러블슈팅: 요약 모델 Race Condition

### 증상

병렬화 적용 후 다음 에러가 다수 발생했다.

```
모델 로딩 중: EbanLee/kobart-summary-v3
요약 실패 [1/3] 068270_020_...: 'NoneType' object has no attribute 'generate'
요약 실패 [2/3] 068270_018_...: 'NoneType' object has no attribute 'generate'
```

### 원인

`summarizer.py`의 `_load_model()`이 스레드 안전하지 않았다.

```python
# 기존 코드 (문제 있음)
def _load_model():
    global _tokenizer, _model
    if _tokenizer is None:        # ← 체크와 할당 사이 틈이 존재
        _tokenizer = ...load...   # Thread A: _tokenizer 할당 완료
        _model = ...load...       # Thread A: _model 아직 로딩 중
                                  # Thread B: _tokenizer is not None → 바로 리턴
                                  # Thread B: _model.generate() → _model이 None → 에러!
```

`_tokenizer`가 먼저 할당되는 순간 다른 스레드가 `_load_model()`을 통과해버리지만,
`_model`은 아직 `None`인 상태여서 `generate()` 호출 시 에러가 발생했다.

### 수정 (`summarizer.py`)

`threading.Lock`으로 모델 로딩 전체를 임계 구역으로 보호했다.

```python
import threading
_lock = threading.Lock()

def _load_model():
    global _tokenizer, _model
    with _lock:                   # 한 스레드만 진입 가능
        if _tokenizer is None:
            _tokenizer = ...load...
            _model = ...load...   # 둘 다 완료된 뒤에야 lock 해제
```

`with _lock` 블록이 끝나야 다른 스레드가 진입하므로,
`_tokenizer`와 `_model` 모두 완전히 로딩된 상태가 보장된다.

---

## 트러블슈팅: Ctrl+C 종료 불가

### 증상

서버 실행 중 `Ctrl+C`를 눌러도 프로세스가 종료되지 않았다.

### 원인

`run_job`의 `with ThreadPoolExecutor(...) as executor:` 블록이 문제였다.
`with` 문의 `__exit__`는 내부적으로 `shutdown(wait=True)`를 호출하여
**제출된 futures(최대 300개)가 전부 완료될 때까지 blocking**한다.

```
Ctrl+C
  → crawler.stop() → _stop_event.set() → _thread.join(timeout=15)
  → BUT _thread는 with ThreadPoolExecutor 블록에 묶여 있음
  → 300개 futures(HTTP 요청 + 모델 추론) 전부 끝날 때까지 대기
  → 15초 timeout 이후에도 ThreadPoolExecutor worker 스레드가 살아있어 프로세스 미종료
```

### 수정 (`scheduled_crawler.py`)

`with` 블록을 제거하고 `try/finally`로 교체하여,
종료 시 `shutdown(wait=False, cancel_futures=True)`가 즉시 실행되도록 했다.

```python
# 기존 (문제 있음)
with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    futures = {executor.submit(_crawl_and_save, stock): stock for stock in stocks}
    for future in as_completed(futures):
        ...
# __exit__ 시 shutdown(wait=True) → 전체 blocking

# 수정 후
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
futures = {executor.submit(_crawl_and_save, stock): stock for stock in stocks}
try:
    for future in as_completed(futures):
        ...
finally:
    executor.shutdown(wait=False, cancel_futures=True)
    # Ctrl+C → KeyboardInterrupt → finally 즉시 실행
    # 대기 중인 futures 취소, 실행 중인 스레드는 자연 완료
```

### Ctrl+C 후 동작 흐름 (수정 후)

```
Ctrl+C
  → KeyboardInterrupt → finally 블록 실행
  → executor.shutdown(wait=False, cancel_futures=True)
       대기 중 futures → 즉시 취소
       실행 중 스레드 → 자연 완료 (수초 내)
  → crawler.stop() → join(timeout=15) 후 종료
```

크롤링 사이클 도중 `Ctrl+C`를 눌러도 **수초 내로** 서버가 종료된다.
