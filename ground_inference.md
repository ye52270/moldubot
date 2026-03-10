# ground_inference.md
> MolduBot 응답 라우팅/후처리/렌더링 운영 기준서 (Ground Inference Contract)
> 본 문서는 **현재 코드 동작과 아키텍처 원칙을 동기화**하기 위한 기준이다.

---

## 1. 목적과 원칙

### 1-1. 제품 원칙
- MolduBot은 메일 전용 챗봇이 아니라 **AI Hub**이다.
- 메일/비메일/혼합 질의를 공통 파이프라인으로 처리한다.
- 형식보다 사실성/근거/실행 가능성을 우선한다.

### 1-2. 출력 원칙
- 출력 모드는 두 가지로 운영한다.
  - `strict`: 템플릿형 응답(구조 강제)
  - `freeform`: 대화형 본문 응답(자연어 중심)
- **원칙**: 구조가 필요한 요청만 `strict`, 그 외는 `freeform`.

### 1-3. 금지 원칙
- 특정 문장 1건 해결용 하드코딩 예외를 공통 경로에 직접 주입하지 않는다.
- 템플릿 모양을 맞추기 위해 의미를 왜곡하지 않는다.
- 문서와 코드가 다르면 둘 중 하나를 숨기지 않고, 테스트와 함께 동기화한다.

---

## 2. 파이프라인(실행 순서)

1. API 진입: `search_chat_flow`
2. 의도 구조분해: `intent_parser` + middleware context 주입
3. 모델 호출: prompt variant 선택 후 agent 실행
4. 후처리: `answer_postprocessor`
5. 메타 생성: `answer_format_metadata`
6. 프론트 렌더: `answer_format.blocks` 우선, 없으면 rich text fallback

---

## 3. Routing / Render Mode 기준

## 3-1. Strict Mode

아래 조건 중 하나라도 만족하면 `strict`를 우선한다.

| 질의 유형 | 대표 신호 | 백엔드 분기(예시) | 도구 | 출력 |
|---|---|---|---|---|
| 현재메일 요약 | `현재메일` + `요약` | `current_mail_summary` 계열 | `run_mail_post_action(current_mail)` | `standard_summary` 섹션형 |
| 현재메일 N줄 요약 | `N줄` + 요약 | line summary 경로 | `run_mail_post_action(current_mail)` | 줄수 고정 요약 |
| 수신자 역할/표 | 역할/수신자/표 요청 | recipient-role/table 경로 | `run_mail_post_action(current_mail)` | 표/카드형 구조 |
| 조회/검색 | 조회/검색/관련/지난 | `mail_search_*` | `search_mails` | 조회 결과/근거 중심 |
| 실행 요청 | 등록/생성/예약 | action 경로 | ToDo/캘린더/회의실 도구 | 실행 결과형 |
| 코드 리뷰 | 리뷰/보안/성능 | code review 경로 | current mail + 리뷰 경로 | 코드리뷰 포맷 |

## 3-2. Freeform Mode

아래 조건이면 `freeform`을 우선한다.

- 후속 질문/추가 확인/해석 요청
- 구조화 템플릿을 명시하지 않은 일반 대화형 질의
- 의도 분해 결과가 `general` 중심이고 실행/조회/요약 강제 신호가 약한 경우

**동작 규칙**
- `freeform`은 카드 숫자 목록 강제를 하지 않는다.
- 본문 문단형 응답을 우선하고, 필요한 최소 불릿만 허용한다.
- 단, 사실 근거는 현재 컨텍스트(현재메일/조회결과/도구 결과) 기반으로 유지한다.

---

## 4. 현재 코드 기준 핵심 분기 포인트

### 4-1. 템플릿 선택
- `format_policy_selector.select_format_template`가 템플릿 ID를 고른다.
- 현재 구현에서 `현재메일` + `요약` 명시가 `current_mail_summary`로 가는 핵심 신호다.
- `정리/분석`만 있고 `요약`이 없으면 `general`로 갈 수 있다.

### 4-2. 후처리 우선순위
- `postprocess_final_answer`에서 최종 렌더가 확정된다.
- 순서:
  - deterministic 강제 렌더
  - JSON contract 파싱/보강
  - contract 렌더
  - fallback 렌더

### 4-3. 프론트 렌더 우선순위
- `metadata.answer_format.blocks`가 있으면 블록 렌더를 우선한다.
- 블록이 없거나 렌더 불가면 `renderRichText`로 자유형 출력한다.
- 단, 현재 구현에는 `current_mail` 범위의 자유형 불릿(2개 이상)을 카드 섹션으로 래핑하는 예외가 있다.

---

## 5. 운영 계약 (문서/코드 동기화 규칙)

1. 라우팅 규칙 변경 시:
   - `format_policy_selector` / middleware / prompt 분기와 이 문서를 동시에 업데이트한다.
2. 출력 포맷 변경 시:
   - `answer_postprocessor` + `answer_format_metadata` + add-in renderer를 함께 검토한다.
3. `strict/freeform` 기준 변경 시:
   - 최소 회귀 테스트(입력→출력 계약) 추가 후 반영한다.
4. 문서와 코드가 다를 경우, ADR/테스트 계약(행동 계약)을 기준으로 원인을 판별한다.
   필요 시 코드/문서를 함께 정렬하고, PR에 차이와 의사결정을 명시한다.

---

## 6. 목표 상태(당면 UX 목표)

- 목표: “템플릿 질의는 템플릿답게, 나머지는 ChatGPT식 본문형”
- 이를 위해 `metadata.render_mode = strict|freeform`를 명시 필드로 운영하고,
  프론트 렌더는 해당 필드를 1순위 기준으로 사용한다.

---

## 7. 버전 이력

| 날짜 | 변경 내용 | 작성자 |
|---|---|---|
| 2026-03-10 | 선행 리팩터링: 현재메일 direct-value 추출 로직을 `query_artifact_extractor`로 분리하고, `answer_postprocessor_current_mail` 결합도를 낮춰 파일 길이를 500줄 이하로 축소. 의도 분류에서 `분석/해석/검토`를 analysis 행위어로 인식하도록 보정 | Codex |
| 2026-03-10 | 기존 초안 전면 개정: AI Hub 원칙 정렬, strict/freeform 운영 기준 재정의, 문서-코드 동기화 계약 추가 | Codex |

---

## 8. 작업 누적 메모

- 2026-03-10 리팩터링 반영 파일:
  `app/services/query_artifact_extractor.py` (신규),  
  `app/services/answer_postprocessor_current_mail.py` (direct-value 추출/정렬 로직 분리),  
  `app/agents/intent_parser_utils.py` (analysis 행위어 인식 보강),  
  `tests/test_query_artifact_extractor.py` (신규),  
  `tests/test_intent_parser_fast_path.py` (analysis 분류 회귀 테스트 추가).
