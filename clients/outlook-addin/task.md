# Outlook Add-in Task Log

## Purpose
- Outlook Add-in 클라이언트 정적 리소스(Manifest/Taskpane/JS/CSS)와 서버 연동 경로를 관리.

## Change History
- 2026-02-28 (before): Add-in 서버 등록을 위한 FastAPI bootstrap 연동 점검 시작.
- 2026-02-28 (after): FastAPI 서버에서 `/addin` 정적 경로를 마운트하고 Add-in API 계약과 호환되는 기본 엔드포인트를 연결.
- 2026-02-28 (before): `taskpane.js` 로직을 제거하고 UI 껍데기 전용 구조로 단순화 작업 시작.
- 2026-02-28 (after): `taskpane.js`를 최소 UI 이벤트 처리만 남기도록 교체하고, `taskpane.html` 스크립트 로딩을 `taskpane.js` 단일 로더로 정리.
- 2026-02-28 (before): UI 껍데기 모드 기준 불필요한 Taskpane 보조 JS 파일 정리 작업 시작.
- 2026-02-28 (after): `taskpane.js` 단일 스크립트만 유지하고 `taskpane.*-utils.js`, `taskpane.workflows.js`, `taskpane.logger.js` 등 미사용 JS 파일 일괄 삭제.
- 2026-02-28 (before): 채팅 입력을 `/search/chat` deep agent 응답으로 연결하도록 `taskpane.js` 전송 로직 복원 작업 시작.
- 2026-02-28 (after): `taskpane.js`를 `/search/chat` 비동기 호출 방식으로 변경하고 전송 중 버튼/입력 비활성화 및 오류 메시지 표시를 추가.

## Update Rule
- Before and after any code change in this folder, append a detailed log entry.
