from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class BookingRequest:
    """
    회의실 예약 입력 데이터.

    Attributes:
        date: 예약 날짜(YYYY-MM-DD)
        start_time: 시작 시간(HH:MM)
        end_time: 종료 시간(HH:MM)
        attendee_count: 참석 인원
        building: 건물명
        floor: 층수
        room_name: 회의실명
        subject: 회의 제목
    """

    date: str
    start_time: str
    end_time: str
    attendee_count: int
    building: str
    floor: int
    room_name: str
    subject: str


class MeetingRoomService:
    """
    로컬 JSON 기반 회의실 조회/예약 서비스를 제공한다.
    """

    def __init__(self, rooms_path: Path, bookings_path: Path) -> None:
        """
        서비스 인스턴스를 초기화한다.

        Args:
            rooms_path: 회의실 마스터 데이터 경로
            bookings_path: 예약 데이터 저장 경로
        """
        self._rooms_path = rooms_path
        self._bookings_path = bookings_path

    def search_rooms(
        self,
        attendee_count: int,
        building: str = "",
        floor: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        조건에 맞는 회의실을 조회한다.

        Args:
            attendee_count: 최소 수용 인원
            building: 건물 필터
            floor: 층수 필터

        Returns:
            조회된 회의실 목록
        """
        rooms = _load_json_list(path=self._rooms_path)
        result: list[dict[str, Any]] = []
        for room in rooms:
            capacity = int(room.get("capacity") or 0)
            if attendee_count > 0 and capacity < attendee_count:
                continue
            if building and str(room.get("building", "")).strip() != building.strip():
                continue
            if floor is not None and int(room.get("floor", -1)) != int(floor):
                continue
            result.append(room)
        return result

    def book_room(self, request: BookingRequest) -> dict[str, Any]:
        """
        회의실 예약을 생성한다. 동일 슬롯 충돌 시 실패를 반환한다.

        Args:
            request: 예약 요청 데이터

        Returns:
            예약 결과 사전
        """
        if not self._is_valid_datetime(request.date, request.start_time, request.end_time):
            return {"status": "failed", "reason": "date/time 형식이 유효하지 않습니다."}

        bookings = _load_json_list(path=self._bookings_path)
        if _has_conflict(bookings=bookings, request=request):
            return {"status": "failed", "reason": "동일 시간대 예약이 이미 존재합니다."}

        booking = {
            "date": request.date,
            "start_time": request.start_time,
            "end_time": request.end_time,
            "attendee_count": request.attendee_count,
            "building": request.building,
            "floor": request.floor,
            "room_name": request.room_name,
            "subject": request.subject,
        }
        bookings.append(booking)
        _write_json_list(path=self._bookings_path, payload=bookings)
        logger.info("회의실 예약 생성 완료: %s", booking)
        return {"status": "completed", "booking": booking}

    def _is_valid_datetime(self, date: str, start_time: str, end_time: str) -> bool:
        """
        입력된 날짜/시간 형식 유효성을 검증한다.

        Args:
            date: 날짜 문자열
            start_time: 시작 시각 문자열
            end_time: 종료 시각 문자열

        Returns:
            유효하면 True
        """
        try:
            start_dt = datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H:%M")
            end_dt = datetime.strptime(f"{date} {end_time}", "%Y-%m-%d %H:%M")
        except ValueError:
            return False
        return end_dt > start_dt


def _load_json_list(path: Path) -> list[dict[str, Any]]:
    """
    JSON 리스트 파일을 읽어 사전 목록으로 반환한다.

    Args:
        path: JSON 파일 경로

    Returns:
        사전 목록. 파일이 없거나 깨졌으면 빈 리스트
    """
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("JSON 파싱 실패: %s", path)
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _write_json_list(path: Path, payload: list[dict[str, Any]]) -> None:
    """
    사전 목록을 JSON 파일로 저장한다.

    Args:
        path: 출력 파일 경로
        payload: 저장할 데이터 목록
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _has_conflict(bookings: list[dict[str, Any]], request: BookingRequest) -> bool:
    """
    기존 예약 목록과 입력 예약의 시간 충돌 여부를 검사한다.

    Args:
        bookings: 기존 예약 목록
        request: 신규 예약 요청

    Returns:
        충돌이 있으면 True
    """
    req_start = datetime.strptime(f"{request.date} {request.start_time}", "%Y-%m-%d %H:%M")
    req_end = datetime.strptime(f"{request.date} {request.end_time}", "%Y-%m-%d %H:%M")

    for booking in bookings:
        if str(booking.get("date", "")) != request.date:
            continue
        if str(booking.get("building", "")) != request.building:
            continue
        if int(booking.get("floor", -1)) != request.floor:
            continue
        if str(booking.get("room_name", "")) != request.room_name:
            continue

        start = datetime.strptime(f"{request.date} {booking.get('start_time', '00:00')}", "%Y-%m-%d %H:%M")
        end = datetime.strptime(f"{request.date} {booking.get('end_time', '00:00')}", "%Y-%m-%d %H:%M")
        if req_start < end and req_end > start:
            return True
    return False

