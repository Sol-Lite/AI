"""
NASDAQ100 네이버 세계 주식 뉴스 크롤러
- CSV: NASDAQ100.csv (stock_code, stock_name, stock_name_en)
- URL: https://m.stock.naver.com/worldstock/stock/{TICKER}.O/localNews
- 종목당 최신 20건 수집 → MongoDB 저장
"""
import csv
import html
import json
import os
import re
import sys
import time

import certifi
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from pymongo import MongoClient

_base = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _base)
sys.path.insert(0, os.path.join(_base, '..', 'StockNews_crawled'))
from config import MONGO_URI, DB_NAME, COLLECTION_NAME
from summarizer import summarize_articles

MOBILE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15',
    'Referer': 'https://m.stock.naver.com/',
}
PC_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
}

NEWS_API_URL = "https://m.stock.naver.com/api/news/stock/{ticker}?pageSize={page_size}&page={page}"
LOCAL_NEWS_URL = "https://m.stock.naver.com/worldstock/stock/{ticker}/localNews"
ARTICLE_URL = "https://n.news.naver.com/mnews/article/{officeId}/{articleId}"

MEDIA_KEYWORDS = ["[포토]", "[사진]", "[동영상]", "[비디오]", "[포토뉴스]", "[영상]"]

# ── MongoDB 연결 ──────────────────────────────────────────────
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

collection.create_index("news_id", unique=True, sparse=True)
collection.create_index([("published_at", -1)])
collection.create_index([("stock_code", 1)])


# ── 본문 전처리 ───────────────────────────────────────────────
_KNOWN_MEDIA = (
    r'뉴시스|뉴스1|연합뉴스|파이낸셜뉴스|헤럴드경제|이데일리|머니투데이'
    r'|한국경제|조선일보|중앙일보|동아일보|한겨레|매일경제'
    r'|데일리안|서울신문|서울경제|아시아경제|뉴스핌'
)
_BYLINE_RE = re.compile(
    r'^(?:'
    r'[\[\(][^\]\)]{1,60}(?:기자|특파원|앵커|논설위원|선임기자)[\]\)]\s*'
    r'|'
    r'\[(?:' + _KNOWN_MEDIA + r')\]\s*'
    r')',
    re.DOTALL,
)

def _strip_bylines(text):
    while True:
        m = _BYLINE_RE.match(text)
        if not m:
            break
        text = text[m.end():].lstrip()
    return text

def clean_body(text):
    text = _strip_bylines(text)
    text = re.sub(r'^\[[^\]]{1,40}기자\]\s*', '', text)
    text = re.sub(r'[가-힣]{2,6}\s*기자\s+[a-zA-Z0-9._+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '', text)
    text = re.sub(r'[a-zA-Z0-9_+-][a-zA-Z0-9._+-]*@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'◀\s*(앵커|리포트)\s*▶\s*', '', text)
    text = re.sub(r'[■◆★☆◇○□]+\s*', '', text)
    text = re.sub(r'\(사진[^)]{0,30}\)', '', text)
    text = re.sub(r'▲\s*.{0,200}', '', text)
    return re.sub(r'\s+', ' ', text).strip()


# ── 기사 본문 파싱 ────────────────────────────────────────────
def fetch_article_body(office_id, article_id):
    url = ARTICLE_URL.format(officeId=office_id, articleId=article_id)
    try:
        r = requests.get(url, headers=MOBILE_HEADERS, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')

        og_image = soup.select_one('meta[property="og:image"]')
        thumbnail_url = og_image['content'] if og_image else ''

        content = soup.select_one('div#dic_area') or soup.select_one('div.newsct_article')
        if not content:
            return '', [], thumbnail_url

        def _extract_lines(tag):
            for br in tag.select('br'):
                br.replace_with('\n')
            return [s.strip() for s in tag.get_text(separator='\n').split('\n') if s.strip()]

        subtitles = []
        summary_tag = content.select_one('strong.media_end_summary')
        if summary_tag:
            subtitles += _extract_lines(summary_tag)
            summary_tag.decompose()
        for tag in content.select("div[style*='border-left'], strong[style*='border-left']"):
            for line in _extract_lines(tag):
                if len(line) > 5 and line not in subtitles:
                    subtitles.append(line)
            tag.decompose()
        for b_tag in content.select('b'):
            text = b_tag.get_text(strip=True)
            if text and len(text) > 5 and text not in subtitles:
                subtitles.append(text)
            b_tag.decompose()
        for tag in content.select('span._PHOTO_VIEWER, em.img_desc'):
            tag.decompose()

        return clean_body(content.get_text(strip=True)), subtitles, thumbnail_url
    except Exception as e:
        print(f'    본문 파싱 실패 ({office_id}/{article_id}): {e}')
    return '', [], ''


# ── 뉴스 목록 수집 (API 우선 → __NEXT_DATA__ 폴백) ────────────
def fetch_news_list(ticker, target=20):
    items = []
    page = 1
    page_size = 20

    while len(items) < target:
        url = NEWS_API_URL.format(ticker=ticker, page_size=page_size, page=page)
        try:
            r = requests.get(url, headers=MOBILE_HEADERS, timeout=10)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f'  [{ticker}] API 요청 실패 (page {page}): {e}')
            break

        # API 응답 구조:
        #   list형 → [{total, items:[기사1]}, {total, items:[기사2]}, ...]
        #             각 원소에 기사 1개씩 들어있으므로 모두 순회
        #   dict형 → {items:[...]} 또는 {newsList:[...]}
        if isinstance(data, list):
            batch = []
            for entry in data:
                if isinstance(entry, dict):
                    entry_items = entry.get('items') or entry.get('list') or entry.get('newsList') or []
                    batch.extend(entry_items)
        elif isinstance(data, dict):
            batch = data.get('items') or data.get('newsList') or data.get('list') or []
        else:
            batch = []

        if not batch:
            print(f'  [{ticker}] page {page}: 기사 없음 → 종료')
            break

        for item in batch:
            if len(items) >= target:
                break
            items.append(item)

        if len(batch) < page_size:
            break
        page += 1

    return items


def fetch_news_list_from_page(ticker, target=20):
    """__NEXT_DATA__ 파싱 폴백"""
    url = LOCAL_NEWS_URL.format(ticker=ticker)
    try:
        r = requests.get(url, headers=PC_HEADERS, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')

        script = soup.find('script', id='__NEXT_DATA__')
        if not script:
            return []

        data = json.loads(script.string)
        props = data.get('props', {}).get('pageProps', {})
        news_list = (
            props.get('newsList') or
            props.get('localNewsList') or
            props.get('data', {}).get('newsList') or
            []
        )
        return news_list[:target]
    except Exception as e:
        print(f'  [{ticker}] 페이지 파싱 실패: {e}')
        return []


# ── 중복 체크 ─────────────────────────────────────────────────
def deduplicate(articles):
    seen = set()
    unique = []
    for a in articles:
        if a['news_id'] not in seen:
            seen.add(a['news_id'])
            unique.append(a)
    existing = set(
        doc['news_id'] for doc in collection.find(
            {'news_id': {'$in': [a['news_id'] for a in unique]}}, {'news_id': 1}
        )
    )
    return [a for a in unique if a['news_id'] not in existing]


# ── 종목별 뉴스 크롤링 ─────────────────────────────────────────
def crawl_stock_news(stock, target=20):
    """
    stock: {
        'ticker': 'AAPL.O',
        'stock_code': 'AAPL',
        'stock_name': '애플',
        'stock_name_en': 'APPLE INC'
    }
    """
    ticker       = stock['ticker']
    stock_code   = stock['stock_code']
    stock_name   = stock['stock_name']
    stock_name_en = stock['stock_name_en']

    raw_items = fetch_news_list(ticker, target=target)

    if not raw_items:
        print(f'  [{ticker}] API 결과 없음 → 페이지 파싱 시도')
        raw_items = fetch_news_list_from_page(ticker, target=target)

    if not raw_items:
        return []

    results = []
    seen = set()

    for item in raw_items:
        if len(results) >= target:
            break

        office_id  = str(item.get('officeId') or item.get('office_id') or '')
        article_id = str(item.get('articleId') or item.get('article_id') or '')
        title      = item.get('title') or item.get('headline') or ''
        source     = item.get('officeName') or item.get('office_name') or item.get('source') or ''
        pub_str    = item.get('publishedAt') or item.get('published_at') or item.get('datetime') or ''

        if not office_id or not article_id:
            continue

        title = html.unescape(title).strip()
        if any(kw in title for kw in MEDIA_KEYWORDS):
            continue

        news_id = f"{stock_code}_{office_id}_{article_id}"
        if news_id in seen:
            continue
        seen.add(news_id)

        pub_dt = None
        if pub_str:
            for fmt, length in [
                ('%Y%m%d%H%M', 12),
                ('%Y-%m-%dT%H:%M:%S', 19),
                ('%Y-%m-%d %H:%M:%S', 19),
                ('%Y.%m.%d %H:%M', 16),
            ]:
                try:
                    pub_dt = datetime.strptime(pub_str[:length], fmt)
                    break
                except (ValueError, TypeError):
                    continue

        body, subtitles, thumbnail_url = fetch_article_body(office_id, article_id)

        results.append({
            'news_id':       news_id,
            'title':         title,
            'subtitles':     subtitles,
            'content':       body,
            'thumbnail_url': thumbnail_url,
            'source':        source,
            'source_url':    ARTICLE_URL.format(officeId=office_id, articleId=article_id),
            'stock_code':    stock_code,
            'stock_name':    stock_name,
            'stock_name_en': stock_name_en,
            'market':        'NASDAQ',
            'published_at':  pub_dt or datetime.now(),
            'fetched_at':    datetime.now(),
        })
        time.sleep(0.3)

    return results


# ── CSV 로드 ──────────────────────────────────────────────────
def load_nasdaq100(filepath):
    """
    NASDAQ100.csv 로드.
    첫 줄('표 1,,')은 DictReader가 헤더로 읽으므로,
    실제 헤더(stock_code, stock_name, stock_name_en)가 있는 두 번째 줄부터 파싱.
    """
    stocks = []
    with open(filepath, newline='', encoding='utf-8-sig') as f:
        lines = f.readlines()

    # 첫 줄이 실제 컬럼명이 아닌 경우(예: '표 1,,') 건너뜀
    start = 0
    if lines and not lines[0].strip().startswith('stock_code'):
        start = 1

    reader = csv.DictReader(lines[start:])
    for row in reader:
        stock_code = row.get('stock_code', '').strip()
        if not stock_code:
            continue
        stocks.append({
            'ticker':       stock_code + '.O',
            'stock_code':   stock_code,
            'stock_name':   row.get('stock_name', '').strip(),
            'stock_name_en': row.get('stock_name_en', '').strip(),
        })
    return stocks


# ── 메인 ─────────────────────────────────────────────────────
if __name__ == '__main__':
    base_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(base_dir, 'NASDAQ100.csv')

    stocks = load_nasdaq100(csv_path)
    TARGET = 20

    print(f'[NASDAQ100 뉴스] {len(stocks)}종목 — 최신 {TARGET}건씩 수집 시작')
    total_saved = 0

    for i, stock in enumerate(stocks, 1):
        ticker = stock['ticker']
        print(f'\n[{i}/{len(stocks)}] {ticker} ({stock["stock_name"]}) 수집 중...')

        articles = crawl_stock_news(stock, target=TARGET)

        if not articles:
            print(f'  → 수집 없음')
            time.sleep(0.5)
            continue

        articles = deduplicate(articles)
        if not articles:
            print(f'  → 모두 중복')
            time.sleep(0.5)
            continue

        articles = summarize_articles(articles)

        try:
            result = collection.insert_many(articles, ordered=False)
            saved = len(result.inserted_ids)
        except Exception as e:
            saved = getattr(e, 'details', {}).get('nInserted', 0)

        total_saved += saved
        print(f'  → {saved}건 저장 ({len(articles)}건 수집)')
        time.sleep(0.5)

    print(f'\n완료. 총 {total_saved}건 저장됨.')
