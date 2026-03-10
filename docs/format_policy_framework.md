# Format Policy Framework (Draft)

## 목적
- 정형화된 업무 질의(메일 요약/조회 요약/기술 이슈 정리/ToDo/회의실/일정)를 공통 포맷으로 안정적으로 출력한다.
- 유사 의도는 동일 템플릿으로 수렴시키고, 복합 질의는 섹션 조합으로 유연하게 처리한다.
- 코드 변경 전 기준 프레임을 확정한다.

## 현재 구조 진단 (As-Is)
- 의도 분해: `app/agents/intent_schema.py`
  - `steps`, `task_type`, `output_format`, `focus_topics`를 반환.
- 라우팅 지시: `app/middleware/policies.py`
  - HIL/서브에이전트/도구 호출 정책을 문장 지시로 주입.
- 출력 계약: `app/models/response_contracts.py`
  - `LLMResponseContract` 중심 JSON 구조.
- 후처리/결정론 렌더: `app/services/answer_postprocessor.py`, `app/services/answer_postprocessor_mail_search.py`
  - 질의/도구 payload 기준 섹션(`주요 내용/기술 이슈/근거 메일`) 생성.
- UI 렌더: `clients/outlook-addin/taskpane.messages.answer_format.js`
  - `answer_format.blocks`의 section key 기반 렌더.

핵심 관찰:
- 기능은 이미 대부분 구현되어 있으나, 포맷 선택 규칙이 프롬프트/미들웨어/후처리에 분산되어 있다.

## 목표 포맷 레지스트리 (Template Registry)

### T1. 현재메일 요약
- Trigger:
  - `steps`에 `read_current_mail` + `summarize_mail`
  - `task_type=summary`
- Output:
  - `format_type=standard_summary` 또는 `summary`
  - 섹션: `제목/기본정보/핵심문제/주요내용/조치`
- Tool:
  - `run_mail_post_action(action="current_mail")`

### T2. `xxx` 관련 메일 조회 후 요약
- Trigger:
  - `steps`에 `search_mails`
  - `task_type=retrieval`
- Output:
  - 섹션: `주요 내용(2~3줄 digest)` + `근거 메일`
- Tool:
  - `search_mails` (필요 시 `search_meeting_schedule`)

### T3. `xxx` 관련 메일의 기술 내용 정리
- Trigger:
  - `steps`에 `search_mails`
  - `focus_topics`에 `tech_issue`
- Output:
  - 섹션: `기술 이슈`(키워드/유형/근거) + `근거 메일`
- Tool:
  - `mail-tech-issue-agent` 또는 tech keyword fan-out `search_mails`

### T4. 현재메일 요약 + 중요 이슈 정리
- Trigger:
  - `read_current_mail + summarize_mail + extract_key_facts`
- Output:
  - 섹션: `요약` + `중요 이슈` + `필요 조치`
- Tool:
  - `run_mail_post_action(action="current_mail")`

### T5. 현재메일 ToDo 생성
- Trigger:
  - `focus`: todo/action registration intent
  - 등록 동사 포함 (`등록/생성/추가/만들어`)
- Output:
  - HIL 승인 카드 + 실행 결과
- Tool:
  - `create_outlook_todo` (명시 등록 의도일 때만)

### T6. 현재메일 기반 회의실 예약
- Trigger:
  - meeting booking intent + slot 확보
- Output:
  - 제안/입력 폼 + HIL 승인 카드 + 실행 결과
- Tool:
  - `book_meeting_room`

## 복합 질의 프레임 (Primary + Facet)

### 원칙
- 단일 템플릿 강제가 아니라 조합형으로 처리.
- `Primary template` 1개 + `Facet section` N개.

### 예시
- 질의: "M365 프로젝트 진행, 일정 메일 요약 + 기술 이슈 검색"
  - Primary: `T2 (mail retrieval summary)`
  - Facet:
    - `F1 tech_issue_section`
    - `F2 evidence_section`
  - 최종 섹션 순서:
    1. 주요 내용
    2. 기술 이슈
    3. 근거 메일

### 충돌 해결 규칙
- 실행 의도(action)와 분석 의도(retrieval)가 동시에 있으면:
  - 먼저 분석 섹션 생성
  - 실행은 HIL 섹션으로 분리
- 근거 부족 시:
  - 섹션 제거 대신 `근거 부족` 표준 문구 사용

## Intent Signature 제안 (코드 변경 전 설계 계약)
- 예시 구조:
```json
{
  "scope": "current_mail|mail_search",
  "task": "summary|retrieval|analysis|action",
  "facets": ["tech_issue", "schedule", "todo", "evidence"],
  "requires_execution": false,
  "requires_hil": false
}
```

용도:
- 템플릿 선택기 입력값으로 사용.
- 기존 `steps/task_type/focus_topics`를 압축한 안정 시그니처.

## 적용 Phase 제안

### Phase 1 (무중단, 최소 리스크)
- 기존 로직 유지.
- `TemplateRegistry` 문서/상수만 추가.
- 후처리에서 템플릿 ID를 로그로만 남김(동작 불변).

### Phase 2 (선택기 도입)
- `template_selector` 추가:
  - `IntentDecomposition + tool_payload` -> `template_id + facets`.
- 기존 렌더 함수를 템플릿 ID로 호출.

### Phase 3 (서브에이전트 계약 정합)
- subagent 출력 JSON을 템플릿 section contract로 고정.
- `query_summaries/aggregated_summary/results`를 section DTO로 변환.

### Phase 4 (평가/품질 게이트)
- 템플릿별 품질 지표:
  - 섹션 누락률
  - 근거 링크 유효성
  - 기술 이슈 precision
  - HIL 성공률

## 트렌드 정합성 (2026-03-07 기준)
- Structured Outputs/JSON Schema 엄격화: 템플릿 계약 강제에 적합.
- Tool Calling + Planner/Worker 분리: 실행과 서술 분리에 적합.
- Multi-agent Supervisor 패턴: 복합 질의를 facet별로 병렬 수집하는 데 적합.
- Eval-driven 운영: 템플릿별 회귀 측정에 적합.

참고 문서:
- OpenAI Structured Outputs: https://developers.openai.com/api/docs/guides/structured-outputs
- OpenAI Function Calling: https://developers.openai.com/api/docs/guides/function-calling
- OpenAI Building Agents: https://developers.openai.com/tracks/building-agents
- OpenAI Cookbook (Structured Outputs): https://cookbook.openai.com/examples/structured_outputs_intro
- OpenAI Cookbook (Multi-agent orchestration): https://cookbook.openai.com/examples/agents_sdk/multi-agent-portfolio-collaboration/multi_agent_portfolio_collaboration
- LangChain Multi-agent: https://docs.langchain.com/oss/python/langchain/multi-agent
- Anthropic (agent patterns): https://www.anthropic.com/engineering/building-effective-agents

## 현재 결론
- 현재 코드에서도 정형 포맷 공통화는 가능하다.
- 우선은 "템플릿 레지스트리 + Primary/Facet 선택 규칙"을 도입해 분산된 규칙을 한곳으로 수렴시키는 것이 가장 안전하다.
