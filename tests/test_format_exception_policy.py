from __future__ import annotations

import unittest

from app.services.format_exception_policy import should_apply_template_driven_contract


class FormatExceptionPolicyTest(unittest.TestCase):
    """template-driven contract 예외 정책을 검증한다."""

    def test_blocks_code_review_query(self) -> None:
        """코드리뷰 질의는 공통 템플릿 계약 렌더를 차단해야 한다."""
        enabled, reason = should_apply_template_driven_contract(
            user_message="현재메일 기준으로 코드 리뷰해줘",
            section_contract={"template_id": "current_mail_summary"},
        )
        self.assertFalse(enabled)
        self.assertEqual(reason, "code_review_exception")

    def test_blocks_report_query(self) -> None:
        """리포트 질의는 공통 템플릿 계약 렌더를 차단해야 한다."""
        enabled, reason = should_apply_template_driven_contract(
            user_message="주간 보고서 작성해줘",
            section_contract={"template_id": "current_mail_summary"},
        )
        self.assertFalse(enabled)
        self.assertEqual(reason, "report_exception")

    def test_blocks_current_mail_recipients_table_query(self) -> None:
        """현재메일 수신자 표 요청은 전용 렌더 우선으로 차단해야 한다."""
        enabled, reason = should_apply_template_driven_contract(
            user_message="현재메일 수신자를 표로 보여줘",
            section_contract={"template_id": "current_mail_summary"},
        )
        self.assertFalse(enabled)
        self.assertEqual(reason, "recipients_table_exception")

    def test_allows_general_current_mail_summary(self) -> None:
        """일반 현재메일 요약 질의는 공통 템플릿 계약 렌더를 허용해야 한다."""
        enabled, reason = should_apply_template_driven_contract(
            user_message="현재메일 요약해줘",
            section_contract={"template_id": "current_mail_summary"},
        )
        self.assertTrue(enabled)
        self.assertEqual(reason, "enabled")

    def test_blocks_current_mail_cause_analysis_query(self) -> None:
        """현재메일 발신 실패 원인 분석 질의는 요약 템플릿 렌더를 차단해야 한다."""
        enabled, reason = should_apply_template_driven_contract(
            user_message="현재메일에서 메일 발신 실패 이유를 설명해줘",
            section_contract={"template_id": "current_mail_summary"},
        )
        self.assertFalse(enabled)
        self.assertEqual(reason, "cause_analysis_policy_override")

    def test_blocks_current_selected_mail_solution_query(self) -> None:
        """현재 선택 메일 해결 요청도 요약 템플릿 렌더를 차단해야 한다."""
        enabled, reason = should_apply_template_driven_contract(
            user_message="현재 선택 메일에서 이슈 대응 방안을 알려줘",
            section_contract={"template_id": "current_mail_summary"},
        )
        self.assertFalse(enabled)
        self.assertEqual(reason, "solution_policy_override")


if __name__ == "__main__":
    unittest.main()
