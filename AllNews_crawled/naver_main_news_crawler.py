"""
네이버 금융 메인뉴스 크롤러
URL: https://finance.naver.com/news/mainnews.naver
- 30분 주기, 20건/사이클
- 텍스트 전처리: StockNews_crawled/naver_stock_news_scraper.py 방식
- 중복 제거:
    1단계 (배치 내) — 제목 SimHash + 본문 Jaccard (news_crawl_filtered.py 방식)
    2단계 (DB 대비) — news_id 정확 매칭 + 최근 24h 기사 본문 Jaccard
- 요약: StockNews_crawled/summarizer.py (EbanLee/kobart-summary-v3)
- MongoDB 저장: sollite.news 컬렉션, subtitle/summary 필드 포함
"""

import hashlib
import html
import os
import re
import sys
import time
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

# App/utils/text.py, StockNews_crawled/summarizer.py import
_app_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "App")
_stock_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "StockNews_crawled")
sys.path.insert(0, _app_path)
sys.path.insert(0, _stock_path)
from utils.text import clean_article_body
from summarizer import summarize_articles

import certifi
import requests
from bs4 import BeautifulSoup
from pymongo import MongoClient

# ── Config ────────────────────────────────────────────────────
MONGO_URI = "mongodb+srv://ADMIN:(Sollite4259)@sqllitecluster.fdieckp.mongodb.net/?appName=SQLLiteCluster"
DB_NAME = "sollite"
COLLECTION_NAME = "news"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

MAIN_NEWS_URL = "https://finance.naver.com/news/mainnews.naver"
ARTICLE_URL_TPL = "https://n.news.naver.com/mnews/article/{office_id}/{article_id}"

TARGET_COUNT = 20
SCHEDULE_INTERVAL = 1800  # 30분(초)
MEDIA_KEYWORDS = ["[포토]", "[사진]", "[동영상]", "[비디오]", "[포토뉴스]", "[영상]"]

# 중복 판정 임계값
SIMHASH_BITS = 64
TITLE_HAMMING_THRESHOLD = 5    # 이하면 유사 제목
CONTENT_JACCARD_THRESHOLD = 0.7

# ── MongoDB 연결 ──────────────────────────────────────────────
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

collection.create_index("news_id", unique=True, sparse=True)
collection.create_index([("published_at", -1)])


# ═══════════════════════════════════════════════════════════════
# 기사 전문 파싱 + subtitle 추출
# - 노이즈 제거: App/domains/news/crawler.py › remove_article_noise 방식
# - 텍스트 클리닝: App/utils/text.py › clean_article_body 사용
# ═══════════════════════════════════════════════════════════════
def _extract_lines(tag) -> list:
    """<br> 태그를 줄바꿈으로 처리 후 비어있지 않은 줄 반환"""
    for br in tag.select("br"):
        br.replace_with("\n")
    return [s.strip() for s in tag.get_text(separator="\n").split("\n") if s.strip()]


def _remove_article_noise(content_tag) -> None:
    """App/crawler.py › remove_article_noise 확장판"""
    for selector in [
        "strong.media_end_summary",   # 소제목 블록 → content에서 제거
        "b",                          # 인라인 소제목 태그 → subtitle로 이미 추출 후 제거
        "span.end_photo_org",
        "em.img_desc",
        "figcaption",
        ".vod_area",
        "div.pharm",                  # 프리미엄 선공개 안내
        "span._PHOTO_VIEWER",
        "table",                      # 사진/표 테이블
        ".reporter_area",
        ".copyright",
    ]:
        for tag in content_tag.select(selector):
            tag.decompose()

    # 배경색/테두리가 있는 프로모션·안내 박스 제거 (AI 프리즘, 구독 안내 등)
    for tag in content_tag.select("div[style*='background']"):
        tag.decompose()


def _remove_caption_credits(text: str) -> str:
    """clean_article_body 호출 전 raw 텍스트에서 사진 캡션+출처 패턴 제거"""
    # 알려진 캡션 출처 키워드
    _SRC = (
        r'제공|SNS|AP|EPA|AFP|로이터|Reuters|게티|Getty'
        r'|뉴시스|뉴스1|연합뉴스|연합|뉴스핌|이데일리|머니투데이'
        r'|한국경제|조선일보|중앙일보|동아일보|한겨레|매일경제|헤럴드경제'
    )
    # 캡션 텍스트 [출처] — 앞 텍스트까지 통째로 제거
    # [^\[]{2,80}: 브래킷 이전 임의 텍스트 / [^\]]*(?:_SRC)[^\]]*: 브래킷 내 어디든 출처 키워드
    _pat = r'[^\[]{2,80}\s*\[[^\]]*(?:' + _SRC + r')[^\]]*\]\s*'
    text = re.sub(_pat, ' ', text)
    # 캡션 텍스트 [언론사=기자명 기자] / [언론사 | 기자명 기자] — 앞 짧은 텍스트 포함 제거
    text = re.sub(r'[가-힣\w·,·\s]{2,60}\[[^\]]{2,40}기자\]\s*', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


_KNOWN_MEDIA = (
    r'뉴시스|뉴스1|연합뉴스|파이낸셜뉴스|헤럴드경제|이데일리|머니투데이'
    r'|한국경제|조선일보|중앙일보|동아일보|한겨레|매일경제|이코노미스트'
    r'|데일리안|더팩트|서울신문|서울경제|아시아경제|아이뉴스|뉴스핌'
)

_LEADING_BYLINE_RE = re.compile(
    r'^(?:'
    # [헤럴드경제=김진 기자] / [더팩트ㅣ김정산 기자] / [이코노미스트 김윤주 기자]
    # — 괄호 안에 기자 역할
    r'[\[\(][^\]\)]{1,60}(?:기자|특파원|앵커|논설위원|선임기자|보험전문기자)[\]\)]\s*'
    r'|'
    # [서울=뉴시스]김래현 기자 = / (서울=연합뉴스) 김유향 기자 = 연합뉴스
    # — 괄호 밖에 기자명 + 기자 역할 + (=|:)
    r'[\[\(][^\]\)]{1,50}[\]\)]\s*[가-힣A-Za-z·\s]{0,20}'
    r'(?:기자|특파원|앵커|보험전문기자|논설위원|선임기자)\s*[=:]?\s*[가-힣]{0,15}\s*'
    r'|'
    # [파이낸셜뉴스] 단독 — 알려진 언론사명만
    r'\[(?:' + _KNOWN_MEDIA + r')\]\s*'
    r')',
    re.DOTALL,
)


def strip_leading_bylines(text: str) -> str:
    """본문 앞 기자/언론사 바이라인을 건너뛰고 실제 내용 시작점부터 반환"""
    while True:
        m = _LEADING_BYLINE_RE.match(text)
        if not m:
            break
        text = text[m.end():].lstrip()
    return text


def _remove_inline_bylines(text: str) -> str:
    """clean_article_body 보완: 본문 중간 노이즈 전역 제거"""
    # (서울=연합뉴스) 기자명 기자 = 패턴
    text = re.sub(r'\([^)]{2,30}=[^)]{2,20}\)\s*[가-힣·\s]{2,15}기자\s*=?\s*', '', text)
    # [언론사=기자명 기자] / [언론사 기자명 기자] 패턴 (비문두 포함)
    text = re.sub(r'\[[^\]]{1,50}기자\]\s*', '', text)
    # [언론사 | 기자명 기자] 파이프 구분 패턴
    text = re.sub(r'\[[^\]\|]{1,30}\|[^\]]{1,30}기자\]\s*', '', text)
    # 사진 | 브랜드명 / 사진 = 브랜드명 캡션 크레딧
    text = re.sub(r'\s*사진\s*[|=]\s*[^\s][^.。\n]{0,30}', '', text)
    # ▲ 로 시작하는 프로모션 문구 (AI 프리즘 등)
    text = re.sub(r'▲\s*.{0,200}', '', text)
    # 이메일 주소 제거
    text = re.sub(r'[a-zA-Z0-9._+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '', text)
    return re.sub(r'\s+', ' ', text).strip()


def fetch_article(office_id: str, article_id: str) -> tuple:
    """반환: (body: str, subtitles: list, thumbnail_url: str)"""
    url = ARTICLE_URL_TPL.format(office_id=office_id, article_id=article_id)
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        og = soup.select_one('meta[property="og:image"]')
        thumbnail_url = og["content"] if og else ""

        content = soup.select_one("#dic_area") or soup.select_one("div.newsct_article")
        if not content:
            return "", [], thumbnail_url

        # subtitle 먼저 추출 (제거 전)
        subtitles = []

        # 방식 1: strong.media_end_summary (요약형 소제목)
        summary_tag = content.select_one("strong.media_end_summary")
        if summary_tag:
            subtitles += _extract_lines(summary_tag)

        # 방식 2: border-left div/strong — 인라인 스타일 소제목 (br 처리)
        for tag in content.select("div[style*='border-left'], strong[style*='border-left']"):
            for line in _extract_lines(tag):
                if len(line) > 5 and line not in subtitles:
                    subtitles.append(line)

        # 방식 3: b 태그 소제목 (border-left 내부 b는 이미 위에서 처리)
        for b_tag in content.select("b"):
            # border-left 컨테이너 안에 있는 b는 스킵 (중복 방지)
            if b_tag.find_parent(style=lambda s: s and "border-left" in s):
                continue
            t = b_tag.get_text(strip=True)
            if t and len(t) > 5 and t not in subtitles:
                subtitles.append(t)

        # 노이즈 제거 (소제목 포함) → content에서 제외
        # strong[style*="border-left"] 는 선택자로 일괄 처리 불가하여 별도 제거
        for tag in content.select("strong[style*='border-left'], div[style*='border-left']"):
            tag.decompose()
        _remove_article_noise(content)

        # App/utils/text.py › clean_article_body 로 텍스트 클리닝
        source = soup.select_one("meta[property='og:article:author']")
        source_name = source["content"].strip() if source else ""
        raw = content.get_text(" ", strip=True)
        raw = _remove_caption_credits(raw)
        raw = strip_leading_bylines(raw)
        body = clean_article_body(raw, source_name)
        body = _remove_inline_bylines(body)

        return body, subtitles, thumbnail_url

    except Exception as e:
        print(f"    본문 파싱 실패 ({office_id}/{article_id}): {e}")
    return "", [], ""


# ═══════════════════════════════════════════════════════════════
# 메인 뉴스 목록 수집
# ═══════════════════════════════════════════════════════════════
def fetch_news_list(page: int = 1) -> list:
    """ul.newsList li 파싱 → [{title, office_id, article_id, source, date_str}]"""
    try:
        r = requests.get(
            MAIN_NEWS_URL,
            params={"page": page},
            headers=HEADERS,
            timeout=10,
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        items = []
        for li in soup.select("ul.newsList li"):
            a_tag = li.select_one("dd.articleSubject a")
            if not a_tag:
                continue

            title = html.unescape(a_tag.get_text(strip=True))
            href = a_tag.get("href", "")

            if not title or not href:
                continue
            if any(kw in title for kw in MEDIA_KEYWORDS):
                continue

            # URL 파라미터에서 office_id, article_id 추출
            qs = parse_qs(urlparse(href).query)
            office_id = qs.get("office_id", [None])[0]
            article_id = qs.get("article_id", [None])[0]
            if not office_id or not article_id:
                continue

            src_tag = li.select_one("span.press")
            source = src_tag.get_text(strip=True) if src_tag else ""

            date_tag = li.select_one("span.wdate")
            date_str = date_tag.get_text(strip=True) if date_tag else ""

            items.append({
                "title": title,
                "office_id": office_id,
                "article_id": article_id,
                "source": source,
                "date_str": date_str,
            })

        return items

    except Exception as e:
        print(f"뉴스 목록 수집 실패 (page={page}): {e}")
        return []


def parse_date(date_str: str) -> datetime:
    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y.%m.%d %H:%M"]:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return datetime.now()


# ═══════════════════════════════════════════════════════════════
# 중복 제거 유틸 (news_crawl_filtered.py 방식)
# ═══════════════════════════════════════════════════════════════
def _simhash(title: str, bits: int = SIMHASH_BITS) -> int:
    title = re.sub(r"[^\w가-힣]", " ", title).strip()
    tokens = title.split()
    v = [0] * bits
    for token in tokens:
        h = int(hashlib.md5(token.encode()).hexdigest(), 16)
        for i in range(bits):
            v[i] += 1 if (h >> i) & 1 else -1
    return sum(1 << i for i in range(bits) if v[i] > 0)


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _shingles(text: str, k: int = 1) -> set:
    words = re.sub(r"[^\w가-힣]", " ", text).split()
    return set(zip(*[words[i:] for i in range(k)])) if len(words) >= k else set()


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def deduplicate_within_batch(articles: list) -> list:
    """
    1단계: 배치 내 중복 제거
    ① 제목 SimHash — Hamming 거리 ≤ TITLE_HAMMING_THRESHOLD 이면 중복
    ② 본문 Jaccard  — 유사도 ≥ CONTENT_JACCARD_THRESHOLD 이면 중복
    """
    # ① 제목 SimHash
    seen_hashes = []
    title_unique = []
    for a in articles:
        h = _simhash(a["title"])
        if all(_hamming(h, prev) > TITLE_HAMMING_THRESHOLD for prev in seen_hashes):
            seen_hashes.append(h)
            title_unique.append(a)

    # ② 본문 Jaccard
    shingle_sets = [_shingles(a["content"]) for a in title_unique]
    unique_indices = []
    for i in range(len(title_unique)):
        is_dup = any(
            _jaccard(shingle_sets[i], shingle_sets[j]) >= CONTENT_JACCARD_THRESHOLD
            for j in unique_indices
        )
        if not is_dup:
            unique_indices.append(i)

    return [title_unique[i] for i in unique_indices]


def deduplicate_against_db(articles: list) -> list:
    """
    2단계: DB 대비 중복 제거
    ① news_id 정확 매칭 — DB에 이미 존재하면 제거
    ② 최근 24h DB 기사와 본문 Jaccard ≥ CONTENT_JACCARD_THRESHOLD 이면 제거
    """
    if not articles:
        return articles

    # ① news_id 정확 매칭
    ids = [a["news_id"] for a in articles]
    existing_ids = {
        doc["news_id"]
        for doc in collection.find({"news_id": {"$in": ids}}, {"news_id": 1})
    }
    articles = [a for a in articles if a["news_id"] not in existing_ids]

    if not articles:
        return articles

    # ② 최근 24h DB 기사와 본문 Jaccard 비교
    cutoff = datetime.now() - timedelta(hours=24)
    recent_docs = list(
        collection.find(
            {"fetched_at": {"$gte": cutoff}},
            {"content": 1, "_id": 0},
        ).limit(300)
    )
    db_shingles = [_shingles(doc.get("content", "")) for doc in recent_docs]

    unique = []
    for a in articles:
        a_sh = _shingles(a["content"])
        is_dup = any(
            _jaccard(a_sh, db_s) >= CONTENT_JACCARD_THRESHOLD
            for db_s in db_shingles
            if db_s
        )
        if not is_dup:
            unique.append(a)

    return unique


# ═══════════════════════════════════════════════════════════════
# 1회 크롤링 사이클
# ═══════════════════════════════════════════════════════════════
def run_job() -> None:
    print(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}] 크롤링 사이클 시작 (목표: {TARGET_COUNT}건)")

    # 1. 뉴스 목록 수집
    raw_list = fetch_news_list(page=1)
    if not raw_list:
        print("  뉴스 목록 수집 실패 — 사이클 종료")
        return
    print(f"  목록 수집: {len(raw_list)}건")

    # 2. 전문 파싱
    articles = []
    seen_news_ids = set()

    for item in raw_list:
        office_id = item["office_id"]
        article_id = item["article_id"]
        news_id = f"{office_id}_{article_id}"

        if news_id in seen_news_ids:
            continue
        seen_news_ids.add(news_id)

        body, subtitles, thumbnail_url = fetch_article(office_id, article_id)
        if len(body) < 50:
            time.sleep(0.3)
            continue

        articles.append({
            "news_id": news_id,
            "title": item["title"],
            "subtitle": subtitles,
            "content": body,
            "thumbnail_url": thumbnail_url,
            "source": item["source"],
            "source_url": ARTICLE_URL_TPL.format(
                office_id=office_id, article_id=article_id
            ),
            "published_at": parse_date(item["date_str"]),
            "fetched_at": datetime.now(),
        })
        time.sleep(0.3)

    print(f"  전문 파싱 완료: {len(articles)}건")
    if not articles:
        return

    # 3. 1단계 중복 제거 (배치 내)
    before = len(articles)
    articles = deduplicate_within_batch(articles)
    print(f"  1단계 중복 제거 (배치 내): {before}건 → {len(articles)}건")

    # 4. 2단계 중복 제거 (DB 대비)
    before = len(articles)
    articles = deduplicate_against_db(articles)
    print(f"  2단계 중복 제거 (DB 대비): {before}건 → {len(articles)}건")

    articles = articles[:TARGET_COUNT]

    if not articles:
        print("  저장할 신규 기사 없음")
        return

    # 5. 요약
    print(f"  요약 시작: {len(articles)}건")
    articles = summarize_articles(articles)

    # 6. MongoDB 저장
    try:
        result = collection.insert_many(articles, ordered=False)
        print(f"  MongoDB 저장 완료: {len(result.inserted_ids)}건")
    except Exception as e:
        print(f"  저장 실패: {e}")


# ═══════════════════════════════════════════════════════════════
# 메인
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 55)
    print(" 네이버 금융 메인뉴스 크롤러")
    print(f" URL     : {MAIN_NEWS_URL}")
    print(f" DB      : {DB_NAME}.{COLLECTION_NAME}")
    print(f" 주기    : {SCHEDULE_INTERVAL // 60}분  |  목표: {TARGET_COUNT}건/사이클")
    print("=" * 55)

    while True:
        try:
            run_job()
        except Exception as e:
            print(f"루프 에러: {e}")
        print(f"\n{SCHEDULE_INTERVAL // 60}분 대기 중...")
        time.sleep(SCHEDULE_INTERVAL)
