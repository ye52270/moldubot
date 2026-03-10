from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.services.mail_service import MailRecord
from app.services.mail_text_utils import extract_recipients_from_body

SEOUL_TZ = ZoneInfo("Asia/Seoul")
MAX_ATTENDEE_COUNT = 8
DEFAULT_ATTENDEE_COUNT = 4
TIME_CANDIDATE_SLOTS = (("10:00", "11:00"), ("14:00", "15:00"), ("16:00", "17:00"))
BUSINESS_START_MINUTE = 9 * 60
BUSINESS_END_MINUTE = 18 * 60


def suggest_meeting_plan_from_mail(mail: MailRecord, rooms: list[dict[str, Any]]) -> dict[str, Any]:
    """
    현재 메일의 DB 요약(summary) 기반으로 회의 제안(안건/참석자/시간/회의실)을 생성한다.

    Args:
        mail: 선택 메일 레코드
        rooms: 회의실 마스터 목록

    Returns:
        제안 payload 사전
    """
    summary_text = _normalize_summary_text(value=str(getattr(mail, "summary_text", "") or ""))
    issues = [summary_text] if summary_text else []
    attendees = _extract_attendees(body_text=mail.body_text)
    attendee_count = _compute_attendee_count(attendees=attendees)
    meeting_subject = _build_meeting_subject(subject=mail.subject, issues=issues)
    time_candidates = _build_time_candidates(body_text=mail.body_text)
    room_candidates = _build_room_candidates(rooms=rooms, limit=3)
    return {
        "meeting_subject": meeting_subject,
        "summary_text": summary_text,
        "major_issues": issues,
        "attendees": attendees,
        "attendee_count": attendee_count,
        "time_candidates": time_candidates,
        "room_candidates": room_candidates,
    }


def _normalize_summary_text(value: str) -> str:
    """
    DB summary 원문을 표시용 텍스트로 정규화한다.

    Args:
        value: summary 원문

    Returns:
        앞뒤 공백 정리된 summary 텍스트
    """
    return str(value or "").strip()


def _extract_attendees(body_text: str) -> list[str]:
    """
    본문 헤더(`To:`)에서 참석자 후보를 추출한다.

    Args:
        body_text: 메일 본문 텍스트

    Returns:
        참석자 후보 목록
    """
    recipients = extract_recipients_from_body(text=body_text)
    deduped: list[str] = []
    for item in recipients:
        normalized = str(item or "").strip()
        if not normalized or normalized in deduped:
            continue
        deduped.append(normalized)
    return deduped[:MAX_ATTENDEE_COUNT]


def _compute_attendee_count(attendees: list[str]) -> int:
    """
    참석자 후보 목록 기준 제안 참석 인원을 계산한다.

    Args:
        attendees: 참석자 후보 목록

    Returns:
        제안 참석 인원
    """
    if not attendees:
        return DEFAULT_ATTENDEE_COUNT
    return max(2, min(MAX_ATTENDEE_COUNT, len(attendees)))


def _build_meeting_subject(subject: str, issues: list[str]) -> str:
    """
    메일 제목/핵심 이슈 기반 회의 안건 요약 문자열을 생성한다.

    Args:
        subject: 메일 제목
        issues: 핵심 이슈 목록

    Returns:
        회의 안건 요약
    """
    cleaned = re.sub(r"^(?:(?:\s*(?:re|fw|fwd)\s*[:：]\s*)+)", "", str(subject or ""), flags=re.IGNORECASE).strip()
    if cleaned:
        compact = re.sub(r"\s+", " ", cleaned)
        return compact[:36]
    if issues:
        return str(issues[0])[:36]
    return "메일 주요 이슈 논의"


def _build_time_candidates(body_text: str) -> list[dict[str, str]]:
    """
    본문 시각 단서를 보조적으로 반영해 회의 시간 후보 3개를 생성한다.

    Args:
        body_text: 메일 본문 텍스트

    Returns:
        시간 후보 목록
    """
    date_text = _extract_date_hint(text=body_text) or _next_business_day().strftime("%Y-%m-%d")
    hinted_slot = _extract_time_slot_hint(text=body_text)
    candidates: list[dict[str, str]] = []
    seed_slots = [hinted_slot] if hinted_slot else []
    seed_slots.extend(TIME_CANDIDATE_SLOTS)
    for start_time, end_time in seed_slots:
        key = f"{date_text}:{start_time}:{end_time}"
        if any(item.get("key") == key for item in candidates):
            continue
        candidates.append(
            {
                "key": key,
                "date": date_text,
                "start_time": start_time,
                "end_time": end_time,
                "label": f"{date_text} {start_time}-{end_time}",
            }
        )
        if len(candidates) >= 3:
            break
    return candidates


def _extract_date_hint(text: str) -> str:
    """
    본문에서 YYYY-MM-DD/YYY.MM.DD 날짜 단서를 추출한다.

    Args:
        text: 메일 본문

    Returns:
        파싱된 날짜 문자열(YYYY-MM-DD), 없으면 빈 문자열
    """
    match = re.search(r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})", str(text or ""))
    if not match:
        return ""
    year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
    try:
        return datetime(year=year, month=month, day=day).strftime("%Y-%m-%d")
    except ValueError:
        return ""


def _extract_time_slot_hint(text: str) -> tuple[str, str] | None:
    """
    본문에서 HH:MM-HH:MM 시간 범위를 추출한다.

    Args:
        text: 메일 본문

    Returns:
        (시작, 종료) 시간 튜플 또는 None
    """
    normalized = _strip_mail_header_lines(text=str(text or ""))
    range_match = re.search(r"(\d{1,2}):(\d{2})\s*[~\-]\s*(\d{1,2}):(\d{2})", normalized)
    if range_match:
        start = _normalize_hhmm(hour=range_match.group(1), minute=range_match.group(2))
        end = _normalize_hhmm(hour=range_match.group(3), minute=range_match.group(4))
        if start and end and end > start and _is_business_time_slot(start_hhmm=start, end_hhmm=end):
            return (start, end)
    point_match = re.search(r"(\d{1,2}):(\d{2})", normalized)
    if not point_match:
        return None
    start = _normalize_hhmm(hour=point_match.group(1), minute=point_match.group(2))
    if not start:
        return None
    end = _add_one_hour(hhmm=start)
    if not _is_business_time_slot(start_hhmm=start, end_hhmm=end):
        return None
    return (start, end)


def _normalize_hhmm(hour: str, minute: str) -> str:
    """
    시/분 숫자 문자열을 `HH:MM` 형식으로 정규화한다.

    Args:
        hour: 시 문자열
        minute: 분 문자열

    Returns:
        정규화된 시각 문자열 또는 빈 문자열
    """
    try:
        hour_num = int(hour)
        minute_num = int(minute)
    except ValueError:
        return ""
    if not (0 <= hour_num <= 23 and 0 <= minute_num <= 59):
        return ""
    return f"{hour_num:02d}:{minute_num:02d}"


def _add_one_hour(hhmm: str) -> str:
    """
    `HH:MM` 시각에 1시간을 더한 시각을 반환한다.

    Args:
        hhmm: 입력 시각

    Returns:
        +1시간 시각
    """
    base = datetime.strptime(hhmm, "%H:%M")
    return (base + timedelta(hours=1)).strftime("%H:%M")


def _strip_mail_header_lines(text: str) -> str:
    """
    전달/인용 메일의 헤더 라인을 제거해 본문 시간 단서 오탐을 줄인다.

    Args:
        text: 메일 본문 원문

    Returns:
        헤더 라인이 제거된 텍스트
    """
    lines = str(text or "").splitlines()
    filtered: list[str] = []
    for line in lines:
        normalized = str(line or "").strip()
        lowered = normalized.lower()
        if lowered.startswith(("from:", "sent:", "to:", "cc:", "subject:")):
            continue
        filtered.append(normalized)
    return "\n".join(filtered)


def _is_business_time_slot(start_hhmm: str, end_hhmm: str) -> bool:
    """
    시간 구간이 업무시간(09:00~18:00) 범위인지 확인한다.

    Args:
        start_hhmm: 시작 시각
        end_hhmm: 종료 시각

    Returns:
        업무시간 범위면 True
    """
    start_minute = _to_minutes(hhmm=start_hhmm)
    end_minute = _to_minutes(hhmm=end_hhmm)
    if start_minute < 0 or end_minute < 0:
        return False
    return BUSINESS_START_MINUTE <= start_minute < end_minute <= BUSINESS_END_MINUTE


def _to_minutes(hhmm: str) -> int:
    """
    HH:MM 문자열을 분 단위 정수로 변환한다.

    Args:
        hhmm: 시각 문자열

    Returns:
        분 단위 값. 파싱 실패 시 -1
    """
    try:
        hour_text, minute_text = str(hhmm or "").split(":")
        hour = int(hour_text)
        minute = int(minute_text)
    except (ValueError, TypeError):
        return -1
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return -1
    return hour * 60 + minute


def _next_business_day() -> datetime:
    """
    오늘 기준 다음 영업일 날짜를 계산한다.

    Returns:
        다음 영업일 datetime
    """
    current = datetime.now(tz=SEOUL_TZ)
    step = current + timedelta(days=1)
    while step.weekday() >= 5:
        step += timedelta(days=1)
    return step


def _build_room_candidates(rooms: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """
    회의실 마스터에서 제안 회의실 후보를 추려 반환한다.

    Args:
        rooms: 회의실 마스터 목록
        limit: 반환 상한

    Returns:
        회의실 후보 목록
    """
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for room in rooms:
        building = str(room.get("building") or "").strip()
        room_name = str(room.get("room_name") or "").strip()
        floor = int(room.get("floor") or 0)
        if not building or not room_name or floor <= 0:
            continue
        key = f"{building}|{floor}|{room_name}"
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            {
                "building": building,
                "floor": floor,
                "room_name": room_name,
                "label": f"{building} {floor}층 {room_name}",
            }
        )
        if len(candidates) >= max(1, limit):
            break
    return candidates
