"""
시황 및 종목 뉴스 응답 템플릿 (한국 시황 / 미국 시황 / 종목별 뉴스)
"""

_SEP = "─" * 24


def format_korea_summary(data: dict) -> str:
    """
    한국 시황 요약 템플릿

    Args:
        data: _fetch_korea_summary() 반환값
            {
                "stock_index":  "KOSDAQ",
                "published_at": "2026년 03월 21일",   # 기사 기준일 (없으면 None)
                "summary": {
                    "date":             str,           # 기사 내 날짜 문자열 (없을 수 있음)
                    "market_event":     list[str],     # 주요 시장 이슈 문장 목록
                    "sectors": {
                        "kospi":  list[str],           # KOSPI 상승 섹터 목록 (예: "건설업(+3%대)")
                        "kosdaq": list[str],           # KOSDAQ 상승 섹터 목록
                    },
                    "stocks": {
                        "kospi": {
                            "up":   list[str],         # KOSPI 상승 종목 (예: "삼성전자(+0.12%)")
                            "down": list[str],         # KOSPI 하락 종목
                        },
                        "kosdaq": {
                            "up":   list[str],
                            "down": list[str],
                        },
                    },
                    "one_line_summary": str,           # 한줄 요약
                }
                # summary가 str인 경우 그대로 출력
                # summary가 None인 경우 오류 메시지 반환
            }
    """
    summary = data.get("summary")
    if not summary:
        return "한국 시황 정보를 불러올 수 없습니다."

    # summary가 문자열인 경우 그대로 반환
    if isinstance(summary, str):
        return f"한국 시황\n{_SEP}\n{summary}"

    published_at     = data.get("published_at", "")
    date             = published_at or summary.get("date", "")
    market_events    = summary.get("market_event", [])
    sectors          = summary.get("sectors", {})
    stocks           = summary.get("stocks", {})
    one_line_summary = summary.get("one_line_summary", "")

    lines = [f"한국 시황  {date}", _SEP]

    if one_line_summary:
        lines.append(one_line_summary)
        lines.append("")

    if market_events:
        lines.append("주요 이슈")
        for event in market_events:
            lines.append(f"  · {event}")
        lines.append("")

    if sectors:
        lines.append("상승 섹터")
        for market, sector_list in sectors.items():
            label = "KOSPI " if market == "kospi" else "KOSDAQ"
            lines.append(f"  {label}  " + "  ·  ".join(sector_list))
        lines.append("")

    if stocks:
        lines.append("주요 종목")
        for market, side_dict in stocks.items():
            label = "KOSPI " if market == "kospi" else "KOSDAQ"
            up_list   = side_dict.get("up",   [])
            down_list = side_dict.get("down", [])
            if up_list:
                lines.append(f"  {label}  ▲ " + "  ·  ".join(up_list))
            if down_list:
                lines.append(f"  {"":6}  ▼ " + "  ·  ".join(down_list))

    lines.append(_SEP)
    return "\n".join(lines)


def format_us_summary(data: dict) -> str:
    """
    미국 시황 요약 템플릿

    Args:
        data: _fetch_us_summary() 반환값
            {
                "stock_index":  "NASDAQ",
                "published_at": "2026년 03월 21일",   # 기사 기준일 (없으면 None)
                "summary": {
                    "date":             str,           # 기사 내 날짜 문자열 (없을 수 있음)
                    "market_event":     list[str],     # 주요 시장 이슈 문장 목록
                    "market_sentiment": str,           # 시장 심리 한줄 설명
                    "one_line_summary": str,           # 한줄 요약
                }
                # summary가 str인 경우 그대로 출력
                # summary가 None인 경우 오류 메시지 반환
            }
    """
    summary = data.get("summary")
    if not summary:
        return "미국 시황 정보를 불러올 수 없습니다."

    if isinstance(summary, str):
        return f"미국 시황\n{_SEP}\n{summary}"

    published_at     = data.get("published_at", "")
    date             = published_at or summary.get("date", "")
    market_events    = summary.get("market_event", [])
    market_sentiment = summary.get("market_sentiment", "")
    one_line_summary = summary.get("one_line_summary", "")

    lines = [f"미국 시황  {date}", _SEP]

    if one_line_summary:
        lines.append(one_line_summary)
        lines.append("")

    if market_events:
        lines.append("주요 이슈")
        for event in market_events:
            lines.append(f"  · {event}")
        lines.append("")

    if market_sentiment:
        lines.append("시장 심리")
        lines.append(f"  {market_sentiment}")

    lines.append(_SEP)
    return "\n".join(lines)


def format_stock_news(data: dict) -> str:
    """
    종목별 뉴스 요약 템플릿

    Args:
        data: _fetch_stock_news_summary() 반환값
            {
                "stock_code": str,       # 조회한 종목 코드 (예: "005930")
                "news": [
                    {
                        "title":        str,       # 뉴스 제목
                        "published_at": str,       # 기사 기준일 (예: "2026년 03월 21일", 없으면 None)
                        "summary": str | dict,     # 뉴스 요약
                                                   #   str인 경우 그대로 출력
                                                   #   dict인 경우 "one_line_summary" 또는 "summary" 키 사용
                    },
                    ...                            # 최신순 최대 3건
                ]
            }
    """
    stock_code = data.get("stock_code", "")
    stock_name = data.get("stock_name") or stock_code
    news       = data.get("news", [])

    lines = [f"{stock_name} 종목 뉴스", _SEP]

    if not news:
        lines.append("관련 뉴스가 없습니다.")
        lines.append(_SEP)
        return "\n".join(lines)

    for idx, item in enumerate(news, start=1):
        title        = item.get("title",        "")
        summary      = item.get("summary",      "")
        published_at = item.get("published_at", "")
        lines.append(f"{idx}. 기사제목: {title}  ({published_at})" if published_at else f"{idx}. 기사제목: {title}")
        if summary:
            if isinstance(summary, str):
                lines.append(f"   요약: {summary}")
            elif isinstance(summary, dict):
                one_line = summary.get("one_line_summary") or summary.get("summary", "")
                if one_line:
                    lines.append(f"   요약: {one_line}")
        lines.append("")

    lines.append(_SEP)
    return "\n".join(lines)
