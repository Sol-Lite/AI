"""
chatbot 레이어 전용 종목 관련 유틸리티

CSV 기반 종목 참조 데이터(이름↔코드 변환, 동의어 등)는
app.stock_ref 모듈로 분리되었습니다.
이 모듈은 chatbot 레이어 고유의 상수와 하위 호환 re-export만 포함합니다.
"""

# ── chatbot 전용 상수 ─────────────────────────────────────────────────────────

# 섹터/테마 키워드 (종목명이 아닌 것들)
_SECTOR_KEYWORDS = {
    "바이오", "반도체", "제약", "화학", "자동차", "it", "금융", "에너지",
    "헬스케어", "게임", "엔터", "식품", "건설", "철강", "전기차", "배터리",
    "2차전지", "항공", "조선", "보험", "은행", "유통", "통신", "방산",
}
# 공개 이름 — chatbot 외부에서 import 시 사용
SECTOR_KEYWORDS = _SECTOR_KEYWORDS

# ── stock_ref re-export (하위 호환) ──────────────────────────────────────────
# 기존 코드에서 `from app.chatbot.resolver import ...` 로 사용하던 항목들.
# 새 코드는 app.stock_ref에서 직접 import하세요.
from app.stock_ref import (  # noqa: F401, E402
    _normalize_message,
    _apply_synonyms,
    resolve_from_csv,
    resolve_all_from_csv,
    resolve_name_from_code,
)
