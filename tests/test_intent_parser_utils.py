from __future__ import annotations

import unittest

from app.agents.intent_parser_utils import infer_intent_dimensions, infer_required_steps_from_query
from app.agents.intent_schema import ExecutionStep, IntentFocusTopic, IntentTaskType


class IntentParserUtilsTest(unittest.TestCase):
    """intent parser 유틸의 required step 계산 계약을 검증한다."""

    def test_infer_required_steps_for_deictic_current_mail_analysis(self) -> None:
        """지시대명사형 현재메일 분석 질의는 read/summarize/extract step을 포함해야 한다."""
        required = infer_required_steps_from_query("이 이메일의 오류 원인을 설명해줘")
        self.assertIn(ExecutionStep.READ_CURRENT_MAIL, required)
        self.assertIn(ExecutionStep.SUMMARIZE_MAIL, required)
        self.assertIn(ExecutionStep.EXTRACT_KEY_FACTS, required)

    def test_infer_required_steps_for_calendar_registration(self) -> None:
        """일정 등록 의도는 book_calendar_event step을 포함해야 한다."""
        required = infer_required_steps_from_query("다음 주 일정 등록해줘")
        self.assertIn(ExecutionStep.BOOK_CALENDAR_EVENT, required)

    def test_infer_intent_dimensions_does_not_mark_tech_issue_without_signal(self) -> None:
        """핵심추출 step만으로 tech_issue 포커스가 과판정되면 안 된다."""
        task_type, _, focus_topics, _ = infer_intent_dimensions(
            user_message="주요한 내용을 3개만 요약해줘",
            steps=[ExecutionStep.SUMMARIZE_MAIL, ExecutionStep.EXTRACT_KEY_FACTS],
        )
        self.assertEqual(IntentTaskType.SUMMARY, task_type)
        self.assertNotIn(IntentFocusTopic.TECH_ISSUE, focus_topics)


if __name__ == "__main__":
    unittest.main()
