from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo

from langchain.tools import tool

from app.core.date_resolver import resolve_booking_date_token
from app.core.logging_config import get_logger
from app.integrations.microsoft_graph.calendar_client import GraphCalendarClient
from app.services.meeting_service import BookingRequest, MeetingRoomService

ROOT_DIR = Path(__file__).resolve().parents[2]
MEETING_ROOMS_PATH = ROOT_DIR / "data" / "meeting" / "meeting_rooms.json"
MEETING_BOOKINGS_PATH = ROOT_DIR / "data" / "mock" / "meeting_bookings.json"

_MEETING_SERVICE = MeetingRoomService(rooms_path=MEETING_ROOMS_PATH, bookings_path=MEETING_BOOKINGS_PATH)
_CALENDAR_CLIENT = GraphCalendarClient()
logger = get_logger(__name__)
SEOUL_TIMEZONE = ZoneInfo("Asia/Seoul")
EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def _normalize_floor(floor: int) -> int | None:
    """
    floor 입력값을 검색용 값으로 정규화한다.

    Args:
        floor: 입력 층수

    Returns:
        1 이상이면 층수, 아니면 None
    """
    return floor if floor > 0 else None


def _build_meeting_event_body(request: BookingRequest) -> str:
    """
    캘린더 일정 본문을 생성한다.

    Args:
        request: 회의실 예약 요청 데이터

    Returns:
        일정 본문 문자열
    """
    return "\n".join(
        [
            f"회의실: {request.building} {request.floor}층 {request.room_name}",
            f"일시: {request.date} {request.start_time} ~ {request.end_time}",
            f"참석 인원: {request.attendee_count}명",
            "생성 경로: MolduBot 회의실 예약",
        ]
    )


def _normalize_attendee_inputs(attendees: list[str] | None) -> tuple[list[str], list[str]]:
    """
    참석자 입력 목록을 이메일 유효값/비유효값으로 분리한다.

    Args:
        attendees: 참석자 문자열 목록

    Returns:
        (유효 이메일 목록, 비유효 입력 목록)
    """
    valid: list[str] = []
    invalid: list[str] = []
    for raw in attendees or []:
        normalized = str(raw or "").strip()
        if not normalized:
            continue
        if EMAIL_PATTERN.fullmatch(normalized):
            if normalized not in valid:
                valid.append(normalized)
            continue
        if normalized not in invalid:
            invalid.append(normalized)
    return valid, invalid


def _append_attendee_note(body_text: str, attendee_notes: list[str]) -> str:
    """
    일정 본문에 참석자 참고 라인을 덧붙인다.

    Args:
        body_text: 기존 본문
        attendee_notes: 본문에만 남길 참석자 문자열

    Returns:
        참석자 라인이 반영된 본문
    """
    lines = [str(body_text or "").strip()]
    if attendee_notes:
        lines.append(f"[참석자] {', '.join(attendee_notes)}")
    return "\n".join([line for line in lines if line]).strip()


@tool
def current_date() -> dict[str, Any]:
    """
    에이전트의 기준 시각(한국 시간)을 반환한다.

    Returns:
        현재 시각/날짜 및 연월일을 포함한 사전
    """
    now = datetime.now(tz=SEOUL_TIMEZONE)
    return {
        "status": "completed",
        "timezone": "Asia/Seoul",
        "iso_datetime": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "year": now.year,
        "month": now.month,
        "day": now.day,
    }


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
    logger.info(
        "book_meeting_room 호출: raw_input=%s",
        {
            "date": date,
            "start_time": start_time,
            "end_time": end_time,
            "attendee_count": attendee_count,
            "building": building,
            "floor": floor,
            "room_name": room_name,
            "subject": subject,
        },
    )
    normalized_date = resolve_booking_date_token(raw_date=date)
    request = BookingRequest(
        date=normalized_date,
        start_time=start_time,
        end_time=end_time,
        attendee_count=max(0, attendee_count),
        building=building.strip(),
        floor=floor,
        room_name=room_name.strip(),
        subject=subject.strip() or "회의",
    )
    logger.info(
        "book_meeting_room 정규화 완료: normalized_request=%s",
        {
            "date": request.date,
            "start_time": request.start_time,
            "end_time": request.end_time,
            "attendee_count": request.attendee_count,
            "building": request.building,
            "floor": request.floor,
            "room_name": request.room_name,
            "subject": request.subject,
        },
    )
    if normalized_date != date:
        logger.info("book_meeting_room 날짜 변환 적용: raw_date=%s normalized_date=%s", date, normalized_date)
    result = _MEETING_SERVICE.book_room(request=request)
    if str(result.get("status") or "").strip() != "completed":
        result["action"] = "book_meeting_room"
        return result

    subject_text = f"[회의실] {request.room_name}"
    event = _CALENDAR_CLIENT.create_event(
        subject=subject_text,
        start_iso=f"{request.date}T{request.start_time}:00",
        end_iso=f"{request.date}T{request.end_time}:00",
        body_text=_build_meeting_event_body(request=request),
    )
    if event is not None:
        result["event"] = {
            "id": event.event_id,
            "web_link": event.web_link,
        }
    else:
        logger.warning("book_meeting_room Graph 일정 생성 실패: 로컬 예약 결과만 반환")

    booking = result.get("booking") if isinstance(result.get("booking"), dict) else {}
    if booking:
        result["answer"] = (
            f"{booking.get('date')} {booking.get('start_time')}-{booking.get('end_time')} "
            f"{booking.get('building')} {booking.get('floor')}층 {booking.get('room_name')} 예약을 완료했습니다."
        )
    result["action"] = "book_meeting_room"
    return result


@tool
def create_outlook_calendar_event(
    subject: str,
    date: str,
    start_time: str,
    end_time: str,
    body: str = "",
    attendees: list[str] | None = None,
) -> dict[str, Any]:
    """
    Outlook 캘린더 일정을 생성한다.

    Args:
        subject: 일정 제목
        date: 일정 날짜(YYYY-MM-DD)
        start_time: 시작 시각(HH:MM)
        end_time: 종료 시각(HH:MM)
        body: 일정 본문
        attendees: 참석자 이메일/이름 목록

    Returns:
        일정 생성 결과 사전
    """
    title = str(subject or "").strip()
    if not title:
        return {"status": "failed", "reason": "subject는 필수입니다."}
    date_text = str(date or "").strip()
    start = str(start_time or "").strip()
    end = str(end_time or "").strip()
    try:
        datetime.strptime(f"{date_text} {start}", "%Y-%m-%d %H:%M")
        datetime.strptime(f"{date_text} {end}", "%Y-%m-%d %H:%M")
    except ValueError:
        return {"status": "failed", "reason": "date/start_time/end_time 형식이 유효하지 않습니다."}
    valid_attendees, invalid_attendees = _normalize_attendee_inputs(attendees=attendees)
    body_text = _append_attendee_note(body_text=str(body or "").strip(), attendee_notes=invalid_attendees)
    event = _CALENDAR_CLIENT.create_event(
        subject=title,
        start_iso=f"{date_text}T{start}:00",
        end_iso=f"{date_text}T{end}:00",
        body_text=body_text,
        attendees=valid_attendees,
    )
    if event is None:
        return {"status": "failed", "reason": "Outlook 일정 생성에 실패했습니다. Graph 설정/로그인을 확인해 주세요."}
    return {
        "action": "create_outlook_calendar_event",
        "status": "completed",
        "answer": f"{date_text} {start}-{end} 일정 등록을 완료했습니다.",
        "event": {
            "id": event.event_id,
            "web_link": event.web_link,
            "subject": title,
            "date": date_text,
            "start_time": start,
            "end_time": end,
        },
    }
