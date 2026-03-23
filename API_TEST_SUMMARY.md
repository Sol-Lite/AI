# API 테스트 변경 요약

## 목적
- `get_market_data`와 `get_db_data(잔고)` 연동이 실제 호출 기준으로 정상 동작하는지 콘솔에서 빠르게 확인

## 반영 내용
- `test_api.py` 신규 작성 및 확장
  - 시장 API 테스트: `price`, `chart`, `daily`, `period_chart`, `ranking`, `index`, `exchange`
  - 잔고 API 테스트: `balance` (`GET /api/balance/cash`)
  - 실행 옵션: `--only market_all|all|개별항목`, 주요 파라미터 인자 추가
- `get_market_data.py` 업데이트
  - `period_chart`에 `period` 반영
  - 허용 enum: `DAILY`, `WEEKLY`, `MONTHLY`, `YEARLY`
  - `stock_code/start_date/end_date/period` 입력 검증 추가

## 실행 방법
- 시장 API 전체: `python test_api.py --only market_all`
- 전체(시장+잔고): `python test_api.py --only all`
- 기간차트 예시: `python test_api.py --only period_chart --stock-code 005930 --start-date 2026-01-01 --end-date 2026-03-23 --period WEEKLY`

## 현재 확인된 상태
- `ranking`: 응답 수신 확인(PASS)
- `balance`: `403` 응답(권한/인증 이슈 가능)
- `period_chart`: 일부 환경에서 timeout(3초) 발생(서버 응답 지연 가능)

## 참고
- `ranking` 테스트는 `type` 인자 충돌 가능성을 고려해 테스트 코드에 fallback 처리 포함
- `test_api.py`는 패키지 초기화 부작용을 피하려고 `get_market_data.py`를 직접 로드하도록 구성
