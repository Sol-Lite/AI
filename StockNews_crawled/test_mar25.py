"""
최신 뉴스 수집 테스트 스크립트
각 종목별 최신 뉴스 5건을 수집·요약해 DB에 저장하고 결과를 출력합니다.
"""

import csv
import html
import os
import re
import sys
import time

import certifi
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from pymongo import MongoClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    MONGO_URI, DB_NAME, COLLECTION_NAME,
    HEADERS, NEWS_API_URL, ARTICLE_URL,
    MEDIA_KEYWORDS,
)
from summarizer import summarize_articles

TARGET_PER_STOCK = 3

# ── MongoDB ───────────────────────────────────────────────────
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

collection.create_index("news_id", unique=True, sparse=True)
collection.create_index([("published_at", -1)])
collection.create_index([("stock_code", 1)])


# ── 종목 로드 ─────────────────────────────────────────────────
def load_kospi200(filepath):
    stocks = []
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = str(row["stock_code"]).zfill(6)
            stocks.append({
                "ticker": code,
                "stock_code": code,
                "stock_name": row["stock_name"],
                "stock_name_en": "",
                "market": "KOSPI",
            })
    return stocks


def load_nasdaq100(filepath):
    stocks = []
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader)  # 1행 메타(표 1) 스킵
        headers = next(reader)  # 2행 헤더
        code_idx = headers.index("stock_code")
        name_idx = headers.index("stock_name")
        name_en_idx = headers.index("stock_name_en")
        for row in reader:
            if not row[code_idx]:
                continue
            stocks.append({
                "ticker": f"{row[code_idx]}.O",
                "stock_code": row[code_idx],
                "stock_name": row[name_idx],
                "stock_name_en": row[name_en_idx],
                "market": "NASDAQ",
            })
    return stocks


# ── 본문 파싱 ─────────────────────────────────────────────────
_KNOWN_MEDIA_SN = (
    r'뉴시스|뉴스1|연합뉴스|파이낸셜뉴스|헤럴드경제|이데일리|머니투데이'
    r'|한국경제|조선일보|중앙일보|동아일보|한겨레|매일경제|이코노미스트'
    r'|데일리안|더팩트|서울신문|서울경제|아시아경제|아이뉴스|뉴스핌'
)
_LEADING_BYLINE_RE = re.compile(
    r'^(?:'
    r'[\[\(][^\]\)]{1,60}(?:기자|특파원|앵커|논설위원|선임기자|보험전문기자)[\]\)]\s*'
    r'|[\[\(][^\]\)]{1,50}[\]\)]\s*[가-힣A-Za-z·\s]{0,20}'
    r'(?:기자|특파원|앵커|보험전문기자|논설위원|선임기자)\s*[=:]?\s*[가-힣]{0,15}\s*'
    r'|\[(?:' + _KNOWN_MEDIA_SN + r')\]\s*'
    r')',
    re.DOTALL,
)


def _strip_leading_bylines(text):
    while True:
        m = _LEADING_BYLINE_RE.match(text)
        if not m:
            break
        text = text[m.end():].lstrip()
    return text


def clean_body(text):
    text = _strip_leading_bylines(text)
    text = re.sub(r'^\[[^\]]{1,40}기자\]\s*', '', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'▶.{0,30}(카카오톡|제보|홈페이지|이메일).{0,100}', '', text)
    text = re.sub(r'[■◆★☆◇○□]+\s*', '', text)
    text = re.sub(r'\[[^\]]*기자[^\]]*@[^\]]*\]', '', text)
    text = re.sub(r'[가-힣]{2,6}\s*기자\s+[a-zA-Z0-9._+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '', text)
    text = re.sub(r'[a-zA-Z0-9_+-][a-zA-Z0-9._+-]*@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '', text)
    return re.sub(r'\s+', ' ', text).strip()


def fetch_article_body(office_id, article_id):
    url = ARTICLE_URL.format(officeId=office_id, articleId=article_id)
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        og_image = soup.select_one('meta[property="og:image"]')
        thumbnail_url = og_image["content"] if og_image else ""
        content = soup.select_one("div#dic_area") or soup.select_one("div.newsct_article")
        if not content:
            return "", [], thumbnail_url
        subtitles = []
        summary_tag = content.select_one("strong.media_end_summary")
        if summary_tag:
            for br in summary_tag.select("br"):
                br.replace_with("\n")
            subtitles += [s.strip() for s in summary_tag.get_text(separator="\n").split("\n") if s.strip()]
            summary_tag.decompose()
        for tag in content.select("span._PHOTO_VIEWER, em.img_desc"):
            tag.decompose()
        return clean_body(content.get_text(strip=True)), subtitles, thumbnail_url
    except Exception as e:
        print(f"    본문 파싱 실패 ({office_id}/{article_id}): {e}")
    return "", [], ""


# ── 최신 뉴스 크롤링 ──────────────────────────────────────────
def crawl_latest(stock, target=TARGET_PER_STOCK):
    ticker = stock["ticker"]
    valid = []
    seen = set()
    page = 1

    while len(valid) < target:
        url = NEWS_API_URL.format(ticker=ticker, page_size=target, page=page)
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"    [{ticker}] API 실패 (page {page}): {e}")
            break

        if not data or "items" not in data[0] or not data[0]["items"]:
            break

        items = data[0]["items"]

        for item in items:
            if len(valid) >= target:
                break

            title = html.unescape(item.get("titleFull") or item.get("title", ""))
            if any(kw in title for kw in MEDIA_KEYWORDS):
                continue

            office_id = item.get("officeId", "")
            article_id = item.get("articleId", "")
            news_id = f"{office_id}_{article_id}"

            if news_id in seen:
                continue
            seen.add(news_id)

            body, subtitles, thumbnail_url = fetch_article_body(office_id, article_id)
            if len(body) < 50:
                time.sleep(0.3)
                continue

            link = ARTICLE_URL.format(officeId=office_id, articleId=article_id)
            valid.append({
                "news_id": news_id,
                "title": title,
                "subtitles": subtitles,
                "content": body,
                "thumbnail_url": thumbnail_url,
                "source": item.get("officeName", ""),
                "source_url": link,
                "stock_code": stock["stock_code"],
                "stock_name": stock["stock_name"],
                "stock_name_en": stock["stock_name_en"],
                "market": stock["market"],
                "published_at": datetime.strptime(item["datetime"], "%Y%m%d%H%M")
                                if item.get("datetime") else datetime.now(),
                "fetched_at": datetime.now(),
            })
            time.sleep(0.3)

        if len(items) < target:
            break
        page += 1

    return valid


# ── 중복 제거 ─────────────────────────────────────────────────
def deduplicate(articles):
    seen = set()
    unique = [a for a in articles if not (a["news_id"] in seen or seen.add(a["news_id"]))]
    news_ids = [a["news_id"] for a in unique]
    existing = set(
        doc["news_id"] for doc in collection.find({"news_id": {"$in": news_ids}}, {"news_id": 1})
    )
    return [a for a in unique if a["news_id"] not in existing]


# ── 메인 ─────────────────────────────────────────────────────
if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    kospi_stocks = load_kospi200(os.path.join(base_dir, "kospi200_targets.csv"))
    nasdaq_stocks = load_nasdaq100(os.path.join(base_dir, "NASDAQ100.csv"))
    all_stocks = kospi_stocks + nasdaq_stocks

    print(f"대상: KOSPI {len(kospi_stocks)}종목 + NASDAQ {len(nasdaq_stocks)}종목 = 총 {len(all_stocks)}종목")
    print(f"종목당 최신 {TARGET_PER_STOCK}건 수집\n")

    total_saved = 0
    total_dup = 0

    for stock in all_stocks:
        ticker = stock["ticker"]
        candidates = crawl_latest(stock)

        if not candidates:
            print(f"  [{ticker}] {stock['stock_name']} — 기사 없음")
            continue

        new_articles = deduplicate(candidates)
        dup_count = len(candidates) - len(new_articles)

        if not new_articles:
            print(f"  [{ticker}] {stock['stock_name']} — {dup_count}건 모두 중복")
            continue

        new_articles = summarize_articles(new_articles)

        try:
            collection.insert_many(new_articles, ordered=False)
            total_saved += len(new_articles)
            total_dup += dup_count
            print(f"  [{ticker}] {stock['stock_name']} — {len(new_articles)}건 저장 (중복 {dup_count}건 제외)")
        except Exception as e:
            print(f"  [{ticker}] {stock['stock_name']} — 저장 실패: {e}")

        time.sleep(0.5)

    print(f"\n=== 완료 ===")
    print(f"총 저장: {total_saved}건  |  중복 제외: {total_dup}건")
    print(f"DB 총 문서 수: {collection.count_documents({})}건")
