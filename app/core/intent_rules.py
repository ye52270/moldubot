from __future__ import annotations

import re

from app.core import intent_rules_date as _intent_rules_date
from app.core import intent_rules_steps as _intent_rules_steps

DEFAULT_SUMMARY_LINE_TARGET = 5
MAX_SUMMARY_LINE_TARGET = 20
REQUIRED_BOOKING_SLOTS = ("date", "start_time", "end_time", "attendee_count")
ALLOWED_RELATIVE_DATE_FILTERS = ("today", "yesterday", "this_week", "last_week", "recent", "tomorrow")
ALLOWED_MISSING_SLOTS = REQUIRED_BOOKING_SLOTS
MAIL_SUMMARY_SKILL_COMMANDS: tuple[str, ...] = ("/메일요약", "/mailsummary")
CODE_REVIEW_SKILL_COMMANDS: tuple[str, ...] = ("/코드분석", "/codeanalysis")
EXPLICIT_SKILL_COMMANDS: tuple[str, ...] = MAIL_SUMMARY_SKILL_COMMANDS + CODE_REVIEW_SKILL_COMMANDS
CHAT_MODE_SKILL = "skill"
CHAT_MODE_FREEFORM = "freeform"


def is_code_review_query(user_message: str) -> bool:
    """
    사용자 질의가 코드 리뷰/코드 분석 요청인지 판별한다.
    """
    normalized = sanitize_user_query(user_message=user_message).replace(" ", "")
    if not normalized:
        return False
    has_code = "코드" in normalized
    has_review = "리뷰" in normalized
    has_analysis = "분석" in normalized
    has_snippet = "코드스니펫" in normalized
    return (has_code and (has_review or has_analysis)) or has_snippet


def sanitize_user_query(user_message: str) -> str:
    """
    사용자 입력 문자열에서 구조분해에 불필요한 노이즈를 제거한다.
    """
    text = str(user_message or "").strip()
    return text.strip('"').strip("'").strip()


def is_mail_summary_skill_query(user_message: str) -> bool:
    """
    사용자 질의가 `/메일요약` 스킬 명령인지 판별한다.
    """
    normalized = sanitize_user_query(user_message=user_message).lower()
    if not normalized:
        return False
    return any(normalized == command or normalized.startswith(f"{command} ") for command in MAIL_SUMMARY_SKILL_COMMANDS)


def is_explicit_skill_query(user_message: str) -> bool:
    """
    사용자 질의가 명시 스킬 슬래시 명령인지 판별한다.
    """
    normalized = sanitize_user_query(user_message=user_message).lower()
    if not normalized:
        return False
    return any(normalized == command or normalized.startswith(f"{command} ") for command in EXPLICIT_SKILL_COMMANDS)


def resolve_chat_mode(user_message: str) -> str:
    """
    사용자 입력을 freeform/skill 2모드로 분류한다.
    """
    if is_explicit_skill_query(user_message=user_message):
        return CHAT_MODE_SKILL
    return CHAT_MODE_FREEFORM


def extract_summary_line_target(user_message: str) -> int:
    """
    사용자 문장에서 목표 요약 줄 수를 추정한다.
    """
    match = re.search(r"(\d{1,2})\s*(줄|개|가지)", user_message)
    if not match:
        return DEFAULT_SUMMARY_LINE_TARGET
    value = int(match.group(1))
    if value < 1:
        return DEFAULT_SUMMARY_LINE_TARGET
    if value > MAX_SUMMARY_LINE_TARGET:
        return MAX_SUMMARY_LINE_TARGET
    return value


def is_allowed_relative_filter(relative_value: str) -> bool:
    """
    상대 날짜 토큰이 허용 범위인지 판별한다.
    """
    return _intent_rules_date.is_allowed_relative_filter(
        relative_value=relative_value,
        allowed_filters=ALLOWED_RELATIVE_DATE_FILTERS,
    )


def infer_steps_from_query(user_message: str) -> list[str]:
    """
    사용자 입력에서 실행 단계(step) 후보를 규칙 기반으로 추출한다.
    """
    text = str(user_message or "").strip()
    if is_mail_summary_skill_query(user_message=text):
        return ["read_current_mail", "summarize_mail"]
    return _intent_rules_steps.infer_steps_from_query(user_message=text)


def build_missing_slots(steps: list[str], user_message: str) -> list[str]:
    """
    회의 예약 단계가 있을 때 필수 슬롯 누락 목록을 계산한다.
    """
    return _intent_rules_steps.build_missing_slots(
        steps=steps,
        user_message=user_message,
        required_slots=REQUIRED_BOOKING_SLOTS,
    )


extract_date_filter_fields = _intent_rules_date.extract_date_filter_fields
is_current_mail_reference = _intent_rules_steps.is_current_mail_reference
is_mail_search_query = _intent_rules_steps.is_mail_search_query
