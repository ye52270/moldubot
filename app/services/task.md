# Services Task Log

## Purpose
- Describe this folder's responsibility.

## Change History
- 2026-02-28: Folder initialized as part of ideal project structure refactor.
- 2026-02-28 (before): 로컬 SQLite 메일 조회/요약/핵심추출/수신자추출 및 회의실 조회/예약의 실제 처리 서비스를 추가하는 작업 시작.
- 2026-02-28 (after): `mail_service.py`, `meeting_service.py`, `task_execution_service.py`를 추가해 실제 메일 조회/요약/핵심추출/수신자 추출/예약(충돌 검사 포함) 처리 경로를 구현하고 `내일` 예약 날짜 추론 보정을 반영.
- 2026-02-28 (before): 3단계 표준화를 위해 메일 조회 후속작업(요약/보고서)을 단일 서비스 경로로 제공하는 API를 `mail_service.py`에 추가하는 작업 시작.
- 2026-02-28 (after): `mail_service.py`에 `run_post_action(action, summary_line_target)`와 보고서 마크다운 합성 경로를 추가해 메일 조회 후속작업(요약/보고서)이 동일 서비스 경로를 재사용하도록 표준화.

## Update Rule
- Before and after any code change in this folder, append a detailed log entry.
