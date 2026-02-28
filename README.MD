# 서버 구동방법

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
