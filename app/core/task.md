# Core Task Log

## Purpose
- Describe this folder's responsibility.

## Change History
- 2026-02-28: Folder initialized as part of ideal project structure refactor.
- 2026-02-28 (before): 공통 logging 설정/로거 획득 모듈 추가 작업 시작.
- 2026-02-28 (after): `logging_config.py` 추가, 공통 포맷/레벨 초기화 함수와 로거 헬퍼 함수 구현.
- 2026-02-28 (before): 의도 분해 규칙을 공통 모듈(`intent_rules.py`)로 분리하는 작업 시작.
- 2026-02-28 (after): `intent_rules.py`에 질의 정제/요약 줄수/날짜필터/step 추론/missing_slots 계산 규칙을 공통 함수로 정리하고 parser 재사용 기준을 확정.
- 2026-02-28 (before): 재검증 이슈 보완을 위해 `intent_rules.py`에 상대 날짜 범위/한글 절대 날짜/회의 일정 step 추론 규칙을 추가하는 작업 시작.
- 2026-02-28 (after): `2주 전부터 지난주까지` 상대 범위 토큰화(`2_weeks_ago_to_last_week`)와 `N월 N일부터 N월 N일까지` 절대 날짜(현재연도 기준 YYYY-MM-DD 변환) 규칙을 추가하고 회의 일정 step 추론을 보강.
- 2026-02-28 (before): `/search/chat` 운영 모니터링을 위해 요청 성공률/지연/폴백 비율을 집계하는 공통 메트릭 모듈(`metrics.py`) 추가 작업 시작.
- 2026-02-28 (after): `metrics.py`를 추가해 요청 수/성공률/폴백 비율/지연(p95 포함)을 스레드 안전하게 집계하는 `ChatMetricsTracker` 싱글턴 모듈을 구현.

## Update Rule
- Before and after any code change in this folder, append a detailed log entry.
