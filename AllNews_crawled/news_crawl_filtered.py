import hashlib
import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from transformers import BartForConditionalGeneration, PreTrainedTokenizerFast


URL = "https://news.naver.com/breakingnews/section/101/259"
JSON_PATH = Path("naver_news_filtered.json")
MODEL_NAME = "EbanLee/kobart-summary-v3"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def simhash_title(title: str, bits: int = 64) -> int:
    title = re.sub(r"[^\w가-힣]", " ", title).strip()
    tokens = title.split()
    v = [0] * bits
    for token in tokens:
        h = int(hashlib.md5(token.encode()).hexdigest(), 16)
        for i in range(bits):
            v[i] += 1 if (h >> i) & 1 else -1
    return sum(1 << i for i in range(bits) if v[i] > 0)


def hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def deduplicate_by_title(news_list: list, threshold: int = 5) -> list:
    seen_hashes = []
    unique = []
    for news in news_list:
        h = simhash_title(news["title"])
        if all(hamming_distance(h, prev) > threshold for prev in seen_hashes):
            seen_hashes.append(h)
            unique.append(news)
    return unique


def word_shingles(text: str, k: int = 1) -> set:
    words = re.sub(r"[^\w가-힣]", " ", text).split()
    return set(zip(*[words[i:] for i in range(k)])) if len(words) >= k else set()


def jaccard_similarity(set_a: set, set_b: set) -> float:
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def deduplicate_by_content(articles: list, threshold: float = 0.7) -> list:
    shingle_sets = [word_shingles(a["content"]) for a in articles]
    unique_indices = []
    for i in range(len(articles)):
        is_dup = any(
            jaccard_similarity(shingle_sets[i], shingle_sets[j]) >= threshold
            for j in unique_indices
        )
        if not is_dup:
            unique_indices.append(i)
    return [articles[i] for i in unique_indices]


def load_model():
    tokenizer = PreTrainedTokenizerFast.from_pretrained(MODEL_NAME)
    model = BartForConditionalGeneration.from_pretrained(MODEL_NAME)
    return tokenizer, model


def clean_summary_text(text: str) -> str:
    cleaned = text.replace("\r", " ").replace("\n", " ").replace('"', "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"(?:\s*\.\s*){3,}", " ", cleaned).strip()
    return cleaned


def summarize_text(tokenizer, model, input_text: str) -> str:
    cleaned_text = " ".join(input_text.split())
    if not cleaned_text:
        return ""

    inputs = tokenizer(
        cleaned_text,
        return_tensors="pt",
        padding="max_length",
        truncation=True,
        max_length=1024,
    )

    summary_text_ids = model.generate(
        inputs["input_ids"],
        attention_mask=inputs["attention_mask"],
        num_beams=8,
        max_length=220,
        min_length=40,
        length_penalty=1.0,
        no_repeat_ngram_size=3,
        early_stopping=True,
    )

    decoded = tokenizer.decode(summary_text_ids[0], skip_special_tokens=True)
    return clean_summary_text(decoded)


def collect_news_list():
    driver = webdriver.Chrome()
    driver.get(URL)
    time.sleep(3)

    while True:
        titles = driver.find_elements(By.CSS_SELECTOR, "a.sa_text_title")
        if len(titles) >= 50:
            break

        try:
            more_btn = driver.find_element(By.PARTIAL_LINK_TEXT, "기사 더보기")
            more_btn.click()
            time.sleep(1)
        except Exception:
            break

    titles = driver.find_elements(By.CSS_SELECTOR, "a.sa_text_title")
    news_list = []

    for title_element in titles[:50]:
        news_list.append(
            {
                "title": title_element.text,
                "link": title_element.get_attribute("href"),
            }
        )

    driver.quit()
    return news_list


def clean_article_content(content_tag) -> str:
    for selector in [
        "figure",
        "figcaption",
        "table",
        "script",
        "style",
        "iframe",
        ".end_photo_org",
        ".img_desc",
        ".media_end_summary",
        ".byline",
        ".reporter_area",
        ".reporter_profile",
        ".copyright",
        ".vod_area",
    ]:
        for node in content_tag.select(selector):
            node.decompose()

    raw_lines = content_tag.get_text("\n", strip=True).split("\n")
    lines = [line.strip() for line in raw_lines if line.strip()]

    filtered_lines = []
    for line in lines:
        if len(line) <= 1:
            continue
        if "기사원문" in line:
            continue
        if "무단전재" in line or "재배포 금지" in line:
            continue
        if "All rights reserved" in line or "Copyright" in line:
            continue
        if "사진=" in line or "/사진=" in line or "사진출처" in line:
            continue
        if "제공." in line and len(line) <= 30:
            continue
        if line.endswith("기자") and len(line) <= 20:
            continue
        if "@" in line and len(line) <= 60:
            continue
        if re.fullmatch(r"입력\s*\d{4}\.\d{2}\.\d{2}.*", line):
            continue

        # Remove source/reporter prefixes like "[이데일리 권오석 기자]" or "[파이낸셜뉴스]"
        line = re.sub(r"^\[[^\]]{1,40}\]\s*", "", line).strip()
        line = re.sub(r"^(?:[가-힣A-Za-z·]+\s*){0,3}기자 =\s*", "", line).strip()

        if not line:
            continue
        filtered_lines.append(line)

    return " ".join(filtered_lines).strip()


def fetch_article(news):
    try:
        response = requests.get(news["link"], headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")

        content_tag = soup.select_one("#dic_area")
        content = clean_article_content(content_tag) if content_tag else ""

        thumb_tag = soup.select_one('meta[property="og:image"]')
        thumbnail = thumb_tag["content"] if thumb_tag else ""
    except Exception:
        content = ""
        thumbnail = ""

    return {
        "title": news["title"],
        "link": news["link"],
        "thumbnail": thumbnail,
        "content": content,
    }


def main():
    tokenizer, model = load_model()
    news_list = collect_news_list()
    result = []

    # 1단계: 제목 기반 중복 제거 (fetch 전)
    before = len(news_list)
    news_list = deduplicate_by_title(news_list, threshold=5)
    print(f"제목 중복 제거: {before}개 → {len(news_list)}개")

    articles = [fetch_article(news) for news in news_list]

    # 2단계: 본문 기반 중복 제거 (요약 전)
    before = len(articles)
    articles = deduplicate_by_content(articles, threshold=0.25)
    print(f"본문 중복 제거: {before}개 → {len(articles)}개")

    for index, article in enumerate(articles, start=1):
        article["summary"] = summarize_text(tokenizer, model, article["content"])
        result.append(article)
        print(f"[{index}/{len(articles)}] completed: {article['title']}")

    JSON_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=4),
        encoding="utf-8",
    )
    print(f"Saved filtered news and summaries to {JSON_PATH}")


if __name__ == "__main__":
    main()