# Middleware Task Log

## Purpose
- Describe this folder's responsibility.

## Change History
- 2026-02-28: Folder initialized as part of ideal project structure refactor.
- 2026-02-28 (before): LangChain v1 공식 미들웨어(before_model/after_model/wrap_model_call/wrap_tool_call) 기반 공통 파이프라인 구축 작업 시작.
- 2026-02-28 (after): `policies.py`(공통 정책), `agent_middlewares.py`(커스텀 미들웨어 4종), `registry.py`(단일 조립 지점)를 추가해 입력 구조분해 주입/모델 출력 가드/도구 오류 표준화/요청 경계 로깅을 중앙화.

## Update Rule
- Before and after any code change in this folder, append a detailed log entry.
