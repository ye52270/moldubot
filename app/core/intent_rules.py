from __future__ import annotations

import re
from calendar import monthrange
from datetime import date, timedelta

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
MAIL_SUMMARY_SKILL_COMMANDS: tuple[str, ...] = ("/메일요약", "/mailsummary")


def is_code_review_query(user_message: str) -> bool:
    """
    사용자 질의가 코드 리뷰/코드 분석 요청인지 판별한다.

    Args:
        user_message: 원본 사용자 입력

    Returns:
        코드 리뷰 요청이면 True
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

    Args:
        user_message: 원본 사용자 입력

    Returns:
        앞뒤 공백/따옴표를 제거한 정제 문자열
    """
    text = str(user_message or "").strip()
    # 테스트 입력에서 자주 섞이는 앞뒤 따옴표를 제거한다.
    return text.strip('"').strip("'").strip()


def is_mail_summary_skill_query(user_message: str) -> bool:
    """
    사용자 질의가 `/메일요약` 스킬 명령인지 판별한다.

    Args:
        user_message: 원본 사용자 입력

    Returns:
        메일요약 스킬 명령이면 True
    """
    normalized = sanitize_user_query(user_message=user_message).lower()
    if not normalized:
        return False
    return any(
        normalized == command or normalized.startswith(f"{command} ")
        for command in MAIL_SUMMARY_SKILL_COMMANDS
    )


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


def _extract_recent_weeks_absolute_range(text: str) -> tuple[str, str, str, str] | None:
    """
    `최근 N주` 표현을 서버 기준 절대 날짜 범위로 추출한다.

    Args:
        text: 사용자 입력

    Returns:
        감지되면 absolute 필드 튜플, 아니면 None
    """
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
    """
    `N월` 또는 `YYYY년 N월` 표현을 절대 월 범위로 추출한다.

    Notes:
        연도가 없으면 현재 연도를 기본으로 사용한다.
        `작년/지난해`, `내년/다음해`가 포함되면 상대 연도를 적용한다.
        메일 조회 문맥이 아닌 일반 문장에서는 과도한 오탐을 막기 위해 동작하지 않는다.

    Args:
        text: 사용자 입력

    Returns:
        감지되면 absolute 필드 튜플, 아니면 None
    """
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
    """
    청구/정산 기간 표현 포함 여부를 반환한다.

    Args:
        text: 사용자 입력

    Returns:
        `N월분/N분기분/상반기분/하반기분` 표현이 포함되면 True
    """
    normalized = str(text or "").strip()
    if not normalized:
        return False
    if re.search(r"\d{1,2}\s*월\s*분", normalized):
        return True
    if re.search(r"\d{1,2}\s*분기\s*분", normalized):
        return True
    if "상반기분" in normalized or "하반기분" in normalized:
        return True
    return False


def _resolve_month_expression_year(text: str, explicit_year: int | None) -> int:
    """
    월 표현의 기준 연도를 결정한다.

    Args:
        text: 사용자 입력
        explicit_year: 명시 연도(있으면 우선)

    Returns:
        해석된 기준 연도
    """
    if explicit_year is not None:
        return explicit_year

    current_year = date.today().year
    if "작년" in text or "지난해" in text:
        return current_year - 1
    if "내년" in text or "다음해" in text:
        return current_year + 1
    return current_year


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
    compact = text.replace(" ", "")
    steps: list[str] = []
    is_mail_search = _is_mail_search_query(text=text)
    has_meeting_room_keyword = (
        "회의실" in text
        or "미팅룸" in text
        or "meetingroom" in compact.lower()
    )
    has_calendar_register_intent = (
        "일정" in text
        and ("등록" in text or "추가" in text or "생성" in text or "잡아" in text)
    )
    has_cause_or_solution_intent = any(
        token in text
        for token in ("왜", "원인", "이유", "문제", "해결", "해결 방법", "대응", "방안")
    )

    if ("메일" in text or "현재메일" in compact) and not is_mail_search:
        steps.append("read_current_mail")
    if is_mail_search:
        steps.append("search_mails")
    if "요약" in text or "정리" in text or "보고서" in text:
        steps.append("summarize_mail")
    if (
        "중요" in text
        or "핵심" in text
        or "주요" in text
        or "키워드" in text
        or "할일" in text
        or "액션아이템" in text
    ):
        steps.append("extract_key_facts")
    if "수신자" in text or "받는" in text:
        steps.append("extract_recipients")
    if "체크리스트" in text or "진행안" in text or "템플릿" in text:
        steps.append("extract_key_facts")
    if has_cause_or_solution_intent:
        steps.append("summarize_mail")
        steps.append("extract_key_facts")
    if "회의 일정" in text:
        steps.append("search_meeting_schedule")
    if has_calendar_register_intent and not has_meeting_room_keyword:
        steps.append("book_calendar_event")
    if has_meeting_room_keyword and ("예약" in text or "잡아" in text or "등록" in text):
        steps.append("book_meeting_room")
    if "예약" in text and not has_calendar_register_intent:
        steps.append("book_meeting_room")

    # 중복을 제거하면서 순서를 유지한다.
    deduped: list[str] = []
    for step in steps:
        if step not in deduped:
            deduped.append(step)
    return deduped


def _is_mail_search_query(text: str) -> bool:
    """
    사용자 입력이 조건 기반 메일 검색 질의인지 판별한다.

    Args:
        text: 원본 사용자 입력

    Returns:
        조건 기반 검색 질의면 True
    """
    has_mail = "메일" in text
    if not has_mail:
        return False
    if "현재메일" in text.replace(" ", ""):
        return False
    if _is_deictic_current_mail_reference(text=text):
        return False
    if "메일에서" in text:
        return True
    if "본문에" in text and ("포함" in text or "들어" in text):
        return True
    search_tokens = ("조회", "관련", "최근", "지난", "찾아", "검색", "보여", "정리")
    if any(token in text for token in search_tokens):
        return True
    return bool(re.search(r"메일(?:을|를)?\s*.*(보고서\s*형식|보고용)", text))


def _is_deictic_current_mail_reference(text: str) -> bool:
    """
    질의가 현재 선택 메일을 지칭하는 지시어 중심 문맥인지 판별한다.

    Args:
        text: 원본 사용자 입력

    Returns:
        지시어 기반 현재메일 문맥이면 True
    """
    compact = str(text or "").replace(" ", "").lower()
    deictic_tokens = (
        "이메일",
        "이메일에서",
        "이메일의",
        "이메일기반",
        "해당메일",
        "이메일본문",
        "이견적",
        "해당견적",
        "이프로젝트",
        "해당프로젝트",
    )
    return any(token in compact for token in deictic_tokens)


def is_mail_search_query(text: str) -> bool:
    """
    사용자 입력이 조건 기반 메일 검색 질의인지 공개 API로 판별한다.

    Args:
        text: 사용자 입력 문자열

    Returns:
        조건 기반 메일 검색 질의면 True
    """
    normalized = str(text or "").strip()
    if not normalized:
        return False
    return _is_mail_search_query(text=normalized)


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
    has_iso_or_dot_date = re.search(r"\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}\.?", text) is not None
    has_date_key = re.search(r"[\"']?(date|날짜)[\"']?\s*[:=]\s*[\"']?\S+", text, flags=re.IGNORECASE) is not None
    if "오늘" in text or "어제" in text or "내일" in text or "주" in text or has_iso_or_dot_date or has_korean_absolute or has_date_key:
        missing.discard("date")
    has_hhmm_time = re.search(r"(?:^|[\s=:>])(?:[01]?\d|2[0-3]):[0-5]\d", text) is not None
    has_start_key = re.search(r"[\"']?(start_time|시작)[\"']?\s*[:=]\s*[\"']?\S+", text, flags=re.IGNORECASE) is not None
    if re.search(r"(오전|오후)?\s*\d{1,2}\s*시", text) or has_hhmm_time or has_start_key:
        missing.discard("start_time")
    has_end_key = re.search(r"[\"']?(end_time|종료)[\"']?\s*[:=]\s*[\"']?\S+", text, flags=re.IGNORECASE) is not None
    has_time_range = re.search(r"(?:[01]?\d|2[0-3]):[0-5]\d\s*[~\-]\s*(?:[01]?\d|2[0-3]):[0-5]\d", text) is not None
    if has_end_key or has_time_range:
        missing.discard("end_time")
    has_attendee_key = re.search(
        r"[\"']?(attendee_count|참석\s*인원|인원)[\"']?\s*[:=]\s*[\"']?\d+",
        text,
        flags=re.IGNORECASE,
    ) is not None
    if re.search(r"\d+\s*명", text) or has_attendee_key:
        missing.discard("attendee_count")
    return sorted(missing)
