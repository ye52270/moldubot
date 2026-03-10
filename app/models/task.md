# Models Task Log

## Purpose
- Describe this folder's responsibility.

## Change History
- 2026-02-28: Folder initialized as part of ideal project structure refactor.
- 2026-02-28 (before): 응답 품질 고도화를 위해 요약/보고서/예약 응답의 계약 모델(Contract) 파일을 추가하는 작업 시작.
- 2026-02-28 (after): `response_contracts.py`를 추가해 요약 응답(`SummaryResponseContract`)과 최종 응답(`FinalAnswerContract`)의 최소 계약을 정의.

## Update Rule
- Before and after any code change in this folder, append a detailed log entry.
- 2026-03-01 (before): 표준 요약 템플릿 렌더를 위해 `LLMResponseContract`에 `basic_info/core_issue/major_points/required_actions/one_line_summary` 필드를 확장하는 작업 시작.
- 2026-03-01 (after): `LLMResponseContract`에 `standard_summary` format과 `basic_info/core_issue/major_points/required_actions/one_line_summary` 필드를 추가하고 normalize 로직에 문자열/리스트/맵 정규화를 적용.
- 2026-03-01 (before): LLM 출력 JSON 강제를 위해 공통 응답 계약 모델(`LLMResponseContract`)을 `response_contracts.py`에 확장하는 작업 시작.
- 2026-03-01 (after): `response_contracts.py`에 `LLMResponseContract`를 추가하고 리스트 필드 정규화(중복 제거, 인라인 마크다운 제거)를 적용해 후처리 입력 계약을 안정화.
- 2026-03-02 (before): 요약 품질 개선을 위해 `LLMResponseContract` 리스트 정규화에서 유사 중복 문장까지 제거하는 보정 작업 시작.
- 2026-03-02 (after): `response_contracts.py`에 compare 정규화(`_normalize_compare_text`)를 추가해 공백/구두점 차이만 있는 major_points/required_actions 중복을 제거하도록 개선.
