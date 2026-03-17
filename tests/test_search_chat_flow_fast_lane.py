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
        """`/메일요약` + cache-hit이면 deep-agent 대신 fast-lane을 사용해야 한다."""
        decomposition = IntentDecomposition(
            original_query="/메일요약",
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
            patch(
                "app.api.search_chat_flow.invoke_text_messages",
                return_value='{"format_type":"standard_summary","title":"테스트","suggested_action_ids":["create_todo"]}',
            ),
            patch("app.api.search_chat_flow.run_mail_post_action", return_value={"action": "current_mail", "status": "completed"}),
            patch("app.api.search_chat_flow.get_deep_chat_agent") as get_agent_mock,
            patch("app.api.search_chat_flow.recommend_next_actions") as recommend_mock,
            patch("app.api.search_chat_flow.resolve_web_sources_for_answer", return_value=([], [])),
            patch("app.api.search_chat_flow.enrich_major_point_related_mails", side_effect=lambda rows, **_: rows),
        ):
            response = run_search_chat(
                payload=ChatRequest(
                    message="/메일요약",
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
        recommend_mock.assert_not_called()

    def test_current_mail_plain_summary_query_uses_fast_lane(self) -> None:
        """`현재메일 요약해줘`도 cache-hit이면 fast-lane을 사용해야 한다."""
        decomposition = IntentDecomposition(
            original_query="현재메일 요약해줘",
            steps=[ExecutionStep.SUMMARIZE_MAIL, ExecutionStep.READ_CURRENT_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.SUMMARY,
            output_format=IntentOutputFormat.GENERAL,
            confidence=0.9,
        )
        cached_context = SimpleNamespace(
            status="completed",
            source="db-cache",
            reason="",
            mail=MailRecord(
                message_id="m-fast-plain",
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
            patch(
                "app.api.search_chat_flow.invoke_text_messages",
                return_value='{"format_type":"standard_summary","title":"테스트","suggested_action_ids":["web_search"]}',
            ),
            patch("app.api.search_chat_flow.run_mail_post_action", return_value={"action": "current_mail", "status": "completed"}),
            patch("app.api.search_chat_flow.get_deep_chat_agent") as get_agent_mock,
            patch("app.api.search_chat_flow.recommend_next_actions") as recommend_mock,
            patch("app.api.search_chat_flow.resolve_web_sources_for_answer", return_value=([], [])),
            patch("app.api.search_chat_flow.enrich_major_point_related_mails", side_effect=lambda rows, **_: rows),
        ):
            response = run_search_chat(
                payload=ChatRequest(
                    message="현재메일 요약해줘",
                    email_id="m-fast-plain",
                    mailbox_user="jaeyoung_dev@outlook.com",
                ),
                log_prefix="test",
            )
        self.assertEqual("completed", response["status"])
        self.assertEqual("web_search", response["metadata"]["next_actions"][0]["action_id"])
        get_agent_mock.assert_not_called()
        recommend_mock.assert_not_called()

    def test_current_mail_summary_fast_path_skips_intent_parser_call(self) -> None:
        """현재메일 요약 fast-path가 활성화되면 intent parser 호출을 생략해야 한다."""
        cached_context = SimpleNamespace(
            status="completed",
            source="db-cache",
            reason="",
            mail=MailRecord(
                message_id="m-fastpath",
                subject="테스트 메일",
                from_address="sender@example.com",
                received_date="2026-03-10T03:38:14Z",
                body_text="본문",
                summary_text="요약",
            ),
        )
        with (
            patch(
                "app.api.search_chat_flow.parse_intent_decomposition_safely",
                side_effect=AssertionError("intent parser should be skipped"),
            ),
            patch("app.api.search_chat_flow.mail_context_service.get_mail_context", return_value=cached_context),
            patch("app.api.search_chat_flow.is_openai_key_configured", return_value=True),
            patch(
                "app.api.search_chat_flow.invoke_text_messages",
                return_value='{"format_type":"standard_summary","title":"테스트","suggested_action_ids":["create_todo"]}',
            ),
            patch("app.api.search_chat_flow.run_mail_post_action", return_value={"action": "current_mail", "status": "completed"}),
            patch("app.api.search_chat_flow.recommend_next_actions") as recommend_mock,
            patch("app.api.search_chat_flow.resolve_web_sources_for_answer", return_value=([], [])),
            patch("app.api.search_chat_flow.enrich_major_point_related_mails", side_effect=lambda rows, **_: rows),
        ):
            response = run_search_chat(
                payload=ChatRequest(
                    message="현재메일 요약해줘",
                    email_id="m-fastpath",
                    mailbox_user="jaeyoung_dev@outlook.com",
                ),
                log_prefix="test",
            )
        self.assertEqual("completed", response["status"])
        recommend_mock.assert_not_called()

    def test_non_summary_current_mail_still_uses_intent_parser(self) -> None:
        """현재메일 비요약 질의는 기존 intent parser 경로를 유지해야 한다."""
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
                message_id="m-non-summary",
                subject="테스트 메일",
                from_address="sender@example.com",
                received_date="2026-03-10T03:38:14Z",
                body_text="본문",
                summary_text="요약",
            ),
        )
        fake_agent = SimpleNamespace()
        fake_agent.execute_turn = lambda user_message, thread_id=None: {
            "status": "completed",
            "answer": "번역 결과",
            "interrupts": [],
        }
        fake_agent.get_last_tool_payload = lambda: {"action": "current_mail", "mail_context": {"message_id": "m-non-summary"}}
        fake_agent.get_last_assistant_answer = lambda: "번역 결과"
        fake_agent.get_last_raw_model_output = lambda: "번역 결과"
        fake_agent.get_last_raw_model_content = lambda: "번역 결과"
        with (
            patch("app.api.search_chat_flow.parse_intent_decomposition_safely", return_value=decomposition) as parse_mock,
            patch("app.api.search_chat_flow.mail_context_service.get_mail_context", return_value=cached_context),
            patch("app.api.search_chat_flow.is_openai_key_configured", return_value=True),
            patch("app.api.search_chat_flow.get_deep_chat_agent", return_value=fake_agent),
            patch("app.api.search_chat_flow.recommend_next_actions", return_value=[]),
            patch("app.api.search_chat_flow.resolve_web_sources_for_answer", return_value=([], [])),
            patch("app.api.search_chat_flow.enrich_major_point_related_mails", side_effect=lambda rows, **_: rows),
        ):
            response = run_search_chat(
                payload=ChatRequest(
                    message="현재메일 번역해줘",
                    email_id="m-non-summary",
                    mailbox_user="jaeyoung_dev@outlook.com",
                ),
                log_prefix="test",
            )

        self.assertEqual("completed", response["status"])
        parse_mock.assert_called_once()

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

    def test_general_agent_contract_suggested_actions_skip_recommender(self) -> None:
        """deep-agent 경로에서도 모델 계약의 suggested_action_ids가 있으면 추천기 폴백을 건너뛰어야 한다."""
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
                message_id="m-general-contract",
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
            "answer": "번역 결과",
            "interrupts": [],
        }
        fake_agent.get_last_tool_payload = lambda: {"action": "current_mail", "mail_context": {"message_id": "m-general-contract"}}
        fake_agent.get_last_assistant_answer = lambda: "번역 결과"
        fake_agent.get_last_raw_model_output = lambda: '{"format_type":"general","answer":"번역 결과","suggested_action_ids":["create_todo"]}'
        fake_agent.get_last_raw_model_content = lambda: '{"format_type":"general","answer":"번역 결과","suggested_action_ids":["create_todo"]}'
        with (
            patch("app.api.search_chat_flow.parse_intent_decomposition_safely", return_value=decomposition),
            patch("app.api.search_chat_flow.mail_context_service.get_mail_context", return_value=cached_context),
            patch("app.api.search_chat_flow.is_openai_key_configured", return_value=True),
            patch("app.api.search_chat_flow.get_deep_chat_agent", return_value=fake_agent),
            patch("app.api.search_chat_flow.recommend_next_actions") as recommend_mock,
            patch("app.api.search_chat_flow.resolve_web_sources_for_answer", return_value=([], [])),
            patch("app.api.search_chat_flow.enrich_major_point_related_mails", side_effect=lambda rows, **_: rows),
        ):
            response = run_search_chat(
                payload=ChatRequest(
                    message="현재메일 번역해줘",
                    email_id="m-general-contract",
                    mailbox_user="jaeyoung_dev@outlook.com",
                ),
                log_prefix="test",
            )

        self.assertEqual("completed", response["status"])
        self.assertEqual("create_todo", response["metadata"]["next_actions"][0]["action_id"])
        recommend_mock.assert_not_called()

    def test_general_agent_freeform_action_tag_skips_recommender(self) -> None:
        """freeform 메타 태그의 suggested_action_ids도 추천기 폴백 없이 복원되어야 한다."""
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
                message_id="m-general-tag",
                subject="번역 테스트 메일",
                from_address="sender@example.com",
                received_date="2026-03-10T03:38:14Z",
                body_text="본문",
                summary_text="요약",
            ),
        )
        fake_agent = SimpleNamespace()
        tagged_answer = "번역 결과입니다.\n[[suggested_action_ids:create_todo,web_search]]"
        fake_agent.execute_turn = lambda user_message, thread_id=None: {
            "status": "completed",
            "answer": tagged_answer,
            "interrupts": [],
        }
        fake_agent.get_last_tool_payload = lambda: {"action": "current_mail", "mail_context": {"message_id": "m-general-tag"}}
        fake_agent.get_last_assistant_answer = lambda: tagged_answer
        fake_agent.get_last_raw_model_output = lambda: tagged_answer
        fake_agent.get_last_raw_model_content = lambda: tagged_answer
        with (
            patch("app.api.search_chat_flow.parse_intent_decomposition_safely", return_value=decomposition),
            patch("app.api.search_chat_flow.mail_context_service.get_mail_context", return_value=cached_context),
            patch("app.api.search_chat_flow.is_openai_key_configured", return_value=True),
            patch("app.api.search_chat_flow.get_deep_chat_agent", return_value=fake_agent),
            patch("app.api.search_chat_flow.recommend_next_actions") as recommend_mock,
            patch("app.api.search_chat_flow.resolve_web_sources_for_answer", return_value=([], [])),
            patch("app.api.search_chat_flow.enrich_major_point_related_mails", side_effect=lambda rows, **_: rows),
        ):
            response = run_search_chat(
                payload=ChatRequest(
                    message="현재메일 번역해줘",
                    email_id="m-general-tag",
                    mailbox_user="jaeyoung_dev@outlook.com",
                ),
                log_prefix="test",
            )

        self.assertEqual("completed", response["status"])
        self.assertEqual("번역 결과입니다.", response["answer"])
        self.assertEqual("create_todo", response["metadata"]["next_actions"][0]["action_id"])
        recommend_mock.assert_not_called()

    def test_general_agent_without_suggested_actions_uses_score_only_fallback(self) -> None:
        """모델 계약에 suggested_action_ids가 없으면 비LLM/비임베딩 score 폴백을 사용해야 한다."""
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
                message_id="m-general-fallback",
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
            "answer": "번역 결과",
            "interrupts": [],
        }
        fake_agent.get_last_tool_payload = lambda: {"action": "current_mail", "mail_context": {"message_id": "m-general-fallback"}}
        fake_agent.get_last_assistant_answer = lambda: "번역 결과"
        fake_agent.get_last_raw_model_output = lambda: "번역 결과"
        fake_agent.get_last_raw_model_content = lambda: "번역 결과"
        with (
            patch("app.api.search_chat_flow.parse_intent_decomposition_safely", return_value=decomposition),
            patch("app.api.search_chat_flow.mail_context_service.get_mail_context", return_value=cached_context),
            patch("app.api.search_chat_flow.is_openai_key_configured", return_value=True),
            patch("app.api.search_chat_flow.get_deep_chat_agent", return_value=fake_agent),
            patch(
                "app.api.search_chat_flow.recommend_next_actions",
                return_value=[{"action_id": "web_search", "title": "외부 정보 검색"}],
            ) as recommend_mock,
            patch("app.api.search_chat_flow.resolve_web_sources_for_answer", return_value=([], [])),
            patch("app.api.search_chat_flow.enrich_major_point_related_mails", side_effect=lambda rows, **_: rows),
        ):
            response = run_search_chat(
                payload=ChatRequest(
                    message="현재메일 번역해줘",
                    email_id="m-general-fallback",
                    mailbox_user="jaeyoung_dev@outlook.com",
                ),
                log_prefix="test",
            )

        self.assertEqual("completed", response["status"])
        self.assertEqual("web_search", response["metadata"]["next_actions"][0]["action_id"])
        kwargs = recommend_mock.call_args.kwargs
        self.assertEqual("score", kwargs.get("selector_mode_override"))
        self.assertFalse(bool(kwargs.get("allow_embeddings")))

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

    def test_completed_response_includes_recommended_next_actions(self) -> None:
        """일반 완료 응답은 추천된 `next_actions`를 metadata에 포함해야 한다."""
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
                message_id="m-next-action",
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
        recommended_actions = [
            {
                "action_id": "search_related_mails",
                "title": "관련 메일 추가 조회",
                "description": "동일 이슈의 과거/연관 메일을 찾아 근거를 확장합니다.",
                "query": "이 주제 관련 메일 최근순으로 5개 조회해줘",
                "priority": "high",
            }
        ]
        with (
            patch("app.api.search_chat_flow.parse_intent_decomposition_safely", return_value=decomposition),
            patch("app.api.search_chat_flow.mail_context_service.get_mail_context", return_value=cached_context),
            patch("app.api.search_chat_flow.is_openai_key_configured", return_value=True),
            patch("app.api.search_chat_flow.get_deep_chat_agent", return_value=fake_agent),
            patch("app.api.search_chat_flow.recommend_next_actions", return_value=recommended_actions),
            patch("app.api.search_chat_flow.resolve_web_sources_for_answer", return_value=([], [])),
            patch("app.api.search_chat_flow.enrich_major_point_related_mails", side_effect=lambda rows, **_: rows),
            patch(
                "app.api.search_chat_flow.build_enrichment_payloads",
                return_value=(None, [], [], {}, {}),
            ),
        ):
            response = run_search_chat(
                payload=ChatRequest(
                    message="현재메일 번역해줘",
                    email_id="m-next-action",
                    mailbox_user="jaeyoung_dev@outlook.com",
                ),
                log_prefix="test",
            )
        self.assertEqual("completed", response["status"])
        self.assertEqual(recommended_actions, response["metadata"]["next_actions"])


if __name__ == "__main__":
    unittest.main()
