from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from app.agents.intent_schema import (
    DateFilter,
    DateFilterMode,
    ExecutionStep,
    IntentDecomposition,
    IntentFocusTopic,
    IntentOutputFormat,
    IntentTaskType,
)
from app.middleware.policies import compose_intent_augmented_text, should_inject_intent_context
from app.services.intent_taxonomy_config import reset_intent_taxonomy_cache


class MiddlewarePoliciesTest(unittest.TestCase):
    """
    미들웨어 intent 컨텍스트 주입 정책을 검증한다.
    """

    def tearDown(self) -> None:
        """환경 변수/캐시를 테스트 간 초기화한다."""
        os.environ.pop("INTENT_TAXONOMY_CONFIG_PATH", None)
        os.environ.pop("MOLDUBOT_ENABLE_MAIL_SUBAGENTS", None)
        reset_intent_taxonomy_cache()

    def test_should_skip_intent_context_for_simple_mail_search(self) -> None:
        """
        단순 메일 조회 질의는 컨텍스트 주입을 생략해야 한다.
        """
        self.assertFalse(should_inject_intent_context("박준용 관련 2월 메일"))

    def test_should_inject_intent_context_for_mail_search_with_summary(self) -> None:
        """
        조회+요약 복합 질의는 컨텍스트 주입이 필요하다.
        """
        self.assertTrue(should_inject_intent_context("조영득 관련 2월 메일 요약"))

    def test_should_skip_intent_context_for_code_review_query(self) -> None:
        """
        코드 리뷰 질의는 전용 프롬프트 충돌 방지를 위해 컨텍스트 주입을 생략해야 한다.
        """
        self.assertFalse(should_inject_intent_context("현재메일 코드 리뷰해줘"))

    def test_compose_intent_augmented_text_includes_routing_instruction_for_solution(self) -> None:
        """
        해결 질의는 실행 라우팅 지시(가능 원인/점검/즉시 조치)가 주입되어야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="현재메일 SSL 이슈 해결 방법 알려줘",
            steps=[ExecutionStep.READ_CURRENT_MAIL, ExecutionStep.SUMMARIZE_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.SOLUTION,
            output_format=IntentOutputFormat.GENERAL,
            confidence=0.82,
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.middleware.policies.get_intent_parser", return_value=parser):
            text = compose_intent_augmented_text("현재메일 SSL 이슈 해결 방법 알려줘")
        self.assertIn("라우팅 지시:", text)
        self.assertIn("가능한 원인/점검 순서/즉시 조치", text)

    def test_compose_intent_augmented_text_adds_clarification_hint_on_low_confidence(self) -> None:
        """
        confidence가 낮으면 확인 질문 지시가 주입되어야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="현재메일 이거 좀 분석",
            steps=[ExecutionStep.READ_CURRENT_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.ANALYSIS,
            output_format=IntentOutputFormat.GENERAL,
            confidence=0.45,
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.middleware.policies.get_intent_parser", return_value=parser):
            text = compose_intent_augmented_text("현재메일 이거 좀 분석")
        self.assertIn("의도가 모호하면", text)

    def test_compose_intent_augmented_text_strips_scope_prefix_for_parser_input(self) -> None:
        """
        scope prefix가 붙은 입력도 parser에는 원본 질의만 전달해야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="현재메일에서 오류 원인 정리해줘",
            steps=[ExecutionStep.READ_CURRENT_MAIL, ExecutionStep.EXTRACT_KEY_FACTS],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.ANALYSIS,
            output_format=IntentOutputFormat.GENERAL,
            confidence=0.82,
        )
        captured: dict[str, str] = {}

        class StubParser:
            def parse(self, user_message: str) -> IntentDecomposition:
                captured["user_message"] = user_message
                return decomposition

        with patch("app.middleware.policies.get_intent_parser", return_value=StubParser()):
            text = compose_intent_augmented_text(
                "[질의 범위] 현재 선택 메일 1건만 기준으로 처리\n현재메일에서 오류 원인 정리해줘"
            )
        self.assertEqual("현재메일에서 오류 원인 정리해줘", captured.get("user_message"))
        self.assertIn("원본 사용자 입력:\n현재메일에서 오류 원인 정리해줘", text)
        self.assertIn("범위 지시: [질의 범위] 현재 선택 메일 1건만 기준으로 처리", text)

    def test_compose_intent_augmented_text_passes_selected_mail_namespace_for_current_scope(self) -> None:
        """
        현재메일 scope 라벨이 있으면 parser에 selected-mail namespace를 전달해야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="현재메일 요약해줘",
            steps=[ExecutionStep.READ_CURRENT_MAIL, ExecutionStep.SUMMARIZE_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.SUMMARY,
            output_format=IntentOutputFormat.STRUCTURED_TEMPLATE,
            confidence=0.8,
        )
        captured: dict[str, object] = {}

        class StubParser:
            def parse(
                self,
                user_message: str,
                has_selected_mail: bool = False,
                selected_message_id_exists: bool = False,
            ) -> IntentDecomposition:
                captured["user_message"] = user_message
                captured["has_selected_mail"] = has_selected_mail
                captured["selected_message_id_exists"] = selected_message_id_exists
                return decomposition

        with patch("app.middleware.policies.get_intent_parser", return_value=StubParser()):
            _ = compose_intent_augmented_text(
                "[질의 범위] 현재 선택 메일 1건만 기준으로 처리\n현재메일 요약해줘"
            )
        self.assertEqual("현재메일 요약해줘", captured.get("user_message"))
        self.assertTrue(bool(captured.get("has_selected_mail")))
        self.assertTrue(bool(captured.get("selected_message_id_exists")))

    def test_compose_intent_augmented_text_passes_default_namespace_without_current_scope(self) -> None:
        """
        현재메일 scope 라벨이 없으면 parser namespace는 기본(False/False)이어야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="일반 질문",
            steps=[ExecutionStep.SUMMARIZE_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.GENERAL,
            output_format=IntentOutputFormat.GENERAL,
            confidence=0.6,
        )
        captured: dict[str, object] = {}

        class StubParser:
            def parse(
                self,
                user_message: str,
                has_selected_mail: bool = False,
                selected_message_id_exists: bool = False,
            ) -> IntentDecomposition:
                captured["user_message"] = user_message
                captured["has_selected_mail"] = has_selected_mail
                captured["selected_message_id_exists"] = selected_message_id_exists
                return decomposition

        with patch("app.middleware.policies.get_intent_parser", return_value=StubParser()):
            _ = compose_intent_augmented_text("일반 질문")
        self.assertEqual("일반 질문", captured.get("user_message"))
        self.assertFalse(bool(captured.get("has_selected_mail")))
        self.assertFalse(bool(captured.get("selected_message_id_exists")))

    def test_compose_intent_augmented_text_for_cause_only_analysis(self) -> None:
        """
        원인 전용 질의는 원인만 지시하고 영향/대응 강제 지시를 넣지 않아야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="현재메일에서 오류 원인 정리해줘",
            steps=[ExecutionStep.READ_CURRENT_MAIL, ExecutionStep.EXTRACT_KEY_FACTS],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.ANALYSIS,
            output_format=IntentOutputFormat.GENERAL,
            confidence=0.8,
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.middleware.policies.get_intent_parser", return_value=parser):
            text = compose_intent_augmented_text("현재메일에서 오류 원인 정리해줘")
        self.assertIn("원인만 간결하게 정리한다", text)
        self.assertNotIn("원인/영향/대응 순서", text)

    def test_compose_intent_augmented_text_for_direct_fact_analysis(self) -> None:
        """
        문제 주소를 직접 묻는 현재메일 분석 질의는 direct-answer 지시를 주입해야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="현재메일에서 어떤 메일주소가 문제인거야?",
            steps=[ExecutionStep.READ_CURRENT_MAIL, ExecutionStep.EXTRACT_KEY_FACTS],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.EXTRACTION,
            output_format=IntentOutputFormat.GENERAL,
            focus_topics=[IntentFocusTopic.RECIPIENTS],
            confidence=0.8,
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.middleware.policies.get_intent_parser", return_value=parser):
            text = compose_intent_augmented_text("현재메일에서 어떤 메일주소가 문제인거야?")
        self.assertIn("해당 값을 먼저 1~3개로 직접 답한다", text)
        self.assertIn("근거 1줄만", text)
        self.assertNotIn("원인/영향/대응 순서", text)

    def test_compose_intent_augmented_text_for_direct_fact_retrieval(self) -> None:
        """
        retrieval로 분류돼도 direct fact 질의면 direct-answer 지시가 주입되어야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="어떤 메일주소가 수신 발신이 안되는거야?",
            steps=[ExecutionStep.SEARCH_MAILS, ExecutionStep.READ_CURRENT_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.RETRIEVAL,
            output_format=IntentOutputFormat.GENERAL,
            confidence=0.75,
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.middleware.policies.get_intent_parser", return_value=parser):
            text = compose_intent_augmented_text(
                "[질의 범위] 현재 선택 메일 1건만 기준으로 처리\n어떤 메일주소가 수신 발신이 안되는거야?"
            )
        self.assertIn("해당 값을 먼저 1~3개로 직접 답한다", text)
        self.assertIn("근거 1줄만", text)

    def test_compose_intent_augmented_text_for_direct_fact_ou_query(self) -> None:
        """
        OU/쿼리 직접 질의도 direct-answer 지시가 주입되어야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="현재메일에서 사용한 OU 쿼리를 알려줘",
            steps=[ExecutionStep.READ_CURRENT_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.EXTRACTION,
            output_format=IntentOutputFormat.GENERAL,
            confidence=0.55,
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.middleware.policies.get_intent_parser", return_value=parser):
            text = compose_intent_augmented_text("현재메일에서 사용한 OU 쿼리를 알려줘")
        self.assertIn("해당 값을 먼저 1~3개로 직접 답한다", text)
        self.assertIn("근거 1줄만", text)

    def test_compose_intent_augmented_text_adds_translation_instruction(self) -> None:
        """
        현재메일 번역 요청은 번역 우선 라우팅 지시를 주입해야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="현재메일 번역해줘",
            steps=[ExecutionStep.READ_CURRENT_MAIL, ExecutionStep.EXTRACT_KEY_FACTS],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.GENERAL,
            output_format=IntentOutputFormat.TRANSLATION,
            confidence=0.55,
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.middleware.policies.get_intent_parser", return_value=parser):
            text = compose_intent_augmented_text("현재메일 번역해줘")
        self.assertIn("요약 대신 원문 의미를 유지한 전체 번역문", text)
        self.assertIn("문단 단위 번역", text)

    def test_compose_intent_augmented_text_removes_search_step_when_scope_is_current_mail(self) -> None:
        """
        현재메일 scope 라벨이 명시된 질의는 앵커 토큰이 없어도 search_mails step을 제거해야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="어떤 메일주소가 수신 발신이 안되는거야?",
            steps=[ExecutionStep.SEARCH_MAILS, ExecutionStep.READ_CURRENT_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.RETRIEVAL,
            output_format=IntentOutputFormat.GENERAL,
            confidence=0.75,
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.middleware.policies.get_intent_parser", return_value=parser):
            text = compose_intent_augmented_text(
                "[질의 범위] 현재 선택 메일 1건만 기준으로 처리\n어떤 메일주소가 수신 발신이 안되는거야?"
            )
        self.assertIn("- steps: read_current_mail", text)
        self.assertNotIn("search_mails", text)

    def test_compose_intent_augmented_text_removes_search_step_for_current_mail_focused_query(self) -> None:
        """
        현재메일 고정 질의는 `search_mails` step을 후단에서 제거해야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="현재메일에서 오류 원인 정리해줘",
            steps=[
                ExecutionStep.EXTRACT_KEY_FACTS,
                ExecutionStep.SEARCH_MAILS,
                ExecutionStep.READ_CURRENT_MAIL,
                ExecutionStep.SUMMARIZE_MAIL,
            ],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.ANALYSIS,
            output_format=IntentOutputFormat.GENERAL,
            confidence=0.8,
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.middleware.policies.get_intent_parser", return_value=parser):
            text = compose_intent_augmented_text("현재메일에서 오류 원인 정리해줘")
        self.assertIn("- steps: extract_key_facts, read_current_mail, summarize_mail", text)
        self.assertNotIn("search_mails", text)

    def test_compose_intent_augmented_text_removes_search_step_for_deictic_email_query(self) -> None:
        """
        지시대명사형 이메일 질의도 current_mail 고정으로 `search_mails`를 제거해야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="이 이메일에서 제출 기한이 뭔지 알려줘",
            steps=[ExecutionStep.SEARCH_MAILS, ExecutionStep.READ_CURRENT_MAIL, ExecutionStep.SUMMARIZE_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.ANALYSIS,
            output_format=IntentOutputFormat.GENERAL,
            confidence=0.8,
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.middleware.policies.get_intent_parser", return_value=parser):
            text = compose_intent_augmented_text("이 이메일에서 제출 기한이 뭔지 알려줘")
        self.assertIn("- steps: read_current_mail, summarize_mail", text)
        self.assertNotIn("search_mails", text)

    def test_compose_intent_augmented_text_blocks_todo_tool_for_summary_style_request(self) -> None:
        """
        수신자 todo/마감기한 요약형 질의는 실행 툴 금지 지시가 주입되어야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="현재 메일에서 수신자를 요약해서 그들이 해야할 todo 와 마감기한을 정해줘",
            steps=[
                ExecutionStep.READ_CURRENT_MAIL,
                ExecutionStep.SUMMARIZE_MAIL,
                ExecutionStep.EXTRACT_RECIPIENTS,
            ],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.EXTRACTION,
            output_format=IntentOutputFormat.GENERAL,
            confidence=0.8,
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.middleware.policies.get_intent_parser", return_value=parser):
            text = compose_intent_augmented_text(decomposition.original_query)

        self.assertIn("create_outlook_todo", text)
        self.assertIn("호출하지 않는다", text)

    def test_compose_intent_augmented_text_uses_intent_taxonomy_tokens(self) -> None:
        """
        수신자 ToDo 요약 판별 토큰은 intent taxonomy 설정값을 따라야 한다.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = os.path.join(temp_dir, "intent_taxonomy.json")
            with open(config_path, "w", encoding="utf-8") as file:
                json.dump(
                    {
                        "recipient_todo_policy": {
                            "recipient_tokens": ["assignee"],
                            "todo_tokens": ["action"],
                            "due_tokens": ["due"],
                            "registration_tokens": ["create"],
                        }
                    },
                    file,
                    ensure_ascii=False,
                )
            os.environ["INTENT_TAXONOMY_CONFIG_PATH"] = config_path
            reset_intent_taxonomy_cache()

            decomposition = IntentDecomposition(
                original_query="현재 메일 assignee action과 due를 정리해줘",
                steps=[
                    ExecutionStep.READ_CURRENT_MAIL,
                    ExecutionStep.SUMMARIZE_MAIL,
                    ExecutionStep.EXTRACT_RECIPIENTS,
                ],
                summary_line_target=5,
                date_filter=DateFilter(mode=DateFilterMode.NONE),
                missing_slots=[],
                task_type=IntentTaskType.EXTRACTION,
                output_format=IntentOutputFormat.GENERAL,
                confidence=0.8,
            )
            parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
            with patch("app.middleware.policies.get_intent_parser", return_value=parser):
                text = compose_intent_augmented_text(decomposition.original_query)

        self.assertIn("create_outlook_todo", text)
        self.assertIn("호출하지 않는다", text)

    def test_compose_intent_augmented_text_skips_clarification_hint_for_explicit_todo_registration(self) -> None:
        """
        명시적 ToDo 등록 요청은 low-confidence여도 확인 질문 지시 대신 도구 실행 지시를 넣어야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="현재메일 기반으로 조치 필요 사항을 ToDo로 등록해줘",
            steps=[ExecutionStep.READ_CURRENT_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.GENERAL,
            output_format=IntentOutputFormat.GENERAL,
            confidence=0.55,
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.middleware.policies.get_intent_parser", return_value=parser):
            text = compose_intent_augmented_text(decomposition.original_query)

        self.assertNotIn("의도가 모호하면", text)
        self.assertIn("create_outlook_todo", text)
        self.assertIn("추가 질문 없이", text)

    def test_compose_intent_augmented_text_forces_tool_execution_for_meeting_room_hil_payload(self) -> None:
        """
        meeting_room_hil payload는 low-confidence여도 확인질문 없이 도구 실행 지시가 주입되어야 한다.
        """
        decomposition = IntentDecomposition(
            original_query='task=book_meeting_room date=2026-03-09 start_time=10:00 end_time=11:00 attendee_count=2',
            steps=[ExecutionStep.BOOK_MEETING_ROOM],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.GENERAL,
            output_format=IntentOutputFormat.GENERAL,
            confidence=0.42,
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.middleware.policies.get_intent_parser", return_value=parser):
            text = compose_intent_augmented_text(decomposition.original_query)

        self.assertNotIn("의도가 모호하면", text)
        self.assertIn("book_meeting_room", text)
        self.assertIn("추가 질문 없이", text)

    def test_compose_intent_augmented_text_forces_tool_execution_for_calendar_event_hil_payload(self) -> None:
        """
        calendar_event_hil payload는 low-confidence여도 확인질문 없이 도구 실행 지시가 주입되어야 한다.
        """
        decomposition = IntentDecomposition(
            original_query=(
                "task=create_outlook_calendar_event subject=점검회의 "
                "date=2026-03-10 start_time=10:00 end_time=11:00"
            ),
            steps=[ExecutionStep.BOOK_CALENDAR_EVENT],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.GENERAL,
            output_format=IntentOutputFormat.GENERAL,
            confidence=0.4,
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.middleware.policies.get_intent_parser", return_value=parser):
            text = compose_intent_augmented_text(decomposition.original_query)

        self.assertNotIn("의도가 모호하면", text)
        self.assertIn("create_outlook_calendar_event", text)
        self.assertIn("추가 질문 없이", text)

    def test_composite_mail_retrieval_includes_subagent_routing_when_enabled(self) -> None:
        """
        복합 조회 질의에서 메일 subagent 플래그가 켜져 있으면 위임 라우팅 지시가 주입되어야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="M365 일정 관련 메일 요약하고 기술 이슈도 같이 알려줘",
            steps=[ExecutionStep.SEARCH_MAILS, ExecutionStep.SUMMARIZE_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.RETRIEVAL,
            output_format=IntentOutputFormat.GENERAL,
            focus_topics=[IntentFocusTopic.SCHEDULE, IntentFocusTopic.TECH_ISSUE],
            confidence=0.8,
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.middleware.policies.get_intent_parser", return_value=parser):
            with patch.dict(os.environ, {"MOLDUBOT_ENABLE_MAIL_SUBAGENTS": "1"}, clear=False):
                text = compose_intent_augmented_text(decomposition.original_query)

        self.assertIn("mail-retrieval-summary-agent", text)
        self.assertIn("mail-tech-issue-agent", text)
        self.assertIn("근거 메일", text)

    def test_composite_mail_retrieval_skips_subagent_routing_when_disabled(self) -> None:
        """
        복합 조회 질의라도 메일 subagent 플래그가 꺼져 있으면 위임 라우팅 지시를 넣지 않아야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="M365 일정 관련 메일 요약하고 기술 이슈도 같이 알려줘",
            steps=[ExecutionStep.SEARCH_MAILS, ExecutionStep.SUMMARIZE_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.RETRIEVAL,
            output_format=IntentOutputFormat.GENERAL,
            focus_topics=[IntentFocusTopic.SCHEDULE, IntentFocusTopic.TECH_ISSUE],
            confidence=0.8,
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.middleware.policies.get_intent_parser", return_value=parser):
            with patch.dict(os.environ, {"MOLDUBOT_ENABLE_MAIL_SUBAGENTS": "0"}, clear=False):
                text = compose_intent_augmented_text(decomposition.original_query)

        self.assertNotIn("mail-retrieval-summary-agent", text)
        self.assertNotIn("mail-tech-issue-agent", text)

    def test_direct_fact_request_overrides_output_format_and_marks_origin(self) -> None:
        """
        direct fact 현재메일 질의에서 structured_template은 general로 override되고 origin이 policy_override여야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="현재메일에서 어떤 메일주소가 문제인거야?",
            steps=[ExecutionStep.READ_CURRENT_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.EXTRACTION,
            output_format=IntentOutputFormat.STRUCTURED_TEMPLATE,
            focus_topics=[IntentFocusTopic.RECIPIENTS],
            confidence=0.72,
            origin="exaone_cached",
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.middleware.policies.get_intent_parser", return_value=parser):
            text = compose_intent_augmented_text(
                "[질의 범위] 현재 선택 메일 1건만 기준으로 처리\n현재메일에서 어떤 메일주소가 문제인거야?"
            )
        self.assertIn("- output_format: general", text)
        self.assertIn("- origin: policy_override", text)

    def test_non_override_keeps_original_origin(self) -> None:
        """
        output_format override 조건이 아니면 기존 origin(exaone_cached)을 유지해야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="현재메일 요약해줘",
            steps=[ExecutionStep.SUMMARIZE_MAIL, ExecutionStep.READ_CURRENT_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.SUMMARY,
            output_format=IntentOutputFormat.LINE_SUMMARY,
            confidence=0.82,
            origin="exaone_cached",
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.middleware.policies.get_intent_parser", return_value=parser):
            text = compose_intent_augmented_text("현재메일 요약해줘")
        self.assertIn("- output_format: line_summary", text)
        self.assertIn("- origin: exaone_cached", text)


if __name__ == "__main__":
    unittest.main()
