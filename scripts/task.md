# Scripts Task Log

## Purpose
- Describe this folder's responsibility.

## Change History
- 2026-02-28: Folder initialized as part of ideal project structure refactor.
- [14:45] 작업 시작: summary queue/backfill 스크립트가 standalone 실행 시 `app` import 오류 없이 동작하도록 경로 보정 작업 시작.
- [14:46] 완료: `backfill_email_summary.py`와 `process_mail_summary_queue.py`가 실행 시 루트 경로를 `sys.path`에 주입하도록 수정해 repo 밖 cwd에서도 정상 실행되게 보정.
- [15:04] 작업 시작: 메일 수집/summary queue/Graph subscription/Chroma 상태를 한 번에 확인하는 점검 스크립트 추가 착수.
- [15:13] 완료: `check_mail_pipeline_health.py`를 추가해 emails/summary queue/Graph subscription/vector index 상태를 단일 JSON으로 점검 가능하게 구성.
- [15:19] 작업 시작: 최근 Graph 메일 pull sync를 수동 실행할 수 있는 보조 스크립트 추가 착수.
- [15:28] 완료: `sync_recent_graph_mail.py`를 추가해 dry-run 및 실제 pull sync를 JSON 결과로 실행할 수 있게 구성.
- [16:03] 작업 시작: 기존 메일 전체를 fallback 벡터 인덱스로 재색인하는 보조 스크립트 추가 착수.
- [16:17] 완료: `backfill_mail_vector_index.py`를 추가해 기존 emails 레코드 103건을 fallback 벡터 인덱스로 재색인하고 저장 행 수를 확인.

## Update Rule
- Before and after any code change in this folder, append a detailed log entry.
