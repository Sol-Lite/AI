"""
news2day.co.kr 마감시황 크롤러
API: https://www.news2day.co.kr/rest/search?searchText=마감시황&searchType=all&from=YYYY-MM-DD&to=YYYY-MM-DD&page=1&sort=latest
- 매일 16:30 실행
- 오늘 날짜 기사만 수집
- <figure id="id_div_main"> / figcaption 내용 제외
- 텍스트 전처리 (특수문자 등)
- ollama llama3.1:8b 요약
- MongoDB sollite.news 저장 (기존 데이터 전체 삭제 후 삽입)
"""

import json
import re
import time
import html as html_module
from json_repair import repair_json

import certifi
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient

from app.core.config import MONGO_URI
from app.core.llm import generate_json_content, get_provider_name

# ── 크롤링 설정 ───────────────────────────────────────────────
SEARCH_API_URL   = "https://www.news2day.co.kr/rest/search"
ARTICLE_BASE_URL = "https://www.news2day.co.kr"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://www.news2day.co.kr/search?searchText=%EB%A7%88%EA%B0%90%EC%8B%9C%ED%99%A9",
}

KST = timezone(timedelta(hours=9))

# ── MongoDB 연결 ──────────────────────────────────────────────
client     = MongoClient(MONGO_URI)
collection = client["sollite"]["news"]


# ═══════════════════════════════════════════════════════════════
# 텍스트 전처리
# ═══════════════════════════════════════════════════════════════
def clean_text(text: str) -> str:
    text = html_module.unescape(text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'[a-zA-Z0-9._+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '', text)
    text = re.sub(r'\[[^\]]{1,50}기자\]\s*', '', text)
    text = re.sub(r'\([^\)]{1,50}기자\)\s*', '', text)
    text = re.sub(r'[가-힣]{2,6}\s*기자\s*[=:]\s*', '', text)
    text = re.sub(r'ⓒ[^\n.。]{0,60}', '', text)
    text = re.sub(r'©[^\n.。]{0,60}', '', text)
    text = re.sub(r'무단\s*전재[^\n.。]{0,60}', '', text)
    text = re.sub(r'[■◆★☆◇○□◎▶▷◀◁△▽▲▼●◉]+\s*', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def parse_html_content(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup.select("figure#id_div_main, figure.class_div_main, figure, figcaption"):
        tag.decompose()
    for tag in soup.select("script, style, iframe, ins"):
        tag.decompose()
    raw = soup.get_text(" ", strip=True)
    return clean_text(raw)


# ═══════════════════════════════════════════════════════════════
# 요약 말투 후처리 (-다 → -습니다)
# ═══════════════════════════════════════════════════════════════
def _to_hamnida(text: str) -> str:
    pairs = [
        # 과거형 동사 (-았/었/했/됐... + 다)
        (r'했다\.', '했습니다.'), (r'됐다\.', '됐습니다.'),
        (r'았다\.', '았습니다.'), (r'었다\.', '었습니다.'),
        (r'겠다\.', '겠습니다.'), (r'였다\.', '였습니다.'),
        (r'왔다\.', '왔습니다.'), (r'갔다\.', '갔습니다.'),
        (r'났다\.', '났습니다.'), (r'랐다\.', '랐습니다.'),
        (r'쳤다\.', '쳤습니다.'), (r'볐다\.', '볐습니다.'),
        # 현재형 동사 (-ㄴ다/는다)
        (r'이다\.', '입니다.'),   (r'한다\.', '합니다.'),
        (r'된다\.', '됩니다.'),   (r'진다\.', '집니다.'),
        (r'린다\.', '립니다.'),   (r'킨다\.', '킵니다.'),
        (r'인다\.', '입니다.'),   (r'는다\.', '습니다.'),
        (r'않는다\.', '않습니다.'),
        # 형용사/보조용언
        (r'있다\.', '있습니다.'), (r'없다\.', '없습니다.'),
        (r'않다\.', '않습니다.'),
        (r'높다\.', '높습니다.'), (r'낮다\.', '낮습니다.'),
        (r'크다\.', '큽니다.'),   (r'작다\.', '작습니다.'),
        (r'같다\.', '같습니다.'), (r'맞다\.', '맞습니다.'),
        (r'좋다\.', '좋습니다.'), (r'나쁘다\.', '나쁩니다.'),
        # 문장 끝($) 버전 — 마침표 없이 끝나는 경우
        (r'했다$', '했습니다.'),  (r'됐다$', '됐습니다.'),
        (r'았다$', '았습니다.'),  (r'었다$', '었습니다.'),
        (r'겠다$', '겠습니다.'),  (r'이다$', '입니다.'),
        (r'한다$', '합니다.'),    (r'된다$', '됩니다.'),
        (r'있다$', '있습니다.'),  (r'없다$', '없습니다.'),
        (r'않다$', '않습니다.'),  (r'높다$', '높습니다.'),
        (r'낮다$', '낮습니다.'),  (r'같다$', '같습니다.'),
    ]
    for pattern, replacement in pairs:
        text = re.sub(pattern, replacement, text)
    return text


def apply_hamnida(summary: dict) -> dict:
    if not summary:
        return summary
    if isinstance(summary.get("market_event"), list):
        summary["market_event"] = [_to_hamnida(s) for s in summary["market_event"]]
    if isinstance(summary.get("one_line_summary"), str):
        summary["one_line_summary"] = _to_hamnida(summary["one_line_summary"])
    if isinstance(summary.get("market_sentiment"), str):
        summary["market_sentiment"] = _to_hamnida(summary["market_sentiment"])
    return summary


# ═══════════════════════════════════════════════════════════════
# REST API로 오늘 기사 목록 수집
# ═══════════════════════════════════════════════════════════════
def fetch_today_articles() -> list:
    today_kst = datetime.now(KST).strftime("%Y-%m-%d")
    articles = []
    page = 1

    while True:
        params = {
            "searchText": "마감시황",
            "searchType": "all",
            "from": today_kst,
            "to": today_kst,
            "page": page,
            "sort": "latest",
        }
        try:
            r = requests.get(SEARCH_API_URL, params=params, headers=HEADERS, timeout=15)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"  API 요청 실패 (page={page}): {e}")
            break

        items       = data.get("list", [])
        total_pages = data.get("pages", {}).get("totalPages", 0)
        total_count = data.get("pages", {}).get("totalElements", 0)

        if page == 1:
            print(f"  검색 결과: 총 {total_count}건 ({total_pages}페이지)")

        if not items:
            break

        for item in items:
            article_id       = item.get("id", "")
            title            = item.get("title", "").replace("[마감시황]", "").replace("(마감시황)", "").strip()
            raw_html         = item.get("content", "")
            link             = item.get("link", "")
            release_date_str = item.get("releaseDate") or item.get("firstReleaseDate", "")

            published_at = datetime.now(KST).replace(tzinfo=None)
            if release_date_str:
                try:
                    dt_utc       = datetime.strptime(release_date_str[:19], "%Y-%m-%dT%H:%M:%S")
                    dt_utc       = dt_utc.replace(tzinfo=timezone.utc)
                    published_at = dt_utc.astimezone(KST).replace(tzinfo=None)
                except ValueError:
                    pass

            if not raw_html:
                continue
            content = parse_html_content(raw_html)
            if len(content) < 50:
                continue

            articles.append({
                "news_id":     article_id,
                "title":       title,
                "content":     content,
                "source":      "news2day",
                "stock_index": "KOSDAQ",
                "source_url":  ARTICLE_BASE_URL + link if link else "",
                "published_at": published_at,
            })

        if page >= total_pages:
            break
        page += 1
        time.sleep(0.3)

    return articles


# ═══════════════════════════════════════════════════════════════
# SageMaker 요약
# ═══════════════════════════════════════════════════════════════
def summarize_with_ollama(content: str, published_at: datetime = None) -> dict:
    if len(content) < 50:
        return {}
    content  = content[:4000]
    date_str = (published_at or datetime.now()).strftime("%Y년 %m월 %d일")

    prompt = f"""아래 [기사 내용]을 읽고 분석하여 JSON을 출력하세요.
주의사항:
- [출력 예시]는 형식만 보여주는 가짜 데이터입니다. 예시의 수치, 종목, 업종, 문장을 절대 그대로 사용하지 마세요.
- 반드시 [기사 내용]에 실제로 등장하는 수치, 종목명, 업종명만 사용하세요.
- market_event와 one_line_summary의 모든 문장은 반드시 '~했습니다.', '~됩니다.', '~입니다.' 형태로 끝내세요. '~했다.', '~됐다.', '~이다.' 형태는 절대 사용하지 마세요.
- 모든 텍스트는 반드시 한국어(한글)로만 작성하세요. 한자(漢字)는 절대 사용하지 마세요. 예: '운수업종' (O), '運輸업종' (X)
- 설명이나 마크다운 없이 JSON만 출력하세요.

[JSON 스키마]
{{
  "date": "날짜 문자열",
  "market_event": ["이벤트1", "이벤트2", ...],
  "sectors": {{
    "kospi": ["상승 업종1(등락률)", ...],
    "kosdaq": ["상승 업종1(등락률)", ...]
  }},
  "stocks": {{
    "kospi": {{"up": ["종목(등락률)", ...], "down": ["종목(등락률)", ...]}},
    "kosdaq": {{"up": ["종목(등락률)", ...], "down": ["종목(등락률)", ...]}}
  }},
  "one_line_summary": "한줄 요약"
}}

[출력 예시]
{{
  "date": "2026년 3월 20일",
  "market_event": [
    "코스피 지수는 전 거래일 대비 50.13포인트(0.87%) 상승한 5813.35로 마감했습니다.",
    "국제 유가 하락과 원/달러 환율 하락(1492원, 전일 대비 9원 하락)이 상승을 뒷받침했습니다.",
    "이란 전쟁 조기 종전 가능성에 대한 기대감이 지정학적 긴장 완화로 이어졌습니다."
  ],
  "sectors": {{
    "kospi": ["건설업(+3%대)", "화학·유통업(+2%대)", "전기·가스업·증권업(+1%대)"],
    "kosdaq": ["건설업(+4%대)", "금속·운송창고업(+1%대)"]
  }},
  "stocks": {{
    "kospi": {{
      "up": ["삼성전자(+0.12%)", "SK하이닉스(+0.39%)", "LG에너지솔루션(+1.48%)"],
      "down": ["한화에어로스페이스(-2.76%)"]
    }},
    "kosdaq": {{
      "up": ["에코프로(+0.99%)", "펩트론(+3.31%)", "에이비엘바이오(+1.68%)"],
      "down": ["리노공업(-4.10%)", "알테오젠(-0.83%)"]
    }}
  }},
  "one_line_summary": "국제유가 하락과 환율 안정, 지정학적 리스크 완화 기대감으로 코스피·코스닥 모두 상승했으며, 건설 및 화학 업종이 주도적인 상승을 기록했습니다."
}}

[기사 내용]
{content}

    위 기사를 분석해 {date_str} 기준 JSON을 출력하세요."""

    try:
        raw = generate_json_content(prompt, temperature=0.1, max_tokens=2048)
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            result = json.loads(repair_json(raw))
        return apply_hamnida(result)
    except Exception as e:
        print(f"  {get_provider_name()} 요약 실패: {e}")
        return {}


# ═══════════════════════════════════════════════════════════════
# 1회 크롤링 사이클
# ═══════════════════════════════════════════════════════════════
def run_job() -> None:
    print(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}] 크롤링 시작 — news2day 마감시황")

    articles = fetch_today_articles()
    print(f"  유효 기사: {len(articles)}건")

    if not articles:
        print("  저장할 기사 없음 — 종료")
        return

    docs = []
    for i, article in enumerate(articles, 1):
        print(f"  [{i}/{len(articles)}] 요약 중: {article['title'][:45]}")
        summary = summarize_with_ollama(article["content"], article.get("published_at"))
        docs.append({
            **article,
            "summary":    summary,
            "fetched_at": datetime.now(),
        })

    for doc in docs:
        collection.update_one(
            {"news_id": doc["news_id"]},
            {"$set": doc},
            upsert=True,
        )
    print(f"  MongoDB 저장 완료: {len(docs)}건")
