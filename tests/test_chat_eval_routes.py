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
        self.assertEqual(None, called["cases_file"])

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

    def test_run_endpoint_forwards_cases_file(self) -> None:
        """run API는 cases_file 값을 서비스로 전달해야 한다."""
        fake_report = {"summary": {"total_cases": 1}}
        with patch("app.api.bootstrap_ops_routes.run_chat_eval_session", return_value=fake_report) as mocked:
            response = self.client.post(
                "/qa/chat-eval/run",
                json={
                    "chat_url": "http://testserver/search/chat",
                    "cases_file": "testprompt.md",
                },
            )
        self.assertEqual(200, response.status_code)
        called = mocked.call_args.kwargs
        self.assertEqual("testprompt.md", called["cases_file"])

    def test_cases_endpoint_forwards_cases_file_query(self) -> None:
        """cases API는 querystring cases_file을 서비스로 전달해야 한다."""
        with patch("app.api.bootstrap_ops_routes.list_chat_eval_cases", return_value=[]) as mocked:
            response = self.client.get("/qa/chat-eval/cases?cases_file=testprompt.md")
        self.assertEqual(200, response.status_code)
        called = mocked.call_args.kwargs
        self.assertEqual("testprompt.md", called["cases_file"])

    def test_defaults_endpoint_uses_env_judge_model(self) -> None:
        """defaults API는 MOLDUBOT_JUDGE_MODEL 값을 기본 Judge로 반환해야 한다."""
        with patch.dict("os.environ", {"MOLDUBOT_JUDGE_MODEL": "claude-haiku-4-5-20251001"}, clear=False):
            response = self.client.get("/qa/chat-eval/defaults")
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("completed", payload.get("status"))
        defaults = payload.get("defaults") or {}
        self.assertEqual("claude-haiku-4-5-20251001", defaults.get("judge_model"))
        self.assertEqual("jaeyoung_dev@outlook.com", defaults.get("mailbox_user"))

    def test_history_endpoint_returns_runs(self) -> None:
        """history API는 실행 이력 목록을 반환해야 한다."""
        fake_runs = [{"run_no": 3, "pass_rate": 82.0}]
        with patch("app.api.bootstrap_ops_routes.list_chat_eval_runs", return_value=fake_runs):
            response = self.client.get("/qa/chat-eval/history?limit=10")
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("completed", payload.get("status"))
        self.assertEqual(1, payload.get("count"))
        self.assertEqual(fake_runs, payload.get("runs"))

    def test_history_detail_endpoint_returns_not_found(self) -> None:
        """history detail API는 없는 차수에 대해 404를 반환해야 한다."""
        with patch("app.api.bootstrap_ops_routes.get_chat_eval_run", return_value=None):
            response = self.client.get("/qa/chat-eval/history/999")
        self.assertEqual(404, response.status_code)
        self.assertIn("chat_eval_history_not_found", str(response.json()))

    def test_pipeline_run_endpoint_returns_pipeline_report(self) -> None:
        """파이프라인 실행 API는 pipeline_report를 반환해야 한다."""
        fake_pipeline_report = {"quality_gate": {"passed": True}, "comparison": {"regression_count": 0}}
        with patch("app.api.bootstrap_ops_routes.run_chat_eval_pipeline", return_value=fake_pipeline_report) as mocked:
            response = self.client.post(
                "/qa/chat-eval/pipeline/run",
                json={
                    "chat_url": "",
                    "judge_model": "gpt-5-mini",
                    "min_pass_rate": 80.0,
                    "min_avg_score": 3.0,
                    "allow_regression_cases": 1,
                },
            )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("completed", payload.get("status"))
        self.assertEqual(fake_pipeline_report, payload.get("pipeline_report"))
        called = mocked.call_args.kwargs
        self.assertEqual("http://testserver/search/chat", called["chat_url"])

    def test_pipeline_run_endpoint_forwards_cases_file(self) -> None:
        """pipeline run API는 cases_file 값을 전달해야 한다."""
        fake_pipeline_report = {"quality_gate": {"passed": True}}
        with patch("app.api.bootstrap_ops_routes.run_chat_eval_pipeline", return_value=fake_pipeline_report) as mocked:
            response = self.client.post(
                "/qa/chat-eval/pipeline/run",
                json={"chat_url": "http://testserver/search/chat", "cases_file": "testprompt.md"},
            )
        self.assertEqual(200, response.status_code)
        called = mocked.call_args.kwargs
        self.assertEqual("testprompt.md", called["cases_file"])

    def test_pipeline_latest_endpoint_returns_not_found(self) -> None:
        """최근 파이프라인 리포트가 없으면 not-found를 반환해야 한다."""
        with patch("app.api.bootstrap_ops_routes.load_latest_chat_eval_pipeline_report", return_value=None):
            response = self.client.get("/qa/chat-eval/pipeline/latest")
        self.assertEqual(200, response.status_code)
        self.assertEqual({"status": "not-found"}, response.json())

    def test_pipeline_download_endpoint_returns_markdown(self) -> None:
        """파이프라인 다운로드 API는 markdown 포맷을 반환해야 한다."""
        fake_pipeline_report = {"quality_gate": {"passed": True}}
        with patch(
            "app.api.bootstrap_ops_routes.load_latest_chat_eval_pipeline_report",
            return_value=fake_pipeline_report,
        ):
            with patch(
                "app.api.bootstrap_ops_routes.render_pipeline_report_markdown",
                return_value="# report",
            ):
                response = self.client.get("/qa/chat-eval/pipeline/download?format=md")
        self.assertEqual(200, response.status_code)
        self.assertIn("text/markdown", str(response.headers.get("content-type")))
        self.assertIn("# report", response.text)


if __name__ == "__main__":
    unittest.main()
