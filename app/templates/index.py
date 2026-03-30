"""
지수
"""

_SEP = "━" * 22

_SIGN_MAP = {"2": "🔺", "5": "🔻", "1": "🔺", "4": "🔻"}

# 사용자 키워드 → API name 필드 매핑
_INDEX_KEYWORD_TO_NAMES = {
    "코스피":  ["KOSPI"],
    "코스닥":  ["KOSDAQ"],
    "나스닥":  ["NASDAQ", "나스닥", "NAS@IXIC", "IXIC"],
    "s&p":    ["S&P 500", "S&P500"],
    "에스앤피": ["S&P 500"],
    "다우":    ["DOW", "DJIA", "DOW JONES"],
    "닛케이":  ["NIKKEI", "N225"],
    "항셍":   ["HANG SENG", "HSI"],
}

# "한국 지수" / "국내 지수" → 코스피 + 코스닥
_KOREAN_INDEX_NAMES = ["KOSPI", "KOSDAQ"]

# "미국 지수" / "해외 지수" / "국외 지수" → 나스닥 + S&P
_US_INDEX_NAMES = ["NASDAQ", "NAS@IXIC", "IXIC", "나스닥", "S&P 500", "S&P500"]

# 환율 관련 name 패턴 (지수 결과에서 제외)
_EXCHANGE_RATE_KEYWORDS = ["USD", "EUR", "JPY", "CNY", "환율", "원달러", "달러원", "USDKRW", "FX"]


def _is_exchange_rate(item: dict) -> bool:
    name_upper = item.get("name", "").upper()
    code_upper = item.get("code", "").upper()
    return any(kw.upper() in name_upper or kw.upper() in code_upper for kw in _EXCHANGE_RATE_KEYWORDS)


def _find_items_by_api_names(items: list, api_names: list) -> list:
    result = []
    for item in items:
        item_name_upper = item.get("name", "").upper()
        if any(n.upper() in item_name_upper for n in api_names):
            if item not in result:
                result.append(item)
    return result


def _filter_for_message(items: list, user_message: str) -> list:
    """사용자 메시지에서 요청한 지수만 추출. 해당 지수가 API에 없으면 '조회 불가' placeholder 추가."""
    msg_lower = user_message.lower()

    # 환율 항목 사전 제거
    items = [item for item in items if not _is_exchange_rate(item)]

    # 한국 지수 / 국내 지수
    is_korean = any(kw in msg_lower for kw in ["한국 지수", "한국지수", "국내 지수", "국내지수", "한국증시 지수"])
    # 미국 지수 / 해외 지수 / 국외 지수
    is_us = any(kw in msg_lower for kw in ["미국 지수", "미국지수", "국외 지수", "국외지수", "해외 지수", "해외지수"])

    if is_korean:
        return _find_items_by_api_names(items, _KOREAN_INDEX_NAMES)

    if is_us:
        return _find_items_by_api_names(items, _US_INDEX_NAMES)

    # 개별 키워드 매칭
    matched = []
    for kw, api_names in _INDEX_KEYWORD_TO_NAMES.items():
        if kw not in msg_lower:
            continue

        found_any = False
        for item in items:
            item_name_upper = item.get("name", "").upper()
            if any(n.upper() in item_name_upper for n in api_names):
                if item not in matched:
                    matched.append(item)
                    found_any = True

        if not found_any:
            # API에 해당 지수 없음 → 조회 불가 표시
            matched.append({
                "name": kw,
                "price": None,
                "sign": None,
                "change": None,
                "changeRate": None,
            })

    # 아무 키워드도 매칭 안 됐으면 환율 제외한 전체 반환
    return matched if matched else items


def format_index(data, user_message: str | None = None) -> str:
    """
    지수 조회 결과를 한국어 텍스트로 변환합니다.

    Args:
        data: Spring API /api/market/indices 반환값 (list)
            [{"code": str, "name": str, "price": float|null,
              "sign": str|null, "change": float|null, "changeRate": float|null}, ...]
        user_message: 사용자 입력 (제공 시 요청한 지수만 필터링)
    """
    items = data if isinstance(data, list) else []
    if not items:
        return "지수 데이터를 불러올 수 없습니다."

    if user_message:
        items = _filter_for_message(items, user_message)

    sections = ["**주요 지수**", _SEP]

    for item in items:
        name        = item.get("name", "")
        price       = item.get("price")
        change      = item.get("change")
        change_rate = item.get("changeRate")
        sign_code   = str(item.get("sign") or "")

        if price is None:
            sections.append(f"**{name}**  \n조회 불가")
            continue

        sign = _SIGN_MAP.get(sign_code, "")
        if not sign and change_rate is not None:
            rate = float(change_rate)
            sign = "🔺" if rate > 0 else "🔻" if rate < 0 else ""

        price_str   = f"{float(price):,.2f}"
        change_str  = f"{sign}{abs(float(change)):,.2f}" if change is not None else ""
        rate_str    = f"({sign}{abs(float(change_rate)):.2f}%)" if change_rate is not None else ""

        block = [
            f"**{name}**",
            f"{price_str}  {change_str} {rate_str}".strip(),
        ]
        sections.append("  \n".join(block))

    sections.append(_SEP)
    return "\n\n".join(sections)