from __future__ import annotations

import re
from pathlib import Path
from datetime import datetime, timedelta

from app.agents.intent_schema import ExecutionStep, IntentDecomposition
from app.services.mail_service import MailService
from app.services.meeting_service import BookingRequest, MeetingRoomService

ROOT_DIR = Path(__file__).resolve().parents[2]
MAIL_DB_PATH = ROOT_DIR / "data" / "sqlite" / "emails.db"
MEETING_ROOMS_PATH = ROOT_DIR / "data" / "mock" / "meeting_rooms.json"
MEETING_BOOKINGS_PATH = ROOT_DIR / "data" / "mock" / "meeting_bookings.json"


class TaskExecutionService:
    """
    의도 구조분해 결과를 기반으로 실제 메일/회의 업무를 수행하는 서비스.
    """

    def __init__(self) -> None:
        """
        서비스 인스턴스를 초기화한다.
        """
        self._mail_service = MailService(db_path=MAIL_DB_PATH)
        self._meeting_service = MeetingRoomService(
            rooms_path=MEETING_ROOMS_PATH,
            bookings_path=MEETING_BOOKINGS_PATH,
        )

    def execute(self, decomposition: IntentDecomposition, user_message: str) -> str:
        """
        의도 단계 목록에 맞춰 업무를 실행하고 사용자 응답을 구성한다.

        Args:
            decomposition: 의도 구조분해 결과
            user_message: 원본 사용자 입력

        Returns:
            실행 결과를 요약한 사용자 응답 텍스트
        """
        lines: list[str] = []
        mail = None

        if ExecutionStep.READ_CURRENT_MAIL in decomposition.steps:
            mail = self._mail_service.read_current_mail()
            if mail is None:
                return "현재 메일을 찾지 못했습니다. 메일 동기화 상태를 확인해 주세요."
            lines.append(f"현재 메일: [{mail.subject}] / 발신자: {mail.from_address} / 수신시각: {mail.received_date}")

        if ExecutionStep.SUMMARIZE_MAIL in decomposition.steps:
            summary_lines = self._mail_service.summarize_current_mail(decomposition.summary_line_target)
            lines.append("메일 요약:")
            lines.extend([f"{idx}. {item}" for idx, item in enumerate(summary_lines, start=1)])

        if ExecutionStep.EXTRACT_KEY_FACTS in decomposition.steps:
            key_facts = self._mail_service.extract_key_facts(limit=5)
            lines.append("중요 내용:")
            lines.extend([f"- {item}" for item in key_facts])

        if ExecutionStep.EXTRACT_RECIPIENTS in decomposition.steps:
            recipients = self._mail_service.extract_recipients(limit=10)
            lines.append(f"수신자 정보: {', '.join(recipients)}")

        if ExecutionStep.SEARCH_MEETING_SCHEDULE in decomposition.steps:
            lines.append("회의 일정 조회는 아직 캘린더 연동 전입니다. 대신 회의실 가용 목록을 확인합니다.")
            rooms = self._meeting_service.search_rooms(attendee_count=0)
            if rooms:
                preview = ", ".join([f"{room['building']} {room['floor']}층 {room['room_name']}" for room in rooms[:3]])
                lines.append(f"가용 회의실 예시: {preview}")

        if ExecutionStep.BOOK_MEETING_ROOM in decomposition.steps:
            missing = decomposition.missing_slots
            if missing and not _can_auto_complete_booking(missing_slots=missing):
                lines.append("회의실 예약에 필요한 정보가 부족합니다.")
                lines.append(f"추가 필요 슬롯: {', '.join(missing)}")
            else:
                lines.append(self._book_with_best_effort(user_message=user_message))

        if not lines:
            return "요청을 처리할 실행 단계를 찾지 못했습니다."
        return "\n".join(lines)

    def _book_with_best_effort(self, user_message: str) -> str:
        """
        사용자 문장에서 예약 값을 추정해 회의실 예약을 시도한다.

        Args:
            user_message: 원본 사용자 입력

        Returns:
            예약 성공/실패 메시지
        """
        date = _infer_booking_date(user_message=user_message)
        start_time = _extract_hour(user_message=user_message) or "14:00"
        end_time = _plus_one_hour(start_time=start_time)
        attendee_count = _extract_attendee_count(user_message=user_message) or 4

        candidates = self._meeting_service.search_rooms(attendee_count=attendee_count)
        if not candidates:
            return "수용 인원에 맞는 가용 회의실을 찾지 못했습니다."
        room = candidates[0]
        result = self._meeting_service.book_room(
            request=_build_booking_request(
                date=date,
                start_time=start_time,
                end_time=end_time,
                attendee_count=attendee_count,
                building=str(room.get("building", "")),
                floor=int(room.get("floor", 0)),
                room_name=str(room.get("room_name", "")),
            )
        )
        if result.get("status") != "completed":
            return f"회의실 예약 실패: {result.get('reason', '원인 미상')}"
        booking = result.get("booking", {})
        return (
            f"회의실 예약 완료: {booking.get('date')} {booking.get('start_time')}-{booking.get('end_time')} "
            f"{booking.get('building')} {booking.get('floor')}층 {booking.get('room_name')}"
        )


def _extract_hour(user_message: str) -> str | None:
    """
    사용자 문장에서 시간을 HH:MM 형태로 추출한다.

    Args:
        user_message: 사용자 입력

    Returns:
        추출된 시간 또는 None
    """
    match = re.search(r"(오전|오후)?\s*(\d{1,2})\s*시", user_message)
    if not match:
        return None
    hour = int(match.group(2))
    meridiem = match.group(1) or ""
    if meridiem == "오후" and hour < 12:
        hour += 12
    if meridiem == "오전" and hour == 12:
        hour = 0
    return f"{hour:02d}:00"


def _infer_booking_date(user_message: str) -> str:
    """
    사용자 문장에서 예약 날짜를 추정한다.

    Args:
        user_message: 사용자 입력

    Returns:
        YYYY-MM-DD 날짜 문자열
    """
    text = user_message.strip()
    iso_match = re.search(r"(\d{4}-\d{1,2}-\d{1,2})", text)
    if iso_match:
        return iso_match.group(1)

    now = datetime.now()
    if "내일" in text:
        return (now + timedelta(days=1)).strftime("%Y-%m-%d")
    if "오늘" in text:
        return now.strftime("%Y-%m-%d")
    return now.strftime("%Y-%m-%d")


def _plus_one_hour(start_time: str) -> str:
    """
    시작 시간 문자열에서 1시간 뒤 시각을 계산한다.

    Args:
        start_time: 시작 시간(HH:MM)

    Returns:
        종료 시간(HH:MM)
    """
    hour, minute = start_time.split(":")
    end_hour = (int(hour) + 1) % 24
    return f"{end_hour:02d}:{int(minute):02d}"


def _extract_attendee_count(user_message: str) -> int | None:
    """
    사용자 문장에서 참석 인원 수를 추출한다.

    Args:
        user_message: 사용자 입력

    Returns:
        참석 인원 또는 None
    """
    match = re.search(r"(\d+)\s*명", user_message)
    if not match:
        return None
    return int(match.group(1))


def _can_auto_complete_booking(missing_slots: list[str]) -> bool:
    """
    누락 슬롯이 자동 보정 가능한 수준인지 판정한다.

    Args:
        missing_slots: 누락 슬롯 목록

    Returns:
        자동 보정 가능하면 True
    """
    return set(missing_slots) <= {"end_time"}


def _build_booking_request(
    date: str,
    start_time: str,
    end_time: str,
    attendee_count: int,
    building: str,
    floor: int,
    room_name: str,
) -> BookingRequest:
    """
    BookingRequest 생성 코드를 함수로 분리한다.

    Args:
        date: 날짜
        start_time: 시작 시간
        end_time: 종료 시간
        attendee_count: 인원
        building: 건물
        floor: 층수
        room_name: 회의실명

    Returns:
        BookingRequest 인스턴스
    """
    return BookingRequest(
        date=date,
        start_time=start_time,
        end_time=end_time,
        attendee_count=attendee_count,
        building=building,
        floor=floor,
        room_name=room_name,
        subject="자동 예약",
    )


_TASK_EXECUTION_SERVICE = TaskExecutionService()


def get_task_execution_service() -> TaskExecutionService:
    """
    TaskExecutionService 싱글턴 인스턴스를 반환한다.

    Returns:
        TaskExecutionService 인스턴스
    """
    return _TASK_EXECUTION_SERVICE
