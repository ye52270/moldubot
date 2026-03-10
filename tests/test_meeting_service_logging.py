from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.services.meeting_service import BookingRequest, MeetingRoomService


class MeetingServiceLoggingTest(unittest.TestCase):
    """
    회의실 예약 로깅 동작을 검증한다.
    """

    def _build_service(self, root: Path) -> MeetingRoomService:
        """
        테스트용 회의실/예약 파일을 생성하고 서비스를 반환한다.

        Args:
            root: 임시 디렉터리 경로

        Returns:
            MeetingRoomService 인스턴스
        """
        rooms_path = root / "rooms.json"
        bookings_path = root / "bookings.json"
        rooms_path.write_text(
            json.dumps(
                [
                    {
                        "building": "A",
                        "floor": 10,
                        "room_name": "Alpha",
                        "capacity": 8,
                    }
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        bookings_path.write_text("[]", encoding="utf-8")
        return MeetingRoomService(rooms_path=rooms_path, bookings_path=bookings_path)

    def test_book_room_invalid_datetime_logs_warning(self) -> None:
        """
        날짜 형식이 잘못된 예약 요청은 warning 로그와 실패 응답을 반환해야 한다.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._build_service(root=Path(tmp_dir))
            request = BookingRequest(
                date="bad-date",
                start_time="14:00",
                end_time="15:00",
                attendee_count=4,
                building="A",
                floor=10,
                room_name="Alpha",
                subject="테스트",
            )
            with self.assertLogs("app.services.meeting_service", level="WARNING") as captured:
                result = service.book_room(request=request)
            self.assertEqual("failed", result["status"])
            self.assertIn("유효하지 않은 날짜/시간 형식", captured.output[0])

    def test_book_room_success_logs_info(self) -> None:
        """
        정상 예약 요청은 info 로그와 완료 응답을 반환해야 한다.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._build_service(root=Path(tmp_dir))
            request = BookingRequest(
                date="2099-01-01",
                start_time="14:00",
                end_time="15:00",
                attendee_count=4,
                building="A",
                floor=10,
                room_name="Alpha",
                subject="테스트",
            )
            with self.assertLogs("app.services.meeting_service", level="INFO") as captured:
                result = service.book_room(request=request)
            self.assertEqual("completed", result["status"])
            self.assertTrue(any("회의실 예약 생성 완료" in line for line in captured.output))


if __name__ == "__main__":
    unittest.main()
