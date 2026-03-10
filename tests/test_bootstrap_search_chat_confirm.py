from __future__ import annotations

import unittest
from unittest.mock import patch

from app.api.bootstrap_routes import search_chat_confirm
from app.api.contracts import ConfirmRequest


class BootstrapSearchChatConfirmTest(unittest.TestCase):
    """`/search/chat/confirm`의 예약 이벤트 메타데이터 포함 여부를 검증한다."""

    def test_includes_booking_event_when_meeting_tool_completed(self) -> None:
        """회의실 예약 도구 payload가 있으면 booking_event를 metadata에 포함한다."""
        with patch("app.api.bootstrap_routes.get_deep_chat_agent") as get_agent:
            agent = get_agent.return_value
            agent.resume_pending_actions.return_value = {
                "status": "completed",
                "thread_id": "thread-1",
                "answer": "회의실 예약이 완료되었습니다.",
                "interrupts": [],
            }
            agent.get_last_tool_payload.return_value = {
                "action": "book_meeting_room",
                "event": {
                    "id": "evt-1",
                    "web_link": "https://outlook.live.com/calendar/item/evt-1",
                },
            }
            response = search_chat_confirm(
                payload=ConfirmRequest(
                    thread_id="thread-1",
                    approved=True,
                    confirm_token="interrupt-1",
                )
            )

        self.assertEqual("completed", response["status"])
        self.assertEqual(
            "https://outlook.live.com/calendar/item/evt-1",
            response["metadata"]["booking_event"]["web_link"],
        )

    def test_includes_todo_task_when_todo_tool_completed(self) -> None:
        """할 일 생성 payload가 있으면 todo_task 메타데이터를 포함한다."""
        with patch("app.api.bootstrap_routes.get_deep_chat_agent") as get_agent:
            agent = get_agent.return_value
            agent.resume_pending_actions.return_value = {
                "status": "completed",
                "thread_id": "thread-2",
                "answer": "할 일 등록이 완료되었습니다.",
                "interrupts": [],
            }
            agent.get_last_tool_payload.return_value = {
                "action": "create_outlook_todo",
                "task": {
                    "id": "task-1",
                    "web_link": "https://outlook.live.com/tasks/item/task-1",
                    "title": "디자인 검토",
                    "due_date": "2026-03-05",
                },
            }
            response = search_chat_confirm(
                payload=ConfirmRequest(
                    thread_id="thread-2",
                    approved=True,
                    confirm_token="interrupt-2",
                )
            )

        self.assertEqual("completed", response["status"])
        self.assertEqual(
            "https://outlook.live.com/tasks/item/task-1",
            response["metadata"]["todo_task"]["web_link"],
        )
        self.assertEqual("디자인 검토", response["metadata"]["todo_task"]["title"])

    def test_includes_booking_event_when_calendar_tool_completed(self) -> None:
        """일정 생성 도구 payload가 있으면 booking_event 메타데이터를 포함한다."""
        with patch("app.api.bootstrap_routes.get_deep_chat_agent") as get_agent:
            agent = get_agent.return_value
            agent.resume_pending_actions.return_value = {
                "status": "completed",
                "thread_id": "thread-3",
                "answer": "일정 등록이 완료되었습니다.",
                "interrupts": [],
            }
            agent.get_last_tool_payload.return_value = {
                "action": "create_outlook_calendar_event",
                "event": {
                    "id": "evt-2",
                    "web_link": "https://outlook.live.com/calendar/item/evt-2",
                },
            }
            response = search_chat_confirm(
                payload=ConfirmRequest(
                    thread_id="thread-3",
                    approved=True,
                    confirm_token="interrupt-3",
                )
            )

        self.assertEqual("completed", response["status"])
        self.assertEqual("evt-2", response["metadata"]["booking_event"]["id"])

    def test_includes_next_actions_when_confirm_completed(self) -> None:
        """승인 완료 응답은 후속 next_actions를 포함해야 한다."""
        with (
            patch("app.api.bootstrap_routes.get_deep_chat_agent") as get_agent,
            patch("app.api.bootstrap_routes.recommend_next_actions") as recommend,
        ):
            agent = get_agent.return_value
            agent.resume_pending_actions.return_value = {
                "status": "completed",
                "thread_id": "thread-4",
                "answer": "할 일 등록이 완료되었습니다.",
                "interrupts": [],
            }
            agent.get_last_tool_payload.return_value = {
                "action": "create_outlook_todo",
                "task": {
                    "id": "task-4",
                    "web_link": "https://outlook.live.com/tasks/item/task-4",
                    "title": "검토",
                    "due_date": "2026-03-08",
                },
            }
            recommend.return_value = [
                {
                    "action_id": "search_related_mails",
                    "title": "관련 메일 추가 조회",
                    "description": "동일 이슈 메일 조회",
                    "query": "이 주제 관련 메일 최근순으로 5개 조회해줘",
                    "priority": "high",
                }
            ]
            response = search_chat_confirm(
                payload=ConfirmRequest(
                    thread_id="thread-4",
                    approved=True,
                    confirm_token="interrupt-4",
                )
            )

        self.assertEqual("completed", response["status"])
        self.assertEqual(1, len(response["metadata"]["next_actions"]))
        self.assertEqual("search_related_mails", response["metadata"]["next_actions"][0]["action_id"])

    def test_returns_failed_with_tool_reason_when_approved_tool_execution_failed(self) -> None:
        """승인 이후 tool 실패 payload가 오면 failed 상태와 실패 사유를 응답해야 한다."""
        with patch("app.api.bootstrap_routes.get_deep_chat_agent") as get_agent:
            agent = get_agent.return_value
            agent.resume_pending_actions.return_value = {
                "status": "completed",
                "thread_id": "thread-5",
                "answer": "",
                "interrupts": [],
            }
            agent.get_last_tool_payload.return_value = {
                "status": "failed",
                "reason": "Outlook ToDo 생성에 실패했습니다. Graph 설정/로그인을 확인해 주세요.",
            }

            response = search_chat_confirm(
                payload=ConfirmRequest(
                    thread_id="thread-5",
                    approved=True,
                    confirm_token="interrupt-5",
                )
            )

        self.assertEqual("failed", response["status"])
        self.assertIn("Outlook ToDo 생성에 실패", response["answer"])
        self.assertEqual([], response["metadata"]["next_actions"])

    def test_uses_prompt_variant_specific_agent_on_confirm(self) -> None:
        """confirm 요청의 prompt_variant가 있으면 동일 variant 에이전트를 사용해야 한다."""
        with patch("app.api.bootstrap_routes.get_deep_chat_agent") as get_agent:
            agent = get_agent.return_value
            agent.resume_pending_actions.return_value = {
                "status": "completed",
                "thread_id": "thread-6",
                "answer": "승인 완료",
                "interrupts": [],
            }
            agent.get_last_tool_payload.return_value = {}
            response = search_chat_confirm(
                payload=ConfirmRequest(
                    thread_id="thread-6",
                    approved=True,
                    confirm_token="interrupt-6",
                    prompt_variant="quality_structured_json_strict",
                )
            )

        get_agent.assert_called_once_with(prompt_variant="quality_structured_json_strict")
        self.assertEqual("completed", response["status"])


if __name__ == "__main__":
    unittest.main()
