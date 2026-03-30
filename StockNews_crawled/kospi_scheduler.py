"""
KOSPI200 종목별 최신 뉴스 수집 스케줄러 (30분마다 실행, 종목당 최대 3건)
"""
import csv
import os
import re
import sys
import time

import certifi
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from pymongo import MongoClient
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from Stocknews_final.config import (
    MONGO_URI, DB_NAME, COLLECTION_NAME,
    HEADERS, ARTICLE_URL, MEDIA_KEYWORDS, SCHEDULE_INTERVAL,
)
from Stocknews_final.summarizer import summarize_articles

PC_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://finance.naver.com/'
}
NEWS_LIST_URL = "https://finance.naver.com/item/news_news.naver?code={code}&page={page}&clusterId="

# ── 설정 ──────────────────────────────────────────────────────
TARGET_PER_STOCK = 3   # 1회 사이클당 종목별 최대 저장 건수

# ── MongoDB 연결 ──────────────────────────────────────────────
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

collection.create_index("news_id", unique=True, sparse=True)
collection.create_index([("published_at", -1)])
collection.create_index([("stock_code", 1)])


# ── 본문 전처리 ───────────────────────────────────────────────
_KNOWN_MEDIA_SN = (
    r'뉴시스|뉴스1|연합뉴스|파이낸셜뉴스|헤럴드경제|이데일리|머니투데이'
    r'|한국경제|조선일보|중앙일보|동아일보|한겨레|매일경제|이코노미스트'
    r'|데일리안|더팩트|서울신문|서울경제|아시아경제|아이뉴스|뉴스핌'
)
_LEADING_BYLINE_RE_SN = re.compile(
    r'^(?:'
    r'[\[\(][^\]\)]{1,60}(?:기자|특파원|앵커|논설위원|선임기자|보험전문기자)[\]\)]\s*'
    r'|'
    r'[\[\(][^\]\)]{1,50}[\]\)]\s*[가-힣A-Za-z·\s]{0,20}'
    r'(?:기자|특파원|앵커|보험전문기자|논설위원|선임기자)\s*[=:]?\s*[가-힣]{0,15}\s*'
    r'|'
    r'\[(?:' + _KNOWN_MEDIA_SN + r')\]\s*'
    r')',
    re.DOTALL,
)

def _strip_leading_bylines(text):
    while True:
        m = _LEADING_BYLINE_RE_SN.match(text)
        if not m:
            break
        text = text[m.end():].lstrip()
    return text

def clean_body(text):
    text = _strip_leading_bylines(text)
    text = re.sub(r'^\[[^\]]{1,40}기자\]\s*', '', text)
    text = re.sub(r'^\[[가-힣a-zA-Z=\s]{2,20}\]\s*[가-힣\s]{2,15}기자\s*=\s*', '', text)
    text = re.sub(r'^\([가-힣a-zA-Z0-9=\s]{2,20}\)\s*[가-힣\s]{2,15}기자\s*=\s*', '', text)
    text = re.sub(r'^\[[가-힣a-zA-Z\s=|ㅣ]{2,20}\]\s*', '', text)
    text = re.sub(r'재생\[[^\]]{1,20}\]', '', text)
    text = re.sub(r'◀\s*(앵커|리포트)\s*▶\s*', '', text)
    text = re.sub(r'<\s*(앵커|기자|리포트)\s*>', '', text)
    text = re.sub(r'\[\s*(앵커|리포트|기자)\s*\]', '', text)
    text = re.sub(r'━[^가-힣]*', '', text)
    text = re.sub(r'\(사진[^)]{0,30}\)', '', text)
    text = re.sub(r'\(제공[^)]{0,20}\)', '', text)
    text = re.sub(r'\(표[^)]{0,20}\)', '', text)
    text = re.sub(r'<사진>', '', text)
    text = re.sub(r'\[[^\]]*기자[^\]]*@[^\]]*\]', '', text)
    text = re.sub(r'[가-힣]{2,6}\s*기자\s+[a-zA-Z0-9._+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '', text)
    text = re.sub(r'[a-zA-Z0-9_+-][a-zA-Z0-9._+-]*@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'▶.{0,30}(카카오톡|제보|홈페이지|이메일).{0,100}', '', text)
    text = re.sub(r'[■◆★☆◇○□]+\s*', '', text)
    _SRC = (
        r'제공|SNS|AP|EPA|AFP|로이터|Reuters|게티|Getty'
        r'|뉴시스|뉴스1|연합뉴스|연합|뉴스핌|이데일리|머니투데이'
        r'|한국경제|조선일보|중앙일보|동아일보|한겨레|매일경제|헤럴드경제'
    )
    _pat = r'[^\[]{2,80}\s*\[[^\]]*(?:' + _SRC + r')[^\]]*\]\s*'
    text = re.sub(_pat, ' ', text)
    text = re.sub(r'[가-힣\w·,·\s]{2,60}\[[^\]]{2,40}기자\]\s*', ' ', text)
    text = re.sub(r'\[[^\]]{1,50}기자\]\s*', '', text)
    text = re.sub(r'\[[^\]\|]{1,30}\|[^\]]{1,30}기자\]\s*', '', text)
    text = re.sub(r'\s*사진\s*[|=]\s*[^\s][^.。\n]{0,30}', '', text)
    text = re.sub(r'▲\s*.{0,200}', '', text)
    return re.sub(r'\s+', ' ', text).strip()


# ── 기사 본문 파싱 ────────────────────────────────────────────
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

        def _extract_lines(tag):
            for br in tag.select("br"):
                br.replace_with("\n")
            return [s.strip() for s in tag.get_text(separator="\n").split("\n") if s.strip()]

        subtitles = []
        summary_tag = content.select_one("strong.media_end_summary")
        if summary_tag:
            subtitles += _extract_lines(summary_tag)
            summary_tag.decompose()
        for tag in content.select("div[style*='border-left'], strong[style*='border-left']"):
            for line in _extract_lines(tag):
                if len(line) > 5 and line not in subtitles:
                    subtitles.append(line)
            tag.decompose()
        for b_tag in content.select("b"):
            if b_tag.find_parent(style=lambda s: s and "border-left" in s):
                continue
            text = b_tag.get_text(strip=True)
            if text and len(text) > 5 and text not in subtitles:
                subtitles.append(text)
            b_tag.decompose()
        for tag in content.select("span._PHOTO_VIEWER, em.img_desc"):
            tag.decompose()

        return clean_body(content.get_text(strip=True)), subtitles, thumbnail_url
    except Exception as e:
        print(f"    본문 파싱 실패 ({office_id}/{article_id}): {e}")
    return "", [], ""


# ── 중복 체크 ─────────────────────────────────────────────────
def deduplicate(articles):
    """배치 내 중복 제거 후 DB에 이미 있는 기사 제거, 최대 TARGET_PER_STOCK건만 반환"""
    seen = set()
    unique = []
    for a in articles:
        if a["news_id"] not in seen:
            seen.add(a["news_id"])
            unique.append(a)
    existing = set(
        doc["news_id"] for doc in collection.find(
            {"news_id": {"$in": [a["news_id"] for a in unique]}}, {"news_id": 1}
        )
    )
    new_articles = [a for a in unique if a["news_id"] not in existing]
    return new_articles[:TARGET_PER_STOCK]


# ── 종목별 최신 기사 크롤링 ──────────────────────────────────
def crawl_latest_news(stock):
    """
    finance.naver.com PC 웹 1페이지(약 12건)에서 대표 기사만 수집.
    deduplicate()에서 새 기사 최대 TARGET_PER_STOCK건으로 제한.
    """
    code = stock["stock_code"]
    candidates = []
    seen = set()

    url = NEWS_LIST_URL.format(code=code, page=1)
    try:
        r = requests.get(url, headers=PC_HEADERS, timeout=10)
        r.raise_for_status()
        r.encoding = 'euc-kr'
    except Exception as e:
        print(f"    [{code}] 목록 요청 실패: {e}")
        return []

    soup = BeautifulSoup(r.text, 'html.parser')
    rows = soup.select('tr.relation_tit, tr.hide_news')

    for row in rows:
        tds = row.find_all('td', recursive=False)
        if not tds:
            continue

        a = tds[0].select_one('a')
        if not a:
            continue

        title = a.text.strip()
        if any(kw in title for kw in MEDIA_KEYWORDS):
            continue

        href = a.get('href', '')
        qs = parse_qs(urlparse(href).query)
        office_id = qs.get('office_id', [''])[0]
        article_id = qs.get('article_id', [''])[0]
        if not office_id or not article_id:
            continue

        news_id = f"{code}_{office_id}_{article_id}"
        if news_id in seen:
            continue
        seen.add(news_id)

        date_td = tds[2] if len(tds) >= 3 else None
        pub_dt = None
        if date_td:
            try:
                pub_dt = datetime.strptime(date_td.text.strip(), "%Y.%m.%d %H:%M")
            except ValueError:
                pass

        body, subtitles, thumbnail_url = fetch_article_body(office_id, article_id)

        candidates.append({
            "news_id": news_id,
            "title": title,
            "subtitles": subtitles,
            "content": body,
            "thumbnail_url": thumbnail_url,
            "source": qs.get('office_name', [''])[0],
            "source_url": ARTICLE_URL.format(officeId=office_id, articleId=article_id),
            "stock_code": code,
            "stock_name": stock["stock_name"],
            "stock_name_en": "",
            "market": "KOSPI",
            "published_at": pub_dt or datetime.now(),
            "fetched_at": datetime.now(),
        })
        time.sleep(0.3)

    return candidates


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
            })
    return stocks


# ── 1회 사이클 ────────────────────────────────────────────────
def run_job(stocks):
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 크롤링 사이클 시작 (총 {len(stocks)}종목, 최대 {TARGET_PER_STOCK}건/종목)")
    all_new = []

    for i, stock in enumerate(stocks, 1):
        ticker = stock["ticker"]

        # 1. 최신 기사 수집 (page 1 전체)
        candidates = crawl_latest_news(stock)
        if not candidates:
            print(f"  [{i}/{len(stocks)}] [{ticker}] {stock['stock_name']} — 기사 없음")
            time.sleep(0.5)
            continue

        # 2. 중복 제거 → 새 기사 최대 3건
        new_articles = deduplicate(candidates)
        if not new_articles:
            print(f"  [{i}/{len(stocks)}] [{ticker}] {stock['stock_name']} — 새 기사 없음")
            time.sleep(0.5)
            continue

        # 3. 요약
        new_articles = summarize_articles(new_articles)

        # 4. 저장
        try:
            result = collection.insert_many(new_articles, ordered=False)
            saved = len(result.inserted_ids)
        except Exception as e:
            saved = getattr(e, "details", {}).get("nInserted", 0)

        all_new.extend(new_articles)
        print(f"  [{i}/{len(stocks)}] [{ticker}] {stock['stock_name']} — {saved}건 저장")
        time.sleep(0.5)

    print(f"사이클 완료. 총 신규 기사: {len(all_new)}건")


# ── 메인 ─────────────────────────────────────────────────────
if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    stocks = load_kospi200(os.path.join(base_dir, "kospi200_targets.csv"))

    print(f"KOSPI {len(stocks)}종목 — 30분 주기 크롤링 시작 (종목당 최대 {TARGET_PER_STOCK}건)")

    while True:
        try:
            run_job(stocks)
        except Exception as e:
            print(f"루프 에러: {e}")
        print(f"{SCHEDULE_INTERVAL // 60}분 대기 중...")
        time.sleep(SCHEDULE_INTERVAL)
