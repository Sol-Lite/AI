"""
Naver 세계 주식 뉴스 크롤러
- URL: https://m.stock.naver.com/worldstock/stock/{TICKER}.O/localNews
- NASDAQ 티커: .O 접미사 (예: TSLA.O, AAPL.O)
- __NEXT_DATA__ JSON → officeId/articleId 추출 → 본문 크롤링
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

LOCAL_NEWS_URL = "https://m.stock.naver.com/worldstock/stock/{ticker}/localNews"
# 한국/세계 주식 모두 동일한 엔드포인트 사용
NEWS_API_URL   = "https://m.stock.naver.com/api/news/stock/{ticker}?pageSize={page_size}&page={page}"
ARTICLE_URL    = "https://n.news.naver.com/mnews/article/{officeId}/{articleId}"

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
    """
    Naver 세계 주식 뉴스 목록 수집.
    반환: [{'officeId': str, 'articleId': str, 'title': str, 'publishedAt': str, 'officeName': str}, ...]
    """
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

        # API 응답 구조: [{"total": N, "items": [...]}]
        # API 응답: [{total, items:[기사1]}, {total, items:[기사2]}, ...]
        # 각 원소에 기사 1개씩 들어있으므로 모두 순회
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
    """
    __NEXT_DATA__ 파싱으로 뉴스 목록 수집 (API 폴백용).
    """
    url = LOCAL_NEWS_URL.format(ticker=ticker)
    try:
        r = requests.get(url, headers=PC_HEADERS, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')

        script = soup.find('script', id='__NEXT_DATA__')
        if not script:
            return []

        data = json.loads(script.string)
        # 경로는 Naver 버전에 따라 다를 수 있음
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
def crawl_worldstock_news(stock, target=20):
    """
    ticker: 'TSLA.O' 형식 (market suffix 포함)
    stock_code: 원래 티커 문자열 (예: 'TSLA')
    """
    ticker     = stock['ticker']       # 예: TSLA.O
    stock_code = stock['stock_code']   # 예: TSLA
    stock_name = stock['stock_name']   # 예: Tesla
    market     = stock.get('market', 'NASDAQ')

    # 1단계: API로 뉴스 목록 시도
    raw_items = fetch_news_list(ticker, target=target)

    # API가 빈 결과 → __NEXT_DATA__ 폴백
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

        # API 응답 필드 추출 (필드명이 다를 수 있어 여러 키 시도)
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

        # 발행일 파싱
        # API datetime 형식: "202603301504" (YYYYMMDDHHmm, 12자리)
        pub_dt = None
        if pub_str:
            for fmt, length in [('%Y%m%d%H%M', 12), ('%Y-%m-%dT%H:%M:%S', 19), ('%Y-%m-%d %H:%M:%S', 19), ('%Y.%m.%d %H:%M', 16)]:
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
            'stock_name_en': stock_name,
            'market':        market,
            'published_at':  pub_dt or datetime.now(),
            'fetched_at':    datetime.now(),
        })
        time.sleep(0.3)

    return results


# ── 종목 로드 ─────────────────────────────────────────────────
def load_stocks(filepath):
    """
    CSV 컬럼: ticker, stock_code, stock_name, market
    ticker 컬럼에 .O 같은 suffix가 없으면 자동으로 .O 붙임 (NASDAQ 기본값)
    """
    stocks = []
    with open(filepath, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = row.get('ticker') or row.get('stock_code', '')
            # suffix 없으면 NASDAQ 기본값 .O 추가
            if ticker and '.' not in ticker:
                ticker = ticker + '.O'
            stocks.append({
                'ticker':     ticker,
                'stock_code': row.get('stock_code') or ticker.split('.')[0],
                'stock_name': row.get('stock_name', ''),
                'market':     row.get('market', 'NASDAQ'),
            })
    return stocks


# ── 메인 ─────────────────────────────────────────────────────
if __name__ == '__main__':
    base_dir = os.path.dirname(os.path.abspath(__file__))

    csv_path = os.path.join(base_dir, 'nasdaq_targets.csv')
    stocks = load_stocks(csv_path)

    TARGET = 20
    print(f'[Naver 세계 주식] {len(stocks)}종목 — 최신 {TARGET}건씩 수집 시작')
    total_saved = 0

    for i, stock in enumerate(stocks, 1):
        ticker = stock['ticker']
        print(f'\n  [{i}/{len(stocks)}] [{ticker}] {stock["stock_name"]} 수집 중...')

        articles = crawl_worldstock_news(stock, target=TARGET)

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

    print(f'\n완료. 총 {total_saved}건 저장됨.')
