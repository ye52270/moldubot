# Intent Routing Operations Guide

## 목적
이 문서는 몰두봇 intent 라우팅 운영 기준을 정의한다.
범위는 `intent_parser -> middleware -> routes -> postprocessor` 경로다.

## 라우팅 스키마
- `task_type`: `general|summary|extraction|analysis|solution|retrieval|action`
- `output_format`: `general|structured_template|detailed_summary|line_summary|table|issue_action|schedule_owner_action`
- `focus_topics`: `mail_general|recipients|cost|tech_issue|schedule|ssl`
- `confidence`: 0.0~1.0

## 실행 분기 규칙
- `task_type=retrieval`: agent prompt variant `fast_compact`
- `task_type=analysis|solution`: agent prompt variant `quality_structured`
- `confidence < 0.60`:
  - 기본 동작: `/search/chat`에서 `needs_clarification` 반환
  - 예외: `runtime_options.skip_intent_clarification=true`면 즉시 실행
- `왜/원인/해결/대응` 질의:
  - intent steps에 `summarize_mail + extract_key_facts`를 포함
  - 후처리에서 분석/해결 템플릿 강제

## 후처리 강제 포맷
- 원인 분석 요청: `원인 / 영향 / 대응`
- 해결 요청: `가능한 원인 / 점검 순서 / 즉시 조치`
- 수신자 표 요청: markdown table 강제

## 장애 대응 Runbook
1. 증상 확인
- `source=intent-clarification` 급증 여부 확인
- `intent_confidence` 평균 급락 여부 확인
2. 빠른 완화
- 임시로 `runtime_options.skip_intent_clarification=true` 적용(운영자/QA 한정)
- prompt variant를 `quality_structured`로 고정해 품질 우선 동작
3. 원인 분석
- `app.agents.intent_parser` 로그에서 `task_type/output_format/confidence` 확인
- `app.middleware.policies` 주입 문구(`라우팅 지시`) 확인
4. 복구
- 실패 질의를 `tests/fixtures`에 추가
- intent/후처리 규칙 보강 후 회귀 테스트 실행

## KPI 기준선
- `intent_required_steps_pass_rate >= 95.0`
- `intent_parse_success_rate >= 99.0`
- `summary_line_compliance_rate >= 95.0`
- `report_format_compliance_rate >= 90.0`
- `booking_failure_reason_compliance_rate >= 90.0`
- `chat_success_rate >= 95.0`
- `avg_latency_ms <= 6500.0`

## 회귀 게이트 실행
```bash
PYTHONPATH=. venv/bin/python tests/eval_routing_quality_gate.py
```
- 결과 파일: `data/reports/chat_eval_latest_gate.json`
- `gate.passed=false`면 배포 보류 후 실패 지표부터 복구

## 신규 Intent 추가 절차
1. 스키마 정의
- `IntentTaskType/IntentOutputFormat/IntentFocusTopic`에 항목 추가
2. 파서 반영
- `_infer_intent_dimensions` 규칙 추가
- 필요 시 `infer_steps_from_query`/`_infer_required_steps_from_query` 보강
3. 실행/렌더 반영
- routes 분기 및 postprocessor 템플릿 추가
4. 테스트
- parser/route/postprocessor 테스트 최소 1개씩 추가
5. 평가
- `tests/eval_intent_complex_cases.py` + KPI 게이트 재실행
