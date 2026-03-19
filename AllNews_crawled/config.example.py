# ── MongoDB 설정 ──────────────────────────────────────────────
MONGO_URI = "mongodb+srv://<USERNAME>:<PASSWORD>@<CLUSTER>.mongodb.net/?appName=<APP_NAME>"
DB_NAME = "your_db_name"
COLLECTION_NAME = "news"

# ── 상수 ──────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

MAIN_NEWS_URL = "https://finance.naver.com/news/mainnews.naver"
ARTICLE_URL_TPL = "https://n.news.naver.com/mnews/article/{office_id}/{article_id}"

MEDIA_KEYWORDS = ["[포토]", "[사진]", "[동영상]", "[비디오]", "[포토뉴스]", "[영상]"]
TARGET_COUNT = 20
SCHEDULE_INTERVAL = 1800  # 30분(초)

# 중복 판정 임계값
SIMHASH_BITS = 64
TITLE_HAMMING_THRESHOLD = 5
CONTENT_JACCARD_THRESHOLD = 0.7
