# Task

## 현재 작업
LangChain v1.0 공식 미들웨어 기반 공통 파이프라인 구축(모델 전/후 처리 중앙화)

## Plan
- [x] 1단계: 미들웨어 설계 원칙을 `task.md`에 상세 계획으로 고정하고 단계/산출물 정의
- [x] 2단계: `app/middleware`에 공통 정책 함수와 LangChain v1 커스텀 미들웨어 클래스 추가
- [x] 3단계: 미들웨어 레지스트리(단일 조립 지점) 구현 및 순서 고정
- [x] 4단계: `deep_chat_agent`를 미들웨어 레지스트리 사용 구조로 전환
- [x] 5단계: 컴파일 및 미들웨어 주입 스모크 테스트로 동작 검증
- [x] 6단계: 작업 로그(루트/폴더별) 완료 처리 및 변경 요약

## 미들웨어 설계 요약
- 단일 조립 지점 원칙: `app/middleware/registry.py`에서만 미들웨어 순서를 정의하고, 다른 모듈은 레지스트리 함수만 사용한다.
- 단일 책임 원칙: 정책(`policies.py`)과 실행(`agent_middlewares.py`)을 분리해 규칙 변경과 실행 체인을 분리한다.
- 전/후 처리 공통화 원칙: 입력 구조분해 주입은 `before_model`, 모델 응답 방어는 `wrap_model_call`, 도구 오류 표준화는 `wrap_tool_call`로 고정한다.
- 관측 가능성 원칙: 요청 경계(`before_agent`/`after_agent`)에 공통 로그를 남겨 추적 포인트를 중앙화한다.

## 테스트 결과 요약
- 실행 일시: 2026-02-28 15:01~15:05 (Asia/Seoul)
- 실행 명령:
  - `venv/bin/python - <<'PY' ...` (기존 10문장 fixture 재실행)
  - `PYTHONPATH=. venv/bin/python tests/eval_intent_edge_cases.py` (경계 20문장 자동 평가)
- 10문장 fixture 결과:
  - 총 10건, 평균 2128.6ms
  - 핵심 패턴 유지: `search_meeting_schedule`, `2_weeks_ago_to_last_week`, 한글 절대 날짜(`2026-02-01~2026-02-15`), 예약 `missing_slots`
- 경계 20문장 평가 결과:
  - 전체 정확도(모든 필드 동시 일치): 100.0% (20/20)
  - `steps`: 100.0%
  - `summary_line_target`: 100.0%
  - `date_filter`: 100.0%
  - `missing_slots`: 100.0%
  - 평균 지연: 1803.6ms (min 1239.0ms, max 3851.8ms)
- 관련 파일:
  - `tests/fixtures/intent_query_cases.py`
  - `tests/fixtures/intent_query_edge_cases.py`
  - `tests/eval_intent_edge_cases.py`

## Action Log
- [10:36] 작업 시작: `taskpane.css`의 참조 끊긴/미사용 스타일 정리 작업 시작
- [10:38] 완료: `clients/outlook-addin/taskpane.css`를 3608줄→373줄로 축소, 현재 `taskpane.html`/`taskpane.js` 사용 셀렉터 기반 스타일만 유지
- [10:40] 작업 시작: `create_deep_agent` 단일 에이전트 기반 채팅 응답 연동 작업 시작
- [10:43] 완료: `/search/chat`에 deep agent 단일 인스턴스 호출을 연결하고 `taskpane.js`를 API 연동 방식으로 복원, OPENAI_API_KEY 미설정 안내 및 오류 처리 반영
- [10:44] 이슈: `.env`에 OPENAI_API_KEY가 존재해도 `app/main.py`에서 dotenv를 로드하지 않아 키 미인식 발생 → 앱 초기화 시 `.env` 로드로 해결 예정
- [10:45] 완료: `app/main.py`에 `load_dotenv` 적용 후 `/search/chat` 응답 source가 `deep-agent`로 전환됨을 확인
- [10:54] 작업 시작: Exaone 의도 구조분해 + deep agent 입력 결합 설계/구현 시작
- [10:56] 이슈: Ollama 모델명 불일치로 `model 'exaone:2.5b' not found` 발생 → `MOLDUBOT_INTENT_MODEL` 환경변수로 실제 태그명 주입 필요
- [10:56] 완료: 의도 구조분해 스키마/파서 추가 및 deep agent 입력 결합, 문법 검증/엔드포인트 동작 확인 완료
- [10:57] 작업 시작: 인터페이스 정의서(의도 구조분해/에이전트/채팅 API) 내용을 `README.MD`에 반영
- [10:57] 완료: `README.MD`에 Agent Orchestration v1 인터페이스 정의서(환경변수, 스키마, `/search/chat` 계약, 내부 호출 순서) 추가
- [10:59] 작업 시작: `README.MD`에 Local Ollama 모델 실행/연결 절차 추가
- [10:59] 완료: `README.MD`에 Exaone 로컬 모델 실행, 태그 확인, 환경변수 연결, 서버 재시작 절차 추가
- [11:04] 작업 시작: print 금지 원칙에 맞춰 공통 logging 모듈 도입 및 에이전트 경로 추적 로그 통합
- [11:06] 완료: `app/core/logging_config.py` 공통 로깅 모듈 추가, `main/api/agents` 공통 로거 통합 및 `/search/chat` 경로 추적 로그 검증 완료
- [11:07] 작업 시작: 의도 구조분해 결과(JSON) 자체를 로그로 확인할 수 있도록 로깅 보강
- [11:08] 완료: `deep_chat_agent.py`에 `IntentDecomposition` JSON 로그 출력 추가, 실제 `/search/chat` 호출에서 구조분해 결과 로그 확인
- [11:15] 작업 시작: Exaone 구조분해 프롬프트를 상세 지시형으로 강화하고 테스트 결과 검증
- [11:16] 완료: `intent_parser._build_prompt`를 강제 규칙형으로 교체하고 동일 문장 테스트 수행(테스트 러너는 환경변수 미반영으로 fallback 확인, 프롬프트 반영 완료)
- [11:18] 작업 시작: 구조분해 결과에 예시/환각 값이 들어가지 않도록 추측 금지 규칙으로 프롬프트 재보정
- [11:18] 완료: `intent_parser._build_prompt`에 추측/예시 금지 및 `missing_slots` 우선 규칙 추가, 서버 로그 확인 기준 정리 완료
- [11:22] 작업 시작: 구조분해 결과 환각 제거를 위한 evidence Rule guardrail 구현 및 검증
- [11:23] 완료: `intent_parser`에 근거 기반 정제 로직 적용 후 동일 문장 테스트에서 `key_points/recipients` 빈 배열 및 필수 누락 슬롯 반영 확인
- [11:25] 작업 시작: `user_goal`을 원문 그대로 고정하도록 가드 규칙 추가
- [11:26] 완료: evidence guardrail에서 `user_goal` 원문 고정 적용 및 동일 문장 테스트로 JSON 결과 확인
- [11:30] 작업 시작: 제안한 복합 JSON 스키마를 Exaone이 실제로 안정 출력하는지 PoC 실행
- [11:31] 완료: 복합 스키마 PoC 결과를 확인했고 형식 준수는 성공했으나 intent/필드 의미 일관성 오류(`report` 과다 true, 일정 날짜 추측, 참조값 오남용)로 즉시 채택은 보류
- [11:32] 작업 시작: 의도 구조분해를 OpenAI 경량 모델로도 선택 가능하도록 provider 스위치 구현
- [11:33] 완료: `MOLDUBOT_INTENT_PROVIDER=openai`, `MOLDUBOT_INTENT_OPENAI_MODEL=gpt-4o-mini` 경로 추가 및 `/search/chat` structured output 동작 확인
- [11:36] 작업 시작: 사용자 제공 10개 문장을 테스트 fixture 데이터로 추가하고 import 경로 제공
- [11:37] 완료: `tests/fixtures/intent_query_cases.py`에 10개 테스트 문장 추가, `INTENT_TEST_CASES` import 검증 완료
- [11:39] 작업 시작: 10개 테스트 문장 전체 의도 구조분해 결과 일괄 실행 및 품질 점검
- [11:39] 완료: Exaone(`exaone3.5:2.4b`)로 10개 문장 일괄 구조분해 실행, 케이스별 steps/missing_slots 품질 결과 수집
- [11:40] 완료: Exaone vs OpenAI(gpt-4o-mini) 10개 문장 재검증 실행, 케이스별 steps/summary/missing_slots 비교 결과 수집
- [11:40] 작업 시작: Exaone vs OpenAI(경량) 동일 10문장 재검증 및 결과 비교
- [11:50] 작업 시작: Exaone 단일 경로 유지 방침에 맞춰 최소 스키마 재설계 및 테스트 코드 정리
- [11:52] 완료: Exaone 전용 최소 스키마/프롬프트로 parser 정리, OpenAI 분기 제거, `/search/chat` 동작 검증 및 README 인터페이스 갱신
- [11:53] 완료: README JSON 예시 형식 정리(후행 콤마 제거) 및 문서 일관성 확인
- [11:56] 작업 시작: 의도 분해 규칙 로직을 `app/core` 공통 모듈로 분리해 parser 의존성을 정리
- [11:57] 작업 시작: AGENTS 원칙에 맞춰 공통 규칙 모듈 연결 마무리(파서 연동/검증/로그 정리)
- [11:58] 이슈: 시스템 `python` 커맨드 미설치로 검증 명령 실패 → `venv/bin/python`으로 컴파일/실행 검증 전환
- [11:58] 완료: `intent_parser`가 `app/core/intent_rules.py`를 공통 사용하도록 리팩터링 완료, `venv/bin/python -m compileall app` 및 샘플 문장 구조분해 결과 검증
- [12:00] 작업 시작: 재검증에서 드러난 3개 이슈(상대 날짜 범위/한글 절대 날짜/회의 일정 intent) 수정 작업 시작
- [12:01] 완료: step 스키마/파서/규칙 모듈을 보강하고 10문장 재실행 검증에서 이슈 3건(케이스 4/5/8) 개선 확인
- [14:36] 작업 시작: LangChain v1 공식 미들웨어 전환 작업 시작(전/후 처리 공통화, 레지스트리 기반 순서 고정)
- [14:38] 완료: `app/middleware` 공통 정책/미들웨어/레지스트리 구현 및 `deep_chat_agent` 미들웨어 주입 전환, 컴파일/주입 스모크 테스트 완료(OpenAI 키 미설정으로 실제 모델 호출 스모크는 미실행)
- [14:39] 작업 시작: `.gitignore`에 Chroma DB 산출물 제외 규칙 추가
- [14:40] 완료: `.gitignore`에 `chroma_db/`, `data/chroma/` 무시 규칙 추가
- [14:40] 작업 시작: `.gitignore`에 SQLite `emails.db` 제외 규칙 추가
- [14:40] 완료: `.gitignore`에 `emails.db`, `database/emails.db`, `data/sqlite/emails.db` 무시 규칙 추가
- [14:41] 작업 시작: Git 추적 대상에서 Chroma DB와 `emails.db`를 인덱스 제거(`git rm --cached`) 처리
- [14:42] 이슈: `git rm --cached data/chroma` 실행 시 `data/chroma/task.md`도 함께 제거 스테이징됨 → 해당 파일만 스테이징/워킹트리 복구 후 `.gitignore` 예외(`!data/chroma/task.md`)로 해결
- [14:42] 완료: `data/chroma` DB 파일들과 `data/sqlite/emails.db`를 Git 인덱스에서 제거하고, `data/chroma/task.md`는 추적 유지 상태로 정리
- [14:42] 작업 시작: 미들웨어 공통화 변경 + DB 파일 추적 제거 상태를 하나의 커밋으로 정리
- [14:42] 완료: `feat(middleware): LangChain v1 공통 미들웨어 레지스트리 도입` 커밋 생성(커밋 해시: `9556267`)
- [14:54] 작업 시작: 로컬 유지/원격 제거 요구사항에 맞춰 DB 파일 삭제 커밋을 원격(main)으로 반영
- [14:55] 작업 시작: 민감 DB/Chroma 파일의 Git 히스토리 완전 삭제(`git filter-repo` + 강제 푸시) 진행
- [14:55] 이슈: `git filter-repo` 미설치 상태 확인 → `venv/bin/pip install git-filter-repo`로 설치 후 히스토리 재작성 진행
- [14:56] 완료: `git filter-repo --invert-paths`로 민감 경로(`chroma_db/`, `database/emails.db`, `data/sqlite/emails.db`, `data/chroma` DB 산출물)를 히스토리에서 제거하고 `origin/main`에 `--force-with-lease` 푸시 완료(원격 트리/히스토리 재검증 결과 0건)
- [15:00] 작업 시작: 메일 조회/요약 테스트 문장 fixture(10개) 재실행으로 구조분해 동작 검증
- [15:01] 완료: fixture 10개 전건 재실행 완료(평균 2128.6ms), `steps/date_filter/missing_slots` 기대 패턴 유지 확인
- [15:00] 작업 시작: 경계 케이스 20개 추가 및 자동 평가 스크립트 기반 품질 지표 산출
- [15:03] 이슈: 날짜 필터 비교 시 Enum 문자열(`DateFilterMode.NONE`)과 기대값(`none`) 비교 불일치로 정확도 0% 표기 → 비교 로직에서 Enum `.value` 정규화로 해결
- [15:05] 완료: 경계 케이스 20개 평가 재실행 결과 100%(20/20), 평균 1803.6ms 확인
- [15:06] 작업 시작: `/search/chat` 실호출 기반 E2E 검증(미들웨어 훅 로그/응답 동작 확인)
- [15:08] 완료: `/search/chat` E2E에서 `before_agent -> before_model -> wrap_model_call(401 예외 가드) -> after_agent` 로그 순서를 확인했고, 모델 인증 실패 시 fallback 응답(`응답을 생성하지 못했습니다...`)으로 정상 복구됨을 검증
- [15:09] 작업 시작: 실제 OpenAI 유효 키 기준 E2E 재검증(정상 응답 경로 확인)
- [15:09] 완료: 임시 서버(`:8002`) 실호출에서 OpenAI `HTTP 200 OK`, 미들웨어 훅(`before_agent -> before_model -> after_agent`) 정상 순서, 비-fallback 정상 답변(`안녕하세요. 미들웨어가 정상적으로 동작하고 있습니다.`) 확인
- [15:12] 작업 시작: GitHub Actions 기반 의도분해 품질 게이트(CI) 구성 및 임계치 자동 판정 추가
- [15:14] 완료: `.github/workflows/intent-quality.yml` 추가(정확도>=95, 평균지연<=2500ms), `tests/eval_intent_edge_cases.py` 품질 게이트 exit code/JSON 출력 지원 및 로컬 PASS 검증 완료
- [15:20] 작업 시작: CI에서 Ollama 의존 제거를 위해 `eval_intent_edge_cases.py` 오프라인(rule-only) 모드 추가 및 워크플로우 반영
- [15:20] 완료: CI 워크플로우를 `--offline-rule-only` 모드로 전환해 환경 의존성을 제거했고, 로컬 동일 명령 실행에서 QUALITY_GATE PASS 확인
- [15:23] 작업 시작: `/search/chat` 운영 모니터링을 위해 공통 메트릭 모듈 및 조회 엔드포인트 구현
- [15:24] 완료: `app/core/metrics.py` 추가 및 `/search/chat` 메트릭 기록 연결, `/search/chat/metrics` 조회에서 성공률/폴백비율/p95 지연 집계 검증 완료
- [15:27] 작업 시작: 핵심 기능 우선순위에 따라 실제 메일 조회/요약/핵심추출/수신자추출/회의실 예약 Tool Calling 구현 착수
- [15:33] 완료: `app/services` 실제 처리 서비스(메일/회의실/업무실행)를 구현하고 `deep_chat_agent`에 비즈니스 실행 경로를 연결해 핵심 문장 E2E에서 요약/추출/예약(정보부족 시 슬롯 안내, `내일 5명 예약` 자동완성) 동작을 확인
- [16:15] 작업 시작: 사용자 요청에 따라 메일/회의 의도를 모델 Tool Calling 전용 경로로 복원(서비스 우선 실행 분기 제거)
- [16:31] 작업 시작: 현재 작업 상태를 스냅샷 커밋/푸시하여 복구 지점(`미들웨어구축전-깔끔버전`) 확보

## 완료된 작업
- [2026-02-28] `README.MD` 서버 실행 절차 문서화 및 `/addin/client-logs` 204 무본문 응답 수정
- [2026-02-28] Outlook Add-in 등록 가능 상태를 위한 FastAPI 서버 bootstrap (`app/`, `data/mock/meeting_rooms.json`) 구성
