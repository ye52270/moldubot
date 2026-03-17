# API Task Log

## Purpose
- Outlook Add-in에서 호출하는 API 엔드포인트와 응답 계약을 관리.

## Change History
- 2026-02-28: Folder initialized as part of ideal project structure refactor.
- 2026-02-28 (before): Outlook 선택 메일 컨텍스트 조회를 위해 `/mail/context` API 계약/엔드포인트 추가 작업 시작.
- 2026-02-28 (after): `MailContextRequest` 계약과 `/mail/context` 엔드포인트를 추가하고 `/search/chat`에서 `email_id` 기반 컨텍스트 로딩을 연동.
- 2026-02-28 (before): 선택 메일 디버깅을 위해 `/search/chat` 수신 시 `email_id`/`mailbox_user` 원본 로그를 추가하는 작업 시작.
- 2026-02-28 (after): `/search/chat` 수신 직후 `email_id`/`mailbox_user`를 터미널 로그로 출력하도록 추가해 선택 메일 전달값 변화를 즉시 확인 가능하게 개선.
- 2026-02-28 (before): Add-in 기본 동작 보장을 위한 API bootstrap 라우터 구현 작업 시작.
- 2026-02-28 (after): `app/api/routes.py` 생성, `/search/*`, `/intents/resolve`, `/api/meeting-rooms*`, `/api/promise/*`, `/api/finance/*`, `/addin/client-logs`, `/addin/export/weekly-report`, `/healthz` 엔드포인트 구현.
- 2026-02-28 (before): `/addin/client-logs` 204 응답에서 `Content-Length` 불일치 예외 수정 작업 시작.
- 2026-02-28 (after): `JSONResponse(status_code=204, content=None)`를 `Response(status_code=204)`로 변경해 `RuntimeError: Response content longer than Content-Length` 해결.
- 2026-02-28 (before): `/search/chat` 엔드포인트를 deep agent 기반 OpenAI 응답으로 전환하는 작업 시작.
- 2026-02-28 (after): `/search/chat`에서 OPENAI_API_KEY 확인 후 deep agent 응답을 반환하도록 변경하고 OpenAI 오류 처리 로깅 추가.
- 2026-02-28 (before): API 라우트 로깅을 공통 로거 모듈로 통합하고 채팅 경로 추적 로그를 보강하는 작업 시작.
- 2026-02-28 (after): `app.core.logging_config.get_logger`를 사용하도록 전환하고 `/search/chat` 요청/검증/완료 단계 추적 로그를 추가.
- 2026-02-28 (before): `/search/chat` 운영 메트릭 수집 및 조회 엔드포인트(`/search/chat/metrics`) 추가 작업 시작.
- 2026-02-28 (after): `/search/chat`에 처리시간/성공여부/fallback 여부 메트릭 기록을 추가하고 `/search/chat/metrics` 스냅샷 조회 엔드포인트를 구현.
- 2026-02-28 (before): `routes.py` 비대화 방지를 위해 요청/응답 모델과 데이터 접근 헬퍼를 분리해 라우터 파일 책임을 축소하는 리팩터링 시작.
- 2026-02-28 (after): `contracts.py`(요청/응답 모델)와 `data_access.py`(파일/경로/데이터 접근 헬퍼)를 분리하고 `routes.py`는 라우터 선언 중심으로 정리해 406줄→296줄로 축소.
- 2026-02-28 (detail): 리팩터링 단계
  1) `routes.py`에서 Pydantic 모델 6종(`ChatRequest` 등) 분리 대상을 식별
  2) `app/api/contracts.py` 신설 및 모델 이동
  3) `_read_json/_write_ndjson/_promise_*` 등 데이터 헬퍼를 `app/api/data_access.py`로 이동
  4) `routes.py`의 내부 헬퍼 삭제 후 모듈 import 교체
  5) `venv/bin/python -m compileall app/api` 및 라우터 로드 스모크(`route_count`, `/search/chat` 존재) 검증

## Update Rule
- Before and after any code change in this folder, append a detailed log entry.
- 2026-03-02 (before): 스트리밍 토큰으로 이미 노출된 내용과 completed 최종 답변 불일치(테이블 값 소실) 문제를 해결하기 위해 `/search/chat/stream` 최종 answer 결정 규칙 보정 작업 시작.
- 2026-03-02 (after): `/search/chat/stream`에서 토큰이 실제 전송된 경우(`emitted_token_count > 0`) completed `answer`를 `raw_answer`로 고정해 스트리밍 중 표시 내용과 최종 렌더가 일치하도록 수정.
- 2026-03-02 (after): 토큰 미전송(JSON prefix suppress) 케이스는 기존대로 `agent final answer` 우선 + 라우터 fallback 후처리를 유지해 JSON 노출 회귀를 방지.
- 2026-03-02 (before): 스트리밍 경로에서 라우터가 수행하던 후처리(`postprocess_final_answer`)를 `@after_model` 결과 우선 구조로 정리하고, 라우터는 fallback만 담당하도록 책임 경계 리팩터링 작업 시작.
- 2026-03-02 (after): `/search/chat/stream`에서 `read_agent_final_answer()`를 우선 사용하도록 변경해 최종 응답 정규화 책임을 미들웨어(`@after_model`)로 일원화.
- 2026-03-02 (after): 라우터의 `postprocess_final_answer` 호출은 agent 최종답변이 비어 있을 때만 fallback으로 유지해 중복 후처리 경로를 축소.
- 2026-03-01 (before): 품질 우선 원칙으로 `/search/chat`의 현재메일 direct-summary/post-action 조기 반환을 제거하고 모든 질의를 deep-agent(LLM) 단일 경로로 통합하는 리팩터링 작업 시작.
- 2026-03-01 (after): `/search/chat`에서 현재메일 조기 반환(`selected-mail-db-summary`, `selected-mail-post-action-*`)을 제거하고 선택메일 컨텍스트 성공/실패/누락과 무관하게 deep-agent 단일 경로로 응답 생성하도록 통합.
- 2026-02-28 (before): 선택 메일 컨텍스트 조회 실패 시 직전 `current_mail`이 재사용되는 문제를 막기 위해 `/search/chat` 실패 분기에서 캐시 초기화 로직 추가 작업 시작.
- 2026-02-28 (after): `/search/chat`에서 선택 메일 컨텍스트 조회 실패 시 `clear_current_mail()` 후 즉시 `selected-mail-context-failed` 응답을 반환하도록 변경해 직전 메일 요약 오염을 차단.
- 2026-02-28 (before): `email_id` 공백 상태에서 직전 current_mail이 재사용되는 문제를 막기 위해 `/search/chat` 현재메일 질의 누락 분기(캐시 초기화+실패 응답) 추가 작업 시작.
- 2026-02-28 (after): 현재메일 질의에서 `email_id`가 비면 `clear_current_mail()` 후 `selected-mail-context-missing` 응답으로 즉시 종료하도록 `/search/chat`에 누락 분기를 추가해 직전 메일 재사용을 차단.
- 2026-02-28 (after): `/search/chat`에 현재메일 질의 direct-summary 경로를 추가해 선택 메일 컨텍스트 성공 시 deep agent를 호출하지 않고 해당 메일 본문 기반 요약을 즉시 반환하도록 개선.
- 2026-02-28 (before): `/addin/client-logs` 수신 내용을 서버 콘솔에서도 즉시 확인할 수 있도록 수신 로그 가시화 보강 작업 시작.
- 2026-02-28 (after): `/addin/client-logs` 엔드포인트에 수신 이벤트(level/event/payload preview) 서버 콘솔 로그를 추가해 클라이언트 컨텍스트 이벤트를 실시간 확인 가능하게 개선.
- 2026-02-28 (before): `/search/chat` 수신 식별자 로깅 가시성(`email_id/message_id`)을 보강해 클라이언트 전송값과 서버 수신값 비교가 가능하도록 개선 작업 시작.
- 2026-02-28 (after): `/search/chat` 시작 로그에서 `email_id`와 동일 값을 `message_id` 별칭으로 함께 출력해 클라이언트(`email_id`)와 서버(`message_id`) 용어 차이로 인한 디버깅 혼선을 줄임.
- 2026-02-28 (before): Add-in 디버그 과정에서 과도하게 증가한 `/addin/client-logs` 콘솔 노이즈를 줄이기 위해 고빈도 이벤트 로그 필터링 정리 작업 시작.
- 2026-02-28 (after): `/addin/client-logs`에서 고빈도 info 이벤트를 필터링(`NOISY_CLIENT_EVENTS`)해 서버 콘솔 스팸을 줄이고 핵심 이벤트 중심으로 관측 가능하도록 정리.
- 2026-03-01 (before): 현재메일 기본 요약 요청에서 DB `summary` 필드를 우선 반환하고, 명시 지시(예: `N줄`)가 있으면 LLM 경로로 우회하도록 `/search/chat` 분기 개선 작업 시작.
- 2026-03-01 (after): `/search/chat`에 기본 현재메일 요약 판별(`현재메일 요약[해줘]`) 함수를 추가하고, 해당 요청에서는 DB `summary` 우선(`selected-mail-db-summary`) 반환, 그 외 명시 지시 요청은 deep-agent 경로를 유지하도록 분기 개선.
- 2026-03-01 (before): 현재메일 질의를 복잡한 다중 경로 대신 공통 파이프라인(`mail_context -> run_post_action -> 공통 렌더`)으로 통합하고 `routes.py` 500줄 초과를 해소하는 리팩터링 작업 시작.
- 2026-03-01 (after): `current_mail_pipeline.py`를 분리해 현재메일 질의 판별/액션 매핑/응답 렌더링을 모듈화하고, `/search/chat`은 `is_current_mail_query` 시 `mail_context_service.run_post_action` 단일 경로를 사용하도록 통합. 기본 요약은 DB summary 우선 유지, 상세/보고서/핵심/수신자 질의도 동일 파이프라인으로 처리.
- 2026-03-01 (before): current mail 파이프라인 정리를 위해 미사용 helper/action 렌더 함수 제거 및 query 판별 유틸 최소화 작업 시작.
- 2026-03-01 (after): `current_mail_pipeline.py`를 `is_current_mail_query` 단일 책임 유틸로 축소하고 미사용 action 매핑/응답 렌더 함수 제거.
- 2026-03-01 (before): `/search/chat` 결과에 근거메일 클릭 메타데이터를 내려주기 위해 selected mail/`mail_search` tool payload 기반 evidence 목록 생성 작업 시작.
- 2026-03-01 (after): `routes.py`에 `metadata.evidence_mails`(제목/수신일/발신자/링크)를 추가하고, `mail_search` tool payload의 top3 결과를 우선 근거로 노출하도록 확장.
- 2026-03-01 (before): 메일 조회 질의에서 조회 목록과 통합 요약을 함께 UI에 전달하기 위해 `/search/chat` metadata 확장 작업 시작.
- 2026-03-01 (after): `mail_search` tool payload에서 `aggregated_summary`를 추출해 `/search/chat` metadata에 포함하도록 연동.
- 2026-03-01 (after): `routes.py` 500줄 규칙 준수를 위해 search-chat 메타 헬퍼를 `search_chat_metadata.py`로 분리(`routes.py` 416줄).
- 2026-03-01 (before): `/search/chat` 요청 종료 시 current mail 컨텍스트 정리(clear)로 전역 상태 누수 방지 작업 시작.
- 2026-03-01 (after): `/search/chat`에서 선택메일 컨텍스트를 사용한 요청은 응답 직전에 `clear_current_mail()`를 수행하도록 정리해 다음 요청으로 current mail이 누수되지 않도록 보강.
- 2026-03-01 (before): Add-in 진행상태 UI 연동을 위해 `/search/chat` 응답을 SSE로 전달하는 `/search/chat/stream` 엔드포인트 추가 작업 시작.
- 2026-03-01 (after): `routes.py`에 `_encode_stream_event` 유틸과 `/search/chat/stream`을 추가해 `progress(received/processing)` + `completed` JSON 이벤트를 `text/event-stream`으로 제공하도록 확장.
- 2026-03-01 (before): 조회 결과 0건인데 selected-mail 근거메일이 남는 회귀를 차단하기 위해 `/search/chat`의 tool evidence 덮어쓰기 조건(`if tool_evidence`) 개선 작업 시작.
- 2026-03-01 (after): `search_chat_metadata.extract_tool_action`를 추가하고 `/search/chat`에서 `action=mail_search`면 결과가 비어도 `metadata.evidence_mails`를 빈 목록으로 강제 덮어쓰도록 수정해 selected-mail 근거 누수를 제거.
- 2026-03-01 (before): v1 메모리 적용을 위해 `/search/chat`에서 thread_id 생성 정책을 정리하고 deep-agent 호출에 thread_id를 전달하도록 API 경로를 리팩터링하는 작업 시작.
- 2026-03-01 (after): `/search/chat`에서 `_resolve_thread_id`로 thread_id를 단일 생성하고 deep-agent 호출(`respond(user_message, thread_id)`) 및 응답 `thread_id`에 동일값을 사용하도록 정리해 메모리 스레드 일관성을 확보.
- 2026-03-01 (after): 사용자 요청으로 `현재메일` 컨텍스트 실패 즉시 반환 가드 변경을 원복하고 기존 deep-agent 단일 경로 동작을 유지.
- 2026-03-01 (before): 브라우저에서 회귀 평가를 실행할 수 있도록 E2E+Judge 실행 API와 결과 조회 API, 간단한 평가 페이지 라우트를 추가하는 작업 시작.

- 2026-03-01 (after): `/qa/chat-eval/run`, `/qa/chat-eval/latest`, `/qa/chat-eval/cases`를 추가해 브라우저 버튼 기반 실호출 평가 실행/최근 결과 조회/케이스 목록 조회를 제공.

- 2026-03-01 (before): 채팅 평가 Judge 기본 모델을 `gpt-5-mini`로 변경하는 API 계약 기본값 조정 작업 시작.

- 2026-03-01 (after): `ChatEvalRunRequest.judge_model` 기본값을 `gpt-5-mini`로 변경해 웹 입력 미지정 시에도 고정 기본 모델이 일관되게 적용되도록 조정.

- 2026-03-01 (before): Judge 컨텍스트 전달 정확도를 높이기 위해 `/search/chat` metadata에 `search_result_count`를 포함하는 보강 작업 시작.

- 2026-03-01 (after): `/search/chat` metadata에 `search_result_count`를 추가해 평가기(LLM Judge)가 조회 0건/다건 문맥을 판단할 수 있도록 응답 계약을 보강.

- 2026-03-01 (after): `/search/chat` metadata `search_result_count`를 활용하는 회귀 테스트를 보강해 mail_search 결과 1건/0건 시 count 전달 계약을 검증.

- 2026-03-01 (before): chat-eval 선택 케이스 재실행 UX를 위해 API 계약에 `case_ids` 필드를 추가하는 작업 시작.
- 2026-03-01 (after): `/search/chat`에 thread follow-up 상태를 기반으로 scope disambiguation을 추가해 모호 질의 시 `needs_clarification` + `metadata.clarification(options)`를 반환하도록 확장.
- 2026-03-01 (after): 사용자가 선택한 `runtime_options.scope`를 반영해 모델 입력에 범위 지시문(`현재메일/직전조회결과/전체검색`)을 주입하고 응답 metadata에 `resolved_scope`를 추가.
- 2026-03-01 (after): `routes.py` 500줄 규칙 준수를 위해 비핵심 엔드포인트(`/qa/chat-eval*`, `/addin/*`, `/api/meeting-rooms*`, `/api/promise/*`, `/api/finance/*`, `/search/chat/metrics`, `/search/chat/confirm`, `/intents/resolve`, `/search/id`)를 `bootstrap_routes.py`로 분리.

- 2026-03-01 (after): `ChatEvalRunRequest`에 `case_ids` 필드를 추가해 선택된 케이스 ID만 재실행할 수 있도록 API 계약을 확장.
- 2026-03-01 (before): 모호 질의 범위 혼선 방지를 위해 `/search/chat`에 scope disambiguation(현재메일/직전조회/전체검색) 응답 계약과 thread follow-up 상태 관리 로직을 추가하는 작업 시작.
- 2026-03-01 (before): 출력 체감 품질 개선을 위해 `/search/chat/stream`에 token 단위 SSE 이벤트를 추가하고 프론트 타이핑 렌더를 지원하는 작업 시작.
- 2026-03-01 (after): `/search/chat/stream`에서 `completed` 직전 `token` SSE 이벤트를 순차 전송하도록 확장하고, `_iter_answer_chunks`를 추가해 프론트가 타이핑 형태로 점진 렌더할 수 있게 변경.
- 2026-03-01 (after): `search_chat_stream`을 `search_chat` 결과 후처리 방식에서 분리해 deep-agent `stream_respond` 토큰을 실시간 중계하도록 전환하고, 완료 시점 metadata(evidence/search_result_count/resolved_scope) 조립과 메트릭 기록을 동일 계약으로 유지.
- 2026-03-01 (after): 실시간 스트림 중 모델 JSON(raw contract) 노출 이슈를 보정하기 위해 `search_chat_stream`에 `postprocess_final_answer`를 적용하고, JSON prefix 감지 시 token 이벤트 표시를 중단해 최종 렌더만 노출되도록 개선.
- 2026-03-02 (before): 포맷 확장성을 위해 `answer_format(v1)` 블록 추출기에서 markdown table/blockquote를 `table/quote` 타입으로 분해하는 보강 작업 시작.
- 2026-03-02 (after): `answer_format_metadata.py`에 table 헤더/행 수집(`headers`, `rows`)과 quote 수집 로직을 추가해 API metadata의 `answer_format.blocks`가 `table/quote`를 포함하도록 확장.
- 2026-03-02 (before): 줄바꿈이 일부 깨진 응답에서 `---`가 divider로 인식되지 않고 텍스트로 노출되는 문제를 완화하기 위한 정규화 보강 작업 시작.
- 2026-03-02 (after): `answer_format_metadata._normalize_text`에 구조 개행 보강(`---`/heading/table delimiter 주변) 로직을 추가해 블록 파싱 안정성을 개선.
- 2026-03-02 (before): 스트리밍/최종 렌더 경로를 단일화하기 위해 `/search/chat/stream`의 token/progress 이벤트 제거 및 completed 1회 전송 구조 리팩터링 작업 시작.
- 2026-03-02 (after): `/search/chat/stream`에서 실시간 token 중계(`event: token`)와 progress 송신을 제거하고, deep-agent `respond()` 기반으로 최종 `event: completed` 1회만 전송하도록 단순화.
- 2026-03-02 (after): 라우트 내 JSON prefix 감지/재청크 전송 유틸(`_looks_like_structured_json_prefix`, `_chunk_text_for_streaming`)을 제거해 불필요한 스트리밍 분기 코드를 정리.
- 2026-03-02 (before): `answer_format` 표 파서가 delimiter 라인을 헤더로 오인해 기본 정보 값이 소실되는 문제를 보정하는 작업 시작.
- 2026-03-02 (after): `answer_format_metadata` 표 파서를 보강해 delimiter 라인(`|---|---|`)을 헤더/데이터로 오인하지 않도록 수정하고, malformed table 블록 생성을 차단.
- 2026-03-02 (after): 구조 개행 보강 정규식(`---`, heading)에서 table delimiter를 훼손하던 패턴을 제거/교정해 기본 정보 key/value row 파싱이 유지되도록 수정.
- 2026-03-02 (before): 대화별 처리시간 UI 표시를 위해 `/search/chat` 및 `/search/chat/stream` metadata에 `elapsed_ms`를 포함하는 응답 계약 확장 작업 시작.
- 2026-03-02 (after): `/search/chat` 및 `/search/chat/stream` completed metadata에 `elapsed_ms`(ms, 소수 1자리)를 포함하도록 확장해 프론트 대화별 처리시간 표시 근거를 제공.
- 2026-03-02 (before): 보고서 고도화를 위해 report 전용 SSE 라우터(`/report/generate`)와 DOCX 다운로드 라우터(`/report/download/{filename}`)를 신규 분리 구현하는 작업 시작.
- 2026-03-02 (after): `report_routes.py`를 추가해 step/html_chunk/done/error SSE 이벤트 스트리밍과 DOCX 파일 다운로드 엔드포인트를 구현하고 `main.py`에 라우터를 등록.
- 2026-03-02 (before): chat-eval 현재메일 케이스의 파라미터 누락 오판을 줄이기 위해 `/qa/chat-eval/run` 입력 가드(`selected_email_id`와 `mailbox_user` 동시 제공)를 추가하는 작업 시작.
- 2026-03-02 (after): `/qa/chat-eval/run`에 `selected_email_id` 제공 시 `mailbox_user` 누락이면 400을 반환하는 검증을 추가.
- 2026-03-02 (before): 보고서 미리보기 공백 이슈 완화를 위해 report stream의 HTML 추출 파서를 code fence(JSON/HTML) 입력까지 허용하도록 보강 작업 시작.
- 2026-03-02 (after): `report_routes._extract_html_from_text`에 코드펜스 제거 정규화를 추가해 ````json ... ``` 형식 응답에서도 `report_html` 추출이 가능하도록 개선.
- 2026-03-02 (before): report SSE에서 html_chunk 누락 시 미리보기 공백이 발생하는 문제를 근본 해소하기 위해 html_chunk 보장 전송 및 네임스페이스 파서 확장 작업 시작.
- 2026-03-02 (after): report-writer 외 report-orchestrator 네임스페이스도 HTML 추출 대상으로 확장하고, html_chunk 0건일 때 완료 직전 html_chunk 1회를 강제 전송하도록 수정.
- 2026-03-02 (before): 보고서 생성 시 report_html 비어 fallback 문구가 출력되는 문제 원인 분석/수정 작업 시작.
- 2026-03-02 (after): report stream HTML 파서를 chunk 재귀 탐색(report_html/html/content)으로 확장해 messages 필드 외 구조에서도 HTML 추출 가능하도록 수정하고 단위 테스트(6건) 통과 확인.
- 2026-03-02 (before): 보고서 생성 시 외부문서 검색을 옵션화(.env 기본값 + 사용자 체크값)하는 작업 시작.
- 2026-03-02 (after): ReportGenerateRequest에 enable_web_research 필드를 추가하고, report agent를 include_web_research 옵션(환경변수 REPORT_WEB_RESEARCH_DEFAULT fallback)으로 분기 생성하도록 수정.
- 2026-03-02 (before): 주간보고 미리보기에서 불릿 하위설명(`-`)이 누락되는 케이스를 줄이기 위해 weekly fallback 템플릿 보강 작업 시작.
- 2026-03-02 (after): `report_routes._build_template_weekly_report_html`의 각 `<li>`를 `핵심 항목<br>- 설명` 형식으로 변경해 fallback 경로에서도 하위 설명이 표시되도록 수정.
- 2026-03-02 (after): report_generate에서 외부검색 비활성 시 Step 2를 \"외부 문서 검색 생략\" done 이벤트로 전송하도록 반영.
- 2026-03-02 (after): report_generate에 성능/병목 분석용 로깅(report.generate.started/step/html_chunk/fallback_invoke/completed)을 추가하고, stream에서 HTML 미수집 시 ainvoke 결과에서 report_html을 재수집하는 근본 보정 적용.
- 2026-03-02 (after): report HTML 추출 시 user/human 메시지 content를 배제하고 assistant/ai 메시지 우선으로 추출하도록 보정, HTML 판별 정규식을 추가해 메일 원문 angle bracket 오탐을 차단.
- 2026-03-02 (before): report_generate SSE 경로 리팩터링(stream_mode 다중 모드, namespace/message 파싱 강화, html_chunk 안정화) 작업 시작.
- 2026-03-02 (after): report_generate를 stream_mode=["updates","messages"]로 전환하고 top-level messages 파싱/namespace 유틸을 추가해 html_chunk 수집 안정성을 높임.
- 2026-03-02 (after): stream/invoke 모두 HTML 미수집 시 실패문구 대신 템플릿 HTML 보고서를 생성하도록 변경하고 스트림 청크 구조 로그(report.generate.stream_chunk)를 추가.
- 2026-03-02 (before): chat-eval run 엔드포인트 500(xhr_non_json_response) 원인 분석/수정 작업 시작.
- 2026-03-02 (after): /qa/chat-eval/run에서 run_chat_eval_session 예외를 logger.exception으로 기록 후 HTTP 502 JSON(detail)로 변환해 xhr_non_json_response를 방지하도록 수정.

- 2026-03-02 (before): `/report/generate`에서 `report_agent.astream` 런타임 반환 형식(3-tuple 등)으로 인한 `too many values to unpack` 오류 수정 작업 시작.
- 2026-03-02 (after): `report_routes.py`에 `_coerce_stream_item` 정규화 유틸을 추가해 `(namespace, chunk)`, `(namespace, chunk, metadata)`, `chunk 단독` 형식을 모두 안전 처리하도록 변경.
- 2026-03-02 (after): `tests/test_report_routes.py`에 3-tuple 스트림 케이스를 추가하고 `PYTHONPATH=. ./venv/bin/python -m unittest tests.test_report_routes`(10 tests) 통과 확인.

- 2026-03-02 (before): report SSE 미리보기 청크 부족으로 UI가 완료 전 공백처럼 보이는 문제를 완화하기 위한 chunk 보장 전송 개선 작업 시작.
- 2026-03-02 (after): `report_routes.py`에 report-writer preview text chunk 추출과 완료 직전 HTML 분할 전송(`PREVIEW_FALLBACK_CHUNK_SIZE`)을 추가해 `html_chunk` 이벤트 다중 수신을 보장.
- 2026-03-02 (after): `tests/test_report_routes.py`에 preview-only stream + fallback HTML 케이스를 추가해 다중 html_chunk 계약을 검증.
- 2026-03-02 (before): report SSE에서 html_chunk 이벤트/미리보기 관련 로직 제거 및 step/done 전용 계약으로 단순화 작업 시작.
- 2026-03-02 (after): `/report/generate`가 step/done/error만 송신하도록 정리, fast/deep 경로 모두 완료 시 `done{docx_url}`만 반환하도록 통일.
- 2026-03-02 (before): 보고서 품질 개선(제목/수신일/발신자 고정, 상세 본문 강화)을 위해 /report/generate 요청 메타데이터 확장 작업 시작.
- 2026-03-02 (after): ReportGenerateRequest에 email_received_date/email_sender를 추가하고 report.generate 경로에서 fast/deep 입력 모두에 메타데이터를 주입하도록 반영.
- 2026-03-02 (after): report.generate 시작 로그에 subject/received_date/sender를 포함해 품질 이슈 추적성을 강화.

- [10:31] 작업 시작: /report/preview 엔드포인트 추가 및 다운로드 UX 분리 착수
- [10:36] 완료: /report/preview/{filename} 엔드포인트 추가(Office Viewer iframe + 상단 다운로드 버튼) 및 테스트 2건 추가
- [10:53] 작업 시작: preview 라우트 HTML 직접 렌더링 및 품질 고정 로직 개선 착수
- [10:55] 이슈: 외부검색 품질 미흡으로 보고서 경로에서 web research 완전 제거로 전환

- [11:03] 작업 시작: report API/프롬프트/미리보기 외부검색 제거 리팩터링
- [11:08] 완료: /report/generate 단일 fast-path(SSE step+done)로 정리, /report/preview srcdoc 렌더링으로 교체
- [11:30] 작업 시작: `/report/weekly/generate` SSE 엔드포인트 및 주간보고 생성 계약 추가 착수
- [11:43] 완료: `/report/weekly/generate` SSE 엔드포인트 구현 완료(주간 메일 조회→요약→주간보고 작성→DOCX), 미리보기/다운로드 URL 포함 done 이벤트 반환.
- [12:29] 작업 시작: 회의실 depth 선택 예약 요구사항 반영을 위해 `/api/meeting-rooms*` 라우트(조회/예약) 확장 작업 착수.
- [12:35] 완료: `/api/meeting-rooms`를 depth 조회(건물→층→회의실)로 유지하면서 데이터 소스를 `data/meeting/meeting_rooms.json`으로 통합하고, `/api/meeting-rooms/book`를 Graph 캘린더 이벤트 생성(`[회의실] {room_name}`, Asia/Seoul) 경로로 전환.
- 2026-03-04 (before): `/search/chat` metadata `next_actions`를 도메인 게이트 기반 추천 결과로 교체하는 API 연동 작업 시작.
- 2026-03-04 (after): `/search/chat`에서 사용하는 `next_actions` 생성기가 도메인 게이트 기반 추천 결과를 반환하도록 연동 유지 및 메타데이터 계약 호환 확인.
- 2026-03-05 (before): `major_point_evidence`를 웹출처 기반에서 벡터 유사 메일 근거(`related_mails`) 기반으로 전환하는 API 메타데이터 리팩터링 작업 시작.
- 2026-03-05 (after): `build_major_point_evidence` 계약을 `related_mails` 중심으로 개편하고, `search_chat_flow`에서 포인트별 유사 메일 검색 보강(`_enrich_major_point_related_mails`)을 추가.
- 2026-03-05 (after): 주요내용 근거 메타데이터에서 웹출처 주입 경로를 제거해 사내 메일 근거 중심으로 단순화.
- [09:56] 작업 시작: HIL confirm을 edit 가능한 공통 승인 계약으로 확장하는 API 작업 시작.
- [10:20] 완료: `ConfirmRequest`에 `decision_type`/`edited_action`을 추가하고 `bootstrap_routes.py` confirm 경로가 `approve|edit|reject`를 정규화해 agent resume 및 응답 메타데이터에 반영하도록 수정.
- [2026-03-17 15:32] 작업 시작: pull 기반 최근 메일 sync를 외부에서 호출할 수 있도록 `bootstrap_ops_routes.py`에 관리용 엔드포인트 추가 착수.
- [2026-03-17 15:36] 완료: `/ops/mail-sync/recent` POST 엔드포인트를 추가해 dry-run과 실제 `MailSyncService` 실행 결과를 JSON으로 반환하도록 구성.
