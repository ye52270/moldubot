from __future__ import annotations

from typing import TypedDict


class ChatQualityCase(TypedDict):
    """
    `/search/chat` 품질 검증용 문장 케이스 타입.

    Attributes:
        case_id: 케이스 식별자
        utterance: 사용자 발화 원문
        pattern: 검증 패턴 설명
    """

    case_id: int
    utterance: str
    pattern: str


CHAT_QUALITY_CASES: list[ChatQualityCase] = [
    {
        "case_id": 1,
        "utterance": "M365 프로젝트 일정관련 최근 2주 메일 찾아줘",
        "pattern": "기간+키워드 메일 조회",
    },
    {
        "case_id": 2,
        "utterance": "현재메일 요약",
        "pattern": "현재메일 요약",
    },
    {
        "case_id": 3,
        "utterance": "조영득 관련 2월 메일 요약",
        "pattern": "인물+월 메일 요약",
    },
    {
        "case_id": 4,
        "utterance": "조영득 관련 2월 메일",
        "pattern": "인물+월 메일 조회",
    },
    {
        "case_id": 5,
        "utterance": "박준용 관련 2월 메일",
        "pattern": "인물+월 메일 조회",
    },
    {
        "case_id": 6,
        "utterance": "tenant 이슈관련 최근 메일",
        "pattern": "이슈 키워드 최근 조회",
    },
    {
        "case_id": 7,
        "utterance": "M365 프로젝트 최근 2주 메일의 주요 내용과 수/발신자 표로 정리",
        "pattern": "조회 후 표 형식 정리",
    },
    {
        "case_id": 8,
        "utterance": "ESG 구축과 관련된 1월 메일 조회하고 todo list를 만들어줘",
        "pattern": "조회 후 TODO 생성",
    },
    {
        "case_id": 9,
        "utterance": "Sense mail 관련 된 메일 찾아줘",
        "pattern": "키워드 메일 조회",
    },
    {
        "case_id": 10,
        "utterance": "메일 수발신 실패와 관련된 메일 찾아서 이슈가 뭔지 정리해줘..",
        "pattern": "조회 후 이슈 요약",
    },
]
