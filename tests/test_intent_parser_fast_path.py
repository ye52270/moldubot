from __future__ import annotations

import unittest
from unittest.mock import patch

from app.agents.intent_parser import ExaoneIntentParser
from app.agents.intent_schema import (
    DateFilter,
    DateFilterMode,
    ExecutionStep,
    IntentDecomposition,
    IntentTaskType,
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
        self.assertEqual("exaone_fresh", result.origin)

    def test_parse_cache_hit_sets_origin_cached(self) -> None:
        """
        동일 질의 cache hit 시 origin은 exaone_cached여야 한다.
        """
        parser = ExaoneIntentParser(
            model_name="exaone3.5:2.4b",
            base_url="http://127.0.0.1:11434",
            fast_path_mode="never",
        )
        mocked = IntentDecomposition(
            original_query="현재메일 요약해줘",
            steps=[ExecutionStep.SUMMARIZE_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            origin="exaone_fresh",
        )
        with patch.object(parser, "_invoke_ollama_structured", return_value=mocked) as invoke_mock:
            first = parser.parse("현재메일 요약해줘")
            second = parser.parse("현재메일 요약해줘")
        self.assertEqual("exaone_fresh", first.origin)
        self.assertEqual("exaone_cached", second.origin)
        invoke_mock.assert_called_once()

    def test_parse_cache_namespace_separates_selected_mail_context(self) -> None:
        """
        동일 질의라도 selected-mail namespace가 다르면 캐시를 분리해야 한다.
        """
        parser = ExaoneIntentParser(
            model_name="exaone3.5:2.4b",
            base_url="http://127.0.0.1:11434",
            fast_path_mode="never",
        )
        mocked = IntentDecomposition(
            original_query="현재메일 번역해줘",
            steps=[ExecutionStep.READ_CURRENT_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            origin="exaone_fresh",
        )
        with patch.object(parser, "_invoke_ollama_structured", return_value=mocked) as invoke_mock:
            first = parser.parse(
                "현재메일 번역해줘",
                has_selected_mail=True,
                selected_message_id_exists=True,
            )
            second = parser.parse(
                "현재메일 번역해줘",
                has_selected_mail=False,
                selected_message_id_exists=False,
            )
            third = parser.parse(
                "현재메일 번역해줘",
                has_selected_mail=True,
                selected_message_id_exists=True,
            )
        self.assertEqual("exaone_fresh", first.origin)
        self.assertEqual("exaone_fresh", second.origin)
        self.assertEqual("exaone_cached", third.origin)
        self.assertEqual(2, invoke_mock.call_count)

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
        self.assertEqual([ExecutionStep.SUMMARIZE_MAIL], result.steps)

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

    def test_fast_path_auto_calls_ollama_for_complex_natural_query(self) -> None:
        """
        `auto` 모드에서 복합 자연어 질의는 fast-path 대신 Ollama 구조분해를 우선해야 한다.
        """
        parser = ExaoneIntentParser(
            model_name="exaone3.5:2.4b",
            base_url="http://127.0.0.1:11434",
            fast_path_mode="auto",
        )
        mocked = IntentDecomposition(
            original_query="현재메일에서 주요 수신자 정보를 알려주고 요약보고서를 만들어줘",
            steps=[
                ExecutionStep.READ_CURRENT_MAIL,
                ExecutionStep.EXTRACT_RECIPIENTS,
                ExecutionStep.SUMMARIZE_MAIL,
            ],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
        )
        with patch.object(parser, "_invoke_ollama_structured", return_value=mocked) as invoke_mock:
            result = parser.parse("현재메일에서 주요 수신자 정보를 알려주고 요약보고서를 만들어줘")
        invoke_mock.assert_called_once()
        self.assertIn(ExecutionStep.READ_CURRENT_MAIL, result.steps)
        self.assertIn(ExecutionStep.SUMMARIZE_MAIL, result.steps)
        self.assertNotIn(ExecutionStep.EXTRACT_RECIPIENTS, result.steps)

    def test_fast_path_auto_uses_rules_for_explicit_skill_command(self) -> None:
        """
        `auto` 모드에서 `/메일요약` 명령은 fast-path로 즉시 구조분해해야 한다.
        """
        parser = ExaoneIntentParser(
            model_name="exaone3.5:2.4b",
            base_url="http://127.0.0.1:11434",
            fast_path_mode="auto",
        )
        with patch.object(parser, "_invoke_ollama_structured", side_effect=AssertionError("should not call")):
            result = parser.parse("/메일요약")
        self.assertIn(ExecutionStep.READ_CURRENT_MAIL, result.steps)
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

    def test_parser_success_path_does_not_inject_required_steps(self) -> None:
        """
        모델 성공 결과에서는 규칙 기반 required step을 강제 주입하지 않아야 한다.
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
        self.assertNotIn(ExecutionStep.EXTRACT_RECIPIENTS, result.steps)
        self.assertIn(ExecutionStep.SUMMARIZE_MAIL, result.steps)
        self.assertIn(ExecutionStep.READ_CURRENT_MAIL, result.steps)

    def test_parser_success_path_does_not_inject_search_step(self) -> None:
        """
        검색형 질의여도 모델 성공 결과에 없는 search step을 규칙으로 주입하지 않아야 한다.
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
        self.assertNotIn(ExecutionStep.SEARCH_MAILS, result.steps)
        self.assertIn(ExecutionStep.READ_CURRENT_MAIL, result.steps)
        self.assertIn(ExecutionStep.EXTRACT_KEY_FACTS, result.steps)

    def test_parser_success_path_keeps_model_steps_without_search_token_normalization(self) -> None:
        """
        모델 성공 결과에서는 질의 토큰 정규화로 step을 제거하지 않아야 한다.
        """
        parser = ExaoneIntentParser(
            model_name="exaone3.5:2.4b",
            base_url="http://127.0.0.1:11434",
            fast_path_mode="never",
            max_steps=3,
        )
        mocked = IntentDecomposition(
            original_query="저 LDAP 쿼리에 대해 외부 검색을 해줘",
            steps=[ExecutionStep.SEARCH_MAILS],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
        )
        with patch.object(parser, "_invoke_ollama_structured", return_value=mocked):
            result = parser.parse("저 LDAP 쿼리에 대해 외부 검색을 해줘")
        self.assertIn(ExecutionStep.SEARCH_MAILS, result.steps)

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

    def test_build_prompt_enforces_translation_priority_contract(self) -> None:
        """
        프롬프트는 번역 의도 우선순위와 현재메일 번역 step 제한 규칙을 명시해야 한다.
        """
        parser = ExaoneIntentParser(
            model_name="exaone3.5:2.4b",
            base_url="http://127.0.0.1:11434",
            fast_path_mode="never",
        )
        prompt = parser._build_prompt("현재메일 번역해줘")
        self.assertIn("translation > action > retrieval > summary > analysis > extraction > general", prompt)
        self.assertIn('output_format = "translation"', prompt)
        self.assertIn('steps = ["read_current_mail"] 만 사용', prompt)
        self.assertIn("번역 요청에서 steps에 extract_key_facts 포함 금지", prompt)

    def test_parser_limits_steps_without_rule_required_expansion_on_success_path(self) -> None:
        """
        성공 경로에서는 step 상한을 적용하되 규칙 기반 required step 확장은 수행하지 않아야 한다.
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

        self.assertEqual(
            [ExecutionStep.BOOK_MEETING_ROOM, ExecutionStep.READ_CURRENT_MAIL],
            result.steps,
        )

    def test_parser_keeps_priority_steps_only_under_limit_for_calendar_registration(self) -> None:
        """
        성공 경로의 일정 등록 질의는 step 상한에 따라 우선순위 step만 유지해야 한다.
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

        self.assertEqual(
            [ExecutionStep.BOOK_CALENDAR_EVENT, ExecutionStep.READ_CURRENT_MAIL],
            result.steps,
        )

    def test_parser_success_path_preserves_llm_metadata_without_rule_recompose(self) -> None:
        """
        모델 성공 결과의 task/output/focus/confidence/summary target은 재합성 없이 유지되어야 한다.
        """
        parser = ExaoneIntentParser(
            model_name="exaone3.5:2.4b",
            base_url="http://127.0.0.1:11434",
            fast_path_mode="never",
            max_steps=4,
        )
        mocked = IntentDecomposition.model_validate(
            {
                "original_query": "주요한 내용을 3개만 요약해줘",
                "steps": ["summarize_mail"],
                "summary_line_target": 3,
                "date_filter": {"mode": "none", "relative": "", "start": "", "end": ""},
                "missing_slots": [],
                "task_type": "summary",
                "output_format": "line_summary",
                "focus_topics": ["mail_general"],
                "confidence": 0.91,
            }
        )
        with patch.object(parser, "_invoke_ollama_structured", return_value=mocked):
            result = parser.parse("주요한 내용을 3개만 요약해줘")
        self.assertEqual(3, result.summary_line_target)
        self.assertEqual("line_summary", result.output_format.value)
        self.assertEqual(["mail_general"], [topic.value for topic in result.focus_topics])
        self.assertEqual(0.91, result.confidence)

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

    def test_fast_path_always_marks_analysis_for_analyze_verb(self) -> None:
        """
        `분석/해석/검토` 행위어가 포함된 현재메일 질의는 analysis task_type으로 분류되어야 한다.
        """
        parser = ExaoneIntentParser(
            model_name="exaone3.5:2.4b",
            base_url="http://127.0.0.1:11434",
            fast_path_mode="always",
        )
        with patch.object(parser, "_invoke_ollama_structured", side_effect=AssertionError("should not call")):
            result = parser.parse("현재메일의 쿼리문을 분석해줘")
        self.assertEqual(IntentTaskType.ANALYSIS, result.task_type)
        self.assertIn(ExecutionStep.READ_CURRENT_MAIL, result.steps)


if __name__ == "__main__":
    unittest.main()
