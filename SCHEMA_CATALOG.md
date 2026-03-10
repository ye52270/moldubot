# Schema Catalog

이 문서는 몰두봇의 출력 스키마를 "문장별"이 아니라 "의도 그룹별"로 운영하기 위한 기준입니다.

## 1) 운영 원칙
- 질문 문장마다 새 스키마를 만들지 않는다.
- 먼저 기존 스키마로 매핑한다.
- 정말 표현 불가능할 때만 신규 스키마를 추가한다.
- 신규 추가 시: 스키마 정의 + 라우팅 규칙 + 테스트 2개(정상/예외)를 같이 반영한다.

## 2) 현재 공통 스키마(운영 대상)

### A. `summary`
- 용도: 일반 요약/N줄 요약
- 대표 필드: `summary_lines`
- 대표 질문:
  - `현재메일 3줄 요약해줘`
  - `지난주 M365 메일 핵심만 요약해줘`

### B. `standard_summary`
- 용도: 현재메일 기본 구조화 요약
- 대표 필드: `basic_info`, `core_issue`, `major_points`, `required_actions`, `one_line_summary`
- 대표 질문:
  - `현재메일 요약해줘`
  - `현재메일 상세 요약해줘`

### C. `report`
- 용도: 보고서/문서형 응답
- 대표 필드: `answer`(보고서 본문)
- 대표 질문:
  - `현재메일 기준 보고서 작성해줘`

### D. `recipient_roles` (field set)
- 용도: 현재메일 수신자별 역할 분석 표
- 위치: `LLMResponseContract.recipient_roles`
- 행 스키마:
```json
{"recipient":"string","role":"string","evidence":"string"}
```
- 대표 질문:
  - `현재메일 수신자를 분석해서 각자 역할을 표로 정리해줘`
- 품질 가드:
  - To 수신자 범위만 허용
  - 발신자/참조자 제외
  - 인사/헤더/`참조:` 근거 제거

### E. `issue_analysis` (section style)
- 용도: 원인/영향/대응 분석
- 대표 질문:
  - `현재메일에서 비용이 문제가 되는 이유가 뭐야?`
  - `기술적 이슈와 일정 영향 원인을 알려줘`

### F. `solution_checklist` (section style)
- 용도: 해결 절차/체크리스트
- 대표 질문:
  - `SSL 인증서 이슈 해결 방법 알려줘`

## 3) 라우팅 결정 트리 (실무용)
1. 사용자 요청이 "현재메일 + 수신자 + 역할 + 표/정리"인가?
- 예: `recipient_roles` 우선
- 아니오: 다음 단계

2. 요청이 요약 중심인가?
- N줄/간단 요약: `summary`
- 현재메일 구조화 요약: `standard_summary`

3. 요청이 원인/해결 중심인가?
- 원인/영향: `issue_analysis`
- 해결/점검: `solution_checklist`

4. 요청이 보고서인가?
- 예: `report`

5. 어디에도 깔끔히 안 맞는가?
- 기존 스키마 조합으로 우선 처리
- 조합이 불가능하면 신규 스키마 후보 등록

## 4) 신규 스키마 추가 기준
아래 3개를 모두 만족할 때만 추가한다.
- 기존 스키마로 핵심 의미를 표현할 수 없다.
- 동일 유형 질문이 반복적으로 발생한다.
- UI 렌더러에서 독립 포맷이 필요한 구조다.

## 5) 예시: 사용자 질문 매핑
- 질문: `현재 메일에서 수신자를 요약해서 그들이 해야할 todo 와 마감기한을 정해줘`
- 1차 권장: 신규 스키마 없이 `recipient_roles + action_items` 조합 검토
- 2차(반복 발생 시): 신규 `recipient_todos` 스키마 추가

`recipient_todos` 초안:
```json
{
  "recipient_todos": [
    {
      "recipient": "string",
      "todo": "string",
      "due_date": "YYYY-MM-DD|미정",
      "due_date_basis": "string"
    }
  ]
}
```

## 6) 구현 체크리스트 (신규 스키마 추가 시)
- `app/models/response_contracts.py` 필드 추가
- `app/agents/prompts.py` JSON 계약/규칙 추가
- 후처리 렌더 경로 추가 (`app/services/*`)
- 테스트 추가:
  - 계약 정규화 테스트
  - 후처리 라우팅/렌더 테스트

## 7) 운영 메모
- 모델은 의미 생성 담당, 규칙은 품질 가드 담당.
- 품질 문제는 모델 성능만의 문제가 아니라 "가드 부재"가 원인인 경우가 많다.
- 스키마 수를 최소화해야 운영 복잡도와 사이드이펙트를 줄일 수 있다.
