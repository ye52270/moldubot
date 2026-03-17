from __future__ import annotations

import os
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
from app.middleware.policies import (
    clear_intent_context_payload_cache,
    compose_intent_augmented_text,
    should_inject_intent_context,
)


class MiddlewarePoliciesTest(unittest.TestCase):
    """
    미들웨어 intent 컨텍스트 주입 정책을 검증한다.
    """

    def tearDown(self) -> None:
        """환경 변수/캐시를 테스트 간 초기화한다."""
        os.environ.pop("INTENT_TAXONOMY_CONFIG_PATH", None)
        os.environ.pop("MOLDUBOT_ENABLE_MAIL_SUBAGENTS", None)
        clear_intent_context_payload_cache()

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

    def test_should_inject_intent_context_for_current_mail_scope_without_additional_parse(self) -> None:
        """
        current_mail scope 라벨이 있으면 추가 파싱 없이 컨텍스트 주입을 유지해야 한다.
        """
        scoped_query = "[질의 범위] 현재 선택 메일 1건만 기준으로 처리\n내 구독이 어떻게 되는지 알려줘"
        self.assertTrue(should_inject_intent_context(scoped_query))

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
        분석 질의는 decomposition 정책 기준 3섹션 정리 지시가 주입되어야 한다.
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
        self.assertIn("원인/영향/대응 순서로 간결하게 정리한다.", text)

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
            focus_topics=[IntentFocusTopic.RECIPIENTS],
            confidence=0.75,
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.middleware.policies.get_intent_parser", return_value=parser):
            text = compose_intent_augmented_text(
                "[질의 범위] 현재 선택 메일 1건만 기준으로 처리\n어떤 메일주소가 수신 발신이 안되는거야?"
            )
        self.assertIn("해당 값을 먼저 1~3개로 직접 답한다", text)
        self.assertIn("근거 1줄만", text)

    def test_compose_intent_augmented_text_for_failed_delivery_address_query_adds_scope_guard(self) -> None:
        """
        수신 실패 주소 질의는 실패 주소만 답하고 전체 수신자 나열을 금지하는 지시를 주입해야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="본문의 수신안되는 메일주소가 뭔지 알려줘",
            steps=[ExecutionStep.READ_CURRENT_MAIL, ExecutionStep.EXTRACT_KEY_FACTS],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.EXTRACTION,
            output_format=IntentOutputFormat.GENERAL,
            focus_topics=[IntentFocusTopic.RECIPIENTS],
            confidence=0.9,
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.middleware.policies.get_intent_parser", return_value=parser):
            text = compose_intent_augmented_text(
                "[질의 범위] 현재 선택 메일 1건만 기준으로 처리\n본문의 수신안되는 메일주소가 뭔지 알려줘"
            )
        self.assertIn("실패가 명시된 주소만 답한다", text)
        self.assertIn("전체 수신자 목록 나열은 금지", text)
        self.assertIn("본문에서 특정 주소를 확인할 수 없습니다", text)

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
            focus_topics=[IntentFocusTopic.RECIPIENTS],
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

    def test_compose_intent_augmented_text_keeps_search_step_for_retrieval_discovery_query(self) -> None:
        """
        current_mail 문맥이라도 discovery 성격 retrieval 질의는 `search_mails`를 유지해야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="현재메일과 관련된 다른 메일 찾아줘",
            steps=[ExecutionStep.SEARCH_MAILS, ExecutionStep.READ_CURRENT_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.RETRIEVAL,
            output_format=IntentOutputFormat.GENERAL,
            confidence=0.76,
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.middleware.policies.get_intent_parser", return_value=parser):
            text = compose_intent_augmented_text(
                "[질의 범위] 현재 선택 메일 1건만 기준으로 처리\n현재메일과 관련된 다른 메일 찾아줘"
            )
        self.assertIn("search_mails", text)

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

    def test_compose_intent_augmented_text_uses_decomposition_for_recipient_todo_summary(self) -> None:
        """
        수신자 ToDo 요약 판별은 taxonomy 토큰 대신 decomposition 신호를 우선 사용해야 한다.
        """
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
            task_type=IntentTaskType.ACTION,
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

    def test_compose_intent_augmented_text_forces_tool_execution_for_meeting_room_json_payload(self) -> None:
        """
        JSON 형태 meeting_room_hil payload도 도구 실행 지시가 주입되어야 한다.
        """
        decomposition = IntentDecomposition(
            original_query='{"task":"book_meeting_room","date":"2026-03-09","start_time":"10:00","end_time":"11:00"}',
            steps=[ExecutionStep.BOOK_MEETING_ROOM],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.GENERAL,
            output_format=IntentOutputFormat.GENERAL,
            confidence=0.41,
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.middleware.policies.get_intent_parser", return_value=parser):
            text = compose_intent_augmented_text(decomposition.original_query)
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
            origin="llm_cached",
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.middleware.policies.get_intent_parser", return_value=parser):
            text = compose_intent_augmented_text(
                "[질의 범위] 현재 선택 메일 1건만 기준으로 처리\n현재메일에서 어떤 메일주소가 문제인거야?"
            )
        self.assertIn("- output_format: general", text)
        self.assertIn("- origin: policy_override", text)

    def test_summary_wording_query_does_not_apply_direct_fact_routing_hint(self) -> None:
        """
        요약형 질의는 extraction으로 분해돼도 direct-fact 라우팅 지시를 주입하면 안 된다.
        """
        decomposition = IntentDecomposition(
            original_query="코드를 간단하게 요약해줘",
            steps=[ExecutionStep.EXTRACT_KEY_FACTS],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.EXTRACTION,
            output_format=IntentOutputFormat.STRUCTURED_TEMPLATE,
            focus_topics=[IntentFocusTopic.MAIL_GENERAL],
            confidence=0.8,
            origin="llm_cached",
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.middleware.policies.get_intent_parser", return_value=parser):
            text = compose_intent_augmented_text(
                "[질의 범위] 현재 선택 메일 1건만 기준으로 처리\n코드를 간단하게 요약해줘"
            )
        self.assertNotIn("해당 값을 먼저 1~3개로 직접 답한다", text)
        self.assertNotIn("근거 1줄만", text)
        self.assertIn("- output_format: general", text)
        self.assertIn("- origin: policy_override", text)

    def test_current_mail_structural_extraction_overrides_analysis_task_type(self) -> None:
        """
        current_mail scope에서 extract_key_facts 중심 질의는 analysis가 아닌 extraction으로 보정되어야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="내 구독이 어떻게 되는지 알려줘",
            steps=[ExecutionStep.EXTRACT_KEY_FACTS],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.ANALYSIS,
            output_format=IntentOutputFormat.STRUCTURED_TEMPLATE,
            focus_topics=[IntentFocusTopic.MAIL_GENERAL],
            confidence=0.9,
            origin="llm_cached",
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.middleware.policies.get_intent_parser", return_value=parser):
            text = compose_intent_augmented_text(
                "[질의 범위] 현재 선택 메일 1건만 기준으로 처리\n내 구독이 어떻게 되는지 알려줘"
            )
        self.assertIn("- task_type: extraction", text)
        self.assertIn("- output_format: general", text)
        self.assertNotIn("원인/영향/대응 순서", text)
        self.assertIn("- origin: policy_override", text)

    def test_non_override_keeps_original_origin(self) -> None:
        """
        output_format override 조건이 아니면 기존 origin(llm_cached)을 유지해야 한다.
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
            origin="llm_cached",
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.middleware.policies.get_intent_parser", return_value=parser):
            text = compose_intent_augmented_text("현재메일 요약해줘")
        self.assertIn("- output_format: line_summary", text)
        self.assertIn("- origin: llm_cached", text)

    def test_natural_current_mail_summary_overrides_structured_template_to_general(self) -> None:
        """
        자연어 현재메일 요약은 structured_template여도 general로 override되어야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="현재메일 요약해줘",
            steps=[ExecutionStep.SUMMARIZE_MAIL, ExecutionStep.READ_CURRENT_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.SUMMARY,
            output_format=IntentOutputFormat.STRUCTURED_TEMPLATE,
            confidence=0.9,
            origin="llm_cached",
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.middleware.policies.get_intent_parser", return_value=parser):
            text = compose_intent_augmented_text(
                "[질의 범위] 현재 선택 메일 1건만 기준으로 처리\n현재메일 요약해줘"
            )
        self.assertIn("- output_format: general", text)
        self.assertIn("- origin: policy_override", text)

    def test_mail_summary_skill_keeps_structured_template_on_current_mail_scope(self) -> None:
        """
        /메일요약 스킬 명령은 current_mail scope에서도 structured_template를 유지해야 한다.
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
            origin="llm_cached",
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.middleware.policies.get_intent_parser", return_value=parser):
            text = compose_intent_augmented_text(
                "[질의 범위] 현재 선택 메일 1건만 기준으로 처리\n/메일요약"
            )
        self.assertIn("- output_format: structured_template", text)
        self.assertIn("- origin: llm_cached", text)

    def test_current_mail_scope_retrieval_search_only_drops_search_step(self) -> None:
        """
        current_mail scope의 retrieval가 search_mails 단독일 때는 search step을 제거해야 한다.
        """
        decomposition = IntentDecomposition(
            original_query="내 구독번호가 어떻게 나와있어?",
            steps=[ExecutionStep.SEARCH_MAILS],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.RETRIEVAL,
            output_format=IntentOutputFormat.STRUCTURED_TEMPLATE,
            focus_topics=[IntentFocusTopic.MAIL_GENERAL],
            confidence=0.9,
            origin="llm_cached",
        )
        parser = type("StubParser", (), {"parse": lambda self, user_message: decomposition})()
        with patch("app.middleware.policies.get_intent_parser", return_value=parser):
            text = compose_intent_augmented_text(
                "[질의 범위] 현재 선택 메일 1건만 기준으로 처리\n내 구독번호가 어떻게 나와있어?"
            )
        self.assertIn("- steps:", text)
        self.assertNotIn("search_mails", text)


if __name__ == "__main__":
    unittest.main()
