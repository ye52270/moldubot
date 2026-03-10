# Core Task Log

## Purpose
- Describe this folder's responsibility.

## Change History
- 2026-02-28: Folder initialized as part of ideal project structure refactor.
- 2026-02-28 (before): 예약 날짜 해석 일관성을 위해 상대 날짜(`오늘/내일/이번주`) 절대값 변환 공통 유틸 추가 작업 시작.
- 2026-02-28 (after): `date_resolver.py`를 추가해 상대/절대 예약 날짜를 서버 기준 `YYYY-MM-DD`로 정규화하는 공통 유틸(`resolve_booking_date_token`)을 구현.
- 2026-02-28 (before): 공통 logging 설정/로거 획득 모듈 추가 작업 시작.
- 2026-02-28 (after): `logging_config.py` 추가, 공통 포맷/레벨 초기화 함수와 로거 헬퍼 함수 구현.
- 2026-02-28 (before): 의도 분해 규칙을 공통 모듈(`intent_rules.py`)로 분리하는 작업 시작.
- 2026-02-28 (after): `intent_rules.py`에 질의 정제/요약 줄수/날짜필터/step 추론/missing_slots 계산 규칙을 공통 함수로 정리하고 parser 재사용 기준을 확정.
- 2026-02-28 (before): 재검증 이슈 보완을 위해 `intent_rules.py`에 상대 날짜 범위/한글 절대 날짜/회의 일정 step 추론 규칙을 추가하는 작업 시작.
- 2026-02-28 (after): `2주 전부터 지난주까지` 상대 범위 토큰화(`2_weeks_ago_to_last_week`)와 `N월 N일부터 N월 N일까지` 절대 날짜(현재연도 기준 YYYY-MM-DD 변환) 규칙을 추가하고 회의 일정 step 추론을 보강.
- 2026-02-28 (before): `/search/chat` 운영 모니터링을 위해 요청 성공률/지연/폴백 비율을 집계하는 공통 메트릭 모듈(`metrics.py`) 추가 작업 시작.
- 2026-02-28 (after): `metrics.py`를 추가해 요청 수/성공률/폴백 비율/지연(p95 포함)을 스레드 안전하게 집계하는 `ChatMetricsTracker` 싱글턴 모듈을 구현.
- 2026-02-28 (before): 2단계 정합성 강화를 위해 `intent_rules.py`의 상대 날짜 토큰/누락 슬롯 규칙 상수를 스키마와 동일 기준으로 통일하는 작업 시작.
- 2026-02-28 (after): `intent_rules.py`에 `ALLOWED_RELATIVE_DATE_FILTERS`, `ALLOWED_MISSING_SLOTS`, `is_allowed_relative_filter`를 추가해 스키마 검증과 동일한 허용 기준을 공통 모듈에서 재사용하도록 통일.
- 2026-03-01 (before): `intent_parser` fast-path 적중률을 높이기 위해 `intent_rules.py` step 추론 규칙(체크리스트/진행안/템플릿) 보강 작업 시작.
- 2026-03-01 (after): `intent_rules.py`에 `체크리스트/진행안/템플릿` 키워드 시 `extract_key_facts`를 추론하도록 추가해 해당 질의가 Ollama 구조분해 fallback으로 과도 step 생성되는 경로를 줄임.

## Update Rule
- Before and after any code change in this folder, append a detailed log entry.
- 2026-03-01 (before): 미들웨어/에이전트의 공통 payload 우선순위 결정을 위해 조회 질의 판별 helper를 공개 함수로 추가하는 작업 시작.
- 2026-03-01 (after): `intent_rules.py`에 `is_mail_search_query` 공개 helper를 추가해 조회형 질의 판별 로직을 미들웨어/에이전트 경로에서 공통 사용하도록 정리.
- 2026-03-01 (after): `is_prompt_trace_enabled()` 유틸을 추가해 `PROMPT_TRACE_ENABLED`(1/true/yes/on) 기반 트레이스 플래그를 공통으로 제공.
- 2026-03-01 (before): 조건 기반 메일 검색 의도 라우팅을 위해 `intent_rules.py` step 추론 규칙에 메일 조회 패턴(`조회/관련/최근/지난`) 보강 작업 시작.
- 2026-03-01 (after): `intent_rules.py`에 `_is_mail_search_query`를 추가하고 해당 질의에서 `search_mails` step을 추론하도록 확장.
- 2026-03-01 (before): `1월달` 메일 조회가 과거 연도로 해석되는 문제를 해결하기 위해 intent 날짜 필터 규칙 확장 작업 시작.
- 2026-03-01 (after): `intent_rules.extract_date_filter_fields`에 월-only 파서(`_extract_month_only_range`)를 추가해 연도 미명시 `N월`을 현재연도 범위로 해석하고, `작년/지난해`, `내년/다음해` 상대 연도 규칙을 적용.
- 2026-03-01 (before): 조회형 메일 질의에서 `read_current_mail` step이 섞여 현재메일 요약 경로로 오인되는 문제를 해소하기 위한 규칙 보정 작업 시작.
- 2026-03-01 (after): `infer_steps_from_query`에서 조건 조회형 메일 질의(`조회/검색/관련/최근/지난`)는 `read_current_mail`을 제외하고 `search_mails` 중심으로 분기하도록 수정.
- 2026-03-01 (before): `최근 4주 메일 조회`가 모델 내부 기준시각(2023)으로 절대 날짜를 생성하는 문제를 차단하기 위해 날짜 규칙 파서 보강 작업 시작.
- 2026-03-01 (after): `intent_rules`에 `_extract_recent_weeks_absolute_range`를 추가해 `최근 N주`를 서버 오늘 기준 absolute(start/end)로 해석하도록 수정, `extract_date_filter_fields` 우선순위에 반영.

- 2026-03-01 (before): 실호출 E2E+Judge 자동화를 위해 20개 채팅 평가 케이스 fixture(`chat_eval_cases.py`)를 core에 추가하는 작업 시작.

- 2026-03-01 (after): 실호출 E2E+Judge 자동화를 위해 `chat_eval_cases.py`에 20개 평가 문장(조회/현재메일/요약/표/보고서 혼합)을 정의하고 API/테스트에서 재사용 가능한 fixture로 반영.

- 2026-03-01 (before): chat-eval 케이스를 DB subject 실데이터 기반으로 재구성(19개 존재 + 1개 미존재)하기 위한 fixture 갱신 작업 시작.

- 2026-03-01 (after): `chat_eval_cases.py`를 실데이터 subject 기반으로 재구성(19개 존재 제목 + 1개 의도적 미존재 제목)하고 케이스 ID(`mail-01`~`mail-20`)는 유지해 기존 선택 실행 UX와 호환되도록 반영.

- 2026-03-01 (before): chat-eval 케이스 다양성 개선을 위해 제목 기반 편중을 줄이고 본문/현재메일 질의를 섞은 혼합형 query 세트로 fixture 재구성 작업 시작.

- 2026-03-01 (after): `chat_eval_cases.py`를 제목 편중에서 벗어나도록 혼합형으로 재구성(제목 기반 8건 + 본문 키워드 기반 4건 + 현재메일 기반 7건 + 미존재 본문 1건)하고 케이스 ID는 유지해 선택 실행 UX와 호환되게 반영.

- 2026-03-01 (before): chat-eval query의 `제목에 ...` 표현 편중을 줄이기 위해 자연어형 조회 문장으로 재작성하는 작업 시작.
- 2026-03-01 (after): `chat_eval_cases.py` 제목 기반 케이스를 전체 제목 복붙에서 부분 키워드 중심 자연어 질의로 보정(예: 조건부 액세스 정책, M365 AD 환경 구축, 퇴직자 수 안내)하고 본문 인명 질의(`박정호`, `박준용`)와 함께 혼합 구성을 유지.
- 2026-03-01 (before): `메일에서 ...`/`본문에 ... 포함된 메일` 질의를 조회형으로 강제 분류해 `search_mails` 누락을 방지하는 intent 규칙 보강 작업 시작.
- 2026-03-01 (after): `intent_rules._is_mail_search_query`를 보강해 `메일에서 ...` 및 `본문에 ... 포함` 패턴을 조회형으로 인식하도록 확장하고 `search_mails` step 누락 가능성을 낮춤.
- 2026-03-01 (before): `1월분/분기분` 표현을 수신일 절대필터로 오탐하는 규칙을 차단하기 위해 date_filter 추출 규칙 보정 작업 시작.
- 2026-03-01 (after): `_extract_month_only_range`에 청구기간 표현(`N월분/N분기분/상반기분/하반기분`) 예외를 추가해 수신일 date_filter absolute 오탐을 차단.
- 2026-03-02 (before): `메일 ... 보고서 형식으로 정리` 질의가 current_mail로 오분류되는 문제를 해결하기 위해 검색 질의 판별 규칙 보강 작업 시작.
- 2026-03-02 (after): `_is_mail_search_query`에 `현재메일` 예외를 추가하고 `정리` 토큰 및 `메일 ... 보고서 형식/보고용` 패턴을 검색형 조건으로 확장해 조회형 질의가 `read_current_mail`로 떨어지는 경로를 차단.
- 2026-03-02 (before): E2E Judge 케이스셋 20개를 사용자 지정 10개 시나리오로 교체하는 작업 시작.
- 2026-03-02 (after): `chat_eval_cases.py` 20개 케이스를 사용자 지정 10개 문구(`mail-01`~`mail-10`)로 교체하고, `현재메일 요약`만 `requires_current_mail=True`로 설정.
