"""
단일 agent — 5개 도구로 모든 질문 처리

도구:
    get_stock_price(stock_code)              — 종목 시세
    get_stock_news(stock_code)               — 종목별 뉴스
    get_portfolio_info(info_type)            — 포트폴리오 (holdings/returns/risk/stats)
    get_market_summary(market)               — 한국/미국 시황 (korea/us/both)
    get_trade_history(query_type, ...)       — 거래내역 (recent/by_stock/by_date)

흐름:
    1. MongoDB에서 대화 기록 조회
    2. system + history + user message → llama
    3. tool_calls → 실행 → 결과 추가 → 재전송 (최대 MAX_TURNS)
    4. 최종 content 반환
"""
import json
import logging
import re
import time
import httpx
from app.core.config import OLLAMA_BASE_URL, OLLAMA_MODEL
from app.templates.guide import _FALLBACK_MESSAGE, _API_ERROR_MESSAGE

logger = logging.getLogger("chatbot.agent")

MAX_TURNS = 5


# ── 도구 정의 ─────────────────────────────────────────────────────────────────

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_stock_price",
            "description": (
                "특정 종목의 현재가, 등락률, 거래량을 조회합니다. "
                "주가/시세/현재가 질문이나 종목명만 언급한 경우에 사용합니다. "
                "예) '하닉은?', '삼성전자 얼마야?', '현차 시세'"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "stock_code": {
                        "type": "string",
                        "description": "종목명으로 입력하세요 (예: 삼성전자, SK하이닉스, 엔비디아, Apple). 숫자 코드 입력 금지.",
                    }
                },
                "required": ["stock_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_news",
            "description": "특정 종목의 최신 뉴스/기사를 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "stock_code": {
                        "type": "string",
                        "description": "종목명으로 입력하세요 (예: 삼성전자, 테슬라, Apple). 숫자 코드 입력 금지.",
                    }
                },
                "required": ["stock_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_portfolio_info",
            "description": "사용자의 포트폴리오 정보를 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "info_type": {
                        "type": "string",
                        "enum": ["holdings", "returns", "risk", "stats"],
                        "description": (
                            "조회할 정보 유형:\n"
                            "- holdings: 현재 보유 중인 종목 목록·비중·보유 여부. '보유 주식/종목 알려줘'는 반드시 이 값 사용.\n"
                            "- returns: 기간별 수익률 (일간, 1개월, 3개월, 6개월)\n"
                            "- risk: 변동성, MDD, 평가손익, 보유 종목별 수익률, 최고/최저 수익 종목 (실현손익은 제공 불가)\n"
                            "- stats: 총 거래 횟수, 매수 횟수, 매도 횟수 (승률·손익비·평균 수익금은 현재 집계 불가)"
                        ),
                    }
                },
                "required": ["info_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_summary",
            "description": "한국 또는 미국 시장의 시황 요약을 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "market": {
                        "type": "string",
                        "enum": ["korea", "us", "both"],
                        "description": "조회할 시장: korea(한국/코스피/코스닥), us(미국/나스닥/S&P500), both(한국+미국 동시 조회)",
                    }
                },
                "required": ["market"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_trade_history",
            "description": "사용자의 거래내역을 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query_type": {
                        "type": "string",
                        "enum": ["recent", "by_stock", "by_date"],
                        "description": (
                            "조회 유형:\n"
                            "- recent: 최근 거래내역 및 전체 거래 요약\n"
                            "- by_stock: 특정 종목의 전체 거래내역\n"
                            "- by_date: 특정 날짜의 거래내역"
                        ),
                    },
                    "stock_code": {
                        "type": "string",
                        "description": "query_type=by_stock일 때 종목명으로 입력하세요 (예: 삼성전자, 엔비디아, 미래에셋증권). 숫자 코드 입력 금지.",
                    },
                    "date": {
                        "type": "string",
                        "description": "query_type=by_date일 때 날짜 (예: 2026-03-27, 3월 27일)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "query_type=recent일 때 조회 건수 (기본값: 10)",
                    },
                    "side": {
                        "type": "string",
                        "enum": ["buy", "sell"],
                        "description": "매수(buy) 또는 매도(sell)만 필터링. recent/by_date 모두 사용 가능. '판 종목'·'매도' → sell, '산 종목'·'매수' → buy. 생략 시 전체 반환.",
                    },
                },
                "required": ["query_type"],
            },
        },
    },
]


# ── 도구 실행기 ───────────────────────────────────────────────────────────────

def _fmt_rate(v) -> str:
    """수익률/등락률 float → 부호 포함 문자열. -0.00 방지"""
    if v is None:
        return "데이터 없음"
    if abs(v) < 0.005:
        return "0.00%"
    sign = "+" if v > 0 else ""
    return f"{sign}{v:.2f}%"


def _fmt_krw(v) -> str:
    if v is None:
        return "데이터 없음"
    return f"{int(v):,}원"


def _fmt_portfolio(info_type: str, data: dict) -> dict:
    """
    LLM 숫자 환각 방지: 포트폴리오 raw 수치를 포맷된 문자열로 교체.
    _해설 필드를 추가해 LLM이 수치를 재해석할 필요 없이 바로 활용하도록 한다.
    """
    if not isinstance(data, dict):
        return data

    if info_type == "holdings":
        holdings = data.get("holdings", [])

        # ── 1. 비중 계산 (포맷 전 raw float 사용) ───────────────────────────
        total_value = sum(h.get("current_value_krw", 0) for h in holdings) or 1
        dom_value   = sum(h.get("current_value_krw", 0) for h in holdings
                         if h.get("market_type") == "domestic")
        dom_pct  = round(dom_value  / total_value * 100, 1)
        fore_pct = round(100 - dom_pct, 1)

        top_h = max(holdings, key=lambda h: h.get("current_value_krw", 0)) if holdings else None

        # ── 2. 포맷: 가격·평가금액 문자열화, 불필요 raw 필드 제거 ────────────
        for h in holdings:
            is_overseas = h.get("market_type") == "overseas"
            raw_buy = h.get("avg_buy_price", 0)
            raw_cur = h.get("current_price", 0)
            raw_val = h.get("current_value_krw", 0)

            if is_overseas:
                h["avg_buy_price"]     = f"${float(raw_buy):,.2f}" if raw_buy else "$0.00"
                h["current_price"]     = f"${float(raw_cur):,.2f}" if raw_cur else "$0.00"
                h["current_value_krw"] = _fmt_krw(raw_val) if raw_val else "조회 불가"
            else:
                h["avg_buy_price"]     = _fmt_krw(raw_buy)
                h["current_price"]     = _fmt_krw(raw_cur)
                h["current_value_krw"] = _fmt_krw(raw_val)

            h["return_rate"] = _fmt_rate(h.get("return_rate", 0))
            h.pop("cost_basis",     None)
            h.pop("cost_basis_krw", None)

        # ── 3. 계산값을 top-level 필드로 주입 + _해설 생성 ─────────────────
        total = len(holdings)
        data["domestic_pct"] = f"{dom_pct}%"
        data["overseas_pct"] = f"{fore_pct}%"
        data["top_holding"]  = top_h["stock_name"] if top_h else None

        profit_stocks = [h for h in holdings if str(h.get("return_rate", "")).startswith("+")]
        loss_stocks   = [h for h in holdings if str(h.get("return_rate", "")).startswith("-")]

        lines = [f"현재 {total}개 종목을 보유 중이에요."]
        lines.append(f"국내 {dom_pct}%, 해외 {fore_pct}%로 구성되어 있고,")
        if top_h:
            lines.append(f"평가금액이 가장 큰 종목은 {top_h['stock_name']}예요.")
        if loss_stocks:
            lines.append(f"{len(profit_stocks)}개 종목은 수익, {len(loss_stocks)}개 종목은 손실 상태예요.")
        elif profit_stocks:
            lines.append(f"{len(profit_stocks)}개 종목 모두 수익 상태예요.")
        data["_해설"] = " ".join(lines)
        return data

    if info_type == "returns":
        for key in ("daily_return", "mdd"):
            if key in data and data[key] is not None:
                data[key] = _fmt_rate(data[key])
        for key in ("return_1m", "return_3m", "return_6m"):
            if key in data:
                data[key] = _fmt_rate(data[key]) if data[key] is not None else "데이터 없음"

        r1    = data.get("return_1m", "데이터 없음")
        r3    = data.get("return_3m", "데이터 없음")
        r6    = data.get("return_6m", "데이터 없음")
        best  = data.get("best_stock")
        worst = data.get("worst_stock")

        all_missing = all(v == "데이터 없음" for v in [r1, r3, r6])
        if all_missing:
            data["_해설"] = (
                "기간별 수익률 데이터가 아직 없어요. "
                "포트폴리오 스냅샷이 충분히 쌓이면 1개월·3개월·6개월 수익률을 확인할 수 있어요."
            )
        lines = [f"1개월 {r1}", f"3개월 {r3}", f"6개월 {r6}"]
        period_str = " / ".join(lines) + " 수익률이에요." if not all_missing else ""
        stock_lines = []
        if best:
            br = _fmt_rate(best.get("return_rate", 0)) if isinstance(best.get("return_rate"), float) else best.get("return_rate", "")
            stock_lines.append(f"수익률이 가장 좋은 종목은 {best['name']}({br})이고,")
        if worst:
            wr = _fmt_rate(worst.get("return_rate", 0)) if isinstance(worst.get("return_rate"), float) else worst.get("return_rate", "")
            stock_lines.append(f"수익률이 가장 낮은 종목은 {worst['name']}({wr})예요.")
        if not all_missing or stock_lines:
            data["_해설"] = " ".join([period_str] + stock_lines).strip()
        return data

    if info_type == "risk":
        raw_mdd  = data.get("mdd", 0)
        raw_vol  = data.get("volatility", 0)
        raw_rec  = data.get("recovery_needed", 0)
        raw_upnl = data.get("unrealized_pnl", 0)

        for key in ("mdd", "volatility"):
            if key in data:
                data[key] = _fmt_rate(data[key])
        if "recovery_needed" in data:
            raw_rec = data["recovery_needed"]
            rec_pct = raw_rec * 100 if isinstance(raw_rec, float) and raw_rec < 1 else float(raw_rec or 0)
            data["recovery_needed"] = f"+{rec_pct:.2f}%"
        prices_incomplete = data.get("prices_incomplete")  # 현재가 누락 종목 목록
        for key in ("realized_pnl",):
            if key in data:
                data[key] = _fmt_krw(data[key])
        if "unrealized_pnl" in data:
            if data["unrealized_pnl"] is None:
                data["unrealized_pnl"] = "조회 불가"
            else:
                data["unrealized_pnl"] = _fmt_krw(data["unrealized_pnl"])
        for stock_key in ("best_stock", "worst_stock"):
            s = data.get(stock_key)
            if s and isinstance(s, dict):
                s["return_rate"]    = _fmt_rate(s.get("return_rate", 0)) if isinstance(s.get("return_rate"), float) else s.get("return_rate", "")
                s["unrealized_pnl"] = _fmt_krw(s.get("unrealized_pnl", 0)) if isinstance(s.get("unrealized_pnl"), (int, float)) else s.get("unrealized_pnl", "")

        # _해설 생성
        mdd_pct  = abs(raw_mdd) * 100 if isinstance(raw_mdd, float) and abs(raw_mdd) < 1 else abs(float(str(raw_mdd).replace("%", "") or 0))
        vol_pct  = abs(raw_vol) * 100 if isinstance(raw_vol, float) and abs(raw_vol) < 1 else abs(float(str(raw_vol).replace("%", "") or 0))
        rec_pct  = raw_rec * 100 if isinstance(raw_rec, float) and raw_rec < 1 else float(str(raw_rec).replace("%", "") or 0)
        upnl_val = int(raw_upnl) if isinstance(raw_upnl, (int, float)) else 0

        lines = []
        if prices_incomplete:
            missing_str = "·".join(prices_incomplete)
            lines.append(f"일부 종목({missing_str}) 현재가 조회 불가로 평가손익을 계산할 수 없어요.")
        elif upnl_val < 0:
            lines.append(f"현재 평가손익은 {upnl_val:,}원으로 손실 상태예요.")
        elif upnl_val > 0:
            lines.append(f"현재 평가손익은 +{upnl_val:,}원으로 수익 상태예요.")

        lines.append(f"MDD는 {mdd_pct:.2f}%로, 보유 기간 중 고점 대비 최대 {mdd_pct:.2f}% 하락이 있었고, 일간 변동성은 {vol_pct:.2f}%예요.")
        if rec_pct > 0:
            lines.append(f"회복을 위해서는 +{rec_pct:.2f}%의 수익률이 필요해요.")

        pos_count  = data.get("pos_count", 0)
        neg_count  = data.get("neg_count", 0)
        best_stock = data.get("best_stock")   # 전체 수익률 최고
        worst_stock= data.get("worst_stock")  # 전체 수익률 최저
        neg_worst  = data.get("neg_worst")    # 손실 종목 중 손실률 최대

        if neg_count == 0:
            # 전체 수익 상태
            lines.append(f"현재 보유 종목 모두 수익 중이에요.")
            if best_stock:
                br = best_stock.get("return_rate", "")
                lines.append(f"수익률이 가장 좋은 종목은 {best_stock['name']}({br})이고,")
            if worst_stock:
                wr = worst_stock.get("return_rate", "")
                lines.append(f"수익률이 가장 낮은 종목은 {worst_stock['name']}({wr})예요.")
        elif pos_count == 0:
            # 전체 손실 상태
            lines.append(f"현재 보유 종목 모두 손실 상태예요.")
            if best_stock:
                br = best_stock.get("return_rate", "")
                lines.append(f"손실이 가장 적은 종목은 {best_stock['name']}({br})이고,")
            if worst_stock:
                wr = worst_stock.get("return_rate", "")
                lines.append(f"손실이 가장 큰 종목은 {worst_stock['name']}({wr})예요.")
        else:
            # 수익/손실 혼재
            if best_stock:
                br = best_stock.get("return_rate", "")
                lines.append(f"수익률이 가장 좋은 종목은 {best_stock['name']}({br})이고,")
            if neg_worst:
                wr = neg_worst.get("return_rate", "")
                lines.append(f"손실이 가장 큰 종목은 {neg_worst['name']}({wr})예요.")

        data["_해설"] = " ".join(lines)
        return data

    if info_type == "stats":
        for key in ("avg_win", "avg_loss", "total_realized"):
            if key in data and data[key] is not None:
                data[key] = _fmt_krw(data[key])

        total = data.get("total_trades", 0)
        buy   = data.get("buy_count",   0)
        sell  = data.get("sell_count",  0)

        lines = [f"총 {total}회 거래 (매수 {buy}회 / 매도 {sell}회)."]
        lines.append("승률·손익비·평균 수익금/손실금은 현재 집계되지 않아요.")
        data["_해설"] = " ".join(lines)
        return data

    return data


def _make_executor(account_id: str):
    def execute(name: str, args: dict) -> str:
        try:
            result = _execute(name, args, account_id)
        except Exception as e:
            result = {"error": str(e)}
        return json.dumps(result, ensure_ascii=False)
    return execute


_CORP_SUFFIX_RE = re.compile(
    r'\s+(electronics|electric|motor|motors|holdings|semiconductor|'
    r'bio|chemical|insurance|securities|bank|co\.?|ltd\.?|corp\.?|inc\.?|'
    r'technology|technologies|group|system|systems)$',
    re.IGNORECASE,
)

_CORP_SUFFIX_RE = re.compile(
    r'\s+(electronics|electric|motor|motors|holdings|semiconductor|'
    r'bio|chemical|insurance|securities|bank|co\.?|ltd\.?|corp\.?|inc\.?|'
    r'technology|technologies|group|system|systems)$',
    re.IGNORECASE,
)

_EN_STOCK_MAP = {
    "samsung":          "삼성전자",
    "hyundai":          "현대차",
    "kia":              "기아",
    "kakao":            "카카오",
    "naver":            "네이버",
    "hynix":            "SK하이닉스",
    "sk hynix":         "SK하이닉스",
    "lg":               "LG전자",
    "lg electronics":   "LG전자",
    "posco":            "POSCO홀딩스",
    "krafton":          "크래프톤",
    "ncsoft":           "엔씨소프트",
    "netmarble":        "넷마블",
    "celltrion":        "셀트리온",
    "samsung bio":      "삼성바이오로직스",
    "kakaopay":         "카카오페이",
    "kakaobank":        "카카오뱅크",
}


def _resolve_stock(stock_input: str) -> str:
    """줄임말/동의어/영문명을 종목코드로 변환합니다. 예) '하닉' → '000660', 'Samsung' → '005930'"""
    from app.stock_ref import resolve_from_csv
    lower = stock_input.lower().strip()

    # 1. _EN_STOCK_MAP 정확히 매칭
    ko = _EN_STOCK_MAP.get(lower)
    if not ko:
        # 2. 회사명 접미어 제거 후 재시도: "Samsung Electronics" → "samsung" → "삼성전자"
        stripped = _CORP_SUFFIX_RE.sub("", lower).strip()
        ko = _EN_STOCK_MAP.get(stripped)
    if ko:
        stock_input = ko

    # 3. CSV 조회 (ticker / 한국어명)
    code, _ = resolve_from_csv(stock_input)
    if code:
        return code

    # 4. Oracle STOCK_NAME_EN 폴백 (해외 full name: "Micron Technology" 등)
    try:
        from app.db.oracle import resolve_stock_code
        db_code = resolve_stock_code(stock_input)
        if db_code:
            return db_code
    except Exception:
        pass

    return stock_input


def _execute(name: str, args: dict, account_id: str) -> dict:
    if name == "get_stock_price":
        from app.data.market import get_market_data
        stock_code = _resolve_stock(args["stock_code"])
        data = get_market_data(type="price", stock_code=stock_code)
        # LLM 숫자 환각 방지: 원시 숫자 제거 후 포맷된 문자열만 전달
        if isinstance(data, dict) and "current_price" in data:
            is_usd = data.get("currency", "KRW") == "USD"
            rate   = float(data.get("change_rate") or 0.0)
            r_sign = "+" if rate >= 0 else ""
            if is_usd:
                price  = float(data.get("current_price") or 0)
                change = float(data.get("change") or 0)
                c_sign = "+" if change >= 0 else ""
                price_str  = f"${price:,.2f}"
                change_str = f"{c_sign}${abs(change):,.2f}"
            else:
                price  = int(data.get("current_price") or 0)
                change = int(data.get("change") or 0)
                c_sign = "+" if change >= 0 else ""
                price_str  = f"{price:,}원"
                change_str = f"{c_sign}{change:,}원"
            return {
                "stock_name":    data.get("stock_name", stock_code),
                "stock_code":    data.get("stock_code", stock_code),
                "current_price": price_str,
                "change":        change_str,
                "change_rate":   f"{r_sign}{rate:.2f}%",
                "volume":        f"{int(data.get('volume') or 0):,}주",
                "market_type":   data.get("market_type"),
                "exchange_code": data.get("exchange_code"),
            }
        return data

    if name == "get_market_summary":
        from app.data.news import get_market_summary
        market = args.get("market", "korea")
        if market == "both":
            korea_result = get_market_summary(type="korea")
            us_result    = get_market_summary(type="us")
            return {"korea": korea_result, "us": us_result}
        return get_market_summary(type=market)

    if name == "get_stock_news":
        from app.data.news import get_market_summary
        stock_code = _resolve_stock(args.get("stock_code", ""))
        return get_market_summary(type="stock_news", stock_code=stock_code)

    if name == "get_portfolio_info":
        from app.data.portfolio import (
            get_holdings,
            get_portfolio_returns, get_portfolio_risk, get_trade_stats,
        )
        info_type = args.get("info_type", "holdings")
        dispatch = {
            "holdings": lambda: get_holdings(account_id),
            "returns":  lambda: get_portfolio_returns(account_id),
            "risk":     lambda: get_portfolio_risk(account_id),
            "stats":    lambda: get_trade_stats(account_id),
        }
        fn = dispatch.get(info_type)
        result = fn() if fn else {"error": f"Unknown info_type: {info_type}"}
        return _fmt_portfolio(info_type, result)

    if name == "get_trade_history":
        from app.data.trades import (
            get_trade_summary, get_recent_trades,
            get_trades_by_stock, get_trades_by_date,
        )
        query_type = args.get("query_type", "recent")
        if query_type == "recent":
            summary = get_trade_summary(account_id)
            recent  = get_recent_trades(account_id, limit=args.get("limit", 10), side=args.get("side"))
            trades  = recent["trades"]
            fmt_trades = []
            for t in trades:
                side_str = "매도" if str(t.get("side", "")).lower() == "sell" else "매수"
                qty      = int(t.get("quantity") or 0)
                price    = float(t.get("price") or 0)
                mkt      = str(t.get("market_type") or "").upper()
                at       = str(t.get("executed_at", ""))[:16]
                name     = str(t.get("stock_name") or "")
                is_overseas = mkt not in ("KOSPI", "KOSDAQ", "")
                if is_overseas:
                    fmt_trades.append(f"{at} {name} {side_str} {qty:,}주 @ 체결가 ${price:,.2f}")
                else:
                    fmt_trades.append(f"{at} {name} {side_str} {qty:,}주 @ 체결가 {int(price):,}원")
            # 종목명 목록 추출 (follow-up 현재가/뉴스 질문 시 _extract_last_stock이 사용)
            seen: list[str] = []
            for t in trades:
                n = str(t.get("stock_name") or "")
                if n and n not in seen:
                    seen.append(n)
            result = {**summary, "거래내역": fmt_trades, "종목목록": seen}
            buy_count  = int(result.get("buy_count",  0))
            sell_count = int(result.get("sell_count", 0))
            if buy_count > sell_count:
                result["매수_매도_비교"] = f"매수({buy_count}건)가 매도({sell_count}건)보다 많습니다."
            elif sell_count > buy_count:
                result["매수_매도_비교"] = f"매도({sell_count}건)가 매수({buy_count}건)보다 많습니다."
            else:
                result["매수_매도_비교"] = f"매수와 매도가 각각 {buy_count}건으로 같습니다."
            return result
        if query_type == "by_stock":
            stock_code = _resolve_stock(args["stock_code"])
            result = get_trades_by_stock(account_id, stock_code=stock_code)
            # raw 숫자 제거 후 포맷된 문장만 전달 (LLM 숫자 환각 방지)
            trades = result.get("trades", [])
            fmt_trades = []
            for t in trades[:5]:
                side  = "매도" if str(t.get("side", "")).lower() == "sell" else "매수"
                qty   = int(t.get("quantity") or 0)
                price = float(t.get("price") or 0)
                mkt   = str(t.get("market_type") or "").upper()
                at    = str(t.get("executed_at", ""))[:16]
                is_overseas = mkt not in ("KOSPI", "KOSDAQ", "")
                if is_overseas:
                    fmt_trades.append(f"{at} {side} {qty:,}주 @ 체결가 ${price:,.2f}")
                else:
                    fmt_trades.append(f"{at} {side} {qty:,}주 @ 체결가 {int(price):,}원")
            return {
                "stock_name": result.get("stock_name", stock_code),
                "stock_code": result.get("stock_code", stock_code),
                "count":      result.get("count", len(trades)),
                "거래내역":   fmt_trades,
            }
        if query_type == "by_date":
            from datetime import date as _date
            date_arg = args.get("date") or str(_date.today())
            result = get_trades_by_date(account_id, date=date_arg, side=args.get("side"))
            trades = result.get("trades", [])
            fmt_trades = []
            for t in trades[:10]:
                side_str  = "매도" if str(t.get("side", "")).lower() == "sell" else "매수"
                qty       = int(t.get("quantity") or 0)
                price     = float(t.get("price") or 0)
                mkt       = str(t.get("market_type") or "").upper()
                at        = str(t.get("executed_at", ""))[:16]
                name      = str(t.get("stock_name") or "종목명 없음")
                is_overseas = mkt not in ("KOSPI", "KOSDAQ", "")
                if is_overseas:
                    fmt_trades.append(f"{at} {name} {side_str} {qty:,}주 @ 체결가 ${price:,.2f}")
                else:
                    fmt_trades.append(f"{at} {name} {side_str} {qty:,}주 @ 체결가 {int(price):,}원")
            # 종목명 목록 추출 (follow-up 현재가/뉴스 질문 시 _extract_last_stock이 사용)
            seen: list[str] = []
            for t in trades:
                n = str(t.get("stock_name") or "")
                if n and n not in seen:
                    seen.append(n)
            return {
                "date":     result.get("date", date_arg),
                "count":    result.get("count", len(trades)),
                "거래내역": fmt_trades,
                "종목목록": seen,
            }
        return {"error": f"Unknown query_type: {query_type}"}

    return {"error": f"Unknown tool: {name}"}


# ── 시스템 프롬프트 ───────────────────────────────────────────────────────────

def _build_tool_system() -> str:
    """1턴용: 도구 선택에만 집중하는 짧은 프롬프트."""
    from datetime import date, timedelta
    today     = date.today()
    yesterday = today - timedelta(days=1)
    weekday_map = ["월", "화", "수", "목", "금", "토", "일"]
    weekday = weekday_map[today.weekday()]
    return f"""당신은 주식 투자 어시스턴트입니다. 오늘: {today}({weekday}요일).

[도구 선택 규칙]
수치가 필요한 질문은 반드시 도구를 먼저 호출하세요. 수치를 직접 생성하는 것은 절대 금지입니다.
도구가 필요하면 반드시 function call(tool_calls) 형식을 사용하세요. 텍스트로 도구를 호출하는 것은 금지입니다.
도구 인자의 종목명은 반드시 한국어로 입력하세요 (삼성전자, SK하이닉스 — Samsung 금지).

도구 선택 기준:
- 특정 종목 현재가/주가/시세 → get_stock_price
- 종목 뉴스/기사 → get_stock_news
- 한국/미국 시장 시황 → get_market_summary (market: korea/us/both)
  · 한국 시황만 → market=korea, 미국 시황만 → market=us
  · 국내+해외/한국+미국/두 시장 동시 → market=both
- 포트폴리오 질문 → get_portfolio_info (info_type 선택)
- 거래내역 질문 → get_trade_history (query_type 선택)
- 손익/평가손익/실현손익/수익률/수익금은 종목명이 있어도 get_portfolio_info 사용, get_stock_price 금지

포트폴리오 info_type 선택:
- 보유 주식/종목 목록, 지금 갖고 있는 종목, 종목 비중, 보유 여부 → holdings
  ※ "보유 주식/종목"은 반드시 get_portfolio_info(holdings). get_trade_history 사용 절대 금지.
  ※ get_trade_history는 과거 매수·매도 이력이며 현재 보유 여부와 무관합니다.
- 포트폴리오 전체 기간 수익률 (1개월·3개월·6개월 전체 포트폴리오 수익률) → returns
  ※ "수익률이 좋은/높은/낮은 종목" 등 종목별 비교는 returns 아님 → risk 사용
- 변동성, MDD, 평가손익, 수익률이 가장 좋은/나쁜 종목, 가장 많이 오른/내린 종목, 종목별 수익률 비교 → risk
  ※ 실현손익은 현재 제공 불가
- 총 거래 횟수, 매수/매도 횟수 → stats
  ※ 승률·손익비·평균 수익금은 현재 집계 불가. 사용자가 물어보면 "현재 제공되지 않아요"라고 안내하세요.

거래내역 query_type 선택:
- "최근에", "최근", "가장 최근", "마지막으로", "요즘" 등 날짜 미지정 최근 거래 → recent
  ※ "최근에 산/판 종목"처럼 명시적 날짜가 없으면 반드시 recent 사용. by_date 사용 금지.
- 특정 종목의 전체 거래 이력 → by_stock
- "오늘", "어제", "N월 N일" 등 명시적 날짜가 있는 거래 → by_date
  ※ 날짜 표현이 없으면 절대 by_date 사용 금지.

by_date 파라미터 규칙:
- '오늘 산/판/거래' → date="{today}"
- '어제 산/판/거래' → date="{yesterday}"
- '산 종목'·'매수' → side=buy, '판 종목'·'매도' → side=sell, '거래/매매' → side 생략

이전 대화 맥락 활용:
- 종목명만 있는 짧은 질문("하닉은?")은 이전 대화의 도구와 동일한 도구를 사용하세요.
  예) 이전에 get_stock_price → "하닉은?" → get_stock_price(SK하이닉스)
  예) 이전에 get_stock_news → "현차는?" → get_stock_news(현대차)
  예) 이전에 get_market_summary(korea) → "미국은?" → get_market_summary(us)
- 이전 대화에 "이전 조회 결과: A +X%, B -Y%." 형식이 있으면 도구를 다시 호출하지 말고 비교해서 답하세요.
- 이전 tool 결과로 답할 수 있으면 도구를 다시 호출하지 마세요.

다단계 질문:
포트폴리오/거래내역에서 종목을 찾은 뒤 현재가/뉴스가 필요하면 도구를 두 번 호출하세요.
예) "포트폴리오에서 제일 오른 종목 현재가" → get_portfolio_info(risk) → best_stock 확인 → get_stock_price(종목명)
예) "가장 최근에 매수한 종목 현재가" → get_trade_history(recent, side=buy, limit=1) → 종목목록[0] 확인 → get_stock_price(종목명)
예) "가장 최근에 판 종목 현재가" → get_trade_history(recent, side=sell, limit=1) → 종목목록[0] 확인 → get_stock_price(종목명)

투자와 무관한 질문: "투자 관련 질문만 답변드릴 수 있어요."라고 안내하세요.
섹터/업종 뉴스 요청: "섹터별 뉴스는 제공하지 않아요. 종목별 뉴스나 시황 뉴스를 이용해 주세요."라고 안내하세요."""


def _build_answer_system() -> str:
    """2턴용: 도구 결과를 받은 뒤 답변 생성에만 집중하는 프롬프트."""
    return """당신은 친근한 주식 투자 어시스턴트입니다.
반드시 해요체(~이에요, ~예요, ~해요, ~어요)로 답하세요. "~입니다", "~합니다", "~습니다" 체는 절대 사용하지 마세요.

[답변 생성 규칙]
- 도구 결과의 수치만 사용하세요. 수치를 재계산하거나 추측하는 것은 절대 금지입니다.
- 이전 turn의 수치를 현재 답변에 혼용하는 것은 절대 금지입니다.
- "조회한 데이터를 보여드렸어요." 같은 빈 응답은 절대 금지입니다. 반드시 질문에 맞는 실질적인 답변을 생성하세요.
- 도구 결과에 "error"가 있으면: get_stock_news → "{종목명}의 뉴스는 아직 수집되지 않았어요.", 그 외 → "데이터를 불러올 수 없어요."

주가 조회 결과 형식 (get_stock_price 도구 결과에만 사용):
"{stock_name} 현재가는 {current_price}이고, 전일 대비 {change} ({change_rate})입니다."
※ 포트폴리오 분석(get_portfolio_info) 결과에는 이 형식을 절대 사용하지 마세요.

포트폴리오 분석 응답 (get_portfolio_info 도구 결과):
- 도구 결과에 "_해설" 필드가 있으면 반드시 그것을 기반으로 답하세요.
- best_stock, worst_stock, neg_worst, pos_best, recovery_needed 등 영어 필드명을 절대 답변에 노출하지 마세요.
- 2~4문장의 해요체(~이에요/예요/해요)로 답하세요. "~입니다/합니다/습니다" 체 금지. 번호 목록·불릿(•, -, *)·표·소제목 형식 금지.
- 투자 조언·주관적 평가("변동성이 높으면 수익이 높다" 등) 금지.
- _해설 내용만 자연스러운 구어체로 풀어서 전달하세요. _해설에 없는 정보(종목명, 수치 등)는 절대 추가하지 마세요.
- _해설에 데이터 부족 안내가 포함된 경우 그 내용만 자연스럽게 전달하고, 없는 수치를 만들어 내지 마세요.
- 현재가·전일대비 같은 시장 가격 정보는 get_portfolio_info 결과에 없으면 절대 언급하지 마세요.

손실/수익 종목 질문 (risk 타입 결과에서만 적용. returns 타입에는 neg_count/pos_count가 없으므로 적용하지 마세요):
- 먼저 neg_count(손실 종목 수)와 pos_count(수익 종목 수)가 도구 결과에 있는지 확인하세요. 없으면 이 규칙은 무시하세요.
- "손실이 가장 큰 종목" / "가장 많이 내린 종목":
  · neg_count > 0이면 neg_worst 종목으로 답하세요.
  · neg_count == 0이면 "현재 모든 종목이 수익 상태로 손실 종목이 없어요."라고 답하세요.
- "수익이 가장 좋은 종목" / "가장 많이 오른 종목":
  · pos_count > 0이면 수익률이 가장 높은 종목 이름과 수익률로 답하세요.
  · pos_count == 0이면 모든 종목이 손실 상태임을 알리고, 손실이 가장 적은 종목 이름과 수익률로 답하세요.
- "수익이 가장 작은/낮은 종목":
  · pos_count > 0이면 수익률이 가장 낮은 수익 종목 이름과 수익률로 답하세요. (수익률이 낮아도 양수면 수익 중)
  · pos_count == 0이면 손실이 가장 큰 종목으로 답하세요.
- worst_stock은 전체 수익률 최저 종목으로, 양수이면 손실 종목이 아닙니다. "손실"이라는 표현을 쓰지 마세요.
- _해설 필드의 수익/손실 상태 설명을 반드시 반영하세요.
- 수치 간 비교는 허용. "양호", "우수", "위험", "안정적" 등 주관적 평가 금지.
- 투자 의견, 매수/매도 권유 금지.

보유 종목 응답:
- 보유 중: 종목명과 보유 수량을 포함해 보유 중임을 안내하세요.
- 미보유: 종목명을 언급하며 보유하지 않음을 안내하세요.

거래내역 응답:
- 도구 결과 "거래내역" 배열의 각 항목을 그대로 나열하세요. 재계산·추측 금지.
- 종목명이 포함되어 있으므로 "(종목명 미기재)" 같은 표현을 쓰지 마세요.
- 해요체(~이에요/예요/해요)로 2~4문장 자연스러운 문장으로 답하세요. 번호 목록·불릿(•, -, *)·소제목 형식 금지.
- 거래내역의 가격은 "체결가"(거래 당시 가격)이에요. "현재가"라고 절대 표현하지 마세요.
- "시가총액", "amount" 등 잘못된 용어 금지. 가격은 "체결가", 총금액은 "거래금액"으로 표현하세요.
- 사용자가 "판 종목"을 물었는데 결과 count=0이면 "해당 날짜에 매도 거래가 없어요."라고 안내하세요.
- 사용자가 날짜를 잘못 언급하면 실제 날짜로 정정하세요.

후속 질문("그 중에 뭐가 좋아?", "비중은?")에는 한두 문장으로 짧게 답하세요.
이전 대화에 포트폴리오 분석 결과가 있어도 전체를 다시 출력하지 마세요.

출력 금지:
- "volatility", "mdd", "best_stock", "unrealized_pnl" 등 영어 변수명
- "포트폴리오 분석 결과를 기반으로 답변합니다", "_해설을 바탕으로" 등 자신의 추론·판단 과정을 설명하는 문장
- 투자 조언, 포트폴리오 조정 권유"""


# ── 텍스트 형식 tool call fallback ───────────────────────────────────────────

_TEXT_TOOL_RE = re.compile(
    r'^(get_stock_price|get_stock_news|get_portfolio_info|get_trade_history|get_market_summary)\s*\(([^)]*)\)\s*$'
)
_TOOL_ARG_KEY = {
    "get_stock_price":    "stock_code",
    "get_stock_news":     "stock_code",
    "get_portfolio_info": "info_type",
    "get_market_summary": "market",
    "get_trade_history":  "query_type",
}


def _parse_text_tool_call(content: str) -> dict | None:
    """
    LLM이 function call 대신 텍스트로 "get_stock_price(삼성전자)" 같이 출력한 경우를 감지합니다.
    감지되면 tool_calls 형식으로 변환해 반환합니다.
    """
    m = _TEXT_TOOL_RE.match(content.strip())
    if not m:
        return None
    tool_name = m.group(1)
    arg_val   = m.group(2).strip().strip("\"'")
    arg_key   = _TOOL_ARG_KEY.get(tool_name, "stock_code")
    return {"function": {"name": tool_name, "arguments": {arg_key: arg_val}}}


# ── ReAct 루프 ────────────────────────────────────────────────────────────────

def _run_agent(
    user_message: str,
    tools: list,
    execute_tool,
    history: list,
) -> tuple[str, list]:
    """
    Returns:
        (response_text, intermediate_messages)
        intermediate_messages: tool_call + tool_result 메시지 목록
                               다음 대화 맥락 파악을 위해 MongoDB에 저장됩니다.
    """
    messages = [{"role": "system", "content": _build_tool_system()}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})
    turn_start = len(messages)  # tool 메시지가 추가되기 시작하는 인덱스
    tool_used = False  # 도구 결과가 추가된 뒤 답변 프롬프트로 교체하기 위한 플래그

    with httpx.Client(timeout=120) as client:
        for turn_idx in range(MAX_TURNS):
            payload = {
                "model":    OLLAMA_MODEL,
                "messages": messages,
                "tools":    tools,
                "stream":   False,
                "options":  {"temperature": 0},
            }
            _llm_start = time.time()
            logger.info("LLM 호출 시작 (turn=%d, model=%s)", turn_idx + 1, OLLAMA_MODEL)
            try:
                resp = client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
                resp.raise_for_status()
                logger.info("LLM 응답 수신 (turn=%d, %.2fs)", turn_idx + 1, time.time() - _llm_start)
            except httpx.TimeoutException:
                logger.error("LLM 타임아웃 (turn=%d, %.2fs 초과)", turn_idx + 1, time.time() - _llm_start)
                return _API_ERROR_MESSAGE, []
            except Exception:
                logger.exception("LLM 호출 오류 (turn=%d)", turn_idx + 1)
                return _API_ERROR_MESSAGE, []

            data       = resp.json()
            message    = data.get("message", {})
            tool_calls = message.get("tool_calls") or []

            if not tool_calls:
                content = message.get("content", "").strip()
                # LLM이 응답을 따옴표로 감싸는 경우 제거 (예: '"삼성전자 현재가는..."')
                if len(content) >= 2 and content[0] == '"' and content[-1] == '"':
                    content = content[1:-1].strip()
                # LLM이 function call 대신 텍스트로 tool call을 작성한 경우 직접 실행
                synthetic = _parse_text_tool_call(content)
                if synthetic:
                    tool_calls = [synthetic]
                else:
                    intermediate = messages[turn_start:]
                    logger.info("LLM 최종 응답 (turn=%d)", turn_idx + 1)
                    if tool_used:
                        # 툴 결과가 있으므로 answer_system으로 최종 답변 재생성
                        messages[0] = {"role": "system", "content": _build_answer_system()}
                        try:
                            ans_payload = {
                                "model":   OLLAMA_MODEL,
                                "messages": messages,
                                "tools":   [],
                                "stream":  False,
                                "options": {"temperature": 0},
                            }
                            ans_resp = client.post(f"{OLLAMA_BASE_URL}/api/chat", json=ans_payload)
                            ans_resp.raise_for_status()
                            ans_content = ans_resp.json().get("message", {}).get("content", "").strip()
                            if len(ans_content) >= 2 and ans_content[0] == '"' and ans_content[-1] == '"':
                                ans_content = ans_content[1:-1].strip()
                            return ans_content or content or _FALLBACK_MESSAGE, intermediate
                        except Exception:
                            logger.exception("answer_system 재생성 실패, 원본 응답 사용")
                    return content or _FALLBACK_MESSAGE, intermediate

            messages.append({"role": "assistant", "tool_calls": tool_calls})
            for call in tool_calls:
                fn   = call.get("function", {})
                name = fn.get("name", "")
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                logger.info("툴 호출: %s(%s)", name, args)
                try:
                    tool_result = execute_tool(name, args)
                except Exception as e:
                    logger.exception("툴 실행 오류: %s", name)
                    tool_result = json.dumps({"error": str(e)}, ensure_ascii=False)

                # 에러 결과를 LLM으로 다시 보내면 환각 발생 → 즉시 종료
                try:
                    _parsed = json.loads(tool_result) if isinstance(tool_result, str) else tool_result
                    if isinstance(_parsed, dict) and _parsed.get("error"):
                        logger.warning("툴 에러 응답: %s → %s", name, _parsed.get("error"))
                        intermediate = messages[turn_start:]
                        if name == "get_stock_news":
                            stock_name = args.get("stock_code", "해당 종목")
                            return f"{stock_name}의 뉴스는 아직 수집되지 않았어요.", intermediate
                        return _API_ERROR_MESSAGE, intermediate
                except Exception:
                    pass

                # get_portfolio_info(holdings/risk) 결과에 특정 종목이 없으면 즉시 "미보유" 반환
                # returns/sector/stats 는 종목별 데이터가 없으므로 체크 제외
                # 포트폴리오 비교/분석 문맥(가장, 수익률, 리스크 등)은 특정 종목 질문이 아니므로 체크 제외
                _PORTFOLIO_ANALYSIS_KW = re.compile(
                    r"가장|제일|젤|수익률|리스크|분석|비중|비율|높은|낮은|많이|적게|오른|내린"
                    r"|평가손익|실현손익|손익|수익금|손실금|평가액|MDD|mdd|변동성|승률|손익비"
                )
                # 미보유 체크: holdings 타입에서만, 분석 키워드 없을 때만 실행
                # risk 타입은 포트폴리오 전체 지표 조회이므로 종목 보유 여부 체크 제외
                if (
                    name == "get_portfolio_info"
                    and args.get("info_type") == "holdings"
                    and not _PORTFOLIO_ANALYSIS_KW.search(user_message)
                ):
                    try:
                        _pf = json.loads(tool_result) if isinstance(tool_result, str) else tool_result
                        from app.stock_ref import resolve_from_csv, _normalize_message as _nm
                        _code, _sname = resolve_from_csv(_nm(user_message))
                        # 추출된 종목명이 실제 메시지에 포함되지 않으면 대명사/오매칭 → 스킵
                        if _code and _sname and _sname in user_message:
                            _all = (
                                [h.get("stock_name", h.get("name", "")) for h in _pf.get("holdings", [])]
                                + [s.get("name", "") for s in _pf.get("stock_returns", [])]
                                + [_pf.get("best_stock", {}).get("name", "")]
                                + [_pf.get("worst_stock", {}).get("name", "")]
                            )
                            if _sname not in _all:
                                return f"{_sname}은(는) 현재 보유 종목이 아니에요.", messages[turn_start:]
                    except Exception:
                        pass

                messages.append({"role": "tool", "name": name, "content": tool_result})
                tool_used = True

                # 거래내역 조회 후 현재가 키워드가 있으면 get_stock_price 자동 실행
                # llama3.1:8b가 종목목록에서 종목명을 제대로 읽지 못해 환각하는 문제를 방지
                _PRICE_KW_RE = re.compile(r"현재가|주가|시세|얼마|가격")
                if name == "get_trade_history" and _PRICE_KW_RE.search(user_message):
                    try:
                        _tr = json.loads(tool_result) if isinstance(tool_result, str) else tool_result
                        _stocks = _tr.get("종목목록", [])
                        if _stocks:
                            _sname = _stocks[0]
                            logger.info("현재가 자동 연계: %s", _sname)
                            _price_result = execute_tool("get_stock_price", {"stock_code": _sname})
                            messages.append({
                                "role": "assistant",
                                "tool_calls": [{"function": {"name": "get_stock_price", "arguments": {"stock_code": _sname}}}],
                            })
                            messages.append({"role": "tool", "name": "get_stock_price", "content": _price_result})
                    except Exception:
                        logger.exception("현재가 자동 연계 실패")

    logger.warning("MAX_TURNS(%d) 초과 — fallback 반환", MAX_TURNS)
    return _FALLBACK_MESSAGE, []


# ── 맥락 보강 ─────────────────────────────────────────────────────────────────

_INTENT_KEYWORDS = ["뉴스", "기사", "주가", "시세", "현재가", "차트", "거래", "수익", "포트폴리오", "시황"]
_TOOL_SUFFIX = {
    "get_stock_news":    "뉴스",
    "get_stock_price":   "현재가",
    "get_trade_history": "거래내역",
}

# "그 종목", "그거", "그 주식" 등 직전 맥락 종목을 가리키는 패턴
_THAT_STOCK_RE = re.compile(r"(그|해당)\s*(종목|거|주식|애|놈)")


def _extract_last_stock(history: list) -> str | None:
    """
    최근 히스토리(최대 6개 메시지)에서 가장 마지막으로 언급된 종목명을 추출합니다.

    우선순위:
      1. get_stock_price / get_stock_news / get_trade_history(by_stock) tool_call 인자
      2. assistant 텍스트 응답의 첫 번째 종목명 ("현대차가 ...")
    """
    recent = history[-6:] if len(history) > 6 else history

    # 1. 가장 최근 tool 결과 메시지에서 stock_name 추출 (코드가 아닌 이름 우선)
    _STOCK_TOOLS = {"get_stock_price", "get_stock_news"}
    for msg in reversed(recent):
        if msg.get("role") != "tool":
            continue
        try:
            data = json.loads(msg["content"]) if isinstance(msg["content"], str) else msg["content"]
        except Exception:
            continue
        tool_name = msg.get("name", "")
        if tool_name in _STOCK_TOOLS:
            sname = data.get("stock_name", "")
            if sname and len(sname) >= 2:
                return sname
        # get_trade_history(recent/by_date) 결과의 종목목록에서 첫 번째 종목 반환
        if tool_name == "get_trade_history":
            stocks = data.get("종목목록", [])
            if stocks:
                return stocks[0]
            # by_stock 결과는 stock_name 필드 직접 보유
            sname = data.get("stock_name", "")
            if sname and len(sname) >= 2:
                return sname

    # 1-b. tool 결과에 stock_name 없으면 tool_call 인자에서 stock_code 추출
    for msg in reversed(recent):
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            for call in msg["tool_calls"]:
                fn   = call.get("function", {})
                name = fn.get("name", "")
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                if name in _STOCK_TOOLS:
                    stock = args.get("stock_code", "")
                    if stock:
                        return stock
                if name == "get_trade_history" and args.get("query_type") == "by_stock":
                    stock = args.get("stock_code", "")
                    if stock:
                        return stock

    # 1-c. get_portfolio_info(risk/returns) 결과에서 best/worst 종목 추출
    # 직전 user 메시지 키워드로 내린(worst) vs 오른(best) 판단
    _last_user_msg = ""
    for m in reversed(recent):
        if m.get("role") == "user":
            _last_user_msg = m.get("content", "")
            break
    _want_worst = bool(re.search(r"내린|하락|손실|나쁜|최저|낮", _last_user_msg))
    for msg in reversed(recent):
        if msg.get("role") != "tool" or msg.get("name") != "get_portfolio_info":
            continue
        try:
            data = json.loads(msg["content"]) if isinstance(msg["content"], str) else msg["content"]
            if _want_worst:
                stock_obj = data.get("worst_stock") or data.get("best_stock")
            else:
                stock_obj = data.get("best_stock") or data.get("worst_stock")
            if isinstance(stock_obj, dict):
                sname = stock_obj.get("name") or stock_obj.get("stock_name", "")
                if sname and len(sname) >= 2:
                    return sname
        except Exception:
            pass
        break

    # 2. 이전 user 메시지들에서 종목명 추출 (recent 범위 내에서 계속 탐색)
    #    예) "삼성전자 보유?" → "몇 주?" → "얼마에 거래했지" 흐름에서 삼성전자 반환
    from app.stock_ref import resolve_from_csv, _normalize_message as _nm2
    for msg in reversed(recent):
        if msg.get("role") == "user":
            _c, _s = resolve_from_csv(_nm2(msg.get("content", "")))
            if _c and _s:
                return _s

    # 3. assistant 텍스트 첫 줄에서 "종목명 + 조사" 패턴 추출
    #    예) "현대차가 -0.49%로", "SK하이닉스는 922,000원"
    _STOCK_IN_TEXT_RE = re.compile(
        r"([\uAC00-\uD7A3A-Za-z0-9&·]{2,12}?)\s*(?:가|이|는|은|의|을|를)\s"
    )
    _SKIP_WORDS = {"현재", "비중", "수익률", "해당", "보유", "이전", "직전", "다음", "해외", "국내", "네"}
    for msg in reversed(recent):
        if msg.get("role") == "assistant" and msg.get("content"):
            for line in msg["content"].strip().split("\n")[:3]:
                m = _STOCK_IN_TEXT_RE.search(line)
                if m:
                    candidate = m.group(1).strip()
                    if len(candidate) >= 2 and candidate not in _SKIP_WORDS:
                        from app.stock_ref import resolve_from_csv
                        _c, _ = resolve_from_csv(candidate)
                        if _c:
                            return candidate

    return None


_PRICE_NEWS_KW = {
    "현재가", "시세", "주가", "뉴스", "기사", "소식", "얼마", "가격",
    # 거래 follow-up: "몇 주 샀지", "얼마에 팔았지" 등
    "샀지", "팔았지", "매수했", "매도했", "거래했", "체결했",
    "몇 주", "수량", "몇 개",
}

# 포트폴리오 도구를 써야 하는 키워드 — get_stock_price로 오인하기 쉬운 단어들
# 긴 키워드가 짧은 키워드보다 먼저 매칭되어야 함 (예: "수익률" > "수익")
# set 대신 list로 순서를 보장
_PORTFOLIO_FORCE_KW: list[str] = [
    "평가손익", "실현손익", "수익금", "손실금", "평가액",  # 4자 이상 먼저
    "거래통계", "매매통계", "투자통계", "거래성과",        # 통계 키워드
    "수익률",                                               # "수익" 보다 먼저
    "거래 통계", "매매 통계", "투자 통계", "거래 성과",
    "손익",
    "수익",
]
_PORTFOLIO_FORCE_INFO: dict[str, str] = {
    "손익":     "risk",
    "평가손익": "risk",
    "실현손익": "risk",
    "수익률":   "returns",
    "수익금":   "risk",
    "손실금":   "risk",
    "평가액":   "holdings",
    "수익":     "risk",
    "거래통계":  "stats",
    "매매통계":  "stats",
    "투자통계":  "stats",
    "거래성과":  "stats",
    "거래 통계": "stats",
    "매매 통계": "stats",
    "투자 통계": "stats",
    "거래 성과": "stats",
}

# 이전에 조회한 종목끼리 비교 — 이전 get_stock_price 결과를 직접 참조해서 답해야 하는 경우
_PRICE_COMPARISON_RE = re.compile(
    r"(두|세|네|여러|그|이)\s*(종목|주식|회사)\s*(중|에서|가운데)"
    r"|(둘|셋|넷)\s*중"
    r"|어느\s*(쪽|게|것|종목|주식)\s*(이|가)?\s*(더|많이)"
    r"|(두|세|여러|이)\s*(종목|주식)\s*(비교|차이)"
    r"|(가장|제일|젤)\s*(많이)?\s*(오른|내린|상승|하락)"
    r"|더\s*(많이|크게)?\s*(오른|내린|올랐|내렸)"
)


def _extract_price_comparison_data(history: list) -> str | None:
    """
    history에서 get_stock_price tool 결과를 수집해 비교용 요약 문자열을 반환합니다.
    2개 이상의 종목 데이터가 있을 때만 반환합니다.

    예) "이전 조회 결과: 삼성전자 +0.54%, 현대차 -0.49%"
    """
    price_items: list[str] = []
    seen_names: set[str] = set()

    for msg in history:
        if msg.get("role") != "tool" or msg.get("name") != "get_stock_price":
            continue
        try:
            data = json.loads(msg["content"]) if isinstance(msg["content"], str) else msg["content"]
        except Exception:
            continue

        name = data.get("stock_name", "")
        if not name or name in seen_names:
            continue
        seen_names.add(name)

        rate = data.get("change_rate", "")
        if isinstance(rate, (int, float)):
            sign = "+" if rate >= 0 else ""
            rate_str = f"{sign}{rate:.2f}%"
        else:
            rate_str = str(rate)

        price_items.append(f"{name} {rate_str}")

    if len(price_items) >= 2:
        return "이전 조회 결과: " + ", ".join(price_items)
    return None


def _has_stock_in_msg(msg: str) -> bool:
    """메시지에 종목명/코드가 포함되어 있는지 확인합니다."""
    from app.stock_ref import resolve_from_csv, _normalize_message
    code, _ = resolve_from_csv(_normalize_message(msg))
    if code:
        return True
    if re.search(r'\b\d{6}\b', msg):
        return True
    if re.search(r'\b[A-Z]{2,5}\b', msg):
        return True
    return False


def _enrich_with_context(user_message: str, history: list) -> str:
    """
    메시지 맥락을 보강합니다.

    1. "그 종목 현재가" → "현대차 현재가"   (대명사 해소)
    2. "현재가 어때" (종목 없음) → "현대차 현재가 어때"  (follow-up 종목 주입)
    3. "하닉은?" (짧은 종목명) → "하닉 뉴스"  (직전 도구 타입 주입)
    """
    msg = user_message.strip()

    # ── 1. "그 종목 X" → "종목명 X" ──────────────────────────────────────────
    if _THAT_STOCK_RE.search(msg):
        stock = _extract_last_stock(history)
        if stock:
            msg = _THAT_STOCK_RE.sub(stock, msg)

    # ── 1-a0. 리스크 분석 질문 → risk 타입 강제 + 수치 해설 지시 ─────────────────
    if re.search(r"리스크\s*(분석|지표|현황|어때|얼마)", msg) or (
        "리스크" in msg and "분석" in msg
    ):
        return (
            f"{msg}\n"
            f"(get_portfolio_info(info_type=risk)를 호출한 뒤, "
            f"_해설 필드를 기반으로 평가손익·MDD·변동성·회복 필요 수익률·수익/손실 종목을 "
            f"2~4문장의 자연스러운 한국어 구어체로 설명하세요. "
            f"번호 목록·불릿·표·영어 필드명 노출 금지. 투자 권유 금지.)"
        )

    # ── 1-a-1. 특정 종목 보유 여부 질문 → holdings 타입 강제 지시 ──────────────────
    _HOLDINGS_CHECK_RE = re.compile(
        r".{1,10}(보유\s*(중|해|하고|있어|있나|있어요|하고\s*있)|갖고\s*있|가지고\s*있)"
    )
    if _HOLDINGS_CHECK_RE.search(msg):
        return f"{msg}\n(get_portfolio_info(info_type=holdings)를 호출한 뒤, 해당 종목의 보유 여부를 답하세요.)"

    # ── 1-a. 보유 종목 비교 질문 → risk 타입 강제 지시 ───────────────────────────
    # "포폴/포트폴리오 내 가장 수익률 좋은/나쁜 종목", "보유 중 가장 많이 오른/내린" 등
    _PORTFOLIO_RANK_RE = re.compile(
        # "보유 종목 중 가장 오른/내린/수익..."
        r"보유\s*(종목|주식|중|한).*?(가장|제일|젤|많이|오른|내린|올랐|내렸|수익|손해|높|낮)"
        r"|"
        r"(가장|제일|젤|더)\s*(많이)?\s*(오른|내린|올랐|내렸|수익|손실).*보유"
        r"|"
        # "포폴/포트폴리오 내에서 가장 수익률 좋은/나쁜/높은/낮은 종목"
        r"(포폴|포트폴리오|내\s*포폴|내\s*포트폴리오).{0,15}(가장|제일|젤).{0,10}(수익|오른|내린|높|낮|좋|나쁨)"
        r"|"
        # "가장/제일 수익률이 좋은/높은/낮은/나쁜 종목" (보유 명시 없어도)
        r"(가장|제일|젤)\s*.{0,8}수익률.{0,8}(좋|높|낮|나쁨|적|크|큰|작)"
        r"|"
        # "수익률이 가장 좋은/높은/낮은 종목"
        r"수익률.{0,5}(가장|제일|젤).{0,5}(좋|높|낮|나쁨|크|큰|작)"
    )
    if _PORTFOLIO_RANK_RE.search(msg):
        needs_price = any(pk in msg for pk in ("현재가", "시세", "주가", "얼마"))
        if needs_price:
            return (
                f"{msg}\n"
                f"(먼저 get_portfolio_info(info_type=risk)로 best_stock/worst_stock을 확인한 뒤, "
                f"해당 종목의 현재가를 get_stock_price로 조회하세요.)"
            )
        return (
            f"{msg}\n"
            f"(get_portfolio_info(info_type=risk)를 사용하세요. "
            f"neg_count/pos_count를 먼저 확인한 뒤: "
            f"'내린/손실' 질문이면 neg_count>0일 때 neg_worst로, neg_count==0이면 손실 종목 없음을 안내하세요. "
            f"'오른/수익' 질문이면 pos_count>0일 때 pos_best 또는 best_stock으로 답하세요. "
            f"'수익 최소' 질문이면 pos_worst 또는 worst_stock으로 답하되 양수 수익률임을 명시하세요.)"
        )

    # ── 1-b. 포트폴리오 키워드 감지 → get_portfolio_info 도구 지시 주입 ─────
    for kw in _PORTFOLIO_FORCE_KW:
        if kw in msg:
            info_type = _PORTFOLIO_FORCE_INFO.get(kw, "risk")
            # 현재가/시세도 함께 요청한 경우 → 두 번 호출 지시
            needs_price = any(pk in msg for pk in ("현재가", "시세", "주가", "얼마"))
            if needs_price:
                return (
                    f"{msg}\n"
                    f"(먼저 get_portfolio_info(info_type={info_type})로 종목을 확인한 뒤, "
                    f"해당 종목의 현재가를 get_stock_price로 조회하세요.)"
                )
            return f"{msg}\n(get_portfolio_info(info_type={info_type})를 호출한 뒤, 결과를 바탕으로 질문에 맞게 수치를 직접 답하세요. get_stock_price 사용 금지)"

    # ── 2. 가격/뉴스/거래 키워드 있는데 종목명 없음 → 직전 종목 주입 ─────────
    if any(kw in msg for kw in _PRICE_NEWS_KW) and not _has_stock_in_msg(msg):
        stock = _extract_last_stock(history)
        if stock:
            # "몇 주?" 는 거래 맥락에서만 "몇 주(株) 거래했어?"로 명확화
            if msg in ("몇 주?", "몇 주", "몇주?", "몇주"):
                return f"{stock} 몇 주 거래했어?"
            return f"{stock} {msg}"

    # ── 3. 두 종목 비교 질문 → 이전 가격 조회 결과를 메시지에 직접 주입 ────────
    if _PRICE_COMPARISON_RE.search(msg):
        price_summary = _extract_price_comparison_data(history)
        if price_summary:
            return (
                f"{msg}\n"
                f"({price_summary}. 새 도구를 호출하지 말고 이 데이터로 바로 비교해서 답하세요.)"
            )

    # ── 4. 짧은 종목명 + 이전 도구 타입 주입 ────────────────────────────────
    if len(msg) > 10 or any(kw in msg for kw in _INTENT_KEYWORDS):
        return user_message

    last_tool = None
    for m in reversed(history):
        if m.get("role") == "assistant" and m.get("tool_calls"):
            fn = m["tool_calls"][0].get("function", {})
            last_tool = fn.get("name")
            break

    suffix = _TOOL_SUFFIX.get(last_tool)
    if suffix:
        base = re.sub(r"[?은는이가도요\s]+$", "", msg)
        return f"{base} {suffix}"

    return user_message


# ── 공개 API ──────────────────────────────────────────────────────────────────

def ask_general(user_context: dict, user_message: str) -> tuple[str, list]:
    """
    단일 agent — 대화 기록 포함해 모든 질문을 처리합니다.

    Returns:
        (response_text, tool_context)
        tool_context: tool_call + tool_result 메시지 목록 (저장은 호출자가 담당)
    """
    account_id    = str(user_context.get("account_id", ""))
    session_since = user_context.get("session_since")

    try:
        from app.db.mongo import get_chat_history
        history = get_chat_history(account_id, limit=6, since=session_since)
    except Exception:
        history = []

    # 템플릿 placeholder를 history에서 제거 — agent가 복사하는 것을 방지
    _PLACEHOLDER = "조회한 데이터를 보여드렸어요."
    history = [
        {**msg, "content": ""}  if msg.get("role") == "assistant" and msg.get("content") == _PLACEHOLDER
        else msg
        for msg in history
    ]

    enriched_message = _enrich_with_context(user_message, history)
    execute_tool = _make_executor(account_id)
    response, tool_context = _run_agent(enriched_message, _TOOLS, execute_tool, history)
    return response, tool_context

