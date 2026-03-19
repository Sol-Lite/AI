# ── MongoDB 설정 ──────────────────────────────────────────────
MONGO_URI = "mongodb+srv://<USERNAME>:<PASSWORD>@<CLUSTER>.mongodb.net/?appName=<APP_NAME>"
DB_NAME = "your_db_name"
COLLECTION_NAME = "stock_news"

# ── 상수 ──────────────────────────────────────────────────────
HEADERS = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15"}
NEWS_API_URL = "https://m.stock.naver.com/api/news/stock/{ticker}?pageSize={page_size}&page={page}"
ARTICLE_URL = "https://n.news.naver.com/mnews/article/{officeId}/{articleId}"

MEDIA_KEYWORDS = ["[포토]", "[사진]", "[동영상]", "[비디오]", "[포토뉴스]", "[영상]"]
TARGET_PER_STOCK = 20   # 종목당 목표 유효 기사 수
SCHEDULE_INTERVAL = 1800  # 30분
