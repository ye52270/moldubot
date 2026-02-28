# Tests Task Log

## Purpose
- Describe this folder's responsibility.

## Change History
- 2026-02-28: Folder initialized as part of ideal project structure refactor.
- 2026-02-28 (before): 의도 구조분해 A/B 테스트용 문장 fixture 데이터 파일 추가 작업 시작.
- 2026-02-28 (after): `tests/fixtures/intent_query_cases.py` 추가, 테스트 문장 10개를 import 가능한 fixture 상수(`INTENT_TEST_CASES`)로 정리.
- 2026-02-28 (before): 경계 케이스 품질 측정을 위해 20개 의도 분해 fixture 및 자동 평가 스크립트 추가 작업 시작.
- 2026-02-28 (after): `tests/fixtures/intent_query_edge_cases.py`(20개 경계 케이스 + 기대값)와 `tests/eval_intent_edge_cases.py`(정확도/지연 자동 평가)를 추가하고 재실행 결과 100%(20/20) 확인.
- 2026-02-28 (before): CI 자동 품질 게이트를 위해 `eval_intent_edge_cases.py`에 임계치 판정(exit code)과 JSON 산출 기능을 추가하는 작업 시작.
- 2026-02-28 (after): `eval_intent_edge_cases.py`에 CLI 임계치(`--min-accuracy-all-fields`, `--max-avg-latency-ms`) 및 JSON 출력(`--output-json`)을 추가하고 품질 게이트 PASS/FAIL에 따라 종료코드를 반환하도록 개선.

## Update Rule
- Before and after any code change in this folder, append a detailed log entry.
