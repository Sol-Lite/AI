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

# 섹터/테마 키워드 (종목명이 아닌 것들)
_SECTOR_KEYWORDS = {
    "바이오", "반도체", "제약", "화학", "자동차", "it", "금융", "에너지",
    "헬스케어", "게임", "엔터", "식품", "건설", "철강", "전기차", "배터리",
    "2차전지", "항공", "조선", "보험", "은행", "유통", "통신", "방산",
}

# CSV 파일 위치: AI/ 루트
_CSV_DIR = Path(__file__).parent.parent.parent

# ── 종목명 동의어 사전 ─────────────────────────────────────────────────────────
# 키: 사용자가 입력할 수 있는 줄임말/별칭
# 값: CSV에 등록된 정식 종목명
_SYNONYMS: dict[str, str] = {
    # ── 삼성 그룹 ────────────────────────────────────────────────────────────────
    "삼전":          "삼성전자",
    "삼성전":        "삼성전자",
    "하이닉":        "SK하이닉스",
    "SK하닉":        "SK하이닉스",
    "sk하닉":        "SK하이닉스",
    "sk하아닉스":        "SK하이닉스",
    "하닉":          "SK하이닉스",
    "삼바":          "삼성바이오로직스",
    "삼성바이오":    "삼성바이오로직스",
    "삼물산":        "삼성물산",
    "삼성생":        "삼성생명",
    "삼성화":        "삼성화재",
    "삼전기":        "삼성전기",
    "삼성에스디아이":       "삼성SDI",
    "삼성SDI":       "삼성SDI",
    "삼SDI":         "삼성SDI",
    "삼성중":        "삼성중공업",
    "삼성SDS":       "삼성에스디에스",
    "삼SDS":         "삼성에스디에스",
    "SDS":           "삼성에스디에스",
    "에스디에스":      "삼성에스디에스",
    "삼성이엔에이":       "삼성E&A",
    "삼성ENA":       "삼성E&A",
    "삼ENA":         "삼성E&A",
    "이엔에이":        "삼성E&A",
    "삼성증":        "삼성증권",
    "삼성카":        "삼성카드",

    # ── 현대 그룹 ────────────────────────────────────────────────────────────────
    "현차":          "현대차",
    "현대자동차":    "현대차",
    "현대모비":      "현대모비스",
    "현모비":        "현대모비스",
    "현대건":        "현대건설",
    "현건":          "현대건설",
    "현대제":        "현대제철",
    "현제철":        "현대제철",
    "현대글로":      "현대글로비스",
    "현글로":        "현대글로비스",
    "현대로템":      "현대로템",
    "현로템":        "현대로템",
    "현대해상":      "현대해상",
    "현대엘리":      "현대엘리베이터",
    "현엘리":        "현대엘리베이터",
    "현대오토":      "현대오토에버",
    "현대위아":      "현대위아",
    "현대백":        "현대백화점",
    "기아차":        "기아",

    # ── HD현대 그룹 ──────────────────────────────────────────────────────────────
    "HD현중":        "HD현대중공업",
    "에이치디현중":        "HD현대중공업",
    "에이치디현대중공업":        "HD현대중공업",
    "현중":          "HD현대중공업",
    "HD한조":        "HD한국조선해양",
    "현대조선":      "HD한국조선해양",
    "HD건기":        "HD건설기계",
    "HD현일":        "HD현대일렉트릭",
    "현대일렉":      "HD현대일렉트릭",
    "HD현대마린":    "HD현대마린솔루션",
    "HD현대마엔":    "HD현대마린엔진",

    # ── LG 그룹 ─────────────────────────────────────────────────────────────────
    "엘지전자":      "LG전자",
    "lg전자":      "LG전자",
    "엘지":          "LG전자",
    "LG엔솔":        "LG에너지솔루션",
    "lg엔솔":        "LG에너지솔루션",
    "lg에너지솔루션":        "LG에너지솔루션",
    "엘지에너지솔루션":        "LG에너지솔루션",
    "엔솔":          "LG에너지솔루션",
    "LG화":          "LG화학",
    "lg화학":          "LG화학",
    "엘지화학":          "LG화학",
    "LG이노":        "LG이노텍",
    "lg이노텍":        "LG이노텍",
    "엘지이노텍":        "LG이노텍",
    "LGD":           "LG디스플레이",
    "LGd":           "LG디스플레이",
    "LG디스":        "LG디스플레이",
    "LG생건":        "LG생활건강",
    "LG유플":        "LG유플러스",
    "LGU":           "LG유플러스",
    "LGCNS":         "LG씨엔에스",
    "LG씨엔에스":    "LG씨엔에스",
    "LG지주":        "LG",
    "lgD":           "LG디스플레이",
    "lgd":           "LG디스플레이",
    "lg디스":        "LG디스플레이",
    "lg생건":        "LG생활건강",
    "lg유플":        "LG유플러스",
    "lgU":           "LG유플러스",
    "lgu":           "LG유플러스",
    "lgCNS":         "LG씨엔에스",
    "lgcns":         "LG씨엔에스",
    "lg씨엔에스":    "LG씨엔에스",
    "lg지주":        "LG",

    # ── SK 그룹 ─────────────────────────────────────────────────────────────────
    "SKT":           "SK텔레콤",
    "SK텔":          "SK텔레콤",
    "SK이노":        "SK이노베이션",
    "SKI":           "SK이노베이션",
    "SK바팜":        "SK바이오팜",
    "SK바사":        "SK바이오사이언스",
    "SK케미":        "SK케미칼",
    "SK스퀘":        "SK스퀘어",
    "SKIET":         "SK아이이테크놀로지",
    "SKC":           "SKC",
    "skt":           "SK텔레콤",
    "sk텔":          "SK텔레콤",
    "sk이노":        "SK이노베이션",
    "skI":           "SK이노베이션",
    "sk바팜":        "SK바이오팜",
    "sk바사":        "SK바이오사이언스",
    "sk케미":        "SK케미칼",
    "sk스퀘":        "SK스퀘어",
    "skIET":         "SK아이이테크놀로지",
    "skist":         "SK아이이테크놀로지",
    "sk아이이테":         "SK아이이테크놀로지",
    "skc":           "SKC",

    # ── 한화 그룹 ────────────────────────────────────────────────────────────────
    "한화에어로":    "한화에어로스페이스",
    "한에어로":      "한화에어로스페이스",
    "한화오션":      "한화오션",
    "한화시스":      "한화시스템",
    "한화솔":        "한화솔루션",
    "한화생":        "한화생명",
    "한화지주":      "한화",
    "한화엔진":      "한화엔진",

    # ── POSCO 그룹 ───────────────────────────────────────────────────────────────
    "포스코":        "POSCO홀딩스",
    "POSCO":         "POSCO홀딩스",
    "posco":         "POSCO홀딩스",
    "포스코퓨처":    "포스코퓨처엠",
    "POSCOFM":       "포스코퓨처엠",
    "poscofm":       "포스코퓨처엠",
    "포스코인터":    "포스코인터내셔널",
    "포스코DX":      "포스코DX",
    "포스코dx":      "포스코DX",

    # ── KB·신한·하나·우리·NH 금융 ────────────────────────────────────────────────
    "깨비":          "KB금융",
    "신한":          "신한지주",
    "하나금융":      "하나금융지주",
    "하나지주":      "하나금융지주",
    "우리금융":      "우리금융지주",
    "우리지주":      "우리금융지주",
    "NH투자":        "NH투자증권",
    "nh투자":        "NH투자증권",
    "n2":        "NH투자증권",
    "메리츠":        "메리츠금융지주",
    "메리츠금융":    "메리츠금융지주",
    "한국금융":      "한국금융지주",
    "한투":          "한국금융지주",
    "BNK":           "BNK금융지주",
    "bnk":           "BNK금융지주",
    "JB금융":        "JB금융지주",
    "iM금융":        "iM금융지주",
    "jb금융":        "JB금융지주",
    "im금융":        "iM금융지주",
    "기업은":        "기업은행",
    "IBK":           "기업은행",
    "ibk":           "기업은행",
    "키움":          "키움증권",
    "미래에셋":      "미래에셋증권",
    "DB손보":        "DB손해보험",
    "DB손해":        "DB손해보험",
    "db손보":        "DB손해보험",
    "db손해":        "DB손해보험",

    # ── 통신 ────────────────────────────────────────────────────────────────────
    "KT통신":        "KT",
    "kt":        "KT",
    "네이버":        "NAVER",
    "naver":        "NAVER",

    # ── 카카오 계열 ──────────────────────────────────────────────────────────────
    "카카오뱅":      "카카오뱅크",
    "카뱅":          "카카오뱅크",
    "kakaobank":          "카카오뱅크",
    "카카오페이":    "카카오페이",
    "kakaopay":    "카카오페이",
    "카페이":        "카카오페이",

    # ── 에너지·화학 ──────────────────────────────────────────────────────────────
    "한전":          "한국전력",
    "에쓰오일":      "S-Oil",
    "S오일":         "S-Oil",
    "s오일":         "S-Oil",
    "금호석화":      "금호석유화학",
    "금호석":        "금호석유화학",
    "롯케미":        "롯데케미칼",
    "롯데케미":      "롯데케미칼",
    "가스공사":      "한국가스공사",
    "한솔케미":      "한솔케미칼",
    "한화솔루션":    "한화솔루션",
    "LS전기":        "LS ELECTRIC",
    "LS일렉":        "LS ELECTRIC",
    "OCI":           "OCI홀딩스",
    "ls전기":        "LS ELECTRIC",
    "ls일렉":        "LS ELECTRIC",
    "oci":           "OCI홀딩스",

    # ── 조선·항공·방산 ───────────────────────────────────────────────────────────
    "KAI":           "한국항공우주",
    "kai":           "한국항공우주",
    "한항우":        "한국항공우주",
    "대항공":        "대한항공",
    "KAL":           "대한항공",
    "kal":           "대한항공",
    "LIG넥":         "LIG넥스원",
    "LIG":           "LIG넥스원",
    "lig":         "LIG넥스원",
    "lig":           "LIG넥스원",
    "한미반":        "한미반도체",
    "효성중":        "효성중공업",

    # ── 유통·소비재 ──────────────────────────────────────────────────────────────
    "롯데쇼":        "롯데쇼핑",
    "롯데지":        "롯데지주",
    "아모레":        "아모레퍼시픽",
    "아모퍼":        "아모레퍼시픽",
    "아모레홀딩":    "아모레퍼시픽홀딩스",
    "불닭":          "삼양식품",
    "삼양":          "삼양식품",
    "BGF":           "BGF리테일",
    "GS리테":        "GS리테일",
    "bgf":           "BGF리테일",
    "gs리테":        "GS리테일",
    "롯데웰":        "롯데웰푸드",
    "하이트":        "하이트진로",
    "진로":          "하이트진로",
    "CJ제일":        "CJ제일제당",
    "CJ대한통운":    "CJ대한통운",
    "CJ지주":        "CJ",
    "cj제일":        "CJ제일제당",
    "cj대한통운":    "CJ대한통운",
    "씨제이지주":        "CJ",
    "씨제이제일":        "CJ제일제당",
    "씨제이대한통운":    "CJ대한통운",
    "씨제이지주":        "CJ",
    "씨제이":        "CJ",
    "cj":        "CJ",

    # ── 게임·엔터 ────────────────────────────────────────────────────────────────
    "엔씨":          "엔씨소프트",
    "NC":            "엔씨소프트",
    "nc":            "엔씨소프트",
    "강랜":          "강원랜드",

    # ── 제약·바이오 ──────────────────────────────────────────────────────────────
    "셀트리":        "셀트리온",
    "한미약":        "한미약품",
    "한미사이":      "한미사이언스",
    "유한":          "유한양행",
    "유양":          "유한양행",
    "대웅":          "대웅제약",
    "한올":          "한올바이오파마",
    "콜마":      "한국콜마",
    "SD바이오":      "에스디바이오센서",
    "sd바이오":      "에스디바이오센서",

    # ── 건설·물류 ────────────────────────────────────────────────────────────────
    "대우건":        "대우건설",
    "지에스건설":        "GS건설",
    "DL이앤씨":      "DL이앤씨",
    "디엘":            "DL",
    "에이치엠엠":           "HMM",
    "팬오션":        "팬오션",
    "한진칼":        "한진칼",

    # ── 기타 ─────────────────────────────────────────────────────────────────────
    "고려아연":      "고려아연",
    "두에빌":        "두산에너빌리티",
    "두산에너빌":    "두산에너빌리티",
    "두산밥캣":      "두산밥캣",
    "두산":          "두산",
    "한타이어":      "한국타이어앤테크놀로지",
    "한국타이어":    "한국타이어앤테크놀로지",
    "코웨이":        "코웨이",
    "한샘":          "한샘",
    "풍산":          "풍산",
    "호텔신라":      "호텔신라",
    "파라다이스":    "파라다이스",
    "지케이엘":           "GKL",
    "케이티엔지":          "KT&G",
    "한전기술":      "한전기술",
    "한전케이피에스":       "한전KPS",
    "엘앤에프":      "엘앤에프",
    "에코프로머티":  "에코프로머티",
    "효성티앤씨":    "효성티앤씨",
    "HS효성":        "HS효성첨단소재",
    "에이치에스효성":        "HS효성첨단소재",
    "씨에스윈드":    "씨에스윈드",
    "이수페타":      "이수페타시스",
    "한일시멘트":    "한일시멘트",
    "더블유게임":    "더블유게임즈",
    "에프엔에프":           "F&F",

    # ── NASDAQ 줄임말·별칭 ────────────────────────────────────────────────────────
    # CSV stock_name / stock_name_en 으로 직접 매칭되는 이름은 여기 넣지 않음
    # 여기는 CSV에 없는 줄임말·오기·별명만 등록"
    "엔디비아":      "엔비디아",          # 오기
    "마소":          "마이크로소프트",
    "구글":          "알파벳 A",
    "알파벳":        "알파벳 A",          # CSV는 "알파벳 A" / "알파벳 C"
    "유튜브":        "알파벳 A",
    "아마존":        "아마존닷컴",        # CSV는 "아마존닷컴"
    "메타":          "메타 플랫폼스(페이스북)",
    "페이스북":      "메타 플랫폼스(페이스북)",
    "페북":          "메타 플랫폼스(페이스북)",
    "테슬":          "테슬라",
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

def _normalize_message(message: str) -> str:
    """
    영문/숫자↔한글 경계 사이의 공백을 제거합니다.
    예) "SK 하이닉스 시세" → "SK하이닉스 시세"
        "LG 전자 주가"    → "LG전자 주가"
    """
    # 영문/숫자 뒤 공백 + 한글
    message = re.sub(r'([A-Za-z0-9])\s+([가-힣])', r'\1\2', message)
    # 한글 뒤 공백 + 영문/숫자
    message = re.sub(r'([가-힣])\s+([A-Za-z0-9])', r'\1\2', message)
    return message


def _apply_synonyms(message: str) -> str:
    """
    메시지에서 동의어를 정식 종목명으로 치환합니다.
    예) "SK하닉 뉴스 보여줘" → "SK하이닉스 뉴스 보여줘"

    단어 경계 체크: alias 뒤에 한글·영문·숫자가 바로 이어지면 치환하지 않습니다.
    예) "삼성" → "삼성전자" 치환 시 "삼성전기"는 건드리지 않습니다.
    """
    # 긴 alias부터 처리해 짧은 alias가 긴 alias를 덮어쓰는 문제 방지
    for alias, canonical in sorted(_SYNONYMS.items(), key=lambda x: len(x[0]), reverse=True):
        pattern = re.compile(re.escape(alias) + r'(?![가-힣a-zA-Z0-9])')
        message = pattern.sub(canonical, message)
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
    message = _normalize_message(message)
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



# 조사 뒤에 올 수 있는 패턴 (파티클 허용 동의어 확장에 사용)
_PARTICLE_LOOKAHEAD = re.compile(r'(?=[이가은는을를와과랑나도,\s]|이랑|이나|$)')


def resolve_all_from_csv(message: str) -> list[tuple[str, str]]:
    """
    메시지에서 여러 종목을 찾아 [(종목코드, 종목명), ...] 반환합니다.

    - 조사가 붙은 alias도 처리 ("삼전이랑" → 삼성전자)
    - 긴 이름 우선 매칭 + 어미 확인으로 부분 매칭 방지 ("SK하이닉스"에서 "SK" 제외)
    """
    original = _normalize_message(message)
    expanded = _apply_synonyms(original)

    # 조사 허용 추가 동의어 확장: "삼전이랑" 처럼 어미 때문에 _apply_synonyms에서 놓친 경우
    for alias, canonical in sorted(_SYNONYMS.items(), key=lambda x: len(x[0]), reverse=True):
        pat = re.compile(re.escape(alias) + r'(?=[이가은는을를와과랑나도,\s]|이랑|이나|$)')
        if pat.search(original) and canonical not in expanded:
            expanded = expanded + " " + canonical

    kospi_list, nasdaq_ko, nasdaq_en = _load_stock_map()
    exp_lower = expanded.lower()
    found: list[tuple[str, str]] = []
    seen_codes: set[str] = set()

    # 긴 이름부터 매칭, 뒤에 한글/영문자 없음을 확인해 부분 매칭 방지
    # ("SK하이닉스" 처리 후 "SK" 가 그 안에서 재매칭되는 것 방지)
    all_ko = sorted(kospi_list + nasdaq_ko, key=lambda x: len(x[0]), reverse=True)
    for name, code in all_ko:
        if code in seen_codes:
            continue
        pat = re.compile(re.escape(name) + r'(?![가-힣a-zA-Z0-9])')
        if pat.search(expanded):
            found.append((code, name))
            seen_codes.add(code)

    for name_clean, code in sorted(nasdaq_en, key=lambda x: len(x[0]), reverse=True):
        if code in seen_codes:
            continue
        pat = re.compile(re.escape(name_clean) + r'(?![a-z0-9])', re.IGNORECASE)
        if pat.search(exp_lower):
            found.append((code, name_clean))
            seen_codes.add(code)

    return found


def resolve_name_from_code(stock_code: str) -> str | None:
    """
    종목코드 → 종목명 역변환.
    예) "000660" → "SK하이닉스"

    Returns:
        종목명 문자열 — 매칭된 경우
        None         — 매칭 없음
    """
    kospi_list, nasdaq_ko, nasdaq_en = _load_stock_map()
    for name, code in kospi_list:
        if code == stock_code:
            return name
    for name, code in nasdaq_ko:
        if code == stock_code:
            return name
    return None
