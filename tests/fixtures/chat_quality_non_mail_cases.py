from __future__ import annotations

from typing import TypedDict


class NonMailQualityCase(TypedDict):
    """비메일 A/B 품질 검증용 케이스 타입."""

    case_id: int
    utterance: str
    pattern: str


CHAT_QUALITY_NON_MAIL_CASES: list[NonMailQualityCase] = [
    {"case_id": 1, "utterance": "오늘 회의실 예약 가능한 곳 알려줘", "pattern": "회의실 조회"},
    {"case_id": 2, "utterance": "프로젝트 예산 현황 요약해줘", "pattern": "예산 조회"},
    {"case_id": 3, "utterance": "이번주 해야 할 업무를 5줄로 정리해줘", "pattern": "일반 요약"},
    {"case_id": 4, "utterance": "비용정산 규정 핵심만 3개로 알려줘", "pattern": "핵심 추출"},
    {"case_id": 5, "utterance": "다음주 화요일 오후 일정 추천해줘", "pattern": "일정 추천"},
    {"case_id": 6, "utterance": "회의 준비 체크리스트 만들어줘", "pattern": "체크리스트"},
    {"case_id": 7, "utterance": "프로젝트 리스크를 보고서 형식으로 정리해줘", "pattern": "보고서"},
    {"case_id": 8, "utterance": "업무 우선순위를 높음/중간/낮음으로 나눠줘", "pattern": "분류"},
    {"case_id": 9, "utterance": "회의 결과 공유 메일 템플릿 만들어줘", "pattern": "템플릿"},
    {"case_id": 10, "utterance": "팀 주간 스탠드업 진행안을 작성해줘", "pattern": "진행안"},
]
