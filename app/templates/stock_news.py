"""
시황 및 종목 뉴스 응답 템플릿 (한국 시황 / 미국 시황 / 종목별 뉴스)
"""

_SEP = "━" * 22

_NEWS_ICONS = ["1️⃣", "2️⃣", "3️⃣"]


def format_korea_summary(data: dict) -> str:
    summary = data.get("summary")
    if not summary:
        return "한국 시황 정보를 불러올 수 없습니다."

    if isinstance(summary, str):
        return f"**🇰🇷 한국 시황**\n\n{_SEP}\n\n{summary}"

    published_at     = data.get("published_at", "")
    date             = published_at or summary.get("date", "")
    market_events    = summary.get("market_event", [])
    sectors          = summary.get("sectors", {})
    stocks           = summary.get("stocks", {})
    one_line_summary = summary.get("one_line_summary", "")

    sections = [f"**🇰🇷 한국 시황  {date}**", _SEP]

    if one_line_summary:
        sections.append(f"**💬 {one_line_summary}**")

    if market_events:
        block = ["**📋 주요 이슈**"]
        for event in market_events:
            block.append(f"• {event}")
        sections.append("  \n".join(block))

    if sectors:
        block = ["**📊 섹터 동향**"]
        for market, sector_list in sectors.items():
            label = "KOSPI" if market == "kospi" else "KOSDAQ"
            block.append(f"**[{label}]**")
            for s in sector_list:
                block.append(f"• {s}")
        sections.append("  \n".join(block))

    if stocks:
        block = ["**📈 주요 종목**"]
        for market, side_dict in stocks.items():
            label = "KOSPI" if market == "kospi" else "KOSDAQ"
            up_list       = side_dict.get("up",   [])
            down_list     = side_dict.get("down", [])
            filtered_up   = [s for s in up_list   if s]
            filtered_down = [s for s in down_list if s]
            if filtered_up or filtered_down:
                block.append(f"**[{label}]**")
            for s in filtered_up:
                block.append(f"🔺 {s}")
            for s in filtered_down:
                block.append(f"🔻 {s}")
        sections.append("  \n".join(block))

    sections.append(_SEP)
    return "\n\n".join(sections)


def format_us_summary(data: dict) -> str:
    summary = data.get("summary")
    if not summary:
        return "미국 시황 정보를 불러올 수 없습니다."

    if isinstance(summary, str):
        return f"**🇺🇸 미국 시황**\n\n{_SEP}\n\n{summary}"

    published_at     = data.get("published_at", "")
    date             = published_at or summary.get("date", "")
    market_events    = summary.get("market_event", [])
    market_sentiment = summary.get("market_sentiment", "")
    one_line_summary = summary.get("one_line_summary", "")

    sections = [f"**🇺🇸 미국 시황  {date}**", _SEP]

    if one_line_summary:
        sections.append(f"**💬 {one_line_summary}**")

    if market_events:
        block = ["**📋 주요 이슈**"]
        for event in market_events:
            block.append(f"• {event}")
        sections.append("  \n".join(block))

    if market_sentiment:
        sections.append(f"**🧭 시장 심리**  \n{market_sentiment}")

    sections.append(_SEP)
    return "\n\n".join(sections)


def format_stock_news(data: dict) -> str:
    stock_code = data.get("stock_code", "")
    stock_name = data.get("stock_name") or stock_code
    news       = data.get("news", [])

    sections = [f"**📰 {stock_name} 종목 뉴스**", _SEP]

    if not news:
        sections.append("관련 뉴스가 없습니다.")
        sections.append(_SEP)
        return "\n\n".join(sections)

    for idx, item in enumerate(news):
        icon         = _NEWS_ICONS[idx] if idx < len(_NEWS_ICONS) else f"{idx + 1}."
        title        = item.get("title",        "")
        summary      = item.get("summary",      "")
        published_at = item.get("published_at", "")

        date_str = f"  ({published_at})" if published_at else ""
        block = [f"**{icon} {title}**{date_str}"]

        if summary:
            if isinstance(summary, str):
                block.append(f"💡 {summary}")
            elif isinstance(summary, dict):
                one_line = summary.get("one_line_summary") or summary.get("summary", "")
                if one_line:
                    block.append(f"💡 {one_line}")

        sections.append("  \n".join(block))

    sections.append(_SEP)
    return "\n\n".join(sections)
