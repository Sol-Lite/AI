"""
KOSPI200 + NASDAQ100 통합 1회 수집 크롤러
- KOSPI200 전 종목 → NASDAQ100 전 종목 순서로 순차 실행
- 종목당 최신 유효 기사 20건 수집
- news_id: {stock_code}_{office_id}_{article_id}
- API 응답 리스트 전체 순회
- insert_many(ordered=False) 로 중복 안전 처리

실행: python bulk_crawler.py
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
FALLBACK_URL = {
    'KOSPI':  "https://m.stock.naver.com/domestic/stock/{code}/news",
    'NASDAQ': "https://m.stock.naver.com/worldstock/stock/{code}/localNews",
}
ARTICLE_URL = "https://n.news.naver.com/mnews/article/{officeId}/{articleId}"

MEDIA_KEYWORDS = ["[포토]", "[사진]", "[동영상]", "[비디오]", "[포토뉴스]", "[영상]"]
TARGET = 20

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
    r'|한국경제|조선일보|중앙일보|동아일보|한겨레|매일경제|이코노미스트'
    r'|데일리안|더팩트|서울신문|서울경제|아시아경제|아이뉴스|뉴스핌'
)
_BYLINE_RE = re.compile(
    r'^(?:'
    r'[\[\(][^\]\)]{1,60}(?:기자|특파원|앵커|논설위원|선임기자|보험전문기자)[\]\)]\s*'
    r'|'
    r'[\[\(][^\]\)]{1,50}[\]\)]\s*[가-힣A-Za-z·\s]{0,20}'
    r'(?:기자|특파원|앵커|보험전문기자|논설위원|선임기자)\s*[=:]?\s*[가-힣]{0,15}\s*'
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
    text = re.sub(r'[^\[]{2,80}\s*\[[^\]]*(?:' + _SRC + r')[^\]]*\]\s*', ' ', text)
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
            if b_tag.find_parent(style=lambda s: s and 'border-left' in s):
                continue
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


# ── 뉴스 목록 수집 ────────────────────────────────────────────
def fetch_news_list(ticker, target=TARGET):
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


def fetch_news_list_from_page(ticker, market):
    """__NEXT_DATA__ 파싱 폴백"""
    url = FALLBACK_URL[market].format(code=ticker)
    try:
        r = requests.get(url, headers=PC_HEADERS, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        script = soup.find('script', id='__NEXT_DATA__')
        if not script:
            return []
        data = json.loads(script.string)
        props = data.get('props', {}).get('pageProps', {})
        return (
            props.get('newsList') or
            props.get('localNewsList') or
            props.get('data', {}).get('newsList') or
            []
        )
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


# ── 종목별 크롤링 ─────────────────────────────────────────────
def crawl_stock_news(stock, target=TARGET):
    ticker     = stock['ticker']
    stock_code = stock['stock_code']
    market     = stock['market']

    raw_items = fetch_news_list(ticker, target=target)
    if not raw_items:
        print(f'  [{ticker}] API 결과 없음 → 페이지 파싱 시도')
        raw_items = fetch_news_list_from_page(ticker, market)

    if not raw_items:
        return []

    results = []
    seen = set()

    for item in raw_items:
        if len(results) >= target:
            break

        office_id  = str(item.get('officeId') or item.get('office_id') or '')
        article_id = str(item.get('articleId') or item.get('article_id') or '')
        if not office_id or not article_id:
            continue

        title = html.unescape(
            item.get('titleFull') or item.get('title') or item.get('headline') or ''
        ).strip()
        if any(kw in title for kw in MEDIA_KEYWORDS):
            continue

        news_id = f"{stock_code}_{office_id}_{article_id}"
        if news_id in seen:
            continue
        seen.add(news_id)

        source  = item.get('officeName') or item.get('office_name') or ''
        pub_str = item.get('datetime') or item.get('publishedAt') or item.get('published_at') or ''

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
            'stock_name':    stock['stock_name'],
            'stock_name_en': stock.get('stock_name_en', ''),
            'market':        market,
            'published_at':  pub_dt or datetime.now(),
            'fetched_at':    datetime.now(),
        })
        time.sleep(0.3)

    return results


# ── CSV 로드 ──────────────────────────────────────────────────
def load_kospi200(filepath):
    stocks = []
    with open(filepath, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = str(row.get('stock_code', '')).strip().zfill(6)
            if not code.strip('0'):
                continue
            stocks.append({
                'ticker':        code,
                'stock_code':    code,
                'stock_name':    row.get('stock_name', '').strip(),
                'stock_name_en': '',
                'market':        'KOSPI',
            })
    return stocks


def load_nasdaq100(filepath):
    stocks = []
    with open(filepath, newline='', encoding='utf-8-sig') as f:
        lines = f.readlines()
    start = 0
    if lines and not lines[0].strip().startswith('stock_code'):
        start = 1
    reader = csv.DictReader(lines[start:])
    for row in reader:
        code = row.get('stock_code', '').strip()
        if not code:
            continue
        stocks.append({
            'ticker':        code + '.O',
            'stock_code':    code,
            'stock_name':    row.get('stock_name', '').strip(),
            'stock_name_en': row.get('stock_name_en', '').strip(),
            'market':        'NASDAQ',
        })
    return stocks


# ── 시장별 수집 실행 ──────────────────────────────────────────
def run_market(stocks, market_label):
    print(f'\n{"="*60}')
    print(f'[{market_label}] {len(stocks)}종목 — 최신 {TARGET}건씩 수집 시작')
    print(f'{"="*60}')

    total_saved = 0

    for i, stock in enumerate(stocks, 1):
        ticker = stock['ticker']
        print(f'\n  [{i}/{len(stocks)}] {ticker} ({stock["stock_name"]}) 수집 중...')

        articles = crawl_stock_news(stock, target=TARGET)
        if not articles:
            print(f'    → 수집 없음')
            time.sleep(0.5)
            continue

        articles = deduplicate(articles)
        if not articles:
            print(f'    → 모두 중복')
            time.sleep(0.5)
            continue

        articles = summarize_articles(articles)

        try:
            result = collection.insert_many(articles, ordered=False)
            saved = len(result.inserted_ids)
        except Exception as e:
            saved = getattr(e, 'details', {}).get('nInserted', 0)

        total_saved += saved
        print(f'    → {saved}건 저장 ({len(articles)}건 수집)')
        time.sleep(0.5)

    print(f'\n[{market_label}] 완료 — 총 {total_saved}건 저장')
    return total_saved


# ── 메인 ─────────────────────────────────────────────────────
if __name__ == '__main__':
    base_dir = os.path.dirname(os.path.abspath(__file__))

    kospi_stocks  = load_kospi200(os.path.join(base_dir, 'kospi200_targets.csv'))
    nasdaq_stocks = load_nasdaq100(os.path.join(base_dir, 'NASDAQ100.csv'))

    print(f'KOSPI200: {len(kospi_stocks)}종목 / NASDAQ100: {len(nasdaq_stocks)}종목')
    print(f'종목당 목표: {TARGET}건\n')

    saved_kospi  = run_market(kospi_stocks,  'KOSPI200')
    saved_nasdaq = run_market(nasdaq_stocks, 'NASDAQ100')

    print(f'\n{"="*60}')
    print(f'전체 완료')
    print(f'  KOSPI200  : {saved_kospi}건 저장')
    print(f'  NASDAQ100 : {saved_nasdaq}건 저장')
    print(f'  합계      : {saved_kospi + saved_nasdaq}건 저장')
    print(f'{"="*60}')
