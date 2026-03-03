from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.bootstrap_routes import router as bootstrap_router
from app.api.routes import router


class ChatEvalRoutesTest(unittest.TestCase):
    """`/qa/chat-eval/*` API 계약을 검증한다."""

    def setUp(self) -> None:
        """테스트용 FastAPI 앱을 초기화한다."""
        app = FastAPI()
        app.include_router(router)
        app.include_router(bootstrap_router)
        self.client = TestClient(app)

    def test_run_endpoint_uses_request_base_url_when_chat_url_missing(self) -> None:
        """`chat_url` 미지정 시 요청 base URL + `/search/chat`을 사용해야 한다."""
        fake_report = {"summary": {"total_cases": 1}}

        with patch("app.api.bootstrap_ops_routes.run_chat_eval_session", return_value=fake_report) as mocked:
            response = self.client.post(
                "/qa/chat-eval/run",
                json={
                    "chat_url": "",
                    "judge_model": "gpt-4o-mini",
                    "case_ids": ["mail-01"],
                    "request_timeout_sec": 20,
                },
            )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("completed", payload.get("status"))
        self.assertEqual(fake_report, payload.get("report"))
        called = mocked.call_args.kwargs
        self.assertEqual("http://testserver/search/chat", called["chat_url"])
        self.assertEqual(20, called["request_timeout_sec"])
        self.assertEqual(["mail-01"], called["case_ids"])

    def test_latest_endpoint_returns_not_found_when_absent(self) -> None:
        """최근 리포트가 없으면 not-found 상태를 반환해야 한다."""
        with patch("app.api.bootstrap_ops_routes.load_latest_chat_eval_report", return_value=None):
            response = self.client.get("/qa/chat-eval/latest")

        self.assertEqual(200, response.status_code)
        self.assertEqual({"status": "not-found"}, response.json())

    def test_run_endpoint_requires_mailbox_user_when_selected_email_id_present(self) -> None:
        """selected_email_id 제공 시 mailbox_user 누락이면 400을 반환해야 한다."""
        response = self.client.post(
            "/qa/chat-eval/run",
            json={
                "chat_url": "",
                "judge_model": "gpt-4o-mini",
                "selected_email_id": "AQMkAD...",
                "mailbox_user": "",
            },
        )
        self.assertEqual(400, response.status_code)
        self.assertIn("mailbox_user", str(response.json()))

    def test_run_endpoint_returns_json_error_when_service_raises(self) -> None:
        """서비스 예외 발생 시 500 HTML 대신 JSON 에러를 반환해야 한다."""
        with patch("app.api.bootstrap_ops_routes.run_chat_eval_session", side_effect=RuntimeError("boom")):
            response = self.client.post(
                "/qa/chat-eval/run",
                json={
                    "chat_url": "http://testserver/search/chat",
                    "judge_model": "gpt-4o-mini",
                    "case_ids": ["mail-01"],
                    "request_timeout_sec": 20,
                },
            )

        self.assertEqual(502, response.status_code)
        payload = response.json()
        self.assertIn("detail", payload)
        self.assertIn("chat_eval_run_failed", str(payload["detail"]))


if __name__ == "__main__":
    unittest.main()
