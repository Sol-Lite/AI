# 주식 뉴스 크롤러 코드 설명

## 대상 파일

| 파일 | 대상 시장 | 입력 CSV |
|------|----------|---------|
| `nasdaq_crawler.py` | NASDAQ100 (해외주식) | `NASDAQ100.csv` |
| `kospi_crawler.py` | KOSPI200 (국내주식) | `kospi200_targets.csv` |

두 파일은 구조가 동일하며, 시장별 URL·종목코드 형식·저장 필드만 다르다.

---

## 전체 실행 흐름

```
CSV 로드
  └─ 종목 리스트 생성
       └─ [종목별 반복]
            ├─ fetch_news_list()         ← 뉴스 목록 API 호출
            │    └─ (실패 시) fetch_news_list_from_page()  ← HTML 파싱 폴백
            ├─ crawl_stock_news()        ← 기사별 본문 수집 + news_id 생성
            │    └─ fetch_article_body() ← 네이버 뉴스 본문 페이지 파싱
            ├─ deduplicate()             ← 중복 제거 (2단계)
            ├─ summarize_articles()      ← KoBART 요약 모델 적용
            └─ collection.insert_many() ← MongoDB 저장
```

---

## 1. 상수 및 URL 정의

```python
# nasdaq_crawler.py
NEWS_API_URL  = "https://m.stock.naver.com/api/news/stock/{ticker}?pageSize={page_size}&page={page}"
LOCAL_NEWS_URL = "https://m.stock.naver.com/worldstock/stock/{ticker}/localNews"
ARTICLE_URL   = "https://n.news.naver.com/mnews/article/{officeId}/{articleId}"

# kospi_crawler.py
NEWS_API_URL  = "https://m.stock.naver.com/api/news/stock/{code}?pageSize={page_size}&page={page}"
LOCAL_NEWS_URL = "https://m.stock.naver.com/domestic/stock/{code}/news"
ARTICLE_URL   = "https://n.news.naver.com/mnews/article/{officeId}/{articleId}"
```

- **NEWS_API_URL**: 뉴스 목록을 JSON으로 받는 내부 API. NASDAQ/KOSPI 모두 동일한 엔드포인트 사용.
- **LOCAL_NEWS_URL**: API 실패 시 폴백으로 HTML을 직접 파싱하는 페이지 URL. 시장에 따라 경로가 다름 (`worldstock` vs `domestic`).
- **ARTICLE_URL**: 개별 기사 본문을 가져오는 네이버 뉴스 URL.

### MEDIA_KEYWORDS

```python
MEDIA_KEYWORDS = ["[포토]", "[사진]", "[동영상]", "[비디오]", "[포토뉴스]", "[영상]"]
```

제목에 이 키워드가 포함된 기사는 수집에서 제외한다. 사진·영상만 있는 기사는 본문 텍스트가 없어 요약 모델에 넣을 내용이 없기 때문이다.

---

## 2. MongoDB 연결 및 인덱스

```python
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

collection.create_index("news_id", unique=True, sparse=True)
collection.create_index([("published_at", -1)])
collection.create_index([("stock_code", 1)])
```

스크립트 시작 시 즉시 MongoDB에 연결하고 3개의 인덱스를 생성(또는 이미 있으면 스킵)한다.

| 인덱스 | 옵션 | 목적 |
|--------|------|------|
| `news_id` | unique, sparse | 동일 기사가 중복 저장되지 않도록 DB 레벨에서 강제 |
| `published_at` | 내림차순 | 최신순 조회 성능 향상 |
| `stock_code` | 오름차순 | 종목별 조회 성능 향상 |

`sparse=True`는 `news_id` 필드가 없는 문서는 유니크 제약에서 제외한다는 의미다.

---

## 3. 본문 전처리 (`clean_body`)

기사 본문에서 노이즈를 제거하는 함수다.

```python
def clean_body(text):
    text = _strip_bylines(text)                          # 기자 바이라인 제거
    text = re.sub(r'^\[[^\]]{1,40}기자\]\s*', '', text) # [홍길동 기자] 형태 제거
    text = re.sub(r'[가-힣]{2,6}\s*기자\s+이메일@도메인', '', text)  # 기자 이메일 제거
    text = re.sub(r'이메일@도메인', '', text)            # 일반 이메일 제거
    text = re.sub(r'https?://\S+', '', text)             # URL 제거
    text = re.sub(r'◀\s*(앵커|리포트)\s*▶\s*', '', text) # 방송 표시 제거
    text = re.sub(r'[■◆★☆◇○□]+\s*', '', text)          # 특수문자 불릿 제거
    text = re.sub(r'\(사진[^)]{0,30}\)', '', text)       # (사진=...) 캡션 제거
    text = re.sub(r'▲\s*.{0,200}', '', text)             # ▲ 이하 이미지 설명 제거
    return re.sub(r'\s+', ' ', text).strip()             # 공백 정규화
```

`_strip_bylines`는 정규식으로 기사 맨 앞에 붙는 `[뉴시스]`, `[홍길동 기자]` 형태의 바이라인을 반복해서 제거한다. 여러 개가 연속으로 붙는 경우도 있어 `while True` 루프로 처리한다.

---

## 4. 기사 본문 파싱 (`fetch_article_body`)

```python
def fetch_article_body(office_id, article_id):
    url = ARTICLE_URL.format(officeId=office_id, articleId=article_id)
    # ...
    content = soup.select_one('div#dic_area') or soup.select_one('div.newsct_article')
```

- `div#dic_area`: 대부분의 네이버 뉴스 본문 영역
- `div.newsct_article`: 일부 언론사의 대체 본문 영역

본문 외에 **소제목(subtitles)**도 별도로 수집한다.

| 선택자 | 의미 |
|--------|------|
| `strong.media_end_summary` | 기사 상단 요약문 |
| `div[style*='border-left']` | 인용구, 강조 박스 |
| `strong[style*='border-left']` | 인용구, 강조 박스 |
| `b` 태그 | 볼드 처리된 소제목 |

소제목 추출 후 해당 태그는 `decompose()`로 제거해 본문 텍스트에 중복되지 않게 한다.

썸네일은 `<meta property="og:image">` 태그에서 가져온다.

---

## 5. 뉴스 목록 수집 (`fetch_news_list`)

### API 응답 구조 주의사항

네이버 뉴스 API는 직관적이지 않은 구조로 응답한다.

```
요청: pageSize=20&page=1
응답: [
  { "total": 8, "items": [기사1] },
  { "total": 1, "items": [기사2] },
  { "total": 1, "items": [기사3] },
  ...
]
```

`pageSize=20`으로 요청하면 리스트 길이가 20이고, 각 원소 안에 기사가 **1개씩** 들어있다. `data[0]['items']`만 읽으면 항상 1건만 가져오는 버그가 발생하므로, 리스트 전체를 순회해야 한다.

```python
if isinstance(data, list):
    batch = []
    for entry in data:
        if isinstance(entry, dict):
            entry_items = entry.get('items') or entry.get('list') or entry.get('newsList') or []
            batch.extend(entry_items)
elif isinstance(data, dict):
    batch = data.get('items') or data.get('newsList') or data.get('list') or []
```

`target`(기본 20건)에 도달하거나 `batch`가 `page_size`보다 적으면(마지막 페이지) 루프를 종료한다.

### 폴백: `fetch_news_list_from_page`

API 요청이 실패하거나 결과가 없을 경우, Next.js가 HTML에 내장하는 `__NEXT_DATA__` JSON을 파싱해 뉴스 목록을 가져온다. 다만 이 방식은 페이지에 초기 로드된 기사만 포함되므로 건수가 적을 수 있다.

---

## 6. 종목별 뉴스 크롤링 (`crawl_stock_news`)

뉴스 목록 API 결과를 받아 기사별로 상세 처리한다.

### `news_id` 생성 규칙

```python
news_id = f"{stock_code}_{office_id}_{article_id}"
# 예시: AAPL_015_0005234567
#       000660_009_0004891234
```

- `stock_code`: 종목 코드 (NASDAQ는 티커, KOSPI는 6자리 숫자)
- `office_id`: 언론사 ID (네이버 내부 코드, 예: 015 = 중앙일보)
- `article_id`: 기사 고유 번호

이 세 값의 조합으로 전체 기사를 고유하게 식별한다.

### 발행일 파싱

API가 날짜 형식을 여러 포맷으로 내려줄 수 있어 순서대로 시도한다.

```python
for fmt, length in [
    ('%Y%m%d%H%M', 12),       # "202603301504"  → 가장 일반적
    ('%Y-%m-%dT%H:%M:%S', 19), # "2026-03-30T15:04:00"
    ('%Y-%m-%d %H:%M:%S', 19), # "2026-03-30 15:04:00"
    ('%Y.%m.%d %H:%M', 16),    # "2026.03.30 15:04"
]:
```

파싱에 모두 실패하면 `datetime.now()`를 사용한다.

### HTML 엔티티 디코딩

```python
title = html.unescape(title).strip()
```

API가 제목을 HTML 인코딩 상태로 내려준다(`&quot;` → `"`, `&#39;` → `'`). `html.unescape()`로 디코딩하지 않으면 DB에 그대로 저장된다.

### MongoDB 저장 필드 구조

| 필드 | 설명 | NASDAQ | KOSPI |
|------|------|--------|-------|
| `news_id` | 기사 고유 ID | `AAPL_015_0001234` | `000660_009_0001234` |
| `title` | 기사 제목 | ✓ | ✓ |
| `subtitles` | 소제목 리스트 | ✓ | ✓ |
| `content` | 정제된 본문 | ✓ | ✓ |
| `summary` | KoBART 요약 | ✓ | ✓ |
| `thumbnail_url` | 썸네일 이미지 URL | ✓ | ✓ |
| `source` | 언론사명 | ✓ | ✓ |
| `source_url` | 원문 URL | ✓ | ✓ |
| `stock_code` | 종목코드 | `AAPL` | `000660` |
| `stock_name` | 종목명 (한글) | `애플` | `SK하이닉스` |
| `stock_name_en` | 종목명 (영문) | `APPLE INC` | (없음) |
| `market` | 시장 구분 | `NASDAQ` | `KOSPI` |
| `published_at` | 기사 발행일시 | ✓ | ✓ |
| `fetched_at` | 수집 일시 | ✓ | ✓ |

---

## 7. 중복 제거 로직 (`deduplicate`)

중복 제거는 **2단계**로 이루어진다.

### 1단계 — 현재 수집 배치 내 중복 제거

```python
seen = set()
unique = []
for a in articles:
    if a['news_id'] not in seen:
        seen.add(a['news_id'])
        unique.append(a)
```

같은 크롤링 실행 안에서 동일한 `news_id`가 두 번 나타나는 경우를 제거한다.
예를 들어 같은 기사가 두 종목의 뉴스 목록에 동시에 노출되는 경우가 이에 해당한다.

### 2단계 — MongoDB 기존 데이터와 대조

```python
existing = set(
    doc['news_id'] for doc in collection.find(
        {'news_id': {'$in': [a['news_id'] for a in unique]}},
        {'news_id': 1}
    )
)
return [a for a in unique if a['news_id'] not in existing]
```

1단계를 통과한 기사들의 `news_id`를 MongoDB에 한 번에 조회(`$in` 쿼리)하여 이미 저장된 기사를 필터링한다.
기사 건수만큼 개별 조회하지 않고 **배치 조회**로 처리해 DB 요청을 최소화한다.

### 3단계 — DB 유니크 인덱스 (최종 안전망)

```python
collection.create_index("news_id", unique=True, sparse=True)
```

2단계까지 통과했더라도, 여러 프로세스가 동시에 실행되거나 경쟁 조건이 발생하는 경우에 대비해 DB 레벨의 유니크 인덱스가 최종 방어선 역할을 한다.
`insert_many(ordered=False)`를 사용해 중복 오류가 발생해도 나머지 기사는 정상 저장된다.

```python
try:
    result = collection.insert_many(articles, ordered=False)
    saved = len(result.inserted_ids)
except Exception as e:
    saved = getattr(e, 'details', {}).get('nInserted', 0)
```

`ordered=False`이므로 중복 키 오류가 발생한 문서를 건너뛰고 나머지를 계속 삽입한다. 예외의 `details.nInserted`로 실제 저장 건수를 확인한다.

### 중복 제거 흐름 요약

```
크롤링된 기사 N건
    │
    ▼
[1단계] 배치 내 중복 제거 (set으로 news_id 비교)
    │
    ▼
[2단계] MongoDB $in 쿼리로 기존 저장 기사 대조
    │
    ▼
신규 기사만 summarize → insert_many(ordered=False)
    │
    ▼
[3단계] DB 유니크 인덱스 (동시 실행 등 엣지케이스 방어)
```

---

## 8. CSV 로드

### `load_nasdaq100` (nasdaq_crawler.py)

```python
# 첫 줄이 '표 1,,' 같은 메타 행인 경우 건너뜀
if lines and not lines[0].strip().startswith('stock_code'):
    start = 1
```

`NASDAQ100.csv`는 첫 줄이 `표 1,,`으로 시작하는 메타 행이 있어 별도 처리가 필요하다.
stock_code에 `.O`를 붙여 네이버 티커 형식(`AAPL.O`)으로 변환한다.

### `load_kospi200` (kospi_crawler.py)

```python
reader = csv.DictReader(f)
```

`kospi200_targets.csv`는 첫 줄이 바로 헤더(`stock_code,stock_name`)이므로 별도 처리 없이 `DictReader`로 읽는다.
6자리 숫자 코드를 그대로 사용한다.

---

## 9. NASDAQ vs KOSPI 차이점 요약

| 항목 | nasdaq_crawler.py | kospi_crawler.py |
|------|-------------------|------------------|
| CSV 파일 | `NASDAQ100.csv` | `kospi200_targets.csv` |
| CSV 컬럼 | stock_code, stock_name, stock_name_en | stock_code, stock_name |
| CSV 특이사항 | 첫 줄 `표 1,,` 건너뜀 | 일반 헤더 |
| 티커 변환 | `AAPL` → `AAPL.O` | 변환 없음 (`000660` 그대로) |
| 뉴스 페이지 URL | `/worldstock/stock/{ticker}/localNews` | `/domestic/stock/{code}/news` |
| DB `market` 필드 | `"NASDAQ"` | `"KOSPI"` |
| DB `stock_name_en` | 저장 (영문명) | 없음 |
| DB `news_id` 예시 | `AAPL_015_0001234` | `000660_009_0001234` |
