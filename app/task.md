# App Task Log

## Purpose
- FastAPI 기반 MolduBot 백엔드 애플리케이션 엔트리포인트와 공통 런타임 구성을 관리.

## Change History
- 2026-02-28: Folder initialized as part of ideal project structure refactor.
- 2026-02-28 (before): Graph 설정 누락 원인 제거를 위해 `main.py`의 `.env` 로드 시점을 라우터 import 이전으로 보정하는 작업 시작.
- 2026-02-28 (after): `app.main`에서 `.env`/logging 초기화 후 `app.api.routes`를 import하도록 순서를 변경해 Graph 클라이언트 초기화 시 환경변수가 누락되지 않도록 수정.
- 2026-02-28 (before): Outlook Add-in 등록/실행을 위한 FastAPI bootstrap 서버 추가 작업 시작.
- 2026-02-28 (after): `app/main.py` 생성, CORS 설정, 정적 경로(`/addin`, `/myhr`, `/myPromise`, `/promise`, `/finance`) 마운트 및 루트 리다이렉트 구현.
- 2026-02-28 (before): `.env`의 OPENAI_API_KEY를 런타임에서 인식하도록 엔트리포인트 dotenv 로드 추가 작업 시작.
- 2026-02-28 (after): `app/main.py`에서 `load_dotenv`를 적용해 `.env`의 OPENAI_API_KEY를 앱 시작 시 로드하도록 수정.
- 2026-02-28 (before): 공통 logging 모듈을 `app.main` 엔트리포인트에 연결하는 작업 시작.
- 2026-02-28 (after): `app.main`에서 `configure_logging` 초기화를 적용하고 부팅/루트 접근 로그를 공통 포맷으로 출력하도록 변경.

## Update Rule
- Before and after any code change in this folder, append a detailed log entry.
- 2026-03-01 (before): API 라우터 분리 리팩터링에 따라 `main.py`에 bootstrap 보조 라우터 등록을 추가해 500줄 규칙 대응 구조를 반영하는 작업 시작.
- 2026-03-01 (after): `app.main`에서 `app.api.bootstrap_routes` 라우터를 함께 등록하도록 변경해 기존 엔드포인트 경로를 유지하면서 `routes.py`를 500줄 이하로 분리할 수 있도록 구성.
- 2026-03-02 (before): 메일 조회 응답 상단 요약을 한 줄 문장 대신 `제목 + 하위 불릿` 형태로 정렬해 가독성을 개선하는 작업 시작.
- 2026-03-02 (issue): `pytest`가 설치되지 않은 실행 환경 확인 → `python -m unittest`로 동일 범위 테스트를 대체 실행.
- 2026-03-02 (after): 조회/검색 요약 요청 시 `주요 내용:` 타이틀과 `-` 하위 불릿으로 렌더링하도록 요약 후처리 로직을 조정하고 관련 테스트를 보강.
