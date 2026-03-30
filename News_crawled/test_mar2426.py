"""
2026-03-24 ~ 2026-03-26 시황 뉴스 수집 테스트 스크립트
- Kosdaq: news2day.co.kr 마감시황 (3일치)
- Nasdaq: hankyung.com 오늘장 미리보기 (3일치)
기존 데이터 삭제 없이 upsert로 저장합니다.
"""

import json
import re
import time
import html as html_module
from json_repair import repair_json

import certifi
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta, date
from pymongo import MongoClient
from config import MONGO_URI, DB_NAME, COLLECTION_NAME, OLLAMA_URL, OLLAMA_MODEL

KST = timezone(timedelta(hours=9))

DATE_FROM = date(2026, 3, 24)
DATE_TO   = date(2026, 3, 26)

# ── MongoDB ───────────────────────────────────────────────────
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client[DB_NAME]
collection = db[COLLECTION_NAME]


# ═══════════════════════════════════════════════════════════════
# 공통 유틸
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


def _to_hamnida(text: str) -> str:
    pairs = [
        (r'했다\.', '했습니다.'), (r'됐다\.', '됐습니다.'),
        (r'았다\.', '았습니다.'), (r'었다\.', '었습니다.'),
        (r'겠다\.', '겠습니다.'), (r'였다\.', '였습니다.'),
        (r'왔다\.', '왔습니다.'), (r'갔다\.', '갔습니다.'),
        (r'났다\.', '났습니다.'), (r'랐다\.', '랐습니다.'),
        (r'쳤다\.', '쳤습니다.'), (r'볐다\.', '볐습니다.'),
        (r'이다\.', '입니다.'),   (r'한다\.', '합니다.'),
        (r'된다\.', '됩니다.'),   (r'진다\.', '집니다.'),
        (r'린다\.', '립니다.'),   (r'킨다\.', '킵니다.'),
        (r'했다$', '했습니다.'),  (r'됐다$', '됐습니다.'),
        (r'았다$', '았습니다.'),  (r'었다$', '었습니다.'),
        (r'겠다$', '겠습니다.'),  (r'이다$', '입니다.'),
        (r'한다$', '합니다.'),    (r'된다$', '됩니다.'),
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


def date_range(start: date, end: date):
    """start ~ end 날짜 리스트 반환"""
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


# ═══════════════════════════════════════════════════════════════
# KOSDAQ — news2day.co.kr
# ═══════════════════════════════════════════════════════════════
KOSDAQ_SEARCH_API = "https://www.news2day.co.kr/rest/search"
KOSDAQ_ARTICLE_BASE = "https://www.news2day.co.kr"
KOSDAQ_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://www.news2day.co.kr/search?searchText=%EB%A7%88%EA%B0%90%EC%8B%9C%ED%99%A9",
}


def parse_kosdaq_html(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup.select("figure#id_div_main, figure.class_div_main, figure, figcaption"):
        tag.decompose()
    for tag in soup.select("script, style, iframe, ins"):
        tag.decompose()
    return clean_text(soup.get_text(" ", strip=True))


def summarize_kosdaq(content: str, published_at: datetime = None) -> dict:
    if len(content) < 50:
        return {}
    content = content[:4000]
    date_str = (published_at or datetime.now()).strftime("%Y년 %m월 %d일")
    prompt = f"""아래 [기사 내용]을 읽고 분석하여 JSON을 출력하세요.
주의사항:
- [출력 예시]는 형식만 보여주는 가짜 데이터입니다. 예시의 수치, 종목, 업종, 문장을 절대 그대로 사용하지 마세요.
- 반드시 [기사 내용]에 실제로 등장하는 수치, 종목명, 업종명만 사용하세요.
- market_event와 one_line_summary의 모든 문장은 반드시 '~했습니다.', '~됩니다.', '~입니다.' 형태로 끝내세요.
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

[기사 내용]
{content}

위 기사를 분석해 {date_str} 기준 JSON을 출력하세요."""

    try:
        r = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "format": "json",
                  "stream": False, "options": {"num_predict": 2048}},
            timeout=180,
        )
        r.raise_for_status()
        raw = r.json().get("response", "{}")
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            result = json.loads(repair_json(raw))
        return apply_hamnida(result)
    except Exception as e:
        print(f"  [Kosdaq] ollama 요약 실패: {e}")
        return {}


def fetch_kosdaq_articles(date_from: date, date_to: date) -> list:
    from_str = date_from.strftime("%Y-%m-%d")
    to_str   = date_to.strftime("%Y-%m-%d")
    articles = []
    page = 1

    print(f"\n[Kosdaq] news2day 마감시황 수집: {from_str} ~ {to_str}")

    while True:
        params = {
            "searchText": "마감시황",
            "searchType": "all",
            "from": from_str,
            "to": to_str,
            "page": page,
            "sort": "latest",
        }
        try:
            r = requests.get(KOSDAQ_SEARCH_API, params=params,
                             headers=KOSDAQ_HEADERS, timeout=15)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"  API 요청 실패 (page={page}): {e}")
            break

        items = data.get("list", [])
        total_pages = data.get("pages", {}).get("totalPages", 0)
        total_count = data.get("pages", {}).get("totalElements", 0)

        if page == 1:
            print(f"  검색 결과: 총 {total_count}건 ({total_pages}페이지)")

        if not items:
            break

        for item in items:
            article_id = item.get("id", "")
            title = item.get("title", "").strip()
            raw_html = item.get("content", "")
            link = item.get("link", "")
            release_date_str = item.get("releaseDate") or item.get("firstReleaseDate", "")

            published_at = datetime.now(KST).replace(tzinfo=None)
            if release_date_str:
                try:
                    dt_utc = datetime.strptime(release_date_str[:19], "%Y-%m-%dT%H:%M:%S")
                    dt_utc = dt_utc.replace(tzinfo=timezone.utc)
                    published_at = dt_utc.astimezone(KST).replace(tzinfo=None)
                except ValueError:
                    pass

            if not raw_html:
                continue
            content = parse_kosdaq_html(raw_html)
            if len(content) < 50:
                continue

            articles.append({
                "news_id": str(article_id),
                "title": title,
                "content": content,
                "source": "news2day",
                "stock_index": "KOSDAQ",
                "source_url": KOSDAQ_ARTICLE_BASE + link if link else "",
                "published_at": published_at,
            })

        if page >= total_pages:
            break
        page += 1
        time.sleep(0.3)

    return articles


def run_kosdaq():
    articles = fetch_kosdaq_articles(DATE_FROM, DATE_TO)
    print(f"  유효 기사: {len(articles)}건")

    if not articles:
        print("  저장할 기사 없음")
        return

    saved = 0
    for article in articles:
        print(f"  요약 중: {article['title'][:50]}")
        summary = summarize_kosdaq(article["content"], article.get("published_at"))
        doc = {**article, "summary": summary, "fetched_at": datetime.now()}
        collection.update_one(
            {"news_id": doc["news_id"]},
            {"$set": doc},
            upsert=True,
        )
        saved += 1
        print(f"  저장: {article['title'][:50]}")

    print(f"[Kosdaq] 완료 — {saved}건 저장(upsert)")


# ═══════════════════════════════════════════════════════════════
# NASDAQ — hankyung.com 오늘장 미리보기
# ═══════════════════════════════════════════════════════════════
NASDAQ_SEARCH_URL = "https://search.hankyung.com/search/total"
NASDAQ_SEARCH_QUERY = "[오늘장 미리보기]"
NASDAQ_ARTICLE_BASE = "https://www.hankyung.com"
NASDAQ_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://search.hankyung.com/",
}


def fetch_nasdaq_article_meta(target_date: date) -> dict | None:
    """hankyung 검색 결과에서 특정 날짜 기사 첫 건 반환"""
    target_str = target_date.strftime("%Y.%m.%d")

    try:
        r = requests.get(
            NASDAQ_SEARCH_URL,
            params={"query": NASDAQ_SEARCH_QUERY},
            headers=NASDAQ_HEADERS,
            timeout=15,
        )
        r.raise_for_status()
    except Exception as e:
        print(f"  [Nasdaq] 검색 요청 실패: {e}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    items = soup.select("ul.article > li")

    if not items:
        print(f"  [Nasdaq] 검색 결과 없음")
        return None

    for item in items:
        date_tag = item.select_one(".date, span[class*='date'], time")
        if not date_tag:
            continue
        date_text = date_tag.get_text(strip=True)
        if target_str not in date_text:
            continue

        a_tag = item.select_one("a[href*='/article/']")
        if not a_tag:
            continue
        url = a_tag.get("href", "")
        if not url.startswith("http"):
            url = NASDAQ_ARTICLE_BASE + url

        tit_tag = item.select_one(".tit, h2, h3")
        title = tit_tag.get_text(strip=True) if tit_tag else a_tag.get_text(strip=True)
        news_id = url.rstrip("/").split("/")[-1]

        published_at = datetime.now(KST).replace(tzinfo=None)
        try:
            published_at = datetime.strptime(date_text.strip(), "%Y.%m.%d %H:%M")
        except ValueError:
            pass

        return {"news_id": news_id, "title": title, "url": url, "published_at": published_at}

    print(f"  [Nasdaq] {target_str} 기사 없음")
    return None


def fetch_nasdaq_content(url: str) -> str:
    try:
        r = requests.get(url, headers=NASDAQ_HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        body = soup.select_one("div#articletxt")
        if not body:
            return ""
        for tag in body.select(
            "figure.article-figure, figcaption.figure-caption, "
            "figure, figcaption, script, style, iframe, "
            ".related-article, .box_related, .article-ad"
        ):
            tag.decompose()
        return clean_text(body.get_text(" ", strip=True))
    except Exception as e:
        print(f"  [Nasdaq] 본문 파싱 실패 ({url}): {e}")
        return ""


def summarize_nasdaq(content: str, published_at: datetime = None) -> dict:
    if len(content) < 50:
        return {}
    content = content[:4000]
    date_str = (published_at or datetime.now()).strftime("%Y년 %m월 %d일")
    prompt = f"""아래 [기사 내용]을 읽고 분석하여 JSON을 출력하세요.
주의사항:
- [출력 예시]는 형식만 보여주는 가짜 데이터입니다. 예시의 수치, 종목, 문장을 절대 그대로 사용하지 마세요.
- 반드시 [기사 내용]에 실제로 등장하는 수치, 내용만 사용하세요.
- 모든 문장은 반드시 '~했습니다.', '~됩니다.', '~입니다.' 형태로 끝내세요.
- 모든 텍스트는 반드시 한국어(한글)로만 작성하세요. 한자(漢字)는 절대 사용하지 마세요. 예: '운수업종' (O), '運輸업종' (X)
- 설명이나 마크다운 없이 JSON만 출력하세요.

[JSON 스키마]
{{
  "date": "날짜 문자열",
  "market_event": ["이벤트1", "이벤트2", ...],
  "market_sentiment": "시장 심리 요약",
  "one_line_summary": "한줄 요약"
}}

[기사 내용]
{content}

위 기사를 분석해 {date_str} 기준 JSON을 출력하세요."""

    try:
        r = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "format": "json",
                  "stream": False, "options": {"num_predict": 2048}},
            timeout=180,
        )
        r.raise_for_status()
        raw = r.json().get("response", "{}")
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            result = json.loads(repair_json(raw))
        return apply_hamnida(result)
    except Exception as e:
        print(f"  [Nasdaq] ollama 요약 실패: {e}")
        return {}


def run_nasdaq():
    print(f"\n[Nasdaq] hankyung 오늘장 미리보기 수집: {DATE_FROM} ~ {DATE_TO}")
    saved = 0

    for d in date_range(DATE_FROM, DATE_TO):
        print(f"\n  날짜: {d.strftime('%Y-%m-%d')}")
        meta = fetch_nasdaq_article_meta(d)
        if not meta:
            continue

        print(f"  기사: {meta['title'][:50]}")

        existing = collection.find_one({"news_id": meta["news_id"]})
        if existing and existing.get("summary"):
            print(f"  이미 저장된 기사(요약 완료) — 스킵")
            continue

        content = fetch_nasdaq_content(meta["url"])
        if len(content) < 50:
            print(f"  본문 없음 — 스킵")
            continue

        print(f"  요약 중...")
        summary = summarize_nasdaq(content, meta.get("published_at"))

        doc = {
            "news_id": meta["news_id"],
            "title": meta["title"],
            "content": content,
            "summary": summary,
            "source": "hankyung",
            "stock_index": "NASDAQ",
            "source_url": meta["url"],
            "published_at": meta["published_at"],
            "fetched_at": datetime.now(),
        }
        collection.update_one(
            {"news_id": meta["news_id"]},
            {"$set": doc},
            upsert=True,
        )
        saved += 1
        print(f"  저장 완료")
        time.sleep(1)

    print(f"[Nasdaq] 완료 — {saved}건 저장(upsert)")


# ═══════════════════════════════════════════════════════════════
# 메인
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print(f"=== 수집 기간: {DATE_FROM} ~ {DATE_TO} ===\n")
    run_kosdaq()
    run_nasdaq()

    # DB 확인
    count = collection.count_documents({
        "published_at": {
            "$gte": datetime(2026, 3, 24),
            "$lt":  datetime(2026, 3, 27),
        }
    })
    print(f"\nDB 내 2026-03-24~26 기사 총계: {count}건")
