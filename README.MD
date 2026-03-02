# MolduBot

## 프로젝트 개요
- FastAPI 백엔드(`app/`)와 Outlook Add-in 프론트(`clients/outlook-addin/`)를 함께 운영하는 사내 업무 보조 봇 프로젝트.
- 메일 조회/요약, 회의실 예약, 일정 등록, 실행예산/비용정산/근태 포털 연동, 보고서 생성 기능을 포함.

## 프로젝트 구조 (2026-03-03 기준)
```text
.
├── app/                  # FastAPI 서버, 에이전트, 미들웨어, 서비스
├── clients/
│   ├── outlook-addin/    # Outlook Add-in UI/스크립트/manifest
│   └── portals/          # myPromise, finance, myHR 정적 포털
├── data/                 # mock/chroma/sqlite/reports/meeting 데이터
├── docs/                 # 문서 및 프롬프트 스냅샷
├── infra/                # 인프라 보조 파일
├── scripts/              # 운영/유틸 스크립트
├── skills/               # 현재 task.md만 존재 (프로젝트 로컬 SKILL.md 없음)
├── tests/                # Python 테스트
├── requirements.txt
└── task.md
```

## Skill 문서 상태
- 루트 및 `skills/` 경로 기준으로 프로젝트 전용 `SKILL.md`/`skill.md` 파일은 현재 없음.
- 스킬 관련 작업 이력은 `skills/task.md`에서 관리.

## 서버 구동방법

## 1) 가상환경 활성화
```bash
cd /Users/jaeyoung/Desktop/moldubot
source venv/bin/activate
```

## 2) 의존성 설치 (최초 1회)
```bash
pip install -r requirements.txt
```

## 3) FastAPI 서버 실행
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 4) 동작 확인
- 헬스체크: `http://127.0.0.1:8000/healthz`
- Add-in 페이지: `http://127.0.0.1:8000/addin/taskpane.html`
- Manifest: `http://127.0.0.1:8000/addin/manifest.xml`

## 5) ngrok으로 외부 공개 (Outlook Add-in 등록용)
```bash
ngrok http 8000
```
- 발급된 HTTPS URL 기준으로 `https://<ngrok-domain>/addin/manifest.xml`를 Outlook Add-in에 등록
- 고정 Public URL을 쓰려면 환경변수 설정 후 실행:
```bash
export MOLDUBOT_PUBLIC_BASE_URL="https://<ngrok-domain>"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 6) Local Ollama 모델 실행/연결 (Exaone)
```bash
# 1) Ollama 서버 실행
ollama serve
```

```bash
# 2) 모델 확인
ollama list
```
- 예시 태그: `exaone3.5:2.4b`

```bash
# 3) 모델 단독 응답 테스트
ollama run exaone3.5:2.4b "안녕"
```

```bash
# 4) MolduBot 의도 구조분해 모델로 연결
export OLLAMA_BASE_URL="http://127.0.0.1:11434"
export MOLDUBOT_INTENT_MODEL="exaone3.5:2.4b"
```

```bash
# 5) FastAPI 재시작 (환경변수 반영)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- 주의: `MOLDUBOT_INTENT_MODEL` 값은 `ollama list`에 보이는 **정확한 태그명**과 동일해야 한다.
- 모델 태그가 다르면 구조분해 단계에서 `model not found`가 발생하고 규칙 기반 fallback으로 동작한다.

## 인터페이스 정의서 (Agent Orchestration v1)

### 1) 처리 원칙
- 1차 의도 구조분해: 로컬 Ollama Exaone
- 2차 실행/응답 생성: LangChain `create_deep_agent` 단일 에이전트
- 구조분해 실패 시: 규칙 기반 fallback으로 최소 실행 단계 보장

### 2) 환경변수 계약
- `OPENAI_API_KEY`: deep agent(OpenAI) 호출 키
- `MOLDUBOT_AGENT_MODEL`: deep agent 모델명 (기본: `gpt-4o-mini`)
- `MOLDUBOT_AGENT_SYSTEM_PROMPT`: deep agent 시스템 프롬프트
- `OLLAMA_BASE_URL`: Ollama 주소 (기본: `http://127.0.0.1:11434`)
- `MOLDUBOT_INTENT_MODEL`: 구조분해용 Ollama 모델 태그 (기본: `exaone3.5:2.4b`)

### 3) 의도 구조분해 스키마
- 코드 기준: `app/agents/intent_schema.py`
- 루트 모델: `IntentDecomposition`

```json
{
  "original_query": "string",
  "steps": [
    "read_current_mail",
    "summarize_mail",
    "extract_key_facts",
    "extract_recipients",
    "book_meeting_room"
  ],
  "summary_line_target": 5,
  "date_filter": {
    "mode": "none | relative | absolute",
    "relative": "",
    "start": "",
    "end": ""
  },
  "missing_slots": ["string"]
}
```

### 3-1) 의도 스키마 검증 규칙
- `date_filter.mode == none`이면 `relative/start/end`는 빈 값으로 정규화된다.
- `date_filter.mode == relative`면 `relative`는 허용 토큰만 허용된다.
  - 허용 토큰: `today`, `yesterday`, `this_week`, `last_week`, `recent`, `tomorrow`, `N_weeks_ago_to_last_week`
- `date_filter.mode == absolute`면 `start/end`는 `YYYY-MM-DD` 형식만 허용된다.
- `missing_slots`는 예약 필수 슬롯(`date`, `start_time`, `end_time`, `attendee_count`)만 유지된다.
- `steps`에 `book_meeting_room`가 없으면 `missing_slots`는 자동으로 빈 배열로 보정된다.

### 3-2) 미들웨어 책임 경계 (LangChain v1)
- `IntentDecompositionMiddleware.before_model`
  - 사용자 입력에 구조분해 컨텍스트를 주입한다.
- `ModelOutputGuardMiddleware.wrap_model_call`
  - 모델 예외/빈 응답을 보정한다.
  - 단, `tool_calls`가 있는 응답은 정상으로 간주하고 빈 content 보정을 생략한다.
- `ToolErrorGuardMiddleware.wrap_tool_call`
  - 도구 예외를 표준 `ToolMessage(status=error)`로 변환한다.
- `RequestResponseLogMiddleware.before_agent/after_agent`
  - 요청 경계 로깅을 공통화한다.

### 4) 서버 인터페이스: `POST /search/chat`
- 요청 본문

```json
{
  "message": "사용자 입력",
  "thread_id": "optional",
  "mode": "optional",
  "email_id": "optional",
  "intent_name": "optional",
  "runtime_options": {}
}
```

- 응답 본문

```json
{
  "status": "completed",
  "thread_id": "outlook_...",
  "answer": "최종 응답 텍스트",
  "metadata": {
    "source": "deep-agent | missing-openai-key | validation | openai-error"
  }
}
```

### 5) 내부 호출 순서
1. `taskpane.js`가 사용자 입력을 `/search/chat`으로 전송
2. 서버가 Exaone 파서(`ExaoneIntentParser`)로 구조분해 시도
3. 구조분해 결과를 텍스트 컨텍스트로 직렬화해 deep agent 입력에 주입
4. deep agent가 최종 응답 생성
5. 실패 시 fallback 응답 또는 오류 안내 반환

### 6) 메일 후속작업 표준 툴 인터페이스
- Tool 이름: `run_mail_post_action`
- 목적: `메일조회 -> (요약 | 보고서)` 후속작업을 단일 경로로 실행
- 입력:
  - `action`: `summary | report` (기본 `summary`)
  - `summary_line_target`: 요약 줄 수(기본 5)
- 출력:
  - 공통: `status`, `action`
  - `summary`: `summary_lines`, `line_count`
  - `report`: `title`, `summary_lines`, `key_facts`, `recipients`, `report_markdown`

## LangSmith에서 에이전트 그래프 확인

### 1) LangSmith 트레이싱 활성화
```bash
export LANGSMITH_API_KEY="<your-langsmith-api-key>"
export LANGSMITH_TRACING="true"
export LANGSMITH_PROJECT="moldubot-dev"
```

### 2) 서버 실행 후 대화 1회 호출
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
curl -X POST http://127.0.0.1:8000/search/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"현재메일 요약해줘"}'
```

### 3) 로컬에서 그래프(Mermaid) 파일 생성
```bash
venv/bin/python scripts/export_agent_graph.py
```
- 기본 출력 파일: `docs/agent_graph.mmd`
- 다른 경로로 저장하려면:
```bash
venv/bin/python scripts/export_agent_graph.py --output docs/agent_graph_custom.mmd
```
- 생성된 `.mmd` 파일을 Mermaid Live Editor(https://mermaid.live)에 붙여 넣으면 즉시 시각화할 수 있다.

### 4) LangSmith UI에서 그래프 확인
- LangSmith 프로젝트(`LANGSMITH_PROJECT`)에서 방금 생성된 run을 연다.
- run 트리에서 `moldubot-chat-turn` 실행을 선택하면 노드/툴 호출 흐름을 그래프 형태로 추적할 수 있다.
- 태그 `moldubot`, `deep-agent`로 필터링하면 해당 실행만 빠르게 찾을 수 있다.

## LangGraph Studio 로컬 실행 (노드 그래프/디버깅)

### 1) 설정 파일
- 프로젝트 루트 `langgraph.json`을 사용한다.
- 그래프 엔트리: `app/agents/langgraph_entry.py:graph`

### 2) 로컬 Studio 서버 실행
```bash
venv/bin/langgraph dev --config langgraph.json --port 2024 --no-browser
```

### 3) Studio 접속
- 터미널 출력의 Studio URL을 열어 노드 그래프/스텝 실행 상태를 확인한다.
- Safari 환경에서 localhost 연결이 막히면 다음 명령을 사용한다.
```bash
venv/bin/langgraph dev --config langgraph.json --port 2024 --no-browser --tunnel
```
