import threading
from transformers import PreTrainedTokenizerFast, BartForConditionalGeneration

MODEL_NAME = "EbanLee/kobart-summary-v3"
MAX_INPUT_LEN = 1026
MAX_SUMMARY_LEN = 300

_tokenizer = None
_model = None
_lock = threading.Lock()


def _load_model():
    global _tokenizer, _model
    with _lock:
        if _tokenizer is None:
            print(f"모델 로딩 중: {MODEL_NAME}")
            _tokenizer = PreTrainedTokenizerFast.from_pretrained(
                MODEL_NAME, local_files_only=True
            )
            _model = BartForConditionalGeneration.from_pretrained(
                MODEL_NAME, local_files_only=True
            )
            print("모델 로드 완료")


def summarize(text: str) -> str:
    if len(text) < 50:
        return text
    _load_model()
    inputs = _tokenizer(
        text,
        return_tensors="pt",
        max_length=MAX_INPUT_LEN,
        truncation=True,
        padding="max_length",
    )
    summary_ids = _model.generate(
        inputs["input_ids"],
        attention_mask=inputs["attention_mask"],
        num_beams=4,
        max_length=MAX_SUMMARY_LEN,
        early_stopping=True,
        no_repeat_ngram_size=3,
    )
    return _tokenizer.decode(summary_ids[0], skip_special_tokens=True)


def summarize_articles(articles: list) -> list:
    total = len(articles)
    result = []
    for i, article in enumerate(articles, 1):
        content = article.get("content", "")
        try:
            article["summary"] = summarize(content)
            print(f"  요약 [{i}/{total}] {article.get('title', '')[:45]} → {article['summary'][:60]}...")
            result.append(article)
        except Exception as e:
            print(f"  요약 실패 [{i}/{total}] {article.get('news_id', '')}: {e} → 저장 제외")
    return result
