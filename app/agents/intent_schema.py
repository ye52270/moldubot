from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ExecutionStep(str, Enum):
    """
    의도 구조분해에서 사용하는 최소 실행 단계를 정의한다.
    """

    READ_CURRENT_MAIL = "read_current_mail"
    SUMMARIZE_MAIL = "summarize_mail"
    EXTRACT_KEY_FACTS = "extract_key_facts"
    EXTRACT_RECIPIENTS = "extract_recipients"
    SEARCH_MEETING_SCHEDULE = "search_meeting_schedule"
    BOOK_MEETING_ROOM = "book_meeting_room"


class DateFilterMode(str, Enum):
    """
    날짜 필터 표현 방식을 정의한다.
    """

    NONE = "none"
    RELATIVE = "relative"
    ABSOLUTE = "absolute"


class DateFilter(BaseModel):
    """
    최소 날짜 필터 구조를 정의한다.

    Attributes:
        mode: 날짜 필터 모드
        relative: 상대 날짜 키워드(today/yesterday/this_week/last_week/recent/tomorrow/2_weeks_ago_to_last_week 등)
        start: 절대 날짜 시작값(YYYY-MM-DD)
        end: 절대 날짜 종료값(YYYY-MM-DD)
    """

    mode: DateFilterMode = Field(default=DateFilterMode.NONE, description="날짜 필터 모드")
    relative: str = Field(default="", description="상대 날짜 키워드")
    start: str = Field(default="", description="절대 날짜 시작값")
    end: str = Field(default="", description="절대 날짜 종료값")


class IntentDecomposition(BaseModel):
    """
    Exaone 최소 구조분해 결과를 담는 표준 모델이다.

    Attributes:
        original_query: 사용자 원문
        steps: 실행 단계 목록
        summary_line_target: 요약 줄 수 목표
        date_filter: 날짜 필터
        missing_slots: 추가 질의가 필요한 누락 슬롯 목록
    """

    original_query: str = Field(default="", description="사용자 원문")
    steps: list[ExecutionStep] = Field(default_factory=list, description="실행 단계 목록")
    summary_line_target: int = Field(default=5, ge=1, le=20, description="요약 줄 수 목표")
    date_filter: DateFilter = Field(default_factory=DateFilter, description="날짜 필터")
    missing_slots: list[str] = Field(default_factory=list, description="누락 슬롯 목록")


def create_default_decomposition(user_message: str) -> IntentDecomposition:
    """
    구조분해 실패 시 사용할 기본 결과를 생성한다.

    Args:
        user_message: 원본 사용자 입력

    Returns:
        최소 정보가 담긴 구조분해 결과
    """
    return IntentDecomposition(
        original_query=user_message.strip(),
        steps=[ExecutionStep.READ_CURRENT_MAIL],
        summary_line_target=5,
        date_filter=DateFilter(mode=DateFilterMode.NONE, relative="", start="", end=""),
        missing_slots=[],
    )


def decomposition_to_context_text(decomposition: IntentDecomposition) -> str:
    """
    구조분해 결과를 deep agent 입력에 주입하기 위한 텍스트로 직렬화한다.

    Args:
        decomposition: 의도 구조분해 결과

    Returns:
        컨텍스트 주입용 문자열
    """
    steps_text = ", ".join(step.value for step in decomposition.steps)
    missing_text = ", ".join(decomposition.missing_slots) if decomposition.missing_slots else "없음"
    return (
        "구조분해 결과:\n"
        f"- original_query: {decomposition.original_query}\n"
        f"- steps: {steps_text}\n"
        f"- summary_line_target: {decomposition.summary_line_target}\n"
        f"- date_filter: {decomposition.date_filter.model_dump()}\n"
        f"- missing_slots: {missing_text}"
    )
