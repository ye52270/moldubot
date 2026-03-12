from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.api.contracts import ChatRequest
from app.api.followup_scope import reset_followup_scope_state_for_test
from app.api.routes import search_chat
from app.services.mail_service import MailRecord


class SearchChatSelectedMailContextTest(unittest.TestCase):
    """선택 메일 컨텍스트가 있어도 `/search/chat`은 LLM 단일 경로를 타야 한다."""

    def setUp(self) -> None:
        """테스트별 follow-up 상태를 초기화한다."""
        reset_followup_scope_state_for_test()

    def test_current_mail_without_email_id_still_uses_deep_agent(self) -> None:
        """현재메일 질의에서 email_id가 없어도 deep-agent 경로로 응답해야 한다."""
        with patch("app.api.routes.clear_current_mail") as clear_current_mail:
            with patch("app.api.routes.is_openai_key_configured", return_value=True):
                with patch("app.api.routes.get_deep_chat_agent") as get_agent:
                    get_agent.return_value.respond.return_value = "LLM 응답"
                    payload = ChatRequest(message="현재메일 요약", email_id="", mailbox_user="")
                    response = search_chat(payload=payload)

        self.assertEqual("deep-agent", response["metadata"]["source"])
        self.assertEqual("LLM 응답", response["answer"])
        self.assertIn("answer_format", response["metadata"])
        self.assertEqual("v1", response["metadata"]["answer_format"]["version"])
        clear_current_mail.assert_called_once()
        called_message = get_agent.return_value.respond.call_args.kwargs["user_message"]
        self.assertIn("현재 선택 메일", called_message)
        self.assertIn("현재메일 요약", called_message)
        self.assertTrue(bool(get_agent.return_value.respond.call_args.kwargs["thread_id"]))

    def test_selected_mail_context_failure_still_uses_deep_agent(self) -> None:
        """선택 메일 조회 실패 시에도 deep-agent 단일 경로로 응답해야 한다."""
        failed_context = SimpleNamespace(status="failed", source="not-found", mail=None, reason="not found")
        with patch("app.api.routes.mail_context_service") as context_service:
            with patch("app.api.routes.clear_current_mail") as clear_current_mail:
                with patch("app.api.routes.is_openai_key_configured", return_value=True):
                    with patch("app.api.routes.get_deep_chat_agent") as get_agent:
                        get_agent.return_value.respond.return_value = "LLM 실패 대체 응답"
                        context_service.get_mail_context.return_value = failed_context
                        payload = ChatRequest(
                            message="현재메일 상세히 요약",
                            email_id="message-1",
                            mailbox_user="user@example.com",
                        )
                        response = search_chat(payload=payload)

        self.assertEqual("deep-agent", response["metadata"]["source"])
        self.assertEqual("LLM 실패 대체 응답", response["answer"])
        clear_current_mail.assert_called_once()
        context_service.get_mail_context.assert_called_once_with(
            message_id="message-1",
            mailbox_user="user@example.com",
        )
        called_message = get_agent.return_value.respond.call_args.kwargs["user_message"]
        self.assertIn("현재 선택 메일", called_message)
        self.assertIn("현재메일 상세히 요약", called_message)

    def test_selected_mail_context_success_uses_deep_agent_not_post_action(self) -> None:
        """선택 메일 컨텍스트 성공 시에도 post-action 대신 deep-agent 단일 경로를 사용해야 한다."""
        cached_context = SimpleNamespace(
            status="completed",
            source="db-cache",
            mail=MailRecord(
                message_id="message-2",
                subject="테스트 메일",
                from_address="sender@example.com",
                received_date="2026-02-28T00:00:00Z",
                body_text="첫 줄입니다. 두 번째 줄입니다.",
                summary_text="요약 결과: 기존 DB 요약",
            ),
            reason="",
        )
        with patch("app.api.routes.mail_context_service") as context_service:
            with patch("app.api.routes.is_openai_key_configured", return_value=True):
                with patch("app.api.routes.get_deep_chat_agent") as get_agent:
                    get_agent.return_value.respond.return_value = "LLM 단일경로 응답"
                    context_service.get_mail_context.return_value = cached_context
                    payload = ChatRequest(
                        message="현재메일 요약",
                        email_id="message-2",
                        mailbox_user="user@example.com",
                    )
                    response = search_chat(payload=payload)

        self.assertEqual("deep-agent", response["metadata"]["source"])
        self.assertEqual("LLM 단일경로 응답", response["answer"])
        evidence_mails = response["metadata"]["evidence_mails"]
        self.assertEqual(1, len(evidence_mails))
        self.assertEqual("message-2", evidence_mails[0]["message_id"])
        self.assertEqual("테스트 메일", evidence_mails[0]["subject"])
        self.assertEqual("", evidence_mails[0]["web_link"])
        context_service.get_mail_context.assert_called_once_with(
            message_id="message-2",
            mailbox_user="user@example.com",
        )
        context_service.run_post_action.assert_not_called()
        called_message = get_agent.return_value.respond.call_args.kwargs["user_message"]
        self.assertIn("현재 선택 메일", called_message)
        self.assertIn("현재메일 요약", called_message)

    def test_selected_mail_context_success_clears_current_mail_after_response(self) -> None:
        """선택 메일 컨텍스트 사용 요청은 응답 후 current_mail 캐시를 정리해야 한다."""
        cached_context = SimpleNamespace(
            status="completed",
            source="db-cache",
            mail=MailRecord(
                message_id="message-3",
                subject="정리 대상 메일",
                from_address="sender@example.com",
                received_date="2026-03-01T00:00:00Z",
                body_text="본문",
                summary_text="요약",
            ),
            reason="",
        )
        with patch("app.api.routes.mail_context_service") as context_service:
            with patch("app.api.routes.is_openai_key_configured", return_value=True):
                with patch("app.api.routes.get_deep_chat_agent") as get_agent:
                    with patch("app.api.routes.clear_current_mail") as clear_current_mail:
                        get_agent.return_value.respond.return_value = "응답"
                        context_service.get_mail_context.return_value = cached_context
                        payload = ChatRequest(
                            message="현재메일 요약",
                            email_id="message-3",
                            mailbox_user="user@example.com",
                        )
                        search_chat(payload=payload)

        clear_current_mail.assert_called_once()

    def test_search_tool_payload_populates_evidence_mails(self) -> None:
        """
        agent의 mail_search tool payload가 있으면 metadata.evidence_mails로 노출되어야 한다.
        """
        with patch("app.api.routes.is_openai_key_configured", return_value=True):
            with patch("app.api.routes.get_deep_chat_agent") as get_agent:
                get_agent.return_value.respond.return_value = "조회 결과입니다."
                get_agent.return_value.get_last_tool_payload.return_value = {
                    "action": "mail_search",
                    "aggregated_summary": ["핵심1", "핵심2"],
                    "results": [
                        {
                            "message_id": "m-10",
                            "subject": "테스트 제목",
                            "received_date": "2026-02-20",
                            "sender_names": "조영득",
                            "web_link": "https://outlook.office.com/mail/m-10",
                        }
                    ],
                }
                payload = ChatRequest(message="지난 주 조영득 관련된 메일 조회", email_id="", mailbox_user="")
                response = search_chat(payload=payload)

        self.assertEqual("deep-agent", response["metadata"]["source"])
        evidence_mails = response["metadata"]["evidence_mails"]
        self.assertEqual(1, len(evidence_mails))
        self.assertEqual("m-10", evidence_mails[0]["message_id"])
        self.assertEqual("조영득", evidence_mails[0]["sender_names"])
        self.assertEqual(["핵심1", "핵심2"], response["metadata"]["aggregated_summary"])
        self.assertEqual(1, response["metadata"]["search_result_count"])

    def test_non_search_tool_payload_does_not_override_selected_mail_evidence(self) -> None:
        """
        mail_search가 아닌 tool payload는 기존 selected-mail 근거메일을 덮어쓰면 안 된다.
        """
        cached_context = SimpleNamespace(
            status="completed",
            source="db-cache",
            mail=MailRecord(
                message_id="message-selected",
                subject="선택 메일 제목",
                from_address="홍길동 <hong@example.com>",
                received_date="2026-03-01T00:00:00Z",
                body_text="본문",
                summary_text="요약",
            ),
            reason="",
        )
        with patch("app.api.routes.mail_context_service") as context_service:
            with patch("app.api.routes.is_openai_key_configured", return_value=True):
                with patch("app.api.routes.get_deep_chat_agent") as get_agent:
                    get_agent.return_value.respond.return_value = "조회 결과입니다."
                    get_agent.return_value.get_last_tool_payload.return_value = {
                        "action": "current_date",
                        "today": "2026-03-01",
                    }
                    context_service.get_mail_context.return_value = cached_context
                    payload = ChatRequest(
                        message="M365 관련 최근메일 3개 조회후 요약해줘",
                        email_id="message-selected",
                        mailbox_user="user@example.com",
                    )
                    response = search_chat(payload=payload)

        evidence_mails = response["metadata"]["evidence_mails"]
        self.assertEqual(1, len(evidence_mails))
        self.assertEqual("message-selected", evidence_mails[0]["message_id"])
        self.assertEqual("선택 메일 제목", evidence_mails[0]["subject"])

    def test_mail_search_empty_results_clears_selected_mail_evidence(self) -> None:
        """
        mail_search payload가 0건이면 selected-mail 근거메일을 비워야 한다.
        """
        cached_context = SimpleNamespace(
            status="completed",
            source="db-cache",
            mail=MailRecord(
                message_id="message-selected",
                subject="선택 메일 제목",
                from_address="홍길동 <hong@example.com>",
                received_date="2026-03-01T00:00:00Z",
                body_text="본문",
                summary_text="요약",
            ),
            reason="",
        )
        with patch("app.api.routes.mail_context_service") as context_service:
            with patch("app.api.routes.is_openai_key_configured", return_value=True):
                with patch("app.api.routes.get_deep_chat_agent") as get_agent:
                    get_agent.return_value.respond.return_value = "검색 결과 없음"
                    get_agent.return_value.get_last_tool_payload.return_value = {
                        "action": "mail_search",
                        "results": [],
                        "count": 0,
                        "aggregated_summary": [],
                    }
                    context_service.get_mail_context.return_value = cached_context
                    payload = ChatRequest(
                        message="M365 관련 최근메일 3개 조회후 요약해줘",
                        email_id="message-selected",
                        mailbox_user="user@example.com",
                    )
                    response = search_chat(payload=payload)

        self.assertEqual([], response["metadata"]["evidence_mails"])
        self.assertEqual([], response["metadata"]["aggregated_summary"])
        self.assertEqual(0, response["metadata"]["search_result_count"])

    def test_thread_id_is_passed_to_agent_when_provided(self) -> None:
        """
        요청에 thread_id가 있으면 동일 값이 agent 호출에 전달되어야 한다.
        """
        with patch("app.api.routes.is_openai_key_configured", return_value=True):
            with patch("app.api.routes.get_deep_chat_agent") as get_agent:
                get_agent.return_value.respond.return_value = "응답"
                payload = ChatRequest(message="현재메일 요약", thread_id="thread-provided")
                response = search_chat(payload=payload)

        self.assertEqual("thread-provided", response["thread_id"])
        called_kwargs = get_agent.return_value.respond.call_args.kwargs
        self.assertEqual("thread-provided", called_kwargs["thread_id"])
        self.assertIn("현재 선택 메일", called_kwargs["user_message"])
        self.assertIn("현재메일 요약", called_kwargs["user_message"])

    def test_thread_id_is_generated_and_reused_for_agent_call(self) -> None:
        """
        요청에 thread_id가 없으면 자동 생성된 값이 agent 호출/응답에 동일 적용되어야 한다.
        """
        with patch("app.api.routes.is_openai_key_configured", return_value=True):
            with patch("app.api.routes.get_deep_chat_agent") as get_agent:
                get_agent.return_value.respond.return_value = "응답"
                payload = ChatRequest(message="현재메일 요약", thread_id=None)
                response = search_chat(payload=payload)

        called_kwargs = get_agent.return_value.respond.call_args.kwargs
        self.assertEqual(response["thread_id"], called_kwargs["thread_id"])
        self.assertTrue(str(response["thread_id"]).startswith("outlook_"))

    def test_unexpected_agent_error_returns_internal_error_message(self) -> None:
        """
        OpenAIError 외 예외가 발생해도 500 대신 내부 오류 응답을 반환해야 한다.
        """
        with patch("app.api.routes.is_openai_key_configured", return_value=True):
            with patch("app.api.routes.get_deep_chat_agent") as get_agent:
                get_agent.return_value.execute_turn.side_effect = RuntimeError("unexpected boom")
                payload = ChatRequest(message="회의실예약", thread_id="thread-error-1")
                response = search_chat(payload=payload)

        self.assertEqual("completed", response["status"])
        self.assertEqual("internal-error", response["metadata"]["source"])
        self.assertIn("내부 오류", response["answer"])

if __name__ == "__main__":
    unittest.main()
