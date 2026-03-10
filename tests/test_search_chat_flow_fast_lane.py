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
        stage_elapsed = response["metadata"].get("stage_elapsed_ms", {})
        self.assertEqual(0.0, float(stage_elapsed.get("llm_call_1", -1)))
        self.assertGreaterEqual(float(stage_elapsed.get("llm_call_2", 0.0)), 0.0)
        get_agent_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
