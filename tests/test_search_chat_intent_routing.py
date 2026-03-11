from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.agents.intent_schema import (
    DateFilter,
    DateFilterMode,
    ExecutionStep,
    IntentDecomposition,
    IntentFocusTopic,
    IntentOutputFormat,
    IntentTaskType,
)
from app.api.contracts import ChatRequest
from app.api.routes import search_chat


class SearchChatIntentRoutingTest(unittest.TestCase):
    """
    `/search/chat`의 intent 기반 라우팅/확인질문 동작을 검증한다.
    """

    def test_low_confidence_returns_intent_clarification(self) -> None:
        """
        intent confidence가 낮으면 agent 실행 전 확인질문을 반환해야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="현재메일 이거 해줘",
            steps=[ExecutionStep.READ_CURRENT_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.GENERAL,
            output_format=IntentOutputFormat.GENERAL,
            confidence=0.42,
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.api.search_chat_flow.get_intent_parser", return_value=parser):
            response = search_chat(payload=ChatRequest(message="현재메일 이거 해줘"))
        self.assertEqual("needs_clarification", response["status"])
        self.assertEqual("intent-clarification", response["metadata"]["source"])
        self.assertIn("요청 의도를 확인할게요", response["answer"])

    def test_skip_intent_clarification_runtime_option_runs_deep_agent(self) -> None:
        """
        runtime_options.skip_intent_clarification=true면 low-confidence여도 deep-agent를 실행해야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="현재메일 이거 해줘",
            steps=[ExecutionStep.READ_CURRENT_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.GENERAL,
            output_format=IntentOutputFormat.GENERAL,
            confidence=0.41,
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.api.search_chat_flow.get_intent_parser", return_value=parser):
            with patch("app.api.routes.is_openai_key_configured", return_value=True):
                fake_agent = MagicMock()
                fake_agent.execute_turn.return_value = {"status": "completed", "answer": "정상 응답", "interrupts": []}
                fake_agent.get_last_tool_payload.return_value = {}
                fake_agent.get_last_assistant_answer.return_value = "정상 응답"
                with patch("app.api.routes.get_deep_chat_agent", return_value=fake_agent):
                    with patch(
                        "app.api.routes._execute_agent_turn",
                        return_value={"status": "completed", "answer": "정상 응답", "interrupts": []},
                    ):
                        response = search_chat(
                            payload=ChatRequest(
                                message="현재메일 이거 해줘",
                                runtime_options={"skip_intent_clarification": True},
                            )
                        )
        self.assertEqual("completed", response["status"])
        self.assertEqual("deep-agent", response["metadata"]["source"])
        self.assertEqual("정상 응답", response["answer"])

    def test_retrieval_task_selects_fast_compact_prompt_variant(self) -> None:
        """
        retrieval task_type은 fast_compact variant agent를 선택해야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="지난주 메일 조회해줘",
            steps=[ExecutionStep.SEARCH_MAILS],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.RETRIEVAL,
            output_format=IntentOutputFormat.GENERAL,
            confidence=0.9,
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.api.search_chat_flow.get_intent_parser", return_value=parser):
            with patch("app.api.routes.is_openai_key_configured", return_value=True):
                fake_agent = MagicMock()
                fake_agent.execute_turn.return_value = {"status": "completed", "answer": "조회 응답", "interrupts": []}
                fake_agent.get_last_tool_payload.return_value = {}
                fake_agent.get_last_assistant_answer.return_value = "조회 응답"
                with patch("app.api.routes.get_deep_chat_agent", return_value=fake_agent) as get_agent_mock:
                    response = search_chat(payload=ChatRequest(message="지난주 메일 조회해줘"))
        self.assertEqual("completed", response["status"])
        get_agent_mock.assert_called_with(prompt_variant="fast_compact")

    def test_mail_summary_skill_selects_json_strict_prompt_variant(self) -> None:
        """
        `/메일요약` 스킬 요청은 strict JSON variant를 선택해야 한다.
        """
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
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.api.search_chat_flow.get_intent_parser", return_value=parser):
            with patch("app.api.routes.is_openai_key_configured", return_value=True):
                fake_agent = MagicMock()
                fake_agent.execute_turn.return_value = {"status": "completed", "answer": "요약 응답", "interrupts": []}
                fake_agent.get_last_tool_payload.return_value = {}
                fake_agent.get_last_assistant_answer.return_value = "요약 응답"
                with patch("app.api.routes.get_deep_chat_agent", return_value=fake_agent) as get_agent_mock:
                    response = search_chat(payload=ChatRequest(message="/메일요약"))
        self.assertEqual("completed", response["status"])
        get_agent_mock.assert_called_with(prompt_variant="quality_structured_json_strict")

    def test_current_mail_work_history_arrange_selects_freeform_grounded_prompt_variant(self) -> None:
        """
        자연어 현재메일 요약/정리형 질의는 freeform grounded variant를 선택해야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="현재메일의 주요 작업 내역을 정리해줘",
            steps=[ExecutionStep.SUMMARIZE_MAIL, ExecutionStep.READ_CURRENT_MAIL, ExecutionStep.EXTRACT_KEY_FACTS],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.SUMMARY,
            output_format=IntentOutputFormat.STRUCTURED_TEMPLATE,
            confidence=0.9,
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.api.search_chat_flow.get_intent_parser", return_value=parser):
            with patch("app.api.routes.is_openai_key_configured", return_value=True):
                fake_agent = MagicMock()
                fake_agent.execute_turn.return_value = {"status": "completed", "answer": "정리 응답", "interrupts": []}
                fake_agent.get_last_tool_payload.return_value = {}
                fake_agent.get_last_assistant_answer.return_value = "정리 응답"
                with patch("app.api.routes.get_deep_chat_agent", return_value=fake_agent) as get_agent_mock:
                    response = search_chat(payload=ChatRequest(message="현재메일의 주요 작업 내역을 정리해줘"))
        self.assertEqual("completed", response["status"])
        get_agent_mock.assert_called_with(prompt_variant="quality_freeform_grounded")

    def test_current_mail_translation_selects_translation_prompt_variant(self) -> None:
        """
        현재메일 번역 요청은 번역 전용 grounded variant를 선택해야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="현재메일 번역해줘",
            steps=[ExecutionStep.READ_CURRENT_MAIL, ExecutionStep.EXTRACT_KEY_FACTS],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.GENERAL,
            output_format=IntentOutputFormat.TRANSLATION,
            confidence=0.75,
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.api.search_chat_flow.get_intent_parser", return_value=parser):
            with patch("app.api.routes.is_openai_key_configured", return_value=True):
                fake_agent = MagicMock()
                fake_agent.execute_turn.return_value = {"status": "completed", "answer": "번역 응답", "interrupts": []}
                fake_agent.get_last_tool_payload.return_value = {}
                fake_agent.get_last_assistant_answer.return_value = "번역 응답"
                with patch("app.api.routes.get_deep_chat_agent", return_value=fake_agent) as get_agent_mock:
                    response = search_chat(payload=ChatRequest(message="현재메일 번역해줘"))
        self.assertEqual("completed", response["status"])
        get_agent_mock.assert_called_with(prompt_variant="quality_translation_grounded")

    def test_current_mail_contact_followup_selects_freeform_prompt_variant(self) -> None:
        """
        현재메일 문맥 후속질문(문의처/연락처)은 structured 대신 freeform grounded variant를 선택해야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="어디로 연락하면 돼?",
            steps=[ExecutionStep.READ_CURRENT_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.EXTRACTION,
            output_format=IntentOutputFormat.GENERAL,
            focus_topics=[IntentFocusTopic.RECIPIENTS],
            confidence=0.75,
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.api.search_chat_flow.get_intent_parser", return_value=parser):
            with patch("app.api.routes.is_openai_key_configured", return_value=True):
                fake_agent = MagicMock()
                fake_agent.execute_turn.return_value = {"status": "completed", "answer": "지원팀에 문의하세요.", "interrupts": []}
                fake_agent.get_last_tool_payload.return_value = {}
                fake_agent.get_last_assistant_answer.return_value = "지원팀에 문의하세요."
                with patch("app.api.routes.get_deep_chat_agent", return_value=fake_agent) as get_agent_mock:
                    response = search_chat(
                        payload=ChatRequest(
                            message="어디로 연락하면 돼?",
                            email_id="m-current",
                            mailbox_user="jaeyoung_dev@outlook.com",
                            runtime_options={"scope": "current_mail"},
                        )
                    )
        self.assertEqual("completed", response["status"])
        get_agent_mock.assert_called_with(prompt_variant="quality_freeform_grounded")

    def test_todo_registration_query_skips_intent_clarification(self) -> None:
        """
        `할일 등록` 실행 요청은 low-confidence여도 intent clarification을 건너뛰어야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="현재메일 주요 키워드 2~3개 할일로 등록",
            steps=[ExecutionStep.READ_CURRENT_MAIL, ExecutionStep.EXTRACT_KEY_FACTS],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.ACTION,
            output_format=IntentOutputFormat.GENERAL,
            confidence=0.41,
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.api.search_chat_flow.get_intent_parser", return_value=parser):
            with patch("app.api.routes.is_openai_key_configured", return_value=True):
                fake_agent = MagicMock()
                fake_agent.execute_turn.return_value = {"status": "completed", "answer": "할일 등록 준비 완료", "interrupts": []}
                fake_agent.get_last_tool_payload.return_value = {}
                fake_agent.get_last_assistant_answer.return_value = "할일 등록 준비 완료"
                with patch("app.api.routes.get_deep_chat_agent", return_value=fake_agent):
                    with patch(
                        "app.api.routes._execute_agent_turn",
                        return_value={"status": "completed", "answer": "할일 등록 준비 완료", "interrupts": []},
                    ):
                        response = search_chat(payload=ChatRequest(message="현재메일 주요 키워드 2~3개 할일로 등록"))

        self.assertEqual("completed", response["status"])
        self.assertEqual("deep-agent", response["metadata"]["source"])

    def test_action_task_type_skips_intent_clarification_without_todo_tokens(self) -> None:
        """
        decomposition이 action이면 ToDo 토큰이 없어도 low-confidence intent clarification을 건너뛰어야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="조치 항목 생성 부탁",
            steps=[ExecutionStep.READ_CURRENT_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.ACTION,
            output_format=IntentOutputFormat.GENERAL,
            confidence=0.41,
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.api.search_chat_flow.get_intent_parser", return_value=parser):
            with patch("app.api.routes.is_openai_key_configured", return_value=True):
                fake_agent = MagicMock()
                fake_agent.execute_turn.return_value = {"status": "completed", "answer": "실행 준비 완료", "interrupts": []}
                fake_agent.get_last_tool_payload.return_value = {}
                fake_agent.get_last_assistant_answer.return_value = "실행 준비 완료"
                with patch("app.api.routes.get_deep_chat_agent", return_value=fake_agent):
                    with patch(
                        "app.api.routes._execute_agent_turn",
                        return_value={"status": "completed", "answer": "실행 준비 완료", "interrupts": []},
                    ):
                        response = search_chat(payload=ChatRequest(message="조치 항목 생성 부탁"))
        self.assertEqual("completed", response["status"])
        self.assertEqual("deep-agent", response["metadata"]["source"])

    def test_current_mail_followup_query_skips_intent_clarification(self) -> None:
        """
        현재메일 컨텍스트가 확정된 후속 질의는 low-confidence여도 의도 확인으로 끊기면 안 된다.
        """
        decomposition = IntentDecomposition(
            original_query="이슈가 어떤거야?",
            steps=[],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.RETRIEVAL,
            output_format=IntentOutputFormat.LINE_SUMMARY,
            confidence=0.41,
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        context_result = SimpleNamespace(
            status="completed",
            source="db-cache",
            reason="",
            mail=SimpleNamespace(
                message_id="m-current",
                subject="FW: [메일서버] Grafana Daily Report 미수신 확인 요청",
                from_address="izocuna@sk.com",
                received_date="2026-03-05T08:28:42Z",
                body_text="본문",
                web_link="https://outlook.live.com/owa/?ItemID=m-current",
            ),
        )
        with patch("app.api.search_chat_flow.get_intent_parser", return_value=parser):
            with patch("app.api.search_chat_flow.mail_context_service.get_mail_context", return_value=context_result):
                with patch("app.api.routes.is_openai_key_configured", return_value=True):
                    fake_agent = MagicMock()
                    fake_agent.execute_turn.return_value = {"status": "completed", "answer": "핵심 이슈는 도메인 차단입니다.", "interrupts": []}
                    fake_agent.get_last_tool_payload.return_value = {}
                    fake_agent.get_last_assistant_answer.return_value = "핵심 이슈는 도메인 차단입니다."
                    with patch("app.api.routes.get_deep_chat_agent", return_value=fake_agent):
                        with patch(
                            "app.api.routes._execute_agent_turn",
                            return_value={"status": "completed", "answer": "핵심 이슈는 도메인 차단입니다.", "interrupts": []},
                        ):
                            response = search_chat(
                                payload=ChatRequest(
                                    message="이슈가 어떤거야?",
                                    email_id="m-current",
                                    mailbox_user="jaeyoung_dev@outlook.com",
                                    runtime_options={"scope": "current_mail"},
                                )
                            )
        self.assertEqual("completed", response["status"])
        self.assertEqual("deep-agent", response["metadata"]["source"])
        self.assertNotIn("needs_clarification", response["status"])

    def test_code_review_query_selects_code_review_expert_prompt_variant(self) -> None:
        """
        코드 리뷰 요청은 code_review_expert variant agent를 선택해야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="현재메일 코드 리뷰해줘",
            steps=[ExecutionStep.READ_CURRENT_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.ANALYSIS,
            output_format=IntentOutputFormat.GENERAL,
            confidence=0.9,
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.api.search_chat_flow.get_intent_parser", return_value=parser):
            with patch("app.api.routes.is_openai_key_configured", return_value=True):
                fake_agent = MagicMock()
                fake_agent.execute_turn.return_value = {"status": "completed", "answer": "리뷰 응답", "interrupts": []}
                fake_agent.get_last_tool_payload.return_value = {}
                fake_agent.get_last_assistant_answer.return_value = "리뷰 응답"
                with patch("app.api.routes.get_deep_chat_agent", return_value=fake_agent) as get_agent_mock:
                    response = search_chat(payload=ChatRequest(message="현재메일 코드 리뷰해줘"))
        self.assertEqual("completed", response["status"])
        get_agent_mock.assert_called_with(prompt_variant="code_review_expert")

    def test_next_action_runtime_option_skips_intent_clarification(self) -> None:
        """
        next_action_id가 전달되면 low-confidence여도 의도 확인질문을 건너뛰어야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="현재메일 기준으로 바로 보낼 수 있는 회신 메일 본문 초안을 작성해줘",
            steps=[ExecutionStep.READ_CURRENT_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.GENERAL,
            output_format=IntentOutputFormat.GENERAL,
            confidence=0.41,
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.api.search_chat_flow.get_intent_parser", return_value=parser):
            with patch("app.api.routes.is_openai_key_configured", return_value=True):
                fake_agent = MagicMock()
                fake_agent.execute_turn.return_value = {"status": "completed", "answer": "회신 초안 본문", "interrupts": []}
                fake_agent.get_last_tool_payload.return_value = {}
                fake_agent.get_last_assistant_answer.return_value = "회신 초안 본문"
                with patch("app.api.routes.get_deep_chat_agent", return_value=fake_agent):
                    with patch(
                        "app.api.routes._execute_agent_turn",
                        return_value={"status": "completed", "answer": "회신 초안 본문", "interrupts": []},
                    ):
                        response = search_chat(
                            payload=ChatRequest(
                                message="현재메일 기준으로 바로 보낼 수 있는 회신 메일 본문 초안을 작성해줘",
                                runtime_options={"next_action_id": "draft_reply"},
                            )
                        )
        self.assertEqual("completed", response["status"])
        self.assertEqual("deep-agent", response["metadata"]["source"])

    def test_web_search_next_action_hides_internal_mail_evidence(self) -> None:
        """
        외부 정보 검색 next action 실행 시 내부 메일 근거 목록은 비노출이어야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="이 이슈 관련 최신 외부 정보 검색해줘",
            steps=[ExecutionStep.READ_CURRENT_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.ANALYSIS,
            output_format=IntentOutputFormat.GENERAL,
            confidence=0.9,
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        context_result = SimpleNamespace(
            status="completed",
            source="db-cache",
            reason="",
            mail=SimpleNamespace(
                message_id="m-1",
                subject="FW: [메일서버] Grafana Daily Report 미수신 확인 요청",
                from_address="izocuna@sk.com",
                received_date="2026-03-05T08:28:42Z",
                body_text="본문",
                web_link="https://outlook.live.com/owa/?ItemID=m-1",
            ),
        )
        with patch("app.api.search_chat_flow.get_intent_parser", return_value=parser):
            with patch("app.api.search_chat_flow.mail_context_service.get_mail_context", return_value=context_result):
                with patch("app.api.routes.is_openai_key_configured", return_value=True):
                    fake_agent = MagicMock()
                    fake_agent.execute_turn.return_value = {"status": "completed", "answer": "외부 검색 결과", "interrupts": []}
                    fake_agent.get_last_tool_payload.return_value = {"action": "run_mail_post_action"}
                    fake_agent.get_last_assistant_answer.return_value = "외부 검색 결과"
                    with patch("app.api.routes.get_deep_chat_agent", return_value=fake_agent):
                        with patch(
                            "app.api.routes._execute_agent_turn",
                            return_value={"status": "completed", "answer": "외부 검색 결과", "interrupts": []},
                        ):
                            response = search_chat(
                                payload=ChatRequest(
                                    message="이 이슈 관련 최신 외부 정보 검색해줘",
                                    email_id="m-1",
                                    mailbox_user="jaeyoung_dev@outlook.com",
                                    runtime_options={"next_action_id": "web_search"},
                                )
                            )
        self.assertEqual("completed", response["status"])
        self.assertEqual([], response["metadata"]["evidence_mails"])

    def test_web_search_next_action_uses_direct_web_route_with_mail_context(self) -> None:
        """
        web_search next action은 deep-agent를 거치지 않고 현재메일 키워드 기반 외부 검색 경로로 처리해야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="이 이슈 관련 최신 외부 정보 검색해줘",
            steps=[ExecutionStep.READ_CURRENT_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.ANALYSIS,
            output_format=IntentOutputFormat.GENERAL,
            confidence=0.9,
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        context_result = SimpleNamespace(
            status="completed",
            source="db-cache",
            reason="",
            mail=SimpleNamespace(
                message_id="m-2",
                subject="FW: [메일서버] Grafana Daily Report 미수신 확인 요청",
                from_address="izocuna@sk.com",
                received_date="2026-03-05T08:28:42Z",
                body_text="본문",
                summary_text="Gmail이 RFC 5322 규칙으로 발신 메일을 차단함",
                web_link="https://outlook.live.com/owa/?ItemID=m-2",
            ),
        )
        fake_sources = [
            {
                "site_name": "Google Workspace Admin Help",
                "title": "Fix bounced or rejected messages",
                "snippet": "RFC 5322 sender format guidance",
                "url": "https://support.google.com/",
                "favicon_url": "",
                "icon_text": "G",
            }
        ]
        with patch("app.api.search_chat_flow.get_intent_parser", return_value=parser):
            with patch("app.api.search_chat_flow.mail_context_service.get_mail_context", return_value=context_result):
                with patch("app.api.search_chat_flow.search_web_sources", return_value=fake_sources):
                    with patch("app.api.routes.get_deep_chat_agent") as get_agent_mock:
                        response = search_chat(
                            payload=ChatRequest(
                                message="이 이슈 관련 최신 외부 정보 검색해줘",
                                email_id="m-2",
                                mailbox_user="jaeyoung_dev@outlook.com",
                                runtime_options={"next_action_id": "web_search"},
                            )
                        )
        self.assertEqual("completed", response["status"])
        self.assertEqual("web-search-direct", response["metadata"]["source"])
        self.assertEqual([], response["metadata"]["evidence_mails"])
        self.assertEqual(1, len(response["metadata"]["web_sources"]))
        self.assertIn("외부 정보 요약", response["answer"])
        get_agent_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
