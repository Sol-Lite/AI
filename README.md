# StockNews 크롤러 프로젝트

MongoDB Atlas(`sollite` DB)에 주식 관련 뉴스를 수집·요약·저장하는 크롤러 모음입니다.

---

## 프로젝트 구조

```
StockNews/
├── News_crawled/               # 시황 뉴스 크롤러 (ollama 요약)
│   ├── Kosdaq_crawler.py       # news2day 마감시황 — 매일 16:30
│   ├── Nasdaq_crawler.py       # 한국경제 오늘장 미리보기 — 매일 08:40
│   ├── config.py               # 인증 정보 (git 제외)
│   └── config.example.py       # 설정 템플릿
│
├── AllNews_crawled/            # 네이버 금융 메인뉴스 크롤러 (KoBART 요약)
│   ├── naver_main_news_crawler.py
│   ├── config.py               # 인증 정보 (git 제외)
│   └── config.example.py
│
└── StockNews_crawled/          # 종목별 뉴스 크롤러 (KoBART 요약)
    ├── naver_stock_news_scraper.py
    ├── summarizer.py
    ├── config.py               # 인증 정보 (git 제외)
    └── config.example.py
```

---

## 크롤러별 상세

### 1. Kosdaq_crawler.py — news2day 마감시황

| 항목        | 내용                                                         |
| ----------- | ------------------------------------------------------------ |
| 소스        | news2day.co.kr REST API (`/rest/search?searchText=마감시황`) |
| 실행        | 매일 **16:30** (KST), `schedule` 라이브러리                  |
| 저장        | `sollite.news` — 실행 시 기존 전체 삭제 후 재삽입            |
| 요약        | ollama `llama3.1:8b` → JSON 구조화                           |
| stock_index | `KOSDAQ`                                                     |

**요약 JSON 스키마**

```json
{
  "date": "2026년 3월 20일",
  "market_event": ["코스피 전일 대비 ..."],
  "sectors": {
    "kospi": ["건설업(+3%대)", ...],
    "kosdaq": ["금속업(+1%대)", ...]
  },
  "stocks": {
    "kospi": { "up": ["삼성전자(+1.2%)", ...], "down": ["..."] },
    "kosdaq": { "up": ["..."], "down": ["..."] }
  },
  "one_line_summary": "한줄 요약"
}
```

---

### 2. Nasdaq_crawler.py — 한국경제 오늘장 미리보기

| 항목        | 내용                                                                 |
| ----------- | -------------------------------------------------------------------- |
| 소스        | 한국경제 검색 (`search.hankyung.com`) → 기사 본문 (`div#articletxt`) |
| 실행        | 매일 **08:40** (KST), `schedule` 라이브러리                          |
| 저장        | `sollite.news` — `news_id` 기준 upsert (중복 저장 방지)              |
| 요약        | ollama `llama3.1:8b` → JSON 구조화                                   |
| stock_index | `NASDAQ`                                                             |

**요약 JSON 스키마**

```json
{
  "date": "2026년 3월 20일",
  "market_event": ["뉴욕 증시 S&P500 -0.27% ..."],
  "market_sentiment": "시장 심리 요약",
  "one_line_summary": "한줄 요약"
}
```

---

### 3. naver_main_news_crawler.py — 네이버 금융 메인뉴스

| 항목      | 내용                                                                       |
| --------- | -------------------------------------------------------------------------- |
| 소스      | 네이버 금융 (`finance.naver.com/news/news_list.naver`, 섹션 101/258/401)   |
| 실행      | **30분** 주기 (`time.sleep`)                                               |
| 저장      | `sollite.news` — `news_id` unique 인덱스, ordered=False 삽입               |
| 요약      | KoBART (`EbanLee/kobart-summary-v3`)                                       |
| 중복 제거 | 배치 내: 제목 SimHash + 본문 Jaccard / DB 대비: news_id + 최근 24h Jaccard |

---

### 4. naver_stock_news_scraper.py — 종목별 뉴스

| 항목      | 내용                                                                 |
| --------- | -------------------------------------------------------------------- |
| 소스      | 네이버 모바일 주식 API (`m.stock.naver.com/api/news/stock/{ticker}`) |
| 실행      | **30분** 주기 (`time.sleep`)                                         |
| 저장      | `sollite.stock_news` — `news_id` unique 인덱스                       |
| 요약      | KoBART (`EbanLee/kobart-summary-v3`)                                 |
| 대상 종목 | KOSPI 200 (`코스피200리스트.xlsx`) + NASDAQ 100 (`Nasdaq-100.xlsx`)  |

---

## MongoDB 컬렉션 스키마

### `sollite.news`

```
news_id         String    기사 고유 ID
title           String    제목
content         String    전처리된 본문
summary         Object    ollama JSON 요약 (또는 KoBART 텍스트)
source          String    "news2day" | "hankyung" | 언론사명
stock_index     String    "KOSDAQ" | "NASDAQ"
source_url      String    원문 URL
published_at    DateTime  기사 게재 시각 (KST 기준, tzinfo 없음)
fetched_at      DateTime  수집 시각
```

### `sollite.stock_news`

```
news_id         String    "{officeId}_{articleId}"
title           String    제목
subtitles       Array     소제목 목록
content         String    전처리된 본문
thumbnail_url   String    대표 이미지 URL
source          String    언론사명
source_url      String    원문 URL
stock_code      String    종목코드 (ex. "005930", "AAPL.O")
stock_name      String    종목명
market          String    "KOSPI" | "NASDAQ"
published_at    DateTime  기사 게재 시각
fetched_at      DateTime  수집 시각
summary         String    KoBART 요약 텍스트
```

---

## ollama JSON 파싱 안정화

`llama3.1:8b`가 긴 응답을 생성하다 토큰 한계에 걸려 JSON이 잘리는 문제를 3단계로 방어합니다.

| 단계       | 방법                               | 효과                                 |
| ---------- | ---------------------------------- | ------------------------------------ |
| 1차 예방   | `content[:4000]` 입력 제한         | 출력 길이 감소 → 잘릴 확률 감소      |
| 2차 예방   | `"options": {"num_predict": 2048}` | 출력 토큰 확보 → JSON 완성 확률 증가 |
| 3차 복구   | `json_repair(raw)`                 | 잘린 JSON 자동 복구 (괄호 닫기 등)   |
| 4차 후처리 | `apply_hamnida(summary)`           | 요약 문장 말투를 `-습니다` 체로 통일 |

---

## 환경 설정

```bash
pip install requests beautifulsoup4 pymongo certifi schedule json-repair
# KoBART 요약 사용 시
pip install transformers torch
# ollama (로컬 설치 후)
ollama pull llama3.1:8b
```

### config.py 설정

각 폴더의 `config.example.py`를 복사해 `config.py`로 만들고 값을 채우세요.

```bash
cp News_crawled/config.example.py News_crawled/config.py
```

```python
# News_crawled/config.py
MONGO_URI = "mongodb+srv://<USERNAME>:<PASSWORD>@<CLUSTER>.mongodb.net/..."
DB_NAME = "sollite"
COLLECTION_NAME = "news"
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.1:8b"
```

> `config.py`는 `.gitignore`에 의해 커밋에서 제외됩니다.

---

## 실행

```bash
# 마감시황 크롤러 (16:30 자동 실행 대기)
python3 News_crawled/Kosdaq_crawler.py

# 오늘장 미리보기 크롤러 (08:40 자동 실행 대기)
python3 News_crawled/Nasdaq_crawler.py

# 네이버 메인뉴스 (30분 주기)
python3 AllNews_crawled/naver_main_news_crawler.py

# 종목별 뉴스 (30분 주기)
python3 StockNews_crawled/naver_stock_news_scraper.py
```
