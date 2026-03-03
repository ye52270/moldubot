from __future__ import annotations

import unittest
from unittest.mock import patch

from app.agents.tools_schedule import create_outlook_calendar_event
from app.integrations.microsoft_graph.calendar_client import GraphCalendarEvent


class ToolsScheduleDateResolutionTest(unittest.TestCase):
    """
    일정 생성 tool의 상대 날짜 해석 동작을 검증한다.
    """

    def test_create_outlook_calendar_event_normalizes_relative_date(self) -> None:
        """
        상대 날짜 입력은 절대 날짜로 변환되어 Graph 호출에 반영되어야 한다.
        """
        with patch("app.agents.tools_schedule.resolve_booking_date_token", return_value="2026-03-04"):
            with patch("app.agents.tools_schedule._CALENDAR_CLIENT") as calendar_client:
                calendar_client.create_event.return_value = GraphCalendarEvent(
                    event_id="event-1",
                    web_link="https://outlook.live.com/calendar/item/1",
                )
                payload = create_outlook_calendar_event.func(
                    subject="점검 일정",
                    date="내일",
                    start_time="09:00",
                    end_time="10:00",
                    body="운영 점검",
                    attendees=["owner@example.com"],
                )

        self.assertEqual("completed", payload["status"])
        self.assertEqual("2026-03-04", payload["event"]["date"])
        call = calendar_client.create_event.call_args.kwargs
        self.assertEqual("2026-03-04T09:00:00", call["start_iso"])
        self.assertEqual("2026-03-04T10:00:00", call["end_iso"])


if __name__ == "__main__":
    unittest.main()
