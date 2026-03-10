# Microsoft Graph Integration Task Log

## Purpose
- Describe this folder's responsibility.

## Change History
- 2026-02-28: Folder initialized as part of ideal project structure refactor.
- 2026-02-28 (before): `message_id` 단건 조회를 위한 Microsoft Graph 메일 클라이언트(토큰 획득 + 메시지 조회) 구현 작업 시작.
- 2026-02-28 (after): `mail_client.py`를 추가해 앱 자격증명 토큰 발급(`.default`)과 `/users/{mailbox_user}/messages/{message_id}` 단건 조회/본문 정규화를 구현.

## Update Rule
- Before and after any code change in this folder, append a detailed log entry.
- 2026-02-28 (before): `AADSTS53003` 등 Graph 실패 원인 식별을 위해 토큰/메시지 조회 실패 로그를 구조화(에러코드/trace/correlation/request-id)하는 작업 시작.
- 2026-02-28 (after): `mail_client.py`에 AADSTS 오류 파싱(Trace/Correlation/Timestamp)과 Graph 실패 응답 메타(request-id/client-request-id, error code/message) 구조화 로그를 추가해 정책 차단/권한 오류를 로그만으로 식별 가능하게 개선.
- 2026-03-01 (before): Graph API 401 발생 시 자연회복 의존을 제거하기 위해 토큰 재획득+1회 재시도 로직 및 단위테스트(TDD) 적용 작업 시작.
- 2026-03-01 (after): `GraphMailClient`에 401 감지 시 `force_refresh` 토큰 재획득 후 1회 재요청을 추가하고, MSAL client 재사용 구조(`_get_msal_app`)를 도입. `tests/test_graph_mail_client.py`에 401→성공/401→실패 회귀 테스트를 추가해 검증 완료.
- 2026-03-01 (before): 개인 outlook.com 계정 호환을 위해 앱 권한(client credential) 기반 구현을 Delegated(PublicClientApplication + /me/messages) 방식으로 전환하는 작업 시작.
- 2026-03-01 (after): `mail_client.py`를 PublicClientApplication + Delegated(`/me/messages`) 기반으로 전환(토큰 캐시 파일 로드/저장, silent→interactive 획득, 401 1회 재시도). 개인 outlook.com 계정 시나리오를 기본 경로로 반영하고 테스트를 동기화.
- 2026-03-02 (before): 회의실 예약 시 개인 Outlook 캘린더에 일정을 생성하기 위해 Graph `/me/events` 전용 클라이언트 추가 작업 시작.
- 2026-03-02 (after): `calendar_client.py`를 추가해 Delegated 토큰 기반 `/me/events` 생성(Asia/Seoul, 401 재시도)을 구현하고, `GraphMailClient`에 토큰 획득/초기화 공개 메서드(`acquire_access_token`, `reset_access_token`)를 추가해 인증 경로를 재사용.
