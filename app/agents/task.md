# Agents Task Log

## Purpose
- Describe this folder's responsibility.

## Change History
- 2026-02-28: Folder initialized as part of ideal project structure refactor.
- 2026-02-28 (before): LangChain v1.0 `create_deep_agent` 단일 에이전트 생성/호출 모듈 추가 작업 시작.
- 2026-02-28 (after): `deep_chat_agent.py` 추가, `create_deep_agent` 단일 인스턴스 캐시 생성/호출 및 응답 텍스트 추출 로직 구현.
- 2026-02-28 (before): Ollama Exaone 기반 의도 구조분해 스키마/파서를 추가하고 deep agent 입력 결합 작업 시작.
- 2026-02-28 (after): `intent_schema.py`, `intent_parser.py` 추가 및 `deep_chat_agent.py`에 구조분해 컨텍스트 주입 로직 통합, 실패 시 규칙 기반 fallback 적용.
- 2026-02-28 (before): agents 모듈 로깅을 공통 logger 헬퍼 기반으로 통합하고 실행 추적 로그를 추가하는 작업 시작.
- 2026-02-28 (after): agents 로거를 `app.core.logging_config.get_logger`로 통합하고 의도 구조분해/응답 생성 단계 로그를 추가.
- 2026-02-28 (before): 의도 구조분해 결과 전체(JSON)를 로그에서 직접 확인할 수 있도록 에이전트 로깅 보강 작업 시작.
- 2026-02-28 (after): `deep_chat_agent.py`에서 `IntentDecomposition` 전체를 JSON 로그로 출력하도록 변경해 분해 결과를 즉시 검증 가능하게 개선.
- 2026-02-28 (before): Exaone 구조분해 프롬프트를 필드/출력 규칙까지 상세화하는 작업 시작.
- 2026-02-28 (after): `intent_parser._build_prompt`를 강제형 스키마/추출 규칙 프롬프트로 교체해 필드 누락 및 불필요 step 포함을 줄이도록 개선.
- 2026-02-28 (before): 추측/예시 생성으로 인한 환각 값을 차단하기 위해 구조분해 프롬프트를 재보정하는 작업 시작.
- 2026-02-28 (after): 입력 외 정보 생성 금지, 예시/가정 문구 금지, unknown 값은 `missing_slots`로 이동 규칙을 프롬프트에 추가해 환각 방지 강화.
- 2026-02-28 (before): 구조분해 결과에 근거 기반 Rule 가드를 적용해 환각 필드(`key_points`, `recipients`, 예약 슬롯)를 정제하는 작업 시작.
- 2026-02-28 (after): `intent_parser`에 evidence guardrail을 추가해 근거 없는 값 제거/필수 슬롯 누락 보강(`missing_slots`)을 강제하고 테스트 로그로 검증 완료.
- 2026-02-28 (before): `user_goal` 재서술 편차를 제거하기 위해 원문 고정 규칙을 가드 로직에 추가하는 작업 시작.
- 2026-02-28 (after): evidence guardrail에서 `user_goal`을 항상 원문 입력으로 고정하도록 변경해 재서술 편차를 제거.
- 2026-02-28 (before): 의도 구조분해 추출기를 OpenAI 경량 모델로 선택 가능하게 provider 스위치 구현 작업 시작.
- 2026-02-28 (after): `intent_parser`에 `MOLDUBOT_INTENT_PROVIDER` 스위치(`ollama|openai`)와 `OpenAIIntentParser(gpt-4o-mini)` 경로를 추가하고 structured output 동작을 검증.
- 2026-02-28 (before): Exaone 단일 경로 운영을 위해 구조분해 스키마를 최소화하고 parser 분기 코드를 정리하는 작업 시작.
- 2026-02-28 (after): Exaone 단일 경로로 회귀해 OpenAI 분기 코드를 제거하고 최소 스키마(`original_query/steps/summary_line_target/date_filter/missing_slots`) 기반 parser로 정리.
- 2026-02-28 (before): parser 내부 규칙 로직을 `app/core/intent_rules.py` 공통 모듈로 분리하는 리팩터링 시작.
- 2026-02-28 (after): `intent_parser.py` 중복 규칙 함수를 제거하고 `app.core.intent_rules` 공통 함수(import)로 연결, 질의 정제/step/date/missing_slots 계산을 단일 규칙 소스로 통합.
- 2026-02-28 (before): `회의 일정` 질의를 명시적으로 다루기 위해 최소 step 스키마/파서 허용값을 확장하는 작업 시작.
- 2026-02-28 (after): `ExecutionStep.SEARCH_MEETING_SCHEDULE`를 추가하고 parser step 매핑/허용값 프롬프트를 동기화해 회의 일정 질의가 메일 조회로 오분류되지 않도록 수정.
- 2026-02-28 (before): deep agent 생성 지점에서 공통 미들웨어 레지스트리를 주입하도록 에이전트 초기화 구조를 전환하는 작업 시작.
- 2026-02-28 (after): `deep_chat_agent.py`에서 입력 전처리 직접 결합 로직을 제거하고 `app.middleware.registry.build_agent_middlewares()`를 `create_deep_agent(..., middleware=...)`로 주입해 전/후 처리를 미들웨어 체인으로 일원화.

## Update Rule
- Before and after any code change in this folder, append a detailed log entry.
