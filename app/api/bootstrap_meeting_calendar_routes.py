from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from app.api.contracts import CalendarEventCreateRequest, CalendarSuggestionRequest, MeetingSuggestionRequest, RoomBookingRequest
from app.api.data_access import meeting_rooms as load_meeting_rooms
from app.core.date_resolver import resolve_booking_date_token
from app.core.logging_config import get_logger
from app.integrations.microsoft_graph.calendar_client import GraphCalendarClient
from app.services.calendar_mail_suggestion_service import suggest_calendar_plan_from_mail
from app.services.mail_context_service import build_mail_context_service
from app.services.meeting_mail_suggestion_service import suggest_meeting_plan_from_mail

router = APIRouter()
logger = get_logger(__name__)
calendar_client = GraphCalendarClient()
ROOT_DIR = Path(__file__).resolve().parents[2]
MAIL_DB_PATH = ROOT_DIR / "data" / "sqlite" / "emails.db"
mail_context_service = build_mail_context_service(db_path=MAIL_DB_PATH)


@router.get("/api/meeting-rooms")
def meeting_rooms(building: str | None = None, floor: int | None = None) -> dict[str, Any]:
    """
    회의실 목록(건물/층/실제 룸)을 조회한다.

    Args:
        building: 건물명 필터
        floor: 층수 필터

    Returns:
        필터 수준에 맞는 회의실 목록
    """
    rooms = load_meeting_rooms()
    if not building:
        buildings = sorted({str(item.get("building", "")).strip() for item in rooms if item.get("building")})
        return {"items": [{"building": name} for name in buildings], "count": len(buildings)}

    if floor is None:
        floors = sorted(
            {
                int(item.get("floor"))
                for item in rooms
                if str(item.get("building", "")).strip() == building and item.get("floor") is not None
            }
        )
        return {"items": [{"building": building, "floor": value} for value in floors], "count": len(floors)}

    filtered = [
        item
        for item in rooms
        if str(item.get("building", "")).strip() == building and int(item.get("floor", -1)) == int(floor)
    ]
    return {"items": filtered, "count": len(filtered)}


@router.post("/api/meeting-rooms/suggest-from-current-mail")
def suggest_meeting_rooms_from_current_mail(payload: MeetingSuggestionRequest) -> dict[str, Any]:
    """
    현재 메일 본문 기반 회의 제안(이슈/참석자/시간/회의실)을 생성한다.

    Args:
        payload: 선택 메일 식별자 요청

    Returns:
        회의 제안 결과
    """
    result = mail_context_service.get_mail_context(
        message_id=payload.message_id,
        mailbox_user=payload.mailbox_user,
    )
    if result.mail is None:
        return {
            "status": "failed",
            "reason": str(result.reason or "선택 메일 컨텍스트를 찾지 못했습니다."),
            "source": result.source,
        }
    proposal = suggest_meeting_plan_from_mail(
        mail=result.mail,
        rooms=load_meeting_rooms(),
    )
    return {
        "status": "completed",
        "source": result.source,
        "proposal": proposal,
    }


@router.post("/api/meeting-rooms/book")
def meeting_room_book(payload: RoomBookingRequest) -> dict[str, Any]:
    """
    회의실 예약 요청을 접수 응답으로 반환한다.

    Args:
        payload: 예약 요청 정보

    Returns:
        예약 접수 결과
    """
    raw_date_text = str(payload.date or "").strip()
    date_text = resolve_booking_date_token(raw_date=raw_date_text)
    start_time = str(payload.start_time or "").strip()
    end_time = str(payload.end_time or "").strip()
    if not _is_valid_booking_datetime(date_text=date_text, start_time=start_time, end_time=end_time):
        return {"status": "failed", "reason": "date/start_time/end_time 형식이 유효하지 않습니다."}
    if date_text != raw_date_text:
        logger.info("meeting_room_book 날짜 변환 적용: raw_date=%s normalized_date=%s", raw_date_text, date_text)

    matched_room = _find_meeting_room(
        rooms=load_meeting_rooms(),
        building=str(payload.building or ""),
        floor=payload.floor,
        room_name=str(payload.room_name or ""),
    )
    if matched_room is None:
        return {"status": "failed", "reason": "선택한 회의실을 찾지 못했습니다."}

    attendee_count = max(1, int(payload.attendee_count or 1))
    title = f"[회의실] {matched_room['building']} {matched_room['floor']}층 {matched_room['room_name']}"
    calendar_body = _build_meeting_event_body(
        booking_date=date_text,
        start_time=start_time,
        end_time=end_time,
        building=matched_room["building"],
        floor=int(matched_room["floor"]),
        room_name=matched_room["room_name"],
        attendee_count=attendee_count,
        meeting_subject=str(payload.subject or "").strip(),
    )
    event = calendar_client.create_event(
        subject=title,
        start_iso=f"{date_text}T{start_time}:00",
        end_iso=f"{date_text}T{end_time}:00",
        body_text=calendar_body,
    )
    if event is None:
        return {"status": "failed", "reason": "Graph 일정 생성에 실패했습니다. 설정/로그인을 확인해 주세요."}

    booking = payload.model_dump()
    booking["date"] = date_text
    booking["attendee_count"] = attendee_count
    booking["subject"] = title
    return {
        "status": "completed",
        "answer": (
            f"{date_text} {start_time}-{end_time} "
            f"{matched_room['building']} {matched_room['floor']}층 {matched_room['room_name']} 예약을 완료했습니다."
        ),
        "booking": booking,
        "event": {
            "id": event.event_id,
            "web_link": event.web_link,
        },
    }


@router.post("/api/calendar-events/suggest-from-current-mail")
def suggest_calendar_event_from_current_mail(payload: CalendarSuggestionRequest) -> dict[str, Any]:
    """
    현재 메일 본문 기반 일정 제안(제목/내용/참석자/기본 시간)을 생성한다.

    Args:
        payload: 선택 메일 식별자 요청

    Returns:
        일정 제안 결과
    """
    result = mail_context_service.get_mail_context(
        message_id=payload.message_id,
        mailbox_user=payload.mailbox_user,
    )
    if result.mail is None:
        return {
            "status": "failed",
            "reason": str(result.reason or "선택 메일 컨텍스트를 찾지 못했습니다."),
            "source": result.source,
        }
    proposal = suggest_calendar_plan_from_mail(mail=result.mail)
    return {
        "status": "completed",
        "source": result.source,
        "proposal": proposal,
    }


@router.post("/api/calendar-events/create")
def create_calendar_event(payload: CalendarEventCreateRequest) -> dict[str, Any]:
    """
    Outlook 개인 캘린더에 일반 일정을 생성한다.

    Args:
        payload: 일정 생성 요청

    Returns:
        생성 결과
    """
    raw_date_text = str(payload.date or "").strip()
    date_text = resolve_booking_date_token(raw_date=raw_date_text)
    start_time = str(payload.start_time or "").strip()
    end_time = str(payload.end_time or "").strip()
    if not _is_valid_booking_datetime(date_text=date_text, start_time=start_time, end_time=end_time):
        return {"status": "failed", "reason": "date/start_time/end_time 형식이 유효하지 않습니다."}
    if date_text != raw_date_text:
        logger.info(
            "create_calendar_event 날짜 변환 적용: raw_date=%s normalized_date=%s",
            raw_date_text,
            date_text,
        )
    title = str(payload.subject or "").strip()
    if not title:
        return {"status": "failed", "reason": "subject는 필수입니다."}
    attendees = [str(item or "").strip() for item in payload.attendees if str(item or "").strip()]
    body_text = str(payload.body or "").strip()
    valid_emails = [item for item in attendees if "@" in item]
    invalid_attendees = [item for item in attendees if "@" not in item]
    if invalid_attendees:
        body_text = "\n".join(
            line
            for line in (body_text, "[참석자] " + ", ".join(invalid_attendees))
            if line
        )
    event = calendar_client.create_event(
        subject=title,
        start_iso=f"{date_text}T{start_time}:00",
        end_iso=f"{date_text}T{end_time}:00",
        body_text=body_text,
        attendees=valid_emails,
    )
    if event is None:
        return {"status": "failed", "reason": "Graph 일정 생성에 실패했습니다. 설정/로그인을 확인해 주세요."}
    return {
        "status": "completed",
        "answer": f"{date_text} {start_time}-{end_time} 일정 등록을 완료했습니다.",
        "event": {
            "id": event.event_id,
            "web_link": event.web_link,
        },
    }


def _find_meeting_room(
    rooms: list[dict[str, Any]],
    building: str,
    floor: int,
    room_name: str,
) -> dict[str, Any] | None:
    """
    건물/층/회의실명으로 회의실 목록에서 대상 회의실을 찾는다.

    Args:
        rooms: 회의실 목록
        building: 건물명
        floor: 층수
        room_name: 회의실명

    Returns:
        매칭 회의실 또는 None
    """
    target_building = str(building or "").strip()
    target_room_name = str(room_name or "").strip()
    for room in rooms:
        if str(room.get("building", "")).strip() != target_building:
            continue
        if int(room.get("floor", -1)) != int(floor):
            continue
        if str(room.get("room_name", "")).strip() != target_room_name:
            continue
        return room
    return None


def _is_valid_booking_datetime(date_text: str, start_time: str, end_time: str) -> bool:
    """
    예약 날짜/시간 문자열 유효성을 검증한다.

    Args:
        date_text: 예약일(YYYY-MM-DD)
        start_time: 시작 시간(HH:MM)
        end_time: 종료 시간(HH:MM)

    Returns:
        유효하면 True
    """
    try:
        start_dt = datetime.strptime(f"{date_text} {start_time}", "%Y-%m-%d %H:%M")
        end_dt = datetime.strptime(f"{date_text} {end_time}", "%Y-%m-%d %H:%M")
    except ValueError:
        return False
    return end_dt > start_dt


def _build_meeting_event_body(
    booking_date: str,
    start_time: str,
    end_time: str,
    building: str,
    floor: int,
    room_name: str,
    attendee_count: int,
    meeting_subject: str,
) -> str:
    """
    Graph 이벤트 본문 문자열을 생성한다.

    Args:
        booking_date: 예약일
        start_time: 시작 시각
        end_time: 종료 시각
        building: 건물명
        floor: 층수
        room_name: 회의실명
        attendee_count: 참석 인원
        meeting_subject: 회의 안건 요약

    Returns:
        텍스트 본문
    """
    subject_line = str(meeting_subject or "").strip()
    lines = [
        "[회의실 예약 정보]",
        f"- 일자: {booking_date}",
        f"- 시간: {start_time} ~ {end_time}",
        f"- 장소: {building} {floor}층 {room_name}",
        f"- 참석 인원: {attendee_count}명",
    ]
    if subject_line:
        lines.append(f"- 회의 안건: {subject_line}")
    lines.append("- 예약 방식: 개인 Outlook 캘린더 일정 등록")
    return "\n".join(lines)
