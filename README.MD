# MolduBot

사내 메일/일정 기반 업무를 지원하는 FastAPI + Outlook Add-in 프로젝트입니다.

## 1. 프로젝트 개요
- 백엔드: `FastAPI` (`app/`)
- 프론트: `Outlook Add-in` (`clients/outlook-addin/`)
- 핵심 기능:
  - 메일 조회/요약/후속 액션(ToDo)
  - 조건 기반 메일 검색(사람/기간/키워드)
  - 회의실 추천/예약, 캘린더 일정 생성
  - 보고서/주간보고 생성(SSE + DOCX 다운로드)
  - Legacy 포털 연동(mock): 실행예산/비용정산/근태

## 2. 현재 구조
```text
.
├── app/
│   ├── main.py                          # FastAPI 진입점, 라우터/정적 mount
│   ├── api/                             # HTTP 엔드포인트
│   ├── agents/                          # Intent parser, deep chat agent, tool registry
│   ├── middleware/                      # LangChain v1 미들웨어 조립/가드
│   ├── services/                        # 메일검색/후처리/평가/보고서 변환 등 도메인 로직
│   ├── integrations/microsoft_graph/    # Graph Mail/Calendar/ToDo 클라이언트
│   └── core/                            # 공통 로깅, 날짜/룰, 메트릭
├── clients/
│   ├── outlook-addin/                   # taskpane UI, manifest, JS/CSS
│   └── portals/                         # myPromise / finance / myHR 정적 페이지
├── config/                              # intent/role taxonomy
├── data/                                # sqlite/mock/reports/chroma 데이터
├── docs/                                # 운영/프롬프트/리포트 문서
├── scripts/                             # 품질평가/데이터셋 유틸
├── tests/                               # pytest + cjs 기반 회귀 테스트
├── requirements.txt
└── task.md
```

## 3. 런타임 로직 (요약)
1. `POST /search/chat` 요청 수신
2. `IntentParser`가 의도 구조분해 시도
   - Fast-path / LRU cache / 실패 시 규칙 기반 fallback
3. `DeepChatAgent` 실행 (`create_deep_agent`)
   - tool: `run_mail_post_action`, `search_mails`, `book_meeting_room`, `create_outlook_calendar_event`, `create_outlook_todo` 등
   - middleware: 로깅, intent 주입, 모델/툴 가드, HIL 승인, 후처리
4. 응답 후 `metadata`에 근거메일/요약/후속액션/포맷 정보 포함
5. 회의실/일정/ToDo는 Human-in-the-Loop 승인(`pending_approval` → `/search/chat/confirm`)

## 4. 주요 API

### 4.1 채팅/컨텍스트
- `GET /healthz`
- `POST /search/chat`
- `POST /search/chat/stream` (SSE)
- `POST /search/chat/confirm`
- `GET /search/chat/metrics`
- `GET /search/chat/runtime-config`
- `POST /mail/context`
- `POST /intents/resolve`
- `POST /search/id`

### 4.2 회의실/일정
- `GET /api/meeting-rooms`
- `POST /api/meeting-rooms/suggest-from-current-mail`
- `POST /api/meeting-rooms/book`
- `POST /api/calendar-events/suggest-from-current-mail`
- `POST /api/calendar-events/create`

### 4.3 보고서
- `POST /report/generate` (SSE)
- `POST /report/weekly/generate` (SSE)
- `GET /report/download/{filename}`
- `GET /report/preview/{filename}`

### 4.4 운영/평가
- `POST /addin/client-logs`
- `POST /addin/export/weekly-report`
- `POST /ops/mail-sync/recent`
- `POST /qa/chat-eval/run`
- `GET /qa/chat-eval/latest`
- `GET /qa/chat-eval/cases`

### 4.5 Legacy 포털(mock)
- Promise: `GET /api/promise/projects`, `GET /api/promise/summaries`, `GET /api/promise/drafts`, `POST /api/promise/drafts`
- Finance: `GET /api/finance/projects`, `GET /api/finance/projects/{project_number}/budget`, `POST /api/finance/claims`
- MyHR: `POST /api/myhr/requests`

## 5. 환경변수
필수/주요 변수:
- `AZURE_OPENAI_ENDPOINT`: Azure OpenAI 엔드포인트 URL
- `AZURE_OPENAI_API_KEY`: Azure OpenAI API Key
- `AZURE_OPENAI_API_VERSION`: Azure OpenAI API 버전 (예: `2024-12-01-preview`)
- `AZURE_OPENAI_DEPLOYMENT`: 기본 채팅/요약 배포명 (예: `gpt-4o-mini`)
- `MOLDUBOT_AGENT_MODEL`: 실행 에이전트 모델 (기본 `gpt-4o-mini`)
- `MOLDUBOT_AGENT_SYSTEM_PROMPT`: 실행 에이전트 시스템 프롬프트
- `MOLDUBOT_AGENT_SKILLS_PATHS`: Deep Agents skills 디렉터리 목록(콤마/세미콜론/줄바꿈 구분, 예: `/skills/core,/skills/mail`)
- `MOLDUBOT_INTENT_MODEL`: 의도 구조분해 모델 (기본 `azure_openai:gpt-4o-mini`)
- `MOLDUBOT_INTENT_BASE_URL`: provider가 base_url을 필요로 할 때 사용하는 endpoint (선택)
- `MOLDUBOT_INTENT_TIMEOUT_SEC`: 의도 구조분해 LLM 호출 timeout(초, 기본 `60`)
- `MOLDUBOT_LOG_LEVEL`: 로깅 레벨
- `PROMPT_TRACE_ENABLED`: 프롬프트 트레이스 로그 on/off
- `MOLDUBOT_PUBLIC_BASE_URL`: Add-in manifest 공개 URL 치환용
- `MOLDUBOT_MAIL_VECTOR_INDEX_ENABLED`: 메일 벡터 인덱스 on/off (기본 `1`)
- `MOLDUBOT_MAIL_VECTOR_DIR`: 벡터 인덱스 저장 경로 (기본 `data/chroma_db`)
- `MOLDUBOT_SUMMARY_SYNC_ON_UPSERT`: 메일 upsert 직후 summary queue 동기 처리 여부 (기본 `1`)

## 6. 런타임 기준
- 운영 권장 Python 버전은 `3.13.x`입니다.
- `Python 3.14`에서는 `chromadb`가 깨져서 Chroma backend를 직접 사용할 수 없습니다.
- 현재 프로젝트는 `3.14`에서도 sqlite fallback 벡터 인덱스로 동작하지만, Chroma까지 정상 사용하려면 `.venv313` 기준으로 실행하는 편이 맞습니다.

## 7. 로컬 실행
```bash
cd /Users/jaeyoung/Desktop/moldubot
python3.13 -m venv .venv313
source .venv313/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

확인 URL:
- `http://127.0.0.1:8000/healthz`
- `http://127.0.0.1:8000/addin/taskpane.html`
- `http://127.0.0.1:8000/addin/manifest.xml`

## 8. 메일 수집/요약/임베딩 운영 명령
최근 메일을 Graph에서 끌어와 DB/summary queue로 동기화:
```bash
.venv313/bin/python scripts/sync_recent_graph_mail.py --limit 20
```

운영 API로 dry-run 확인:
```bash
curl -s -X POST "http://127.0.0.1:8000/ops/mail-sync/recent?limit=20&dry_run=true"
```

운영 API로 실제 sync 실행:
```bash
curl -s -X POST "http://127.0.0.1:8000/ops/mail-sync/recent?limit=20"
```

메일/queue/vector 상태 점검:
```bash
.venv313/bin/python scripts/check_mail_pipeline_health.py
```

summary 누락분 재큐잉:
```bash
.venv313/bin/python scripts/backfill_email_summary.py --db-path data/sqlite/emails.db
```

summary queue 처리:
```bash
.venv313/bin/python scripts/process_mail_summary_queue.py --db-path data/sqlite/emails.db --max-jobs 20
```

기존 메일 전체를 벡터 인덱스로 재색인:
```bash
.venv313/bin/python scripts/backfill_mail_vector_index.py --db-path data/sqlite/emails.db
```

## 9. 테스트
```bash
source .venv313/bin/activate
pytest -q
```

선택 실행 예시:
```bash
pytest -q tests/test_search_chat_e2e_samples.py
pytest -q tests/test_report_routes.py
pytest -q tests/test_bootstrap_meeting_routes.py
```

## 10. 현재 운영 상태 메모
- `emails.db` 기준 메일 `103`건, summary 누락 `0`건, summary queue `completed 103`건 기준으로 복구 완료
- `.venv313` 기준 health 상태에서 `vector_index.backend = chromadb` 확인
- `Python 3.14` 경로는 fallback backend로만 사용할 것

## 11. 개발 규칙 메모
- 작업 시작 전 루트 `task.md`에 Plan/Action Log를 먼저 업데이트
- `print()` 대신 공통 `logging` 사용 (`app/core/logging_config.py`)
- 중복 로직은 공통 함수/모듈로 추출
- 변경 시 회귀 테스트를 함께 수행

## 12. 최근 수정 (2026-03-17)
- Graph 최근 메일 pull sync 경로 추가:
  - `GraphMailClient.list_recent_messages`
  - `MailSyncService`
  - `scripts/sync_recent_graph_mail.py`
  - `POST /ops/mail-sync/recent`
- summary 누락 + stale completed queue row 재큐잉 정책 복구
- `Python 3.14` Chroma 비호환 대응 sqlite fallback backend 추가
- `Python 3.13.12` 기반 `.venv313` 환경에서 Chroma backend 복구 및 재색인 완료
