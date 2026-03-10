# Intent Taxonomy Guide

`intent` 라우팅 규칙을 운영 중에 코드 수정 없이 조정하는 방법입니다.

## 1) 설정 파일 위치
- 기본: `config/intent_taxonomy.json`
- 환경변수 override: `INTENT_TAXONOMY_CONFIG_PATH=/abs/path/intent_taxonomy.json`

## 2) 현재 지원 규칙
- `recipient_todo_policy`
  - `recipient_tokens`: 수신자 질의 토큰
  - `todo_tokens`: 할 일 질의 토큰
  - `due_tokens`: 마감/기한 토큰
  - `registration_tokens`: 실제 등록 의도 토큰

## 3) 동작 원리
- 질의가 `recipient + todo + due`를 모두 포함하고
- `registration` 토큰이 없으면
- 라우팅 지시에 `create_outlook_todo 호출 금지`를 주입합니다.

즉, 아래처럼 분기됩니다.
- 요약/정리형: `현재 메일에서 수신자 todo와 마감기한 정리해줘` -> 표/요약만 생성
- 실행형: `현재메일 기준 todo 등록해줘` -> ToDo 등록 경로 허용(HIL)

## 4) 운영 튜닝 예시
```json
{
  "recipient_todo_policy": {
    "recipient_tokens": ["수신자", "담당자", "assignee"],
    "todo_tokens": ["todo", "할일", "action"],
    "due_tokens": ["마감", "기한", "due"],
    "registration_tokens": ["등록", "생성", "create"]
  }
}
```

## 5) 반영 방식
- 서버 재시작 없이 파일 변경 시 자동 반영(mtime 기반 캐시 갱신)
- 파싱 실패/파일 누락 시 기본값으로 안전 fallback
