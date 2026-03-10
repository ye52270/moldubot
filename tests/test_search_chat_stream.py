from __future__ import annotations

import unittest
from unittest.mock import MagicMock
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import _encode_stream_event, router


class SearchChatStreamTest(unittest.TestCase):
    """`/search/chat/stream` SSE 응답 계약을 검증한다."""

    def setUp(self) -> None:
        """테스트용 FastAPI 앱/클라이언트를 초기화한다."""
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)

    def test_encode_stream_event_builds_json_payload(self) -> None:
        """SSE 인코더가 event/data 블록을 JSON으로 직렬화해야 한다."""
        text = _encode_stream_event(event="progress", payload={"phase": "processing"})

        self.assertIn("event: progress", text)
        self.assertIn('data: {"phase": "processing"}', text)
        self.assertTrue(text.endswith("\n\n"))

    def test_search_chat_stream_emits_progress_token_and_completed(self) -> None:
        """스트림 엔드포인트는 progress/token/completed 이벤트를 순서대로 내려야 한다."""
        fake_agent = MagicMock()
        fake_agent.stream_execute_turn.return_value = {
            "status": "completed",
            "thread_id": "thread-1",
            "answer": "테스트 응답",
            "interrupts": [],
        }
        fake_agent.get_last_assistant_answer.return_value = "테스트 응답"
        fake_agent.get_last_tool_payload.return_value = {}
        fake_agent.resume_pending_actions.return_value = {
            "status": "completed",
            "thread_id": "thread-1",
            "answer": "요청을 취소했습니다.",
            "interrupts": [],
        }
        def _stream_turn_side_effect(*args, **kwargs):
            on_token = kwargs.get("on_token")
            if callable(on_token):
                on_token("테")
                on_token("스트")
            return {
                "status": "completed",
                "thread_id": "thread-1",
                "answer": "테스트 응답",
                "interrupts": [],
            }

        fake_agent.stream_execute_turn.side_effect = _stream_turn_side_effect
        with patch("app.api.routes.is_openai_key_configured", return_value=True):
            with patch("app.api.routes.get_deep_chat_agent", return_value=fake_agent):
                response = self.client.post(
                    "/search/chat/stream",
                    json={"message": "현재메일 요약"},
                )

        self.assertEqual(200, response.status_code)
        self.assertIn("text/event-stream", response.headers.get("content-type", ""))
        self.assertIn("event: progress", response.text)
        self.assertIn("event: token", response.text)
        self.assertIn("event: completed", response.text)
        self.assertIn("테스트 응답", response.text)
        self.assertIn("elapsed_ms", response.text)

    def test_search_chat_stream_skips_token_when_answer_empty(self) -> None:
        """토큰 콜백이 비어있으면 token 이벤트는 생략되어야 한다."""
        with patch(
            "app.api.routes._run_search_chat",
            return_value={
                "status": "completed",
                "thread_id": "t-1",
                "answer": "",
                "metadata": {"elapsed_ms": 1.0},
            },
        ):
            response = self.client.post(
                "/search/chat/stream",
                json={"message": "테스트"},
            )

        self.assertEqual(200, response.status_code)
        self.assertIn("event: progress", response.text)
        self.assertNotIn("event: token", response.text)
        self.assertIn("event: completed", response.text)

    def test_search_chat_stream_emits_token_for_code_review_query(self) -> None:
        """코드리뷰 질의도 진행 가시성을 위해 token 이벤트를 노출해야 한다."""
        def _run_search_chat_side_effect(*args, **kwargs):
            token_callback = args[2] if len(args) >= 3 else kwargs.get("token_callback")
            if callable(token_callback):
                token_callback("중간")
                token_callback("토큰")
            return {
                "status": "completed",
                "thread_id": "thread-cr-1",
                "answer": "## 코드 리뷰\n최종본",
                "metadata": {"elapsed_ms": 12.0},
            }

        with patch("app.api.routes._run_search_chat", side_effect=_run_search_chat_side_effect):
            response = self.client.post(
                "/search/chat/stream",
                json={"message": "현재메일 코드 리뷰해줘"},
            )

        self.assertEqual(200, response.status_code)
        self.assertIn("event: progress", response.text)
        self.assertIn("event: token", response.text)
        self.assertIn("event: completed", response.text)

    def test_search_chat_stream_prefers_agent_final_answer_before_route_fallback(self) -> None:
        """completed.answer는 agent의 최종 응답(`@after_model`)을 우선 사용해야 한다."""
        fake_agent = MagicMock()
        fake_agent.respond.return_value = ""
        fake_agent.get_last_tool_payload.return_value = {}
        fake_agent.get_last_assistant_answer.return_value = "후처리 완료 응답"
        with patch("app.api.routes.is_openai_key_configured", return_value=True):
            with patch("app.api.routes.get_deep_chat_agent", return_value=fake_agent):
                with patch(
                    "app.api.routes.postprocess_final_answer",
                    side_effect=RuntimeError("route fallback must not run"),
                ):
                    response = self.client.post(
                        "/search/chat/stream",
                        json={"message": "현재메일 요약"},
                    )

        self.assertEqual(200, response.status_code)
        self.assertIn("후처리 완료 응답", response.text)

    def test_search_chat_stream_handles_unexpected_error_as_completed_payload(self) -> None:
        """스트리밍 경로의 비-OpenAI 예외도 completed 이벤트(internal-error)로 반환해야 한다."""
        fake_agent = MagicMock()
        fake_agent.stream_execute_turn = None
        fake_agent.execute_turn.side_effect = RuntimeError("unexpected boom")
        with patch("app.api.routes.is_openai_key_configured", return_value=True):
            with patch("app.api.routes.get_deep_chat_agent", return_value=fake_agent):
                response = self.client.post(
                    "/search/chat/stream",
                    json={"message": "회의실예약"},
                )

        self.assertEqual(200, response.status_code)
        self.assertIn("event: completed", response.text)
        self.assertIn("internal-error", response.text)
        self.assertIn("내부 오류", response.text)

    def test_search_chat_stream_retries_after_auto_dismiss_for_non_action_query(self) -> None:
        """비-실행 질의에서 기존 인터럽트가 남아 있으면 자동 정리 후 재시도해야 한다."""
        fake_agent = MagicMock()
        fake_agent.stream_execute_turn = None
        fake_agent.resume_pending_actions.return_value = {
            "status": "completed",
            "answer": "요청을 취소했습니다.",
            "thread_id": "t-1",
            "interrupts": [],
        }
        with patch("app.api.routes.is_openai_key_configured", return_value=True):
            with patch("app.api.routes.get_deep_chat_agent", return_value=fake_agent):
                with patch(
                    "app.api.routes._execute_agent_turn",
                    side_effect=[
                        {
                            "status": "interrupted",
                            "answer": "회의실/일정/ToDo 실행 전 승인 확인이 필요합니다.",
                            "thread_id": "t-1",
                            "interrupts": [{"interrupt_id": "i-1", "actions": [{"name": "create_outlook_todo"}]}],
                        },
                        {
                            "status": "completed",
                            "answer": "요약 결과",
                            "thread_id": "t-1",
                            "interrupts": [],
                        },
                    ],
                ):
                    response = self.client.post(
                        "/search/chat/stream",
                        json={"message": "현재메일 3~5줄로 요약"},
                    )

        self.assertEqual(200, response.status_code)
        self.assertIn("event: completed", response.text)
        self.assertIn("요약 결과", response.text)
        self.assertNotIn("pending_approval", response.text)
        fake_agent.resume_pending_actions.assert_called_once()


if __name__ == "__main__":
    unittest.main()
