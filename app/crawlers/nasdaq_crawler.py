"""
한국경제 '[오늘장 미리보기]' 크롤러
검색: https://search.hankyung.com/search/total?query=%5B%EC%98%A4%EB%8A%98%EC%9E%A5+%EB%AF%B8%EB%A6%AC%EB%B3%B4%EA%B8%B0%5D
- 매일 08:40 실행
- 오늘 날짜 최신 기사 1건 수집
- <figure class="article-figure"> / figcaption 제외
- 텍스트 전처리 (특수문자 등)
- ollama llama3.1:8b 요약
- MongoDB sollite.news 저장 (중복 시 upsert)
"""

import json
import re
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
SEARCH_URL   = "https://search.hankyung.com/search/total"
SEARCH_QUERY = "[뉴욕 증시 브리핑]"
ARTICLE_BASE = "https://www.hankyung.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://search.hankyung.com/",
}

KST = timezone(timedelta(hours=9))

# ── MongoDB 연결 ──────────────────────────────────────────────
client     = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
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
    text = re.sub(r'[가-힣]{2,6}\s*기자\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'ⓒ[^\n.。]{0,60}', '', text)
    text = re.sub(r'©[^\n.。]{0,60}', '', text)
    text = re.sub(r'무단\s*전재[^\n.。]{0,60}', '', text)
    text = re.sub(r'[■◆★☆◇○□◎▶▷◀◁△▽▲▼●◉]+\s*', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


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
    if isinstance(summary.get("sectors"), list):
        summary["sectors"] = [_to_hamnida(s) for s in summary["sectors"]]
    stocks = summary.get("stocks")
    if isinstance(stocks, dict):
        if isinstance(stocks.get("up"), list):
            stocks["up"] = [_to_hamnida(s) for s in stocks["up"]]
        if isinstance(stocks.get("down"), list):
            stocks["down"] = [_to_hamnida(s) for s in stocks["down"]]
    return summary


# ═══════════════════════════════════════════════════════════════
# 검색 결과에서 오늘 최신 기사 1건 추출
# ═══════════════════════════════════════════════════════════════
def fetch_today_article_meta() -> dict | None:
    today_str = datetime.now(KST).strftime("%Y.%m.%d")

    try:
        r = requests.get(
            SEARCH_URL,
            params={"query": SEARCH_QUERY},
            headers=HEADERS,
            timeout=15,
        )
        r.raise_for_status()
    except Exception as e:
        print(f"  검색 페이지 요청 실패: {e}")
        return None

    soup  = BeautifulSoup(r.text, "html.parser")
    items = soup.select("ul.article > li")

    if not items:
        print("  검색 결과 없음")
        return None

    for item in items:
        date_tag = item.select_one(".date, span[class*='date'], time")
        if not date_tag:
            continue
        date_text = date_tag.get_text(strip=True)
        if today_str not in date_text:
            continue

        a_tag = item.select_one("a[href*='/article/']")
        if not a_tag:
            continue
        url = a_tag.get("href", "")
        if not url.startswith("http"):
            url = ARTICLE_BASE + url

        tit_tag = item.select_one(".tit, h2, h3")
        title   = tit_tag.get_text(strip=True) if tit_tag else a_tag.get_text(strip=True)
        news_id = url.rstrip("/").split("/")[-1]

        published_at = datetime.now(KST).replace(tzinfo=None)
        try:
            published_at = datetime.strptime(date_text.strip(), "%Y.%m.%d %H:%M")
        except ValueError:
            pass

        return {
            "news_id":     news_id,
            "title":       title,
            "url":         url,
            "published_at": published_at,
        }

    print(f"  오늘({today_str}) 날짜 기사 없음")
    return None


# ═══════════════════════════════════════════════════════════════
# 기사 본문 파싱
# ═══════════════════════════════════════════════════════════════
def fetch_article_content(url: str) -> str:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        body = soup.select_one("div#articletxt")
        if not body:
            print(f"  본문 컨테이너 없음: {url}")
            return ""

        for tag in body.select(
            "figure.article-figure, figcaption.figure-caption, "
            "figure, figcaption, script, style, iframe"
        ):
            tag.decompose()

        for tag in body.select(".related-article, .box_related, .article-ad"):
            tag.decompose()

        return clean_text(body.get_text(" ", strip=True))

    except Exception as e:
        print(f"  본문 파싱 실패 ({url}): {e}")
        return ""


# ═══════════════════════════════════════════════════════════════
# ollama 요약
# ═══════════════════════════════════════════════════════════════
def summarize_with_ollama(content: str, published_at: datetime = None) -> dict:
    if len(content) < 50:
        return {}
    content  = content[:4000]
    date_str = (published_at or datetime.now()).strftime("%Y년 %m월 %d일")

    prompt = f"""아래 [기사 내용]을 읽고 분석하여 JSON을 출력하세요.
주의사항:
- 코스피, 코스닥에 관한 이벤트는 절대 포함하지 마세요. 나스닥, S&P500, 다우 등 해외 시장과 관련 내용만 분석하세요.
- [출력 예시]는 형식만 보여주는 가짜 데이터입니다. 예시의 수치, 종목, 문장을 절대 그대로 사용하지 마세요.
- 반드시 [기사 내용]에 실제로 등장하는 수치, 종목명, 섹터명만 사용하세요.
- market_event, one_line_summary의 모든 문장은 반드시 '~했습니다.', '~됩니다.', '~입니다.' 형태로 끝내세요. '~다, ~했다.', '~됐다.', '~이다.' 형태는 절대 사용하지 마세요.
- market_event, one_line_summary, sectors는 반드시 한국어(한글)로만 작성하세요. 한자(漢字)는 절대 사용하지 마세요.
- stocks의 종목명은 기사에 표기된 원문 그대로 사용하세요 (영문: "Nvidia", 한글: "엔비디아" 등 기사 표기 따름).
- sectors와 stocks에 등장하지 않는 항목은 빈 배열([])로 두세요.
- 설명이나 마크다운 없이 JSON만 출력하세요.

[JSON 스키마]
{{
  "date": "날짜 문자열",
  "market_event": ["이벤트1", "이벤트2", ...],
  "sectors": ["상승/하락 섹터1(등락률)", ...],
  "stocks": {{
    "up": ["종목명(등락률)", ...],
    "down": ["종목명(등락률)", ...]
  }},
  "one_line_summary": "한줄 요약"
}}

[출력 예시 - 형식 참고용 가짜 데이터, 절대 그대로 사용 금지]
{{
  "date": "2026년 3월 20일",
  "market_event": [
    "간밤 뉴욕 증시는 S&P500(-0.27%), 나스닥(-0.28%), 다우(-0.44%) 소폭 하락 마감했습니다.",
    "연준 금리 동결 결정에도 경기 침체 우려가 커지며 기술주 중심으로 매물이 출회됐습니다.",
    "원/달러 환율은 전일 대비 9원 하락한 1492원으로 안정세를 보였습니다."
  ],
  "sectors": ["기술(-1.2%)", "에너지(+0.8%)", "헬스케어(-0.5%)"],
  "stocks": {{
    "up": ["Nvidia(+2.15%)", "Meta(+1.03%)", "Amazon(+0.77%)"],
    "down": ["Micron(-3.78%)", "Intel(-2.10%)", "Tesla(-1.55%)"]
  }},
  "one_line_summary": "연준 금리 동결 발표에도 경기 침체 우려로 기술주가 하락하며 나스닥이 소폭 내렸습니다."
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
    print(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}] 크롤링 시작 — 한경 오늘장 미리보기")

    meta = fetch_today_article_meta()
    if not meta:
        print("  수집할 기사 없음 — 종료")
        return

    print(f"  기사: {meta['title'][:50]}")
    print(f"  URL : {meta['url']}")

    if collection.find_one({"news_id": meta["news_id"]}):
        print("  이미 저장된 기사 — 종료")
        return

    content = fetch_article_content(meta["url"])
    if len(content) < 50:
        print("  본문 없음 — 종료")
        return
    print(f"  본문 길이: {len(content)}자")

    print("  요약 중...")
    summary = summarize_with_ollama(content, meta.get("published_at"))

    clean_title = re.sub(r'\[뉴욕\s*증시\s*브리핑\]\s*', '', meta["title"]).strip()

    doc = {
        "news_id":     meta["news_id"],
        "title":       clean_title,
        "content":     content,
        "summary":     summary,
        "source":      "hankyung",
        "stock_index": "NASDAQ",
        "source_url":  meta["url"],
        "published_at": meta["published_at"],
        "fetched_at":  datetime.now(),
    }

    collection.update_one(
        {"news_id": meta["news_id"]},
        {"$set": doc},
        upsert=True,
    )
    print(f"  MongoDB 저장 완료: {meta['title'][:50]}")
