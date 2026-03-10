from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.agents.intent_schema import (
    DateFilter,
    DateFilterMode,
    ExecutionStep,
    IntentDecomposition,
    IntentOutputFormat,
    IntentTaskType,
)
from app.api.contracts import ChatRequest
from app.api.search_chat_flow import run_search_chat
from app.services.mail_service import MailRecord


class SearchChatFlowFastLaneTest(unittest.TestCase):
    """현재메일 요약 fast-lane 동작을 검증한다."""

    def test_current_mail_summary_cache_hit_uses_single_call_fast_lane(self) -> None:
        """summarize_mail+read_current_mail + cache-hit이면 deep-agent 대신 fast-lane을 사용해야 한다."""
        decomposition = IntentDecomposition(
            original_query="현재메일 요약해줘",
            steps=[ExecutionStep.SUMMARIZE_MAIL, ExecutionStep.READ_CURRENT_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.SUMMARY,
            output_format=IntentOutputFormat.STRUCTURED_TEMPLATE,
            confidence=0.9,
        )
        cached_context = SimpleNamespace(
            status="completed",
            source="db-cache",
            reason="",
            mail=MailRecord(
                message_id="m-fast",
                subject="테스트 메일",
                from_address="sender@example.com",
                received_date="2026-03-10T03:38:14Z",
                body_text="본문",
                summary_text="요약",
            ),
        )
        with (
            patch("app.api.search_chat_flow.parse_intent_decomposition_safely", return_value=decomposition),
            patch("app.api.search_chat_flow.mail_context_service.get_mail_context", return_value=cached_context),
            patch("app.api.search_chat_flow.is_openai_key_configured", return_value=True),
            patch("app.api.search_chat_flow.invoke_text_messages", return_value='{"format_type":"standard_summary","title":"테스트"}'),
            patch("app.api.search_chat_flow.run_mail_post_action", return_value={"action": "current_mail", "status": "completed"}),
            patch("app.api.search_chat_flow.get_deep_chat_agent") as get_agent_mock,
            patch("app.api.search_chat_flow.recommend_next_actions", return_value=[]),
            patch("app.api.search_chat_flow.resolve_web_sources_for_answer", return_value=([], [])),
            patch("app.api.search_chat_flow.enrich_major_point_related_mails", side_effect=lambda rows, **_: rows),
        ):
            response = run_search_chat(
                payload=ChatRequest(
                    message="현재메일 요약해줘",
                    email_id="m-fast",
                    mailbox_user="jaeyoung_dev@outlook.com",
                ),
                log_prefix="test",
            )
        self.assertEqual("completed", response["status"])
        self.assertEqual("deep-agent", response["metadata"]["source"])
        self.assertFalse(str(response["answer"]).strip().startswith("{"))
        stage_elapsed = response["metadata"].get("stage_elapsed_ms", {})
        self.assertEqual(0.0, float(stage_elapsed.get("llm_call_1", -1)))
        self.assertGreaterEqual(float(stage_elapsed.get("llm_call_2", 0.0)), 0.0)
        get_agent_mock.assert_not_called()

    def test_current_mail_work_history_arrange_does_not_use_fast_lane(self) -> None:
        """`정리` 기반 작업내역 질의(extract_key_facts 포함)는 fast-lane 대상이 아니어야 한다."""
        decomposition = IntentDecomposition(
            original_query="현재메일의 주요 작업 내역을 정리해줘",
            steps=[ExecutionStep.SUMMARIZE_MAIL, ExecutionStep.READ_CURRENT_MAIL, ExecutionStep.EXTRACT_KEY_FACTS],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.SUMMARY,
            output_format=IntentOutputFormat.LINE_SUMMARY,
            confidence=0.9,
        )
        cached_context = SimpleNamespace(
            status="completed",
            source="db-cache",
            reason="",
            mail=MailRecord(
                message_id="m-keyfacts",
                subject="작업 메일",
                from_address="sender@example.com",
                received_date="2026-03-10T03:38:14Z",
                body_text="본문",
                summary_text="요약",
            ),
        )
        fake_agent = SimpleNamespace()
        fake_agent.execute_turn = lambda user_message, thread_id=None: {
            "status": "completed",
            "answer": "작업 내역 정리 응답",
            "interrupts": [],
        }
        fake_agent.get_last_tool_payload = lambda: {}
        fake_agent.get_last_assistant_answer = lambda: "작업 내역 정리 응답"
        fake_agent.get_last_raw_model_output = lambda: "작업 내역 정리 응답"
        fake_agent.get_last_raw_model_content = lambda: "작업 내역 정리 응답"
        with (
            patch("app.api.search_chat_flow.parse_intent_decomposition_safely", return_value=decomposition),
            patch("app.api.search_chat_flow.mail_context_service.get_mail_context", return_value=cached_context),
            patch("app.api.search_chat_flow.is_openai_key_configured", return_value=True),
            patch("app.api.search_chat_flow.get_deep_chat_agent", return_value=fake_agent) as get_agent_mock,
            patch("app.api.search_chat_flow.invoke_text_messages", return_value='{"format_type":"standard_summary","title":"테스트"}') as invoke_text_mock,
            patch("app.api.search_chat_flow.recommend_next_actions", return_value=[]),
            patch("app.api.search_chat_flow.resolve_web_sources_for_answer", return_value=([], [])),
            patch("app.api.search_chat_flow.enrich_major_point_related_mails", side_effect=lambda rows, **_: rows),
        ):
            response = run_search_chat(
                payload=ChatRequest(
                    message="현재메일의 주요 작업 내역을 정리해줘",
                    email_id="m-keyfacts",
                    mailbox_user="jaeyoung_dev@outlook.com",
                ),
                log_prefix="test",
            )
        self.assertEqual("completed", response["status"])
        get_agent_mock.assert_called_once()
        invoke_text_mock.assert_not_called()

    def test_general_output_skips_web_and_related_mail_postprocess(self) -> None:
        """general 출력 포맷 + non-mail_search tool action이면 web/related_mail 후처리를 스킵해야 한다."""
        decomposition = IntentDecomposition(
            original_query="현재메일 번역해줘",
            steps=[ExecutionStep.READ_CURRENT_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.GENERAL,
            output_format=IntentOutputFormat.GENERAL,
            confidence=0.75,
        )
        cached_context = SimpleNamespace(
            status="completed",
            source="db-cache",
            reason="",
            mail=MailRecord(
                message_id="m-general",
                subject="번역 테스트 메일",
                from_address="sender@example.com",
                received_date="2026-03-10T03:38:14Z",
                body_text="본문",
                summary_text="요약",
            ),
        )
        fake_agent = SimpleNamespace()
        fake_agent.execute_turn = lambda user_message, thread_id=None: {
            "status": "completed",
            "answer": "번역 결과입니다.",
            "interrupts": [],
        }
        fake_agent.get_last_tool_payload = lambda: {"action": "current_mail", "status": "completed"}
        fake_agent.get_last_assistant_answer = lambda: "번역 결과입니다."
        fake_agent.get_last_raw_model_output = lambda: "번역 결과입니다."
        fake_agent.get_last_raw_model_content = lambda: "번역 결과입니다."
        with (
            patch("app.api.search_chat_flow.parse_intent_decomposition_safely", return_value=decomposition),
            patch("app.api.search_chat_flow.mail_context_service.get_mail_context", return_value=cached_context),
            patch("app.api.search_chat_flow.is_openai_key_configured", return_value=True),
            patch("app.api.search_chat_flow.get_deep_chat_agent", return_value=fake_agent),
            patch("app.api.search_chat_flow.recommend_next_actions", return_value=[]),
            patch("app.api.search_chat_flow.resolve_web_sources_for_answer", return_value=([], [])) as resolve_web_mock,
            patch("app.api.search_chat_flow.enrich_major_point_related_mails", side_effect=lambda rows, **_: rows) as enrich_mock,
            patch(
                "app.api.search_chat_flow.build_enrichment_payloads",
                return_value=(None, [], [], {}, {}),
            ),
        ):
            response = run_search_chat(
                payload=ChatRequest(
                    message="현재메일 번역해줘",
                    email_id="m-general",
                    mailbox_user="jaeyoung_dev@outlook.com",
                ),
                log_prefix="test",
            )
        self.assertEqual("completed", response["status"])
        resolve_web_mock.assert_not_called()
        enrich_mock.assert_not_called()
        stage_elapsed = response["metadata"].get("stage_elapsed_ms", {})
        self.assertIn("web_sources_ms", stage_elapsed)
        self.assertIn("related_mail_ms", stage_elapsed)
        self.assertIn("contract_render_ms", stage_elapsed)


if __name__ == "__main__":
    unittest.main()
