"""
종목명 → 종목코드 변환 모듈

CSV 파일을 서버 시작 시 1회 로드하여 dict로 캐싱합니다.
사용자 메시지에서 가장 긴 종목명부터 순서대로 검사해 종목코드를 반환합니다.

지원 종목:
  kospi200_targets.csv  — KOSPI 200 (한글 종목명 → 6자리 코드)
  NASDAQ100.csv         — NASDAQ 100 (한글 종목명 / 영문 종목명 → 영문 티커)

영문 매칭 정규화:
  "APPLE INC" → "apple"  /  "ADVANCED MICRO DEVICES INC" → "advanced micro devices"
  INC, CORP, CO, PLC, NV, LLC 등 법인 접미사를 제거하고 소문자로 비교합니다.
  사용자가 "Apple", "apple", "advanced micro devices" 로 입력해도 매칭됩니다.
"""
import csv
import re
from functools import lru_cache
from pathlib import Path

# CSV 파일 위치: AI/ 루트
_CSV_DIR = Path(__file__).parent.parent.parent

# ── 종목명 동의어 사전 ─────────────────────────────────────────────────────────
# 키: 사용자가 입력할 수 있는 줄임말/별칭
# 값: CSV에 등록된 정식 종목명
_SYNONYMS: dict[str, str] = {
    # KOSPI
    "삼전":      "삼성전자",
    "삼성":      "삼성전자",
    "하이닉":    "SK하이닉스",
    "SK하닉":    "SK하이닉스",
    "sk하닉":    "SK하이닉스",
    "하닉":      "SK하이닉스",
    "현대":      "현대차",
    "기아차":    "기아",
    "LG전자":    "LG전자",
    "엘지전자":  "LG전자",
    "엘지":      "LG전자",
    "카카오뱅":  "카카오뱅크",
    "카뱅":      "카카오뱅크",
    "카카오페이": "카카오페이",
    "카페이":    "카카오페이",
    "네이버":    "NAVER",
    # NASDAQ
    "엔비디아":  "엔비디아",   # 한글 표기 통일
    "엔디비아":  "엔비디아",
    "nvda":      "엔비디아",
    "마소":      "마이크로소프트",
    "ms":        "마이크로소프트",
    "구글":      "알파벳 A",
    "알파벳":    "알파벳 A",
    "유튜브":    "알파벳 A",
    "아마존":    "아마존닷컴",
    "메타":      "메타 플랫폼스(페이스북)",
    "페이스북":  "메타 플랫폼스(페이스북)",
    "테슬":      "테슬라",
}

# 영문 사명 끝에 붙는 법인 접미사 (반복 제거 대상)
# "AMAZON COM INC" → 1차: "AMAZON COM" → 2차: "AMAZON"
_EN_SUFFIX = re.compile(
    r'\s+(COM|INC|CORP|CO|PLC|NV|LLC|LTD|AG|SA|SE|LP|GROUP|HOLDINGS?|COMPANY|'
    r'ENTERPRISES?|INTERNATIONAL|TECHNOLOGIES?|PHARMACEUTICALS?|SEMICONDUCTOR|'
    r'SPON.*|EACH.*|EUR.*|NY\s+REGISTRY.*)\s*$',
    re.IGNORECASE,
)


def _clean_en_name(raw: str) -> str:
    """
    법인 접미사를 반복 제거 후 소문자 반환.
    예) 'APPLE INC'         → 'apple'
        'AMAZON COM INC'    → 'amazon'   (COM → INC 순으로 2회 제거)
        'ADVANCED MICRO DEVICES INC' → 'advanced micro devices'
    """
    text = raw.strip()
    while True:
        cleaned = _EN_SUFFIX.sub("", text).strip()
        if cleaned == text:
            break
        text = cleaned
    return text.lower()


# ── CSV 로드 ───────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _load_stock_map() -> tuple[
    list[tuple[str, str]],   # kospi: [(한글명, 코드), ...]  — 길이 내림차순
    list[tuple[str, str]],   # nasdaq_ko: [(한글명, 코드), ...]
    list[tuple[str, str]],   # nasdaq_en: [(정규화된 영문명, 코드), ...]
]:
    """
    CSV에서 종목명·코드 리스트를 1회 로드합니다.
    긴 이름 순으로 정렬해 부분 매칭 오류를 방지합니다.
    """
    kospi_list  = _read_kospi()
    ko_list, en_list = _read_nasdaq()
    return kospi_list, ko_list, en_list


def _read_kospi() -> list[tuple[str, str]]:
    """kospi200_targets.csv — 헤더: stock_code, stock_name"""
    path = _CSV_DIR / "kospi200_targets.csv"
    result = []
    try:
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                name = row.get("stock_name", "").strip()
                code = row.get("stock_code", "").strip()
                if name and code:
                    result.append((name, code))
    except FileNotFoundError:
        pass
    return sorted(result, key=lambda x: len(x[0]), reverse=True)


def _read_nasdaq() -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """
    NASDAQ100.csv — 첫 줄 타이틀(표 1,,) 건너뜀
    헤더: stock_code, stock_name, stock_name_en

    Returns:
        (ko_list, en_list)
        ko_list: [(한글명, 코드), ...]
        en_list: [(정규화된 영문명, 코드), ...]  — 길이 내림차순
    """
    path = _CSV_DIR / "NASDAQ100.csv"
    ko_list, en_list = [], []
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()

        header_idx = next(
            (i for i, line in enumerate(lines) if line.startswith("stock_code")),
            None,
        )
        if header_idx is None:
            return ko_list, en_list

        for row in csv.DictReader(lines[header_idx:]):
            code    = row.get("stock_code",    "").strip()
            name_ko = row.get("stock_name",    "").strip()
            name_en = row.get("stock_name_en", "").strip()

            if not code:
                continue
            if name_ko:
                ko_list.append((name_ko, code))
            if name_en:
                cleaned = _clean_en_name(name_en)
                if cleaned:
                    en_list.append((cleaned, code))

    except FileNotFoundError:
        pass

    ko_list = sorted(ko_list, key=lambda x: len(x[0]), reverse=True)
    en_list = sorted(en_list, key=lambda x: len(x[0]), reverse=True)
    return ko_list, en_list


# ── 공개 API ──────────────────────────────────────────────────────────────────

def _apply_synonyms(message: str) -> str:
    """
    메시지에서 동의어를 정식 종목명으로 치환합니다.
    예) "SK하닉 뉴스 보여줘" → "SK하이닉스 뉴스 보여줘"
    """
    for alias, canonical in _SYNONYMS.items():
        if alias in message:
            message = message.replace(alias, canonical)
    return message


def resolve_from_csv(message: str) -> tuple[str | None, str | None]:
    """
    사용자 메시지에서 종목명을 찾아 (종목코드, 종목명)을 반환합니다.

    매칭 순서:
      0. 동의어 치환  (예: SK하닉 → SK하이닉스)
      1. KOSPI 200 한글 종목명  (예: 삼성전자, SK하이닉스)
      2. NASDAQ 100 한글 종목명 (예: 애플, 테슬라)
      3. NASDAQ 100 영문 종목명 (예: Apple, apple, advanced micro devices)
         → 대소문자 무시, 법인 접미사(INC 등) 제거 후 비교

    Args:
        message: 사용자 입력 메시지

    Returns:
        (stock_code, stock_name) — 매칭된 경우
        (None, None)             — 매칭 없음
    """
    message = _apply_synonyms(message)

    kospi_list, nasdaq_ko, nasdaq_en = _load_stock_map()
    msg_lower = message.lower()

    # 1. KOSPI 한글 종목명
    for name, code in kospi_list:
        if name in message:
            return code, name

    # 2. NASDAQ 한글 종목명
    for name, code in nasdaq_ko:
        if name in message:
            return code, name

    # 3. NASDAQ 영문 종목명 (소문자 정규화 후 비교)
    for name_clean, code in nasdaq_en:
        if name_clean in msg_lower:
            return code, name_clean

    return None, None
