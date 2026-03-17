from __future__ import annotations

import re
from calendar import monthrange
from datetime import date, timedelta


def extract_date_filter_fields(user_message: str) -> tuple[str, str, str, str]:
    """
    사용자 문장에서 날짜 필터 필드(mode/relative/start/end)를 추출한다.
    """
    text = user_message.strip()
    absolute_iso = _extract_iso_absolute_range(text=text)
    if absolute_iso is not None:
        return absolute_iso

    absolute_korean = _extract_korean_absolute_range(text=text)
    if absolute_korean is not None:
        return absolute_korean

    month_only_range = _extract_month_only_range(text=text)
    if month_only_range is not None:
        return month_only_range

    recent_weeks_range = _extract_recent_weeks_absolute_range(text=text)
    if recent_weeks_range is not None:
        return recent_weeks_range

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


def is_allowed_relative_filter(relative_value: str, allowed_filters: tuple[str, ...]) -> bool:
    """
    상대 날짜 토큰이 허용 범위인지 판별한다.
    """
    token = str(relative_value or "").strip()
    if not token:
        return False
    if token in allowed_filters:
        return True
    return re.fullmatch(r"\d+_weeks_ago_to_last_week", token) is not None


def _extract_iso_absolute_range(text: str) -> tuple[str, str, str, str] | None:
    absolute_match = re.search(r"(\d{4}-\d{1,2}-\d{1,2}).*?(\d{4}-\d{1,2}-\d{1,2})", text)
    if not absolute_match:
        return None
    return ("absolute", "", absolute_match.group(1), absolute_match.group(2))


def _extract_korean_absolute_range(text: str) -> tuple[str, str, str, str] | None:
    month_day_range = re.search(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일.*?(\d{1,2})\s*월\s*(\d{1,2})\s*일", text)
    if not month_day_range:
        return None
    current_year = date.today().year
    start = _format_ymd(current_year, int(month_day_range.group(1)), int(month_day_range.group(2)))
    end = _format_ymd(current_year, int(month_day_range.group(3)), int(month_day_range.group(4)))
    return ("absolute", "", start, end)


def _extract_relative_range(text: str) -> tuple[str, str, str, str] | None:
    range_match = re.search(r"(\d{1,2})\s*주\s*전부터\s*지난\s*주까지", text)
    if not range_match:
        return None
    weeks_ago = int(range_match.group(1))
    return ("relative", f"{weeks_ago}_weeks_ago_to_last_week", "", "")


def _extract_recent_weeks_absolute_range(text: str) -> tuple[str, str, str, str] | None:
    if "메일" not in text:
        return None
    match = re.search(r"최근\s*(\d{1,2})\s*주", text)
    if not match:
        return None
    weeks = int(match.group(1))
    if weeks < 1:
        return None
    today = date.today()
    start = today - timedelta(days=weeks * 7)
    return ("absolute", "", start.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))


def _extract_month_only_range(text: str) -> tuple[str, str, str, str] | None:
    if "메일" not in text:
        return None
    if _contains_billing_period_terms(text=text):
        return None
    if re.search(r"\d{1,2}\s*월\s*\d{1,2}\s*일", text):
        return None

    month_match = re.search(r"(?:(\d{4})\s*년\s*)?(\d{1,2})\s*월(?:달)?", text)
    if not month_match:
        return None

    explicit_year = int(month_match.group(1)) if month_match.group(1) else None
    month = int(month_match.group(2))
    if month < 1 or month > 12:
        return None

    year = _resolve_month_expression_year(text=text, explicit_year=explicit_year)
    last_day = monthrange(year, month)[1]
    start = _format_ymd(year, month, 1)
    end = _format_ymd(year, month, last_day)
    return ("absolute", "", start, end)


def _contains_billing_period_terms(text: str) -> bool:
    normalized = str(text or "").strip()
    if not normalized:
        return False
    if re.search(r"\d{1,2}\s*월\s*분", normalized):
        return True
    if re.search(r"\d{1,2}\s*분기\s*분", normalized):
        return True
    return "상반기분" in normalized or "하반기분" in normalized


def _resolve_month_expression_year(text: str, explicit_year: int | None) -> int:
    if explicit_year is not None:
        return explicit_year
    current_year = date.today().year
    if "작년" in text or "지난해" in text:
        return current_year - 1
    if "내년" in text or "다음해" in text:
        return current_year + 1
    return current_year


def _format_ymd(year: int, month: int, day: int) -> str:
    return f"{year:04d}-{month:02d}-{day:02d}"
