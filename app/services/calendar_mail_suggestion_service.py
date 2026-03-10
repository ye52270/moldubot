from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.services.mail_service import MailRecord
from app.services.mail_text_utils import extract_recipients_from_body

SEOUL_TZ = ZoneInfo("Asia/Seoul")
DEFAULT_START_TIME = "10:00"
DEFAULT_END_TIME = "11:00"
MAX_ATTENDEES = 10


def suggest_calendar_plan_from_mail(mail: MailRecord) -> dict[str, object]:
    """
    현재 메일 기반 일정 등록 기본값을 생성한다.

    Args:
        mail: 선택 메일 레코드

    Returns:
        일정 카드 프리필에 사용할 제안 payload
    """
    summary_text = _normalize_summary_text(value=mail.summary_text)
    key_points = [summary_text] if summary_text else []
    attendees = _extract_attendees(body_text=mail.body_text)
    event_date = _extract_date_hint(text=mail.body_text) or _next_business_day().strftime("%Y-%m-%d")
    start_time, end_time = _extract_time_hint(text=mail.body_text)
    subject = _build_subject(subject=mail.subject, key_points=key_points)
    body = _build_body(summary_text=summary_text, attendees=attendees)
    return {
        "subject": subject,
        "body": body,
        "summary_text": summary_text,
        "key_points": key_points,
        "attendees": attendees,
        "date": event_date,
        "start_time": start_time,
        "end_time": end_time,
    }


def _normalize_summary_text(value: str) -> str:
    """
    DB summary 필드를 표시용 문자열로 정규화한다.

    Args:
        value: summary 원본 값

    Returns:
        공백 정리된 summary 문자열
    """
    return str(value or "").strip()


def _extract_attendees(body_text: str) -> list[str]:
    """
    메일 본문 헤더의 수신자 정보를 참석자 후보로 추출한다.

    Args:
        body_text: 메일 본문

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
    return deduped[:MAX_ATTENDEES]


def _extract_date_hint(text: str) -> str:
    """
    본문에서 `YYYY-MM-DD` 또는 `YYYY.MM.DD` 형태 날짜를 추출한다.

    Args:
        text: 메일 본문

    Returns:
        추출된 날짜 문자열(YYYY-MM-DD) 또는 빈 문자열
    """
    matched = re.search(r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})", str(text or ""))
    if not matched:
        return ""
    year, month, day = int(matched.group(1)), int(matched.group(2)), int(matched.group(3))
    try:
        return datetime(year=year, month=month, day=day).strftime("%Y-%m-%d")
    except ValueError:
        return ""


def _extract_time_hint(text: str) -> tuple[str, str]:
    """
    본문에서 시각 힌트를 추출해 시작/종료 시각을 반환한다.

    Args:
        text: 메일 본문

    Returns:
        (시작 시각, 종료 시각)
    """
    normalized = str(text or "")
    range_match = re.search(r"(\d{1,2}):(\d{2})\s*[~\-]\s*(\d{1,2}):(\d{2})", normalized)
    if range_match:
        start = _normalize_hhmm(hour=range_match.group(1), minute=range_match.group(2))
        end = _normalize_hhmm(hour=range_match.group(3), minute=range_match.group(4))
        if start and end and end > start:
            return start, end
    point_match = re.search(r"(\d{1,2}):(\d{2})", normalized)
    if not point_match:
        return DEFAULT_START_TIME, DEFAULT_END_TIME
    start = _normalize_hhmm(hour=point_match.group(1), minute=point_match.group(2))
    if not start:
        return DEFAULT_START_TIME, DEFAULT_END_TIME
    end = (datetime.strptime(start, "%H:%M") + timedelta(hours=1)).strftime("%H:%M")
    return start, end


def _normalize_hhmm(hour: str, minute: str) -> str:
    """
    시/분 문자열을 `HH:MM` 형식으로 정규화한다.

    Args:
        hour: 시 문자열
        minute: 분 문자열

    Returns:
        정규화된 시각 또는 빈 문자열
    """
    try:
        hour_num = int(hour)
        minute_num = int(minute)
    except ValueError:
        return ""
    if not (0 <= hour_num <= 23 and 0 <= minute_num <= 59):
        return ""
    return f"{hour_num:02d}:{minute_num:02d}"


def _build_subject(subject: str, key_points: list[str]) -> str:
    """
    메일 제목 기반 일정 제목을 생성한다.

    Args:
        subject: 메일 제목
        key_points: 핵심 포인트

    Returns:
        일정 제목
    """
    cleaned = re.sub(r"^(?:(?:\s*(?:re|fw|fwd)\s*[:：]\s*)+)", "", str(subject or ""), flags=re.IGNORECASE).strip()
    if cleaned:
        compact = re.sub(r"\s+", " ", cleaned)
        return f"[일정] {compact[:36]}"
    if key_points:
        return f"[일정] {str(key_points[0])[:28]}"
    return "[일정] 현재메일 주요 내용 논의"


def _build_body(summary_text: str, attendees: list[str]) -> str:
    """
    일정 본문 기본 텍스트를 생성한다.

    Args:
        summary_text: 현재메일 요약(summary 필드) 원문
        attendees: 참석자 후보 목록

    Returns:
        일정 본문 문자열
    """
    lines = ["[현재메일 요약]"]
    if summary_text:
        lines.append(summary_text)
    else:
        lines.append("저장된 summary가 없습니다.")
    if attendees:
        lines.append("")
        lines.append("[참석자 후보]")
        lines.append("- " + ", ".join(attendees))
    return "\n".join(lines)


def _next_business_day() -> datetime:
    """
    오늘 기준 다음 영업일을 반환한다.

    Returns:
        다음 영업일 datetime
    """
    current = datetime.now(tz=SEOUL_TZ)
    step = current + timedelta(days=1)
    while step.weekday() >= 5:
        step += timedelta(days=1)
    return step
