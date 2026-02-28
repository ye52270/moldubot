# API Task Log

## Purpose
- Outlook Add-in에서 호출하는 API 엔드포인트와 응답 계약을 관리.

## Change History
- 2026-02-28: Folder initialized as part of ideal project structure refactor.
- 2026-02-28 (before): Add-in 기본 동작 보장을 위한 API bootstrap 라우터 구현 작업 시작.
- 2026-02-28 (after): `app/api/routes.py` 생성, `/search/*`, `/intents/resolve`, `/api/meeting-rooms*`, `/api/promise/*`, `/api/finance/*`, `/addin/client-logs`, `/addin/export/weekly-report`, `/healthz` 엔드포인트 구현.
- 2026-02-28 (before): `/addin/client-logs` 204 응답에서 `Content-Length` 불일치 예외 수정 작업 시작.
- 2026-02-28 (after): `JSONResponse(status_code=204, content=None)`를 `Response(status_code=204)`로 변경해 `RuntimeError: Response content longer than Content-Length` 해결.
- 2026-02-28 (before): `/search/chat` 엔드포인트를 deep agent 기반 OpenAI 응답으로 전환하는 작업 시작.
- 2026-02-28 (after): `/search/chat`에서 OPENAI_API_KEY 확인 후 deep agent 응답을 반환하도록 변경하고 OpenAI 오류 처리 로깅 추가.
- 2026-02-28 (before): API 라우트 로깅을 공통 로거 모듈로 통합하고 채팅 경로 추적 로그를 보강하는 작업 시작.
- 2026-02-28 (after): `app.core.logging_config.get_logger`를 사용하도록 전환하고 `/search/chat` 요청/검증/완료 단계 추적 로그를 추가.

## Update Rule
- Before and after any code change in this folder, append a detailed log entry.
