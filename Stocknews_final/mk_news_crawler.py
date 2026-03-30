"""
매일경제(mk.co.kr) 종목명 검색 기반 뉴스 크롤러
- /news/economy/ 또는 /news/stock/ 카테고리 기사만 수집
- 최신순 정렬, stock_news 컬렉션 스키마에 맞춰 저장
- Selenium으로 "더보기" 버튼 클릭 → JS 기반 페이지네이션 처리
"""
import os
import re
import sys
import time
import certifi
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote
from pymongo import MongoClient
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import MONGO_URI, DB_NAME, COLLECTION_NAME
from summarizer import summarize_articles

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.mk.co.kr/',
}
SEARCH_URL = "https://www.mk.co.kr/search?word={word}&sort=desc&dateType=all&searchField=all&newsType=all&page={page}"
ALLOWED_CATEGORIES = {'/news/economy/', '/news/stock/'}

# ── MongoDB 연결 ──────────────────────────────────────────────
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client[DB_NAME]
collection = db[COLLECTION_NAME]  # stock_news

collection.create_index("news_id", unique=True, sparse=True)
collection.create_index([("published_at", -1)])
collection.create_index([("stock_code", 1)])


# ── 기사 본문 파싱 ────────────────────────────────────────────
def fetch_article_body(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        r.encoding = 'utf-8'
        soup = BeautifulSoup(r.text, 'html.parser')

        # 썸네일
        og_image = soup.select_one('meta[property="og:image"]')
        thumbnail = og_image['content'] if og_image else ''

        # 본문 영역 선택
        content = (
            soup.select_one('div.news_cnt_detail_wrap') or
            soup.select_one('div#article_body') or
            soup.select_one('div.art_txt')
        )
        if not content:
            return '', [], thumbnail

        # 이미지/캡션 관련 태그 제거
        for tag in content.select(
            'div.thumb_area, figure, figcaption, img, '
            '.img, .photo, .image_area, .thumb, '
            'div[class*="thumb"], div[class*="photo"], div[class*="image"]'
        ):
            tag.decompose()

        # 소제목 추출 (strong, h2, h3 태그)
        subtitles = []
        for tag in content.select('strong, h2, h3'):
            text = tag.get_text(strip=True)
            if text and len(text) > 5 and text not in subtitles:
                subtitles.append(text)
            tag.decompose()

        body = content.get_text(separator=' ', strip=True)
        # 연속 공백 정리
        body = re.sub(r'\s+', ' ', body).strip()

        return body, subtitles, thumbnail
    except Exception as e:
        print(f'    본문 파싱 실패 ({url}): {e}')
        return '', [], ''


def _make_driver():
    """헤드리스 Chrome 드라이버 생성."""
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument(f'user-agent={HEADERS["User-Agent"]}')
    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
    )


# ── 종목명으로 최신 뉴스 수집 ─────────────────────────────────
def crawl_mk_news(stock_name, stock_code='', target=3, driver=None):
    """
    매일경제에서 stock_name 검색 후
    /news/economy/ 또는 /news/stock/ 기사를 최신순으로 target건 수집.
    stock_news 컬렉션 스키마에 맞는 문서 반환.

    driver: 외부에서 생성한 Selenium WebDriver 인스턴스 (없으면 내부 생성 후 종료).
    """
    word = quote(stock_name)
    url = SEARCH_URL.format(word=word, page=1)
    results = []
    seen = set()

    owns_driver = driver is None
    if owns_driver:
        driver = _make_driver()

    try:
        driver.get(url)
        time.sleep(1.5)

        while len(results) < target:
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            items = soup.select('ul.result_news_list li.news_node')

            added_this_round = 0
            for item in items:
                if len(results) >= target:
                    break

                a = item.select_one('a.news_item')
                if not a:
                    continue

                href = a.get('href', '')
                if not any(cat in href for cat in ALLOWED_CATEGORIES):
                    continue
                if href in seen:
                    continue
                seen.add(href)

                article_id = href.rstrip('/').split('/')[-1]
                news_id = f"mk_{article_id}"

                title_tag = item.select_one('h3.news_ttl')
                time_tag  = item.select_one('p.time_info')
                title = title_tag.text.strip() if title_tag else ''

                pub_dt = None
                if time_tag:
                    try:
                        pub_dt = datetime.strptime(time_tag.text.strip(), '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        pass

                body, subtitles, thumbnail = fetch_article_body(href)

                results.append({
                    'news_id':       news_id,
                    'title':         title,
                    'subtitles':     subtitles,
                    'content':       body,
                    'thumbnail_url': thumbnail,
                    'source':        '매일경제',
                    'source_url':    href,
                    'stock_code':    stock_code,
                    'stock_name':    stock_name,
                    'stock_name_en': '',
                    'market':        'KOSPI',
                    'published_at':  pub_dt or datetime.now(),
                    'fetched_at':    datetime.now(),
                })
                added_this_round += 1
                print(f'  [{len(results)}] {pub_dt} {title[:45]}')
                time.sleep(0.3)

            if len(results) >= target:
                break

            # "더보기" 버튼 클릭으로 다음 20건 로드
            btns = driver.find_elements(By.CSS_SELECTOR, '[data-btn-more]')
            visible_btns = [b for b in btns if b.is_displayed()]
            if not visible_btns:
                print(f'  더보기 버튼 없음 → 종료 (수집: {len(results)}건)')
                break

            driver.execute_script('arguments[0].click();', visible_btns[0])
            time.sleep(1.5)

            # 클릭 후에도 새 아이템이 없으면 종료
            if added_this_round == 0:
                print(f'  더보기 후 새 기사 없음 → 종료 (수집: {len(results)}건)')
                break

    finally:
        if owns_driver:
            driver.quit()

    return results


# ── 종목 로드 ─────────────────────────────────────────────────
def load_stocks(filepath):
    import csv
    stocks = []
    with open(filepath, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            stocks.append({
                'stock_code': str(row['stock_code']).zfill(6),
                'stock_name': row['stock_name'],
            })
    return stocks


# ── 메인 ─────────────────────────────────────────────────────
if __name__ == '__main__':
    import os
    base_dir = os.path.dirname(os.path.abspath(__file__))
    stocks = load_stocks(os.path.join(base_dir, 'kospi200_targets.csv'))
    target = 20

    print(f'[매일경제] {len(stocks)}종목 — 최신 {target}건씩 수집 시작')
    total_saved = 0

    driver = _make_driver()
    try:
        for i, stock in enumerate(stocks, 1):
            stock_name = stock['stock_name']
            stock_code = stock['stock_code']

            articles = crawl_mk_news(stock_name, stock_code=stock_code, target=target, driver=driver)

            if not articles:
                print(f'  [{i}/{len(stocks)}] [{stock_code}] {stock_name} — 수집 없음')
                continue

            # 요약
            articles = summarize_articles(articles)

            # MongoDB 저장
            try:
                result = collection.insert_many(articles, ordered=False)
                saved = len(result.inserted_ids)
            except Exception as e:
                saved = getattr(e, 'details', {}).get('nInserted', 0)

            total_saved += saved
            print(f'  [{i}/{len(stocks)}] [{stock_code}] {stock_name} — {saved}건 저장 ({len(articles)}건 수집)')
            time.sleep(0.5)
    finally:
        driver.quit()

    print(f'\n완료. 총 {total_saved}건 저장됨.')
