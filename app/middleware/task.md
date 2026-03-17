# Middleware Task Log

## Purpose
- Describe this folder's responsibility.

## Change History
- 2026-02-28: Folder initialized as part of ideal project structure refactor.
- 2026-02-28 (before): LangChain v1 공식 미들웨어(before_model/after_model/wrap_model_call/wrap_tool_call) 기반 공통 파이프라인 구축 작업 시작.
- 2026-02-28 (after): `policies.py`(공통 정책), `agent_middlewares.py`(커스텀 미들웨어 4종), `registry.py`(단일 조립 지점)를 추가해 입력 구조분해 주입/모델 출력 가드/도구 오류 표준화/요청 경계 로깅을 중앙화.
- 2026-02-28 (before): tool-calling 시 `AIMessage.content`가 비어도 정상인데 fallback으로 오탐되는 문제를 해결하기 위해 `ModelOutputGuardMiddleware` 보정 작업 시작.
- 2026-02-28 (after): `agent_middlewares.py`에 `has_tool_call_signal` 공통 판별 함수를 추가하고, `ModelOutputGuardMiddleware.wrap_model_call`이 tool_calls 응답을 정상으로 통과시키도록 수정해 fallback 오탐을 제거.
- 2026-02-28 (before): 응답 품질 정책 중앙화를 위해 공통 후처리 모듈을 미들웨어 체인에 연결하는 작업 시작.
- 2026-02-28 (after): `agent_middlewares.py`에 `FinalAnswerPostProcessMiddleware`를 추가하고 `registry.py`에 연결해 최종 응답 후처리를 미들웨어 체인으로 일원화.

## Update Rule
- Before and after any code change in this folder, append a detailed log entry.
- 2026-03-02 (before): LangChain v1 미들웨어 권장 패턴 정렬을 위해 최종 응답 후처리 훅을 `@after_agent`에서 `@after_model`로 이관하는 리팩터링 작업 시작.
- 2026-03-02 (after): `agent_middlewares.py`에 `@after_model postprocess_model_answer`를 도입해 모델 응답 직후 후처리(계약 정규화)를 수행하도록 전환. tool call 응답은 후처리에서 제외(`has_tool_call_signal` 체크)해 기존 동작과 충돌을 방지.
- 2026-03-02 (after): `registry.py` 미들웨어 순서를 `... guard_model_output -> postprocess_model_answer -> guard_tool_error ...`로 조정해 후처리가 모델 단계에서 일관되게 실행되도록 정렬.
- 2026-03-01 (before): after_agent 후처리의 tool payload 추출 규칙을 에이전트와 동일하게 맞추기 위해 공통 selector 연동 작업 시작.
- 2026-03-01 (after): `FinalAnswerPostProcessMiddleware`의 tool payload 추출을 공통 selector(`extract_preferred_tool_payload_from_messages`)로 교체하고, 조회형 질의에서는 `mail_search` payload를 우선 선택하도록 보정.
- 2026-03-01 (before): 모델 요약 편차를 줄이기 위해 after_agent에서 최신 ToolMessage payload를 후처리로 전달하고, postprocessor에서 tool 근거 기반 contract 보강(제목/basic_info/summary_lines) 적용 작업 시작.
- 2026-03-01 (after): `FinalAnswerPostProcessMiddleware`가 최종 AI 응답 직전 ToolMessage JSON payload를 추출해 postprocessor로 전달하도록 확장(품질 보강 근거 전달).
- 2026-03-01 (after): `ModelOutputGuardMiddleware`에 prompt trace 로그를 추가해 모델 호출 직전 메시지(`prompt_trace.model_request`)와 모델 응답(`prompt_trace.model_response`)을 조건부 출력하도록 확장.
- 2026-03-01 (before): LangChain v1 공개 API 기준으로 미들웨어를 데코레이터(`@before_model/@wrap_model_call/@wrap_tool_call/@after_agent`) 중심으로 통일하고 SummarizationMiddleware를 체인에 추가하는 리팩터링 작업 시작.
- 2026-03-01 (after): `agent_middlewares.py`를 LangChain v1 공개 API(`langchain.agents.middleware`) + 데코레이터 훅(`@before_agent/@before_model/@wrap_model_call/@wrap_tool_call/@after_agent`) 구조로 리팩터링하고 기존 클래스형 미들웨어를 제거해 불필요 코드를 정리.
- 2026-03-01 (after): `registry.py`에 `SummarizationMiddleware`를 최신 인자(`trigger`, `keep`)로 추가하고, `OPENAI_API_KEY` 미설정 시 비활성화되는 안전 빌더를 도입해 초기화 사이드이펙트를 차단.

- 2026-03-02 (before): after_model 후처리에서 과거 턴 tool payload가 선택되어 조회 요약이 엉키는 문제를 해결하기 위해 tool payload 선택 범위/순서 보정 작업 시작.
- 2026-03-02 (after): `agent_middlewares._extract_latest_tool_payload`가 현재 턴(직전 HumanMessage 이후) ToolMessage만 우선 사용하도록 보정해 이전 턴 조회 payload 오염을 차단.
- 2026-03-02 (after): 현재 턴 ToolMessage가 없는 예외 케이스는 기존 동작과 호환되도록 전체 구간 최신 payload fallback을 유지.
- [09:56] 작업 시작: HIL 승인 정책을 edit 가능한 공통 계약으로 확장하는 미들웨어 설정 작업 시작.
- [10:20] 완료: `registry.py`의 `book_meeting_room`/`create_outlook_todo`/`create_outlook_calendar_event`에 `allowed_decisions=[approve, edit, reject]`를 적용해 수정 후 승인 경로를 허용.
