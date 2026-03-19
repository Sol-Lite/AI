from transformers import PreTrainedTokenizerFast, BartForConditionalGeneration

MODEL_NAME = "EbanLee/kobart-summary-v3"
MAX_INPUT_LEN = 1026
MAX_SUMMARY_LEN = 300

print(f"모델 로딩 중: {MODEL_NAME}")
tokenizer = PreTrainedTokenizerFast.from_pretrained(MODEL_NAME)
model = BartForConditionalGeneration.from_pretrained(MODEL_NAME)
print("모델 로드 완료")


def summarize(text: str) -> str:
    if len(text) < 50:
        return text
    inputs = tokenizer(
        text,
        return_tensors="pt",
        max_length=MAX_INPUT_LEN,
        truncation=True,
        padding="max_length",
    )
    summary_ids = model.generate(
        inputs["input_ids"],
        attention_mask=inputs["attention_mask"],
        num_beams=4,
        max_length=MAX_SUMMARY_LEN,
        early_stopping=True,
        no_repeat_ngram_size=3,
    )
    return tokenizer.decode(summary_ids[0], skip_special_tokens=True)


def summarize_articles(articles: list) -> list:
    total = len(articles)
    for i, article in enumerate(articles, 1):
        content = article.get("content", "")
        try:
            article["summary"] = summarize(content)
            print(f"  요약 [{i}/{total}] {article.get('title', '')[:45]} → {article['summary'][:60]}...")
        except Exception as e:
            print(f"  요약 실패 [{i}/{total}] {article.get('news_id', '')}: {e}")
            article["summary"] = ""
    return articles
