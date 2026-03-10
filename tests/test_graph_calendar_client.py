from __future__ import annotations

import types
import unittest
from unittest.mock import MagicMock, patch

from app.integrations.microsoft_graph.calendar_client import GraphCalendarClient


class GraphCalendarClientTest(unittest.TestCase):
    """GraphCalendarClient 동작을 검증한다."""

    def test_create_event_success(self) -> None:
        auth_client = MagicMock()
        auth_client.is_configured.return_value = True
        auth_client.acquire_access_token.return_value = "token-1"

        fake_response = types.SimpleNamespace(
            status_code=201,
            json=lambda: {"id": "event-1", "webLink": "https://outlook.live.com/event/1"},
        )
        with patch(
            "app.integrations.microsoft_graph.calendar_client.requests.post",
            return_value=fake_response,
        ):
            client = GraphCalendarClient(auth_client=auth_client)
            event = client.create_event(
                subject="[회의실] 1801",
                start_iso="2026-03-03T10:00:00",
                end_iso="2026-03-03T11:00:00",
                body_text="본문",
            )

        self.assertIsNotNone(event)
        self.assertEqual("event-1", event.event_id if event else "")
        self.assertEqual("https://outlook.live.com/event/1", event.web_link if event else "")

    def test_create_event_returns_none_when_not_configured(self) -> None:
        auth_client = MagicMock()
        auth_client.is_configured.return_value = False
        client = GraphCalendarClient(auth_client=auth_client)
        event = client.create_event(
            subject="[회의실] 1801",
            start_iso="2026-03-03T10:00:00",
            end_iso="2026-03-03T11:00:00",
            body_text="본문",
        )
        self.assertIsNone(event)

    def test_create_event_includes_attendees_payload(self) -> None:
        auth_client = MagicMock()
        auth_client.is_configured.return_value = True
        auth_client.acquire_access_token.return_value = "token-1"

        captured_payload: dict[str, object] = {}

        def fake_post(url, headers=None, json=None, timeout=10):  # type: ignore[no-untyped-def]
            del url, headers, timeout
            captured_payload.update(json or {})
            return types.SimpleNamespace(
                status_code=201,
                json=lambda: {"id": "event-2", "webLink": "https://outlook.live.com/event/2"},
            )

        with patch("app.integrations.microsoft_graph.calendar_client.requests.post", side_effect=fake_post):
            client = GraphCalendarClient(auth_client=auth_client)
            _ = client.create_event(
                subject="[일정] 점검 회의",
                start_iso="2026-03-03T14:00:00",
                end_iso="2026-03-03T15:00:00",
                body_text="본문",
                attendees=["user1@contoso.com", "user2@contoso.com"],
            )

        attendees = captured_payload.get("attendees")
        self.assertIsInstance(attendees, list)
        self.assertEqual(2, len(attendees if isinstance(attendees, list) else []))


if __name__ == "__main__":
    unittest.main()
