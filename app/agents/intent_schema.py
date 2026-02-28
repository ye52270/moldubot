from __future__ import annotations

from enum import Enum
import re

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.intent_rules import ALLOWED_MISSING_SLOTS, is_allowed_relative_filter


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

    @model_validator(mode="after")
    def validate_date_filter_consistency(self) -> "DateFilter":
        """
        mode에 맞는 날짜 필터 필드 정합성을 검증한다.

        Returns:
            검증을 통과한 DateFilter 인스턴스

        Raises:
            ValueError: mode와 필드 조합이 유효하지 않은 경우
        """
        if self.mode == DateFilterMode.NONE:
            self.relative = ""
            self.start = ""
            self.end = ""
            return self

        if self.mode == DateFilterMode.RELATIVE:
            self.start = ""
            self.end = ""
            if not is_allowed_relative_filter(self.relative):
                raise ValueError("date_filter.relative 값이 허용되지 않습니다.")
            return self

        # absolute 모드에서는 상대 토큰을 금지하고 날짜 형식을 강제한다.
        self.relative = ""
        if self.start and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", self.start):
            raise ValueError("date_filter.start는 YYYY-MM-DD 형식이어야 합니다.")
        if self.end and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", self.end):
            raise ValueError("date_filter.end는 YYYY-MM-DD 형식이어야 합니다.")
        return self


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

    @field_validator("original_query", mode="before")
    @classmethod
    def normalize_original_query(cls, value: object) -> str:
        """
        원문 필드를 문자열로 정규화하고 앞뒤 공백을 제거한다.

        Args:
            value: 입력 원문 값

        Returns:
            정규화된 원문 문자열
        """
        return str(value or "").strip()

    @field_validator("steps")
    @classmethod
    def dedupe_steps(cls, value: list[ExecutionStep]) -> list[ExecutionStep]:
        """
        steps 목록의 중복을 제거하면서 원래 순서를 유지한다.

        Args:
            value: 실행 단계 목록

        Returns:
            중복 제거된 실행 단계 목록
        """
        deduped: list[ExecutionStep] = []
        for step in value:
            if step not in deduped:
                deduped.append(step)
        return deduped

    @field_validator("missing_slots")
    @classmethod
    def normalize_missing_slots(cls, value: list[str]) -> list[str]:
        """
        누락 슬롯 목록을 허용값 기준으로 정규화한다.

        Args:
            value: 누락 슬롯 목록

        Returns:
            허용값만 남긴 정렬된 슬롯 목록
        """
        normalized: list[str] = []
        for slot in value:
            slot_name = str(slot or "").strip()
            if slot_name in ALLOWED_MISSING_SLOTS and slot_name not in normalized:
                normalized.append(slot_name)
        return sorted(normalized)

    @model_validator(mode="after")
    def align_missing_slots_with_steps(self) -> "IntentDecomposition":
        """
        예약 step 유무에 따라 missing_slots를 일관되게 보정한다.

        Returns:
            보정된 IntentDecomposition 인스턴스
        """
        has_booking_step = ExecutionStep.BOOK_MEETING_ROOM in self.steps
        if not has_booking_step:
            self.missing_slots = []
        return self


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
