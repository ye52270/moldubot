from __future__ import annotations

from typing import TypedDict


class IntentQueryCase(TypedDict):
    """
    의도 구조분해 테스트용 발화와 패턴 설명을 담는 항목 타입.

    Attributes:
        case_id: 테스트 케이스 식별자
        utterance: 사용자 발화 원문
        pattern: 커버하려는 패턴 설명
    """

    case_id: int
    utterance: str
    pattern: str


INTENT_TEST_CASES: list[IntentQueryCase] = [
    {
        "case_id": 1,
        "utterance": "ESG 관련 메일 찾아줘",
        "pattern": "단순 키워드 검색",
    },
    {
        "case_id": 2,
        "utterance": "김부장이 보낸 메일 3줄로 요약해",
        "pattern": "발신자 + 줄수 지정",
    },
    {
        "case_id": 3,
        "utterance": "어제 온 메일 중에 할일 뽑아줘",
        "pattern": "상대날짜 + 추출",
    },
    {
        "case_id": 4,
        "utterance": "2주 전부터 지난주까지 ESG 메일 보고서 형식으로 정리해줘",
        "pattern": "상대날짜 범위 + 보고서",
    },
    {
        "case_id": 5,
        "utterance": "이번 주 회의 일정 알려줘",
        "pattern": "캘린더 + 상대날짜",
    },
    {
        "case_id": 6,
        "utterance": "ESG 메일 요약하고 내일 오후 2시에 팀 회의 잡아줘",
        "pattern": "복합 (메일+일정) 병렬",
    },
    {
        "case_id": 7,
        "utterance": "박대리한테 온 메일 상세하게 분석해줘",
        "pattern": "발신자 + 상세 출력",
    },
    {
        "case_id": 8,
        "utterance": "2월 1일부터 2월 15일까지 결재 관련 메일 찾아줘",
        "pattern": "절대날짜 범위 + 키워드",
    },
    {
        "case_id": 9,
        "utterance": "최근 메일에서 액션아이템 추출해서 간략하게 정리해줘",
        "pattern": "추출 + 간략 출력",
    },
    {
        "case_id": 10,
        "utterance": "ESG 메일 찾아서 요약해줘",
        "pattern": "의존관계 (검색→요약 순차)",
    },
]

