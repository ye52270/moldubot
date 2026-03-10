from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.bootstrap_routes import router


class BootstrapHitlConfirmTest(unittest.TestCase):
    """`/search/chat/confirm`의 HIL 재개 계약을 검증한다."""

    def setUp(self) -> None:
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)

    def test_confirm_approved_resumes_pending_actions(self) -> None:
        with patch("app.api.bootstrap_routes.get_deep_chat_agent") as get_agent:
            get_agent.return_value.resume_pending_actions.return_value = {
                "status": "completed",
                "thread_id": "thread-hitl-1",
                "answer": "승인 처리 후 ToDo를 등록했습니다.",
                "interrupts": [],
            }
            response = self.client.post(
                "/search/chat/confirm",
                json={
                    "thread_id": "thread-hitl-1",
                    "approved": True,
                    "confirm_token": "interrupt-1",
                },
            )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("completed", payload.get("status"))
        self.assertEqual("thread-hitl-1", payload.get("thread_id"))
        self.assertIn("ToDo", payload.get("answer", ""))


if __name__ == "__main__":
    unittest.main()
