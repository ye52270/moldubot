from __future__ import annotations

import unittest
from unittest.mock import patch

from app.api.contracts import ChatRequest
from app.api.routes import search_chat


class SearchChatHitlTest(unittest.TestCase):
    """`/search/chat`의 HIL 인터럽트 응답 계약을 검증한다."""

    def test_returns_pending_approval_when_agent_interrupts(self) -> None:
        """에이전트가 인터럽트 상태를 반환하면 pending_approval 응답이어야 한다."""
        interrupted_result = {
            "status": "interrupted",
            "thread_id": "thread-hitl-1",
            "answer": "할일 등록 전 확인이 필요합니다.",
            "interrupts": [
                {
                    "interrupt_id": "interrupt-1",
                    "actions": [
                        {
                            "name": "create_outlook_todo",
                            "args": {"title": "API 오류 확인", "due_date": "2026-03-05"},
                            "description": "ToDo 등록 승인 요청",
                            "allowed_decisions": ["approve", "reject"],
                        }
                    ],
                }
            ],
        }
        with patch("app.api.routes.is_openai_key_configured", return_value=True):
            with patch("app.api.routes.get_deep_chat_agent") as get_agent:
                get_agent.return_value.execute_turn.return_value = interrupted_result
                payload = ChatRequest(message="현재메일 요약해서 todo 등록해줘", thread_id="thread-hitl-1")
                response = search_chat(payload=payload)

        self.assertEqual("pending_approval", response["status"])
        self.assertEqual("thread-hitl-1", response["thread_id"])
        self.assertIn("confirm", response["metadata"])
        self.assertTrue(response["metadata"]["confirm"]["required"])
        self.assertEqual("interrupt-1", response["metadata"]["confirm"]["confirm_token"])
        self.assertEqual("create_outlook_todo", response["metadata"]["confirm"]["actions"][0]["name"])


if __name__ == "__main__":
    unittest.main()
