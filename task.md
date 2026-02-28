# Task

## 현재 작업
의도 구조분해 규칙 보강(날짜 범위/한글 절대날짜/회의 일정 intent) 및 재검증

## Plan
- [x] 1단계: 공통 규칙 모듈에 상대 날짜 범위/한글 절대 날짜 파싱 규칙 추가
- [x] 2단계: 회의 일정 intent step을 스키마/파서에 반영
- [x] 3단계: 10문장 재실행으로 개선 효과 검증 및 로그 정리

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

## 완료된 작업
- [2026-02-28] `README.MD` 서버 실행 절차 문서화 및 `/addin/client-logs` 204 무본문 응답 수정
- [2026-02-28] Outlook Add-in 등록 가능 상태를 위한 FastAPI 서버 bootstrap (`app/`, `data/mock/meeting_rooms.json`) 구성
