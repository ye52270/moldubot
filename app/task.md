# App Task Log

## Purpose
- FastAPI 기반 MolduBot 백엔드 애플리케이션 엔트리포인트와 공통 런타임 구성을 관리.

## Change History
- 2026-02-28: Folder initialized as part of ideal project structure refactor.
- 2026-02-28 (before): Outlook Add-in 등록/실행을 위한 FastAPI bootstrap 서버 추가 작업 시작.
- 2026-02-28 (after): `app/main.py` 생성, CORS 설정, 정적 경로(`/addin`, `/myhr`, `/myPromise`, `/promise`, `/finance`) 마운트 및 루트 리다이렉트 구현.
- 2026-02-28 (before): `.env`의 OPENAI_API_KEY를 런타임에서 인식하도록 엔트리포인트 dotenv 로드 추가 작업 시작.
- 2026-02-28 (after): `app/main.py`에서 `load_dotenv`를 적용해 `.env`의 OPENAI_API_KEY를 앱 시작 시 로드하도록 수정.
- 2026-02-28 (before): 공통 logging 모듈을 `app.main` 엔트리포인트에 연결하는 작업 시작.
- 2026-02-28 (after): `app.main`에서 `configure_logging` 초기화를 적용하고 부팅/루트 접근 로그를 공통 포맷으로 출력하도록 변경.

## Update Rule
- Before and after any code change in this folder, append a detailed log entry.
