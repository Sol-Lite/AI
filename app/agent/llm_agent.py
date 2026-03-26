"""
(11) 거래내역 / (12) 포트폴리오 분석 — llama AI agent

단순 조회 메시지 → 템플릿 포맷 반환
세부 질문 메시지 → 데이터를 컨텍스트로 llama에게 답변 요청

세부 질문 판단 키워드: 가장, 왜, 어떤, 얼마나, 비교, 최고, 최저, 몇, 언제, 어느, 분석, 추천
"""
import json
import httpx
from app.core.config import OLLAMA_BASE_URL, OLLAMA_MODEL

# 세부 질문으로 판단하는 키워드
_COMPLEX_KEYWORDS = [
    "가장", "왜", "어떤", "얼마나", "비교", "최고", "최저",
    "몇", "언제", "어느", "분석", "추천", "평균", "합계", "총",
]


def is_complex_query(message: str) -> bool:
    """단순 조회인지 세부 질문인지 판단합니다."""
    return any(kw in message for kw in _COMPLEX_KEYWORDS)


# ── llama 호출 ────────────────────────────────────────────────────────────────

def _ask_llama(system_prompt: str, user_message: str) -> str:
    """Ollama /api/chat 호출 → 응답 텍스트 반환"""
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
        "stream": False,
    }
    try:
        with httpx.Client(timeout=60) as client:
            resp = client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json()["message"]["content"]
    except httpx.TimeoutException:
        return "응답 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요."
    except Exception as e:
        return f"AI 응답 오류: {e}"


# ── (11) 거래내역 agent ───────────────────────────────────────────────────────

_TRADES_SYSTEM = """당신은 주식 투자 어시스턴트입니다.
아래는 사용자의 거래내역 데이터(JSON)입니다. 이 데이터만을 근거로 사용자 질문에 한국어로 간결하게 답하세요.
데이터에 없는 내용은 "데이터에서 확인할 수 없습니다"라고 답하세요.

거래 데이터:
{data}
"""


def ask_trades(data: dict, user_message: str) -> str:
    """거래내역 데이터를 컨텍스트로 llama에게 질문합니다."""
    system = _TRADES_SYSTEM.format(data=json.dumps(data, ensure_ascii=False, indent=2))
    return _ask_llama(system, user_message)


# ── (12) 포트폴리오 분석 agent ────────────────────────────────────────────────

_PORTFOLIO_SYSTEM = """당신은 투자 포트폴리오 분석 전문가입니다.
아래는 사용자의 포트폴리오 분석 데이터(JSON)입니다. 이 데이터만을 근거로 사용자 질문에 한국어로 간결하게 답하세요.
수치는 구체적으로 언급하고, 데이터에 없는 내용은 "데이터에서 확인할 수 없습니다"라고 답하세요.

포트폴리오 데이터:
{data}
"""


def ask_portfolio(data: dict, user_message: str) -> str:
    """포트폴리오 데이터를 컨텍스트로 llama에게 질문합니다."""
    system = _PORTFOLIO_SYSTEM.format(data=json.dumps(data, ensure_ascii=False, indent=2))
    return _ask_llama(system, user_message)
