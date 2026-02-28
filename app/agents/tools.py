from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain.tools import tool

from app.services.mail_service import MailService
from app.services.meeting_service import BookingRequest, MeetingRoomService

ROOT_DIR = Path(__file__).resolve().parents[2]
MAIL_DB_PATH = ROOT_DIR / "data" / "sqlite" / "emails.db"
MEETING_ROOMS_PATH = ROOT_DIR / "data" / "mock" / "meeting_rooms.json"
MEETING_BOOKINGS_PATH = ROOT_DIR / "data" / "mock" / "meeting_bookings.json"

_MAIL_SERVICE = MailService(db_path=MAIL_DB_PATH)
_MEETING_SERVICE = MeetingRoomService(rooms_path=MEETING_ROOMS_PATH, bookings_path=MEETING_BOOKINGS_PATH)


def _normalize_floor(floor: int) -> int | None:
    """
    floor 입력값을 검색용 값으로 정규화한다.

    Args:
        floor: 입력 층수

    Returns:
        1 이상이면 층수, 아니면 None
    """
    return floor if floor > 0 else None


@tool
def read_current_mail() -> dict[str, Any]:
    """
    현재(가장 최근) 메일 1건을 조회한다.

    Returns:
        메일 식별자/제목/발신자/수신일/본문 미리보기를 포함한 사전
    """
    mail = _MAIL_SERVICE.read_current_mail()
    if mail is None:
        return {"status": "failed", "reason": "현재 메일을 찾지 못했습니다."}
    return {
        "status": "completed",
        "message_id": mail.message_id,
        "subject": mail.subject,
        "from_address": mail.from_address,
        "received_date": mail.received_date,
        "body_preview": mail.body_text[:400],
    }


@tool
def run_mail_post_action(action: str = "summary", summary_line_target: int = 5) -> dict[str, Any]:
    """
    메일 조회 후속작업(요약/보고서)을 단일 실행 경로로 처리한다.

    Args:
        action: `summary` 또는 `report`
        summary_line_target: 요약 줄 수 목표

    Returns:
        후속작업 실행 결과 사전
    """
    mail = _MAIL_SERVICE.get_current_mail()
    if mail is None:
        mail = _MAIL_SERVICE.read_current_mail()
    if mail is None:
        return {"status": "failed", "reason": "현재 메일을 찾지 못했습니다."}

    payload = _MAIL_SERVICE.run_post_action(
        action=action,
        summary_line_target=summary_line_target,
    )
    return {"status": "completed", **payload}


@tool
def summarize_mail(summary_line_target: int = 5) -> dict[str, Any]:
    """
    현재 메일 본문을 지정한 줄 수로 요약한다.

    Args:
        summary_line_target: 목표 요약 줄 수

    Returns:
        요약 라인 목록
    """
    lines = _MAIL_SERVICE.summarize_current_mail(line_target=summary_line_target)
    return {"status": "completed", "summary_lines": lines, "line_count": len(lines)}


@tool
def extract_key_facts(limit: int = 5) -> dict[str, Any]:
    """
    현재 메일에서 핵심 포인트를 추출한다.

    Args:
        limit: 최대 포인트 개수

    Returns:
        핵심 포인트 목록
    """
    facts = _MAIL_SERVICE.extract_key_facts(limit=limit)
    return {"status": "completed", "key_facts": facts}


@tool
def extract_recipients(limit: int = 10) -> dict[str, Any]:
    """
    현재 메일에서 수신자 목록을 추출한다.

    Args:
        limit: 최대 수신자 개수

    Returns:
        수신자 목록
    """
    recipients = _MAIL_SERVICE.extract_recipients(limit=limit)
    return {"status": "completed", "recipients": recipients}


@tool
def search_meeting_rooms(attendee_count: int = 0, building: str = "", floor: int = 0) -> dict[str, Any]:
    """
    참석 인원/건물/층수 조건으로 회의실을 조회한다.

    Args:
        attendee_count: 참석 인원
        building: 건물명
        floor: 층수

    Returns:
        조회된 회의실 목록
    """
    rooms = _MEETING_SERVICE.search_rooms(
        attendee_count=max(0, attendee_count),
        building=building,
        floor=_normalize_floor(floor),
    )
    return {"status": "completed", "rooms": rooms, "count": len(rooms)}


@tool
def book_meeting_room(
    date: str,
    start_time: str,
    end_time: str,
    attendee_count: int,
    building: str,
    floor: int,
    room_name: str,
    subject: str = "회의",
) -> dict[str, Any]:
    """
    회의실 예약을 생성한다.

    Args:
        date: 예약 날짜(YYYY-MM-DD)
        start_time: 시작 시각(HH:MM)
        end_time: 종료 시각(HH:MM)
        attendee_count: 참석 인원
        building: 건물명
        floor: 층수
        room_name: 회의실명
        subject: 회의 제목

    Returns:
        예약 결과 사전
    """
    request = BookingRequest(
        date=date,
        start_time=start_time,
        end_time=end_time,
        attendee_count=max(0, attendee_count),
        building=building.strip(),
        floor=floor,
        room_name=room_name.strip(),
        subject=subject.strip() or "회의",
    )
    return _MEETING_SERVICE.book_room(request=request)


def get_agent_tools() -> list[Any]:
    """
    deep agent에 주입할 도구 목록을 반환한다.

    Returns:
        LangChain tool 객체 목록
    """
    return [
        read_current_mail,
        run_mail_post_action,
        summarize_mail,
        extract_key_facts,
        extract_recipients,
        search_meeting_rooms,
        book_meeting_room,
    ]
