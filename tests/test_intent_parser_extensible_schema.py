from __future__ import annotations

import unittest

from app.agents.intent_parser import ExaoneIntentParser
from app.agents.intent_schema import (
    ExecutionStep,
    IntentFocusTopic,
    IntentOutputFormat,
    IntentTaskType,
    decomposition_to_context_text,
)


class IntentParserExtensibleSchemaTest(unittest.TestCase):
    """
    확장 의도 스키마(task/output/focus/confidence) 추론 동작을 검증한다.
    """

    def setUp(self) -> None:
        """
        테스트용 fast-path parser를 준비한다.
        """
        self.parser = ExaoneIntentParser(
            model_name="exaone3.5:2.4b",
            base_url="http://127.0.0.1:11434",
            fast_path_mode="always",
            max_steps=3,
        )

    def test_detailed_summary_query_maps_to_summary_and_detailed_format(self) -> None:
        """
        상세요약 질의는 summary/detailed_summary로 분류되어야 한다.
        """
        result = self.parser.parse("현재메일 상세히 요약해줘")
        self.assertEqual(IntentTaskType.SUMMARY, result.task_type)
        self.assertEqual(IntentOutputFormat.DETAILED_SUMMARY, result.output_format)
        self.assertGreaterEqual(result.confidence, 0.7)

    def test_line_summary_query_maps_to_line_summary_format(self) -> None:
        """
        N줄 요약 질의는 line_summary 포맷으로 분류되어야 한다.
        """
        result = self.parser.parse("현재메일 3줄 요약해줘")
        self.assertEqual(3, result.summary_line_target)
        self.assertEqual(IntentOutputFormat.LINE_SUMMARY, result.output_format)

    def test_recipient_table_query_maps_to_extraction_and_table(self) -> None:
        """
        수신자 표 질의는 extraction/table 및 recipients focus를 가져야 한다.
        """
        result = self.parser.parse("현재메일 수신자를 분석해서 역할을 표로 정리해줘")
        self.assertEqual(IntentTaskType.EXTRACTION, result.task_type)
        self.assertEqual(IntentOutputFormat.TABLE, result.output_format)
        self.assertIn(IntentFocusTopic.RECIPIENTS, result.focus_topics)

    def test_cost_cause_query_maps_to_analysis_focus_cost(self) -> None:
        """
        비용 원인 질의는 analysis와 cost focus로 분류되어야 한다.
        """
        result = self.parser.parse("현재메일에서 비용이 문제가 되는건 왜그래?")
        self.assertEqual(IntentTaskType.ANALYSIS, result.task_type)
        self.assertIn(IntentFocusTopic.COST, result.focus_topics)
        self.assertIn(ExecutionStep.SUMMARIZE_MAIL, result.steps)
        self.assertIn(ExecutionStep.EXTRACT_KEY_FACTS, result.steps)

    def test_ssl_solution_query_maps_to_solution_focus_ssl(self) -> None:
        """
        SSL 해결 질의는 solution과 ssl focus로 분류되어야 한다.
        """
        result = self.parser.parse("현재 메일에서 SSL 인증서 이슈에 대해서 해결 방법을 알려줘")
        self.assertEqual(IntentTaskType.SOLUTION, result.task_type)
        self.assertIn(IntentFocusTopic.SSL, result.focus_topics)
        self.assertIn(ExecutionStep.SUMMARIZE_MAIL, result.steps)
        self.assertIn(ExecutionStep.EXTRACT_KEY_FACTS, result.steps)

    def test_context_text_contains_extended_fields(self) -> None:
        """
        컨텍스트 직렬화 문자열에 확장 필드가 포함되어야 한다.
        """
        result = self.parser.parse("현재메일에서 왜 기술적 이슈가 생기고, 일정에 문제가 생기는거야")
        context_text = decomposition_to_context_text(decomposition=result)
        self.assertIn("task_type:", context_text)
        self.assertIn("output_format:", context_text)
        self.assertIn("focus_topics:", context_text)
        self.assertIn("confidence:", context_text)


if __name__ == "__main__":
    unittest.main()
