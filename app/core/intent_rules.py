from __future__ import annotations

import re
from datetime import date

DEFAULT_SUMMARY_LINE_TARGET = 5
MAX_SUMMARY_LINE_TARGET = 20
REQUIRED_BOOKING_SLOTS = ("date", "start_time", "end_time", "attendee_count")
ALLOWED_RELATIVE_DATE_FILTERS = (
    "today",
    "yesterday",
    "this_week",
    "last_week",
    "recent",
    "tomorrow",
)
ALLOWED_MISSING_SLOTS = REQUIRED_BOOKING_SLOTS


def sanitize_user_query(user_message: str) -> str:
    """
    사용자 입력 문자열에서 구조분해에 불필요한 노이즈를 제거한다.

    Args:
        user_message: 원본 사용자 입력

    Returns:
        앞뒤 공백/따옴표를 제거한 정제 문자열
    """
    text = str(user_message or "").strip()
    # 테스트 입력에서 자주 섞이는 앞뒤 따옴표를 제거한다.
    return text.strip('"').strip("'").strip()


def extract_summary_line_target(user_message: str) -> int:
    """
    사용자 문장에서 목표 요약 줄 수를 추정한다.

    Args:
        user_message: 원본 사용자 입력

    Returns:
        추정된 줄 수. 탐지 실패 시 기본값 5
    """
    match = re.search(r"(\d{1,2})\s*줄", user_message)
    if not match:
        return DEFAULT_SUMMARY_LINE_TARGET

    value = int(match.group(1))
    if value < 1:
        return DEFAULT_SUMMARY_LINE_TARGET
    if value > MAX_SUMMARY_LINE_TARGET:
        return MAX_SUMMARY_LINE_TARGET
    return value


def extract_date_filter_fields(user_message: str) -> tuple[str, str, str, str]:
    """
    사용자 문장에서 날짜 필터 필드(mode/relative/start/end)를 추출한다.

    Args:
        user_message: 원본 사용자 입력

    Returns:
        (mode, relative, start, end) 튜플
    """
    text = user_message.strip()
    absolute_iso = _extract_iso_absolute_range(text=text)
    if absolute_iso is not None:
        return absolute_iso

    absolute_korean = _extract_korean_absolute_range(text=text)
    if absolute_korean is not None:
        return absolute_korean

    relative_range = _extract_relative_range(text=text)
    if relative_range is not None:
        return relative_range

    relative_map = (
        ("오늘", "today"),
        ("어제", "yesterday"),
        ("이번 주", "this_week"),
        ("이번주", "this_week"),
        ("지난주", "last_week"),
        ("최근", "recent"),
        ("내일", "tomorrow"),
    )
    for needle, value in relative_map:
        if needle in text:
            return ("relative", value, "", "")

    return ("none", "", "", "")


def _extract_iso_absolute_range(text: str) -> tuple[str, str, str, str] | None:
    """
    YYYY-MM-DD 형식의 절대 날짜 범위를 추출한다.

    Args:
        text: 사용자 입력

    Returns:
        감지되면 absolute 필드 튜플, 아니면 None
    """
    absolute_match = re.search(r"(\d{4}-\d{1,2}-\d{1,2}).*?(\d{4}-\d{1,2}-\d{1,2})", text)
    if not absolute_match:
        return None
    return ("absolute", "", absolute_match.group(1), absolute_match.group(2))


def _extract_korean_absolute_range(text: str) -> tuple[str, str, str, str] | None:
    """
    `N월 N일부터 N월 N일까지` 형식의 절대 날짜 범위를 추출한다.

    Args:
        text: 사용자 입력

    Returns:
        감지되면 absolute 필드 튜플, 아니면 None
    """
    month_day_range = re.search(
        r"(\d{1,2})\s*월\s*(\d{1,2})\s*일.*?(\d{1,2})\s*월\s*(\d{1,2})\s*일",
        text,
    )
    if not month_day_range:
        return None

    current_year = date.today().year
    start = _format_ymd(current_year, int(month_day_range.group(1)), int(month_day_range.group(2)))
    end = _format_ymd(current_year, int(month_day_range.group(3)), int(month_day_range.group(4)))
    return ("absolute", "", start, end)


def _extract_relative_range(text: str) -> tuple[str, str, str, str] | None:
    """
    상대 날짜 범위 표현을 단일 relative 토큰으로 정규화한다.

    Args:
        text: 사용자 입력

    Returns:
        감지되면 relative 필드 튜플, 아니면 None
    """
    range_match = re.search(r"(\d{1,2})\s*주\s*전부터\s*지난\s*주까지", text)
    if range_match:
        weeks_ago = int(range_match.group(1))
        return ("relative", f"{weeks_ago}_weeks_ago_to_last_week", "", "")
    return None


def is_allowed_relative_filter(relative_value: str) -> bool:
    """
    상대 날짜 토큰이 허용 범위인지 판별한다.

    Args:
        relative_value: 검사할 상대 날짜 토큰

    Returns:
        허용 토큰이거나 `N_weeks_ago_to_last_week` 패턴이면 True
    """
    token = str(relative_value or "").strip()
    if not token:
        return False
    if token in ALLOWED_RELATIVE_DATE_FILTERS:
        return True
    return re.fullmatch(r"\d+_weeks_ago_to_last_week", token) is not None


def _format_ymd(year: int, month: int, day: int) -> str:
    """
    연/월/일 값을 YYYY-MM-DD 문자열로 변환한다.

    Args:
        year: 연도
        month: 월
        day: 일

    Returns:
        YYYY-MM-DD 포맷 문자열
    """
    return f"{year:04d}-{month:02d}-{day:02d}"


def infer_steps_from_query(user_message: str) -> list[str]:
    """
    사용자 입력에서 실행 단계(step) 후보를 규칙 기반으로 추출한다.

    Args:
        user_message: 원본 사용자 입력

    Returns:
        step 문자열 목록
    """
    text = user_message.strip()
    steps: list[str] = []

    if "메일" in text:
        steps.append("read_current_mail")
    if "요약" in text or "정리" in text or "보고서" in text:
        steps.append("summarize_mail")
    if "중요" in text or "핵심" in text or "할일" in text or "액션아이템" in text:
        steps.append("extract_key_facts")
    if "수신자" in text or "받는" in text:
        steps.append("extract_recipients")
    if "회의 일정" in text or ("회의" in text and "일정" in text):
        steps.append("search_meeting_schedule")
    if "예약" in text or "잡아" in text:
        steps.append("book_meeting_room")

    # 중복을 제거하면서 순서를 유지한다.
    deduped: list[str] = []
    for step in steps:
        if step not in deduped:
            deduped.append(step)
    return deduped


def build_missing_slots(steps: list[str], user_message: str) -> list[str]:
    """
    회의 예약 단계가 있을 때 필수 슬롯 누락 목록을 계산한다.

    Args:
        steps: step 문자열 목록
        user_message: 원본 사용자 입력

    Returns:
        누락 슬롯 목록
    """
    if "book_meeting_room" not in steps:
        return []

    text = user_message.strip()
    missing = set(REQUIRED_BOOKING_SLOTS)

    has_korean_absolute = re.search(r"\d{1,2}\s*월\s*\d{1,2}\s*일", text) is not None
    if "오늘" in text or "어제" in text or "내일" in text or "주" in text or re.search(r"\d{4}-\d{1,2}-\d{1,2}", text) or has_korean_absolute:
        missing.discard("date")
    if re.search(r"(오전|오후)?\s*\d{1,2}\s*시", text):
        missing.discard("start_time")
    if re.search(r"\d+\s*명", text):
        missing.discard("attendee_count")

    # 종료 시간은 명시되지 않는 경우가 많아 누락으로 유지한다.
    return sorted(missing)
