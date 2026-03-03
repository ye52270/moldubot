from __future__ import annotations

import unittest
from unittest.mock import patch

from app.agents.intent_parser import ExaoneIntentParser
from app.agents.intent_schema import (
    DateFilter,
    DateFilterMode,
    ExecutionStep,
    IntentDecomposition,
)


class IntentParserFastPathTest(unittest.TestCase):
    """
    intent parser fast-path 모드 동작을 검증한다.
    """

    def test_fast_path_always_skips_ollama_call(self) -> None:
        """
        `always` 모드에서는 Ollama 호출 없이 규칙 기반 분해를 사용해야 한다.
        """
        parser = ExaoneIntentParser(
            model_name="exaone3.5:2.4b",
            base_url="http://127.0.0.1:11434",
            fast_path_mode="always",
        )
        with patch.object(parser, "_invoke_ollama_structured", side_effect=AssertionError("should not call")):
            result = parser.parse("현재 메일 3줄 요약해줘")
        self.assertIn(ExecutionStep.READ_CURRENT_MAIL, result.steps)
        self.assertIn(ExecutionStep.SUMMARIZE_MAIL, result.steps)
        self.assertEqual(3, result.summary_line_target)

    def test_fast_path_never_calls_ollama(self) -> None:
        """
        `never` 모드에서는 Ollama 구조분해 호출을 수행해야 한다.
        """
        parser = ExaoneIntentParser(
            model_name="exaone3.5:2.4b",
            base_url="http://127.0.0.1:11434",
            fast_path_mode="never",
        )
        mocked = IntentDecomposition(
            original_query="현재 메일 요약해줘",
            steps=[ExecutionStep.SUMMARIZE_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
        )
        with patch.object(parser, "_invoke_ollama_structured", return_value=mocked) as invoke_mock:
            result = parser.parse("현재 메일 요약해줘")
        invoke_mock.assert_called_once()
        self.assertIn(ExecutionStep.READ_CURRENT_MAIL, result.steps)
        self.assertIn(ExecutionStep.SUMMARIZE_MAIL, result.steps)

    def test_fast_path_auto_uses_rules_when_steps_detected(self) -> None:
        """
        `auto` 모드에서 초단순 현재메일 질의는 fast-path를 사용해야 한다.
        """
        parser = ExaoneIntentParser(
            model_name="exaone3.5:2.4b",
            base_url="http://127.0.0.1:11434",
            fast_path_mode="auto",
        )
        with patch.object(parser, "_invoke_ollama_structured", side_effect=AssertionError("should not call")):
            result = parser.parse("현재메일 요약해줘")
        self.assertEqual([ExecutionStep.READ_CURRENT_MAIL, ExecutionStep.SUMMARIZE_MAIL], result.steps)

    def test_fast_path_auto_uses_rule_based_for_complex_query_with_known_steps(self) -> None:
        """
        `auto` 모드에서 규칙으로 단계 추출이 가능한 복합 질의는 Ollama를 생략해야 한다.
        """
        parser = ExaoneIntentParser(
            model_name="exaone3.5:2.4b",
            base_url="http://127.0.0.1:11434",
            fast_path_mode="auto",
        )
        with patch.object(parser, "_invoke_ollama_structured", side_effect=AssertionError("should not call")):
            result = parser.parse("현재메일에서 주요 수신자 정보를 알려주고 요약보고서를 만들어줘")
        self.assertIn(ExecutionStep.READ_CURRENT_MAIL, result.steps)
        self.assertIn(ExecutionStep.EXTRACT_RECIPIENTS, result.steps)
        self.assertIn(ExecutionStep.SUMMARIZE_MAIL, result.steps)

    def test_fast_path_auto_calls_ollama_when_rule_steps_are_not_detected(self) -> None:
        """
        `auto` 모드에서 규칙 단계 추출이 불가능한 질의는 Ollama를 호출해야 한다.
        """
        parser = ExaoneIntentParser(
            model_name="exaone3.5:2.4b",
            base_url="http://127.0.0.1:11434",
            fast_path_mode="auto",
        )
        mocked = IntentDecomposition(
            original_query="추상적인 전략 방향성을 검토해줘",
            steps=[ExecutionStep.SUMMARIZE_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
        )
        with patch.object(parser, "_invoke_ollama_structured", return_value=mocked) as invoke_mock:
            _ = parser.parse("추상적인 전략 방향성을 검토해줘")
        invoke_mock.assert_called_once()

    def test_parser_limits_steps_by_priority(self) -> None:
        """
        모델 응답 steps가 과도할 때 우선순위 기준 상한으로 제한해야 한다.
        """
        parser = ExaoneIntentParser(
            model_name="exaone3.5:2.4b",
            base_url="http://127.0.0.1:11434",
            fast_path_mode="never",
            max_steps=2,
        )
        mocked = IntentDecomposition(
            original_query="noop query",
            steps=[
                ExecutionStep.READ_CURRENT_MAIL,
                ExecutionStep.EXTRACT_KEY_FACTS,
                ExecutionStep.BOOK_MEETING_ROOM,
                ExecutionStep.SEARCH_MEETING_SCHEDULE,
            ],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
        )
        with patch.object(parser, "_invoke_ollama_structured", return_value=mocked):
            result = parser.parse("noop query")
        self.assertEqual(
            [ExecutionStep.BOOK_MEETING_ROOM, ExecutionStep.SEARCH_MEETING_SCHEDULE],
            result.steps,
        )

    def test_parser_falls_back_when_required_steps_missing(self) -> None:
        """
        모델 결과에 필수 step(수신자)이 없으면 규칙 기반 fallback으로 전환해야 한다.
        """
        parser = ExaoneIntentParser(
            model_name="exaone3.5:2.4b",
            base_url="http://127.0.0.1:11434",
            fast_path_mode="never",
            max_steps=2,
        )
        mocked = IntentDecomposition(
            original_query="현재메일에서 주요 수신자 정보를 알려주고 요약보고서를 만들어줘",
            steps=[ExecutionStep.READ_CURRENT_MAIL, ExecutionStep.SUMMARIZE_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
        )
        with patch.object(parser, "_invoke_ollama_structured", return_value=mocked):
            result = parser.parse("현재메일에서 주요 수신자 정보를 알려주고 요약보고서를 만들어줘")
        self.assertIn(ExecutionStep.EXTRACT_RECIPIENTS, result.steps)
        self.assertIn(ExecutionStep.SUMMARIZE_MAIL, result.steps)
        self.assertIn(ExecutionStep.READ_CURRENT_MAIL, result.steps)

    def test_parser_falls_back_when_search_step_missing_for_search_query(self) -> None:
        """
        검색형 질의에서 모델 결과에 search_mails가 없으면 규칙 기반 fallback으로 전환해야 한다.
        """
        parser = ExaoneIntentParser(
            model_name="exaone3.5:2.4b",
            base_url="http://127.0.0.1:11434",
            fast_path_mode="never",
            max_steps=3,
        )
        mocked = IntentDecomposition(
            original_query="IT Application 위탁운영 1월분 계산서 발행 요청 메일에서 액션 아이템만 뽑아줘",
            steps=[ExecutionStep.EXTRACT_KEY_FACTS, ExecutionStep.READ_CURRENT_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.ABSOLUTE, start="2026-01-01", end="2026-01-31"),
            missing_slots=[],
        )
        with patch.object(parser, "_invoke_ollama_structured", return_value=mocked):
            result = parser.parse("IT Application 위탁운영 1월분 계산서 발행 요청 메일에서 액션 아이템만 뽑아줘")
        self.assertIn(ExecutionStep.SEARCH_MAILS, result.steps)
        self.assertNotIn(ExecutionStep.READ_CURRENT_MAIL, result.steps)
        self.assertNotIn(ExecutionStep.EXTRACT_KEY_FACTS, result.steps)

    def test_build_prompt_marks_monthly_billing_terms_as_non_date_filter(self) -> None:
        """
        프롬프트는 N월분/분기분 표현을 수신일 필터로 해석하지 않도록 명시해야 한다.
        """
        parser = ExaoneIntentParser(
            model_name="exaone3.5:2.4b",
            base_url="http://127.0.0.1:11434",
            fast_path_mode="never",
        )
        prompt = parser._build_prompt("IT Application 위탁운영 1월분 계산서 발행 요청 메일에서 액션 아이템만 뽑아줘")
        self.assertIn('"N월분", "N분기분", "상반기분", "하반기분"', prompt)
        self.assertIn('date_filter는 반드시 none', prompt)
        self.assertIn('"지난달에 받은"', prompt)

    def test_parser_preserves_required_steps_under_step_limit(self) -> None:
        """
        step 상한 적용 시에도 수신자/핵심/요약/예약 필수 step이 누락되지 않아야 한다.
        """
        parser = ExaoneIntentParser(
            model_name="exaone3.5:2.4b",
            base_url="http://127.0.0.1:11434",
            fast_path_mode="never",
            max_steps=2,
        )
        mocked = IntentDecomposition(
            original_query="현재메일 주요 내용과 수신자정보 요약 후 회의실 예약",
            steps=[
                ExecutionStep.BOOK_MEETING_ROOM,
                ExecutionStep.READ_CURRENT_MAIL,
                ExecutionStep.SUMMARIZE_MAIL,
                ExecutionStep.EXTRACT_RECIPIENTS,
                ExecutionStep.EXTRACT_KEY_FACTS,
            ],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
        )
        with patch.object(parser, "_invoke_ollama_structured", return_value=mocked):
            result = parser.parse("현재메일 주요 내용과 수신자정보 요약 후 회의실 예약")

        self.assertIn(ExecutionStep.BOOK_MEETING_ROOM, result.steps)
        self.assertIn(ExecutionStep.READ_CURRENT_MAIL, result.steps)
        self.assertIn(ExecutionStep.SUMMARIZE_MAIL, result.steps)
        self.assertIn(ExecutionStep.EXTRACT_RECIPIENTS, result.steps)
        self.assertIn(ExecutionStep.EXTRACT_KEY_FACTS, result.steps)

    def test_parser_preserves_calendar_booking_step_for_current_mail_schedule_registration(self) -> None:
        """
        현재메일 일정 등록 질의는 step 상한 상황에서도 calendar booking step을 유지해야 한다.
        """
        parser = ExaoneIntentParser(
            model_name="exaone3.5:2.4b",
            base_url="http://127.0.0.1:11434",
            fast_path_mode="never",
            max_steps=2,
        )
        mocked = IntentDecomposition(
            original_query="현재메일 요약 후 주요 수신자를 참석자로 해서 일정 등록해줘",
            steps=[
                ExecutionStep.READ_CURRENT_MAIL,
                ExecutionStep.SUMMARIZE_MAIL,
                ExecutionStep.EXTRACT_RECIPIENTS,
                ExecutionStep.BOOK_CALENDAR_EVENT,
            ],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
        )
        with patch.object(parser, "_invoke_ollama_structured", return_value=mocked):
            result = parser.parse("현재메일 요약 후 주요 수신자를 참석자로 해서 일정 등록해줘")

        self.assertIn(ExecutionStep.BOOK_CALENDAR_EVENT, result.steps)
        self.assertIn(ExecutionStep.READ_CURRENT_MAIL, result.steps)
        self.assertIn(ExecutionStep.SUMMARIZE_MAIL, result.steps)
        self.assertIn(ExecutionStep.EXTRACT_RECIPIENTS, result.steps)

    def test_parser_reuses_cached_decomposition_for_same_query(self) -> None:
        """
        동일 질의를 반복하면 구조분해 캐시를 사용해 Ollama 호출을 생략해야 한다.
        """
        parser = ExaoneIntentParser(
            model_name="exaone3.5:2.4b",
            base_url="http://127.0.0.1:11434",
            fast_path_mode="never",
            max_steps=3,
        )
        mocked = IntentDecomposition(
            original_query="어제 온 메일 요약해줘",
            steps=[ExecutionStep.SEARCH_MAILS, ExecutionStep.SUMMARIZE_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.RELATIVE, relative="yesterday"),
            missing_slots=[],
        )
        with patch.object(parser, "_invoke_ollama_structured", return_value=mocked) as invoke_mock:
            first = parser.parse("어제 온 메일 요약해줘")
            second = parser.parse("어제 온 메일 요약해줘")
        invoke_mock.assert_called_once()
        self.assertEqual(first.steps, second.steps)

    def test_parser_calls_ollama_when_query_changes(self) -> None:
        """
        질의가 다르면 캐시를 재사용하지 않고 새 구조분해를 호출해야 한다.
        """
        parser = ExaoneIntentParser(
            model_name="exaone3.5:2.4b",
            base_url="http://127.0.0.1:11434",
            fast_path_mode="never",
            max_steps=3,
        )
        mocked = IntentDecomposition(
            original_query="메일 요약",
            steps=[ExecutionStep.SEARCH_MAILS, ExecutionStep.SUMMARIZE_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
        )
        with patch.object(parser, "_invoke_ollama_structured", return_value=mocked) as invoke_mock:
            parser.parse("어제 온 메일 요약해줘")
            parser.parse("지난주 온 메일 요약해줘")
        self.assertEqual(2, invoke_mock.call_count)


if __name__ == "__main__":
    unittest.main()
