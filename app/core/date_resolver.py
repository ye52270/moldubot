from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

ISO_DATE_PATTERN = r"\d{4}-\d{1,2}-\d{1,2}"
SEOUL_TIMEZONE = ZoneInfo("Asia/Seoul")
WEEKDAY_TOKEN_TO_INDEX = {
    "월": 0,
    "월요일": 0,
    "화": 1,
    "화요일": 1,
    "수": 2,
    "수요일": 2,
    "목": 3,
    "목요일": 3,
    "금": 4,
    "금요일": 4,
    "토": 5,
    "토요일": 5,
    "일": 6,
    "일요일": 6,
}


def resolve_booking_date_token(raw_date: str, reference_date: date | None = None) -> str:
    """
    예약 날짜 입력값(상대/절대)을 서버 기준 절대 날짜(YYYY-MM-DD)로 정규화한다.

    Args:
        raw_date: 모델/사용자 입력 날짜 문자열
        reference_date: 기준 날짜(테스트 용도), 기본값은 서버 오늘 날짜

    Returns:
        정규화된 절대 날짜 문자열. 규칙 미일치 시 원본 trim 문자열 반환
    """
    text = str(raw_date or "").strip()
    if not text:
        return text

    base_date = reference_date or datetime.now(tz=SEOUL_TIMEZONE).date()
    iso_candidate = _normalize_iso_date(text=text)
    if iso_candidate:
        return iso_candidate

    lowered = text.lower()
    if text in {"오늘"} or lowered == "today":
        return base_date.strftime("%Y-%m-%d")
    if text in {"내일"} or lowered == "tomorrow":
        return (base_date + timedelta(days=1)).strftime("%Y-%m-%d")
    if text in {"모레"}:
        return (base_date + timedelta(days=2)).strftime("%Y-%m-%d")

    if _contains_this_week_token(text=text, lowered=lowered):
        return _resolve_weekday_with_offset(text=text, base_date=base_date, week_offset=0)
    if _contains_next_week_token(text=text, lowered=lowered):
        return _resolve_weekday_with_offset(text=text, base_date=base_date, week_offset=1)
    if _contains_last_week_token(text=text, lowered=lowered):
        return _resolve_weekday_with_offset(text=text, base_date=base_date, week_offset=-1)

    return text


def _resolve_weekday_with_offset(text: str, base_date: date, week_offset: int) -> str:
    """
    기준 주차 오프셋과 요일 토큰으로 날짜를 계산한다.

    Args:
        text: 날짜 원문
        base_date: 기준일
        week_offset: 주차 오프셋(이번주=0, 다음주=1, 지난주=-1)

    Returns:
        계산된 절대 날짜(YYYY-MM-DD)
    """
    weekday_index = _extract_weekday_index(text=text)
    if weekday_index is None:
        return (base_date + timedelta(days=week_offset * 7)).strftime("%Y-%m-%d")
    week_start = base_date - timedelta(days=base_date.weekday()) + timedelta(days=week_offset * 7)
    return (week_start + timedelta(days=weekday_index)).strftime("%Y-%m-%d")


def _contains_this_week_token(text: str, lowered: str) -> bool:
    """
    이번 주 표현 포함 여부를 반환한다.

    Args:
        text: 원문
        lowered: 소문자 영문 원문

    Returns:
        이번 주 토큰 포함 여부
    """
    return "이번주" in text or "이번 주" in text or "this week" in lowered


def _contains_next_week_token(text: str, lowered: str) -> bool:
    """
    다음 주 표현 포함 여부를 반환한다.

    Args:
        text: 원문
        lowered: 소문자 영문 원문

    Returns:
        다음 주 토큰 포함 여부
    """
    return "다음주" in text or "다음 주" in text or "next week" in lowered


def _contains_last_week_token(text: str, lowered: str) -> bool:
    """
    지난 주 표현 포함 여부를 반환한다.

    Args:
        text: 원문
        lowered: 소문자 영문 원문

    Returns:
        지난 주 토큰 포함 여부
    """
    return "지난주" in text or "지난 주" in text or "last week" in lowered


def _normalize_iso_date(text: str) -> str | None:
    """
    ISO 날짜 문자열을 YYYY-MM-DD 형태로 보정한다.

    Args:
        text: 입력 문자열

    Returns:
        보정된 날짜 문자열 또는 None
    """
    if re.fullmatch(ISO_DATE_PATTERN, text) is None:
        return None
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None
    return parsed.strftime("%Y-%m-%d")


def _extract_weekday_index(text: str) -> int | None:
    """
    문자열에서 요일 토큰을 찾아 weekday 인덱스를 반환한다.

    Args:
        text: 입력 문자열

    Returns:
        월=0 ... 일=6, 감지 실패 시 None
    """
    for token, weekday_index in WEEKDAY_TOKEN_TO_INDEX.items():
        if token in text:
            return weekday_index
    return None
