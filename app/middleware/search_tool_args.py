from __future__ import annotations

from datetime import date, timedelta
import re
from typing import Any

from app.core.intent_rules import extract_date_filter_fields
from app.services.mail_search_utils import extract_person_anchor_tokens
from app.services.person_identity_parser import normalize_person_identity

SEARCH_TOOL_NAMES = {"search_mails", "search_meeting_schedule"}
ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PERSON_FALLBACK_PATTERN = re.compile(r"([가-힣]{2,4})\s*메일")
PERSON_FALLBACK_STOPWORDS = {
    "현재",
    "관련",
    "요약",
    "정리",
    "조회",
    "검색",
    "최근",
    "지난",
    "전체",
    "메일",
}


def normalize_search_tool_args(tool_name: str, tool_args: dict[str, Any], user_message: str) -> dict[str, Any]:
    """
    검색 도구 호출 인자를 사용자 원문 슬롯 기준으로 정규화한다.

    Args:
        tool_name: 호출 대상 도구명
        tool_args: 모델이 생성한 도구 인자
        user_message: 사용자 원문 질의

    Returns:
        정규화된 도구 인자 사전
    """
    if str(tool_name or "").strip() not in SEARCH_TOOL_NAMES:
        return dict(tool_args) if isinstance(tool_args, dict) else {}

    base_args = dict(tool_args) if isinstance(tool_args, dict) else {}
    normalized_query = str(base_args.get("query") or "").strip() or str(user_message or "").strip()
    if normalized_query:
        base_args["query"] = normalized_query

    person = _extract_person_slot(user_message=user_message)
    if person and not str(base_args.get("person") or "").strip():
        base_args["person"] = person

    start_date, end_date, has_date_intent = _extract_date_slots(user_message=user_message)
    if has_date_intent and start_date and end_date:
        base_args["start_date"] = start_date
        base_args["end_date"] = end_date
    elif not has_date_intent:
        base_args["start_date"] = ""
        base_args["end_date"] = ""
    else:
        start = str(base_args.get("start_date") or "").strip()
        end = str(base_args.get("end_date") or "").strip()
        if start and not _is_iso_date(start):
            base_args["start_date"] = ""
        if end and not _is_iso_date(end):
            base_args["end_date"] = ""

    return base_args


def _extract_person_slot(user_message: str) -> str:
    """
    사용자 질의에서 인물 슬롯을 추출한다.

    Args:
        user_message: 사용자 원문 질의

    Returns:
        정규화된 인물 문자열
    """
    anchors = extract_person_anchor_tokens(query=str(user_message or ""))
    if anchors:
        normalized = normalize_person_identity(token=anchors[0])
        return str(normalized or "").strip()
    fallback = _extract_person_slot_fallback(user_message=user_message)
    if not fallback:
        return ""
    normalized = normalize_person_identity(token=fallback)
    return str(normalized or "").strip()


def _extract_person_slot_fallback(user_message: str) -> str:
    """
    앵커 패턴에 걸리지 않는 자연어 질의에서 인물 슬롯을 보조 추출한다.

    Args:
        user_message: 사용자 원문 질의

    Returns:
        인물 후보 문자열
    """
    text = str(user_message or "").strip()
    if not text:
        return ""
    match = PERSON_FALLBACK_PATTERN.search(text)
    if not match:
        return ""
    candidate = str(match.group(1) or "").strip()
    if candidate in PERSON_FALLBACK_STOPWORDS:
        return ""
    return candidate


def _extract_date_slots(user_message: str) -> tuple[str, str, bool]:
    """
    사용자 질의에서 검색용 날짜 슬롯을 추출한다.

    Args:
        user_message: 사용자 원문 질의

    Returns:
        (start_date, end_date, has_date_intent) 튜플
    """
    mode, relative, start, end = extract_date_filter_fields(user_message=str(user_message or ""))
    if mode == "none":
        return ("", "", False)
    if mode != "absolute":
        resolved = _resolve_relative_date_slots(relative_token=relative)
        if resolved is None:
            return ("", "", True)
        return (*resolved, True)
    normalized_start = str(start or "").strip()
    normalized_end = str(end or "").strip()
    if not (_is_iso_date(normalized_start) and _is_iso_date(normalized_end)):
        return ("", "", True)
    return (normalized_start, normalized_end, True)


def _resolve_relative_date_slots(relative_token: str) -> tuple[str, str] | None:
    """
    relative 날짜 토큰을 검색용 절대 날짜 범위로 변환한다.

    Args:
        relative_token: 상대 날짜 토큰

    Returns:
        절대 날짜 범위. 해석 실패 시 None
    """
    token = str(relative_token or "").strip()
    if not token:
        return None
    today = date.today()
    if token == "today":
        return (_to_ymd(today), _to_ymd(today))
    if token == "yesterday":
        yesterday = today - timedelta(days=1)
        return (_to_ymd(yesterday), _to_ymd(yesterday))
    if token == "tomorrow":
        tomorrow = today + timedelta(days=1)
        return (_to_ymd(tomorrow), _to_ymd(tomorrow))
    if token == "this_week":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        return (_to_ymd(start), _to_ymd(end))
    if token == "last_week":
        this_week_start = today - timedelta(days=today.weekday())
        start = this_week_start - timedelta(days=7)
        end = this_week_start - timedelta(days=1)
        return (_to_ymd(start), _to_ymd(end))
    if token == "recent":
        start = today - timedelta(days=14)
        return (_to_ymd(start), _to_ymd(today))
    range_match = re.fullmatch(r"(\d+)_weeks_ago_to_last_week", token)
    if range_match:
        weeks = int(range_match.group(1))
        this_week_start = today - timedelta(days=today.weekday())
        last_week_end = this_week_start - timedelta(days=1)
        start = this_week_start - timedelta(days=(weeks + 1) * 7)
        return (_to_ymd(start), _to_ymd(last_week_end))
    return None


def _to_ymd(target: date) -> str:
    """
    date 객체를 YYYY-MM-DD로 변환한다.

    Args:
        target: 변환 대상 날짜

    Returns:
        YYYY-MM-DD 문자열
    """
    return target.strftime("%Y-%m-%d")


def _is_iso_date(value: str) -> bool:
    """
    문자열이 YYYY-MM-DD 형식인지 검사한다.

    Args:
        value: 검사 대상 문자열

    Returns:
        ISO 날짜 형식이면 True
    """
    return ISO_DATE_PATTERN.fullmatch(str(value or "").strip()) is not None
