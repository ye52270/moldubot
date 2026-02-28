# Tests Task Log

## Purpose
- Describe this folder's responsibility.

## Change History
- 2026-02-28: Folder initialized as part of ideal project structure refactor.
- 2026-02-28 (before): 의도 구조분해 A/B 테스트용 문장 fixture 데이터 파일 추가 작업 시작.
- 2026-02-28 (after): `tests/fixtures/intent_query_cases.py` 추가, 테스트 문장 10개를 import 가능한 fixture 상수(`INTENT_TEST_CASES`)로 정리.
- 2026-02-28 (before): 경계 케이스 품질 측정을 위해 20개 의도 분해 fixture 및 자동 평가 스크립트 추가 작업 시작.
- 2026-02-28 (after): `tests/fixtures/intent_query_edge_cases.py`(20개 경계 케이스 + 기대값)와 `tests/eval_intent_edge_cases.py`(정확도/지연 자동 평가)를 추가하고 재실행 결과 100%(20/20) 확인.

## Update Rule
- Before and after any code change in this folder, append a detailed log entry.
