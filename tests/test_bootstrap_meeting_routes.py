from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.bootstrap_routes import router
from app.integrations.microsoft_graph.calendar_client import GraphCalendarEvent


class BootstrapMeetingRoutesTest(unittest.TestCase):
    """bootstrap 회의실 라우트 계약을 검증한다."""

    def setUp(self) -> None:
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)

    def test_meeting_rooms_returns_building_floor_room_depth(self) -> None:
        fake_rooms = [
            {"building": "sku-tower", "floor": 18, "room_name": "1801", "capacity": 8},
            {"building": "sku-tower", "floor": 18, "room_name": "1803", "capacity": 10},
            {"building": "sku-tower", "floor": 19, "room_name": "1901", "capacity": 6},
        ]
        with patch("app.api.bootstrap_meeting_calendar_routes.load_meeting_rooms", return_value=fake_rooms):
            building_resp = self.client.get("/api/meeting-rooms")
            floor_resp = self.client.get("/api/meeting-rooms?building=sku-tower")
            room_resp = self.client.get("/api/meeting-rooms?building=sku-tower&floor=18")

        self.assertEqual(200, building_resp.status_code)
        self.assertEqual(1, building_resp.json().get("count"))
        self.assertEqual(2, floor_resp.json().get("count"))
        self.assertEqual(2, room_resp.json().get("count"))

    def test_meeting_room_book_creates_graph_event(self) -> None:
        fake_rooms = [{"building": "sku-tower", "floor": 18, "room_name": "1801", "capacity": 8}]
        with patch("app.api.bootstrap_meeting_calendar_routes.load_meeting_rooms", return_value=fake_rooms):
            with patch(
                "app.api.bootstrap_meeting_calendar_routes.calendar_client.create_event",
                return_value=GraphCalendarEvent(event_id="event-123", web_link="https://outlook.live.com/event/123"),
            ) as mocked_create_event:
                response = self.client.post(
                    "/api/meeting-rooms/book",
                    json={
                        "building": "sku-tower",
                        "floor": 18,
                        "room_name": "1801",
                        "date": "2026-03-03",
                        "start_time": "10:00",
                        "end_time": "11:00",
                        "attendee_count": 4,
                        "subject": "M365 구축 일정 논의",
                    },
                )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("completed", payload.get("status"))
        self.assertEqual("[회의실] 1801", payload.get("booking", {}).get("subject"))
        self.assertEqual("event-123", payload.get("event", {}).get("id"))
        self.assertIn("회의 안건: M365 구축 일정 논의", str(mocked_create_event.call_args.kwargs.get("body_text")))

    def test_meeting_room_book_normalizes_relative_date(self) -> None:
        fake_rooms = [{"building": "sku-tower", "floor": 18, "room_name": "1801", "capacity": 8}]
        with patch("app.api.bootstrap_meeting_calendar_routes.load_meeting_rooms", return_value=fake_rooms):
            with patch("app.api.bootstrap_meeting_calendar_routes.resolve_booking_date_token", return_value="2026-03-04"):
                with patch(
                    "app.api.bootstrap_meeting_calendar_routes.calendar_client.create_event",
                    return_value=GraphCalendarEvent(event_id="event-777", web_link="https://outlook.live.com/event/777"),
                ) as mocked_create_event:
                    response = self.client.post(
                        "/api/meeting-rooms/book",
                        json={
                            "building": "sku-tower",
                            "floor": 18,
                            "room_name": "1801",
                            "date": "내일",
                            "start_time": "10:00",
                            "end_time": "11:00",
                            "attendee_count": 4,
                            "subject": "운영 점검",
                        },
                    )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("completed", payload.get("status"))
        self.assertEqual("2026-03-04", payload.get("booking", {}).get("date"))
        self.assertEqual("2026-03-04T10:00:00", mocked_create_event.call_args.kwargs.get("start_iso"))

    def test_meeting_room_suggestion_from_current_mail(self) -> None:
        fake_mail = SimpleNamespace(
            subject="FW: M365 구축 일정 협의 요청",
            body_text="To: kim@sk.com;lee@sk.com\n2026-03-03 10:00~11:00 협의 필요",
            summary_text="M365 구축 일정 협의 및 테스트 일정 확인 필요",
        )
        fake_rooms = [
            {"building": "sku-tower", "floor": 18, "room_name": "1801", "capacity": 8},
            {"building": "sku-tower", "floor": 19, "room_name": "1901", "capacity": 6},
        ]
        fake_result = SimpleNamespace(status="completed", source="db-cache", reason="", mail=fake_mail)
        with patch("app.api.bootstrap_meeting_calendar_routes.mail_context_service.get_mail_context", return_value=fake_result):
            with patch("app.api.bootstrap_meeting_calendar_routes.load_meeting_rooms", return_value=fake_rooms):
                response = self.client.post(
                    "/api/meeting-rooms/suggest-from-current-mail",
                    json={"message_id": "mail-1", "mailbox_user": "user@example.com"},
                )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("completed", payload.get("status"))
        proposal = payload.get("proposal", {})
        self.assertTrue(isinstance(proposal.get("major_issues"), list))
        self.assertEqual("M365 구축 일정 협의 및 테스트 일정 확인 필요", proposal.get("summary_text"))
        self.assertEqual("M365 구축 일정 협의 및 테스트 일정 확인 필요", proposal.get("major_issues", [""])[0])
        self.assertTrue(isinstance(proposal.get("time_candidates"), list))
        self.assertTrue(isinstance(proposal.get("room_candidates"), list))
        self.assertGreaterEqual(int(proposal.get("attendee_count", 0)), 2)


if __name__ == "__main__":
    unittest.main()
