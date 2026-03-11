from __future__ import annotations

import unittest

from app.agents.intent_schema import (
    DateFilter,
    DateFilterMode,
    ExecutionStep,
    IntentDecomposition,
    IntentOutputFormat,
    IntentTaskType,
)
from app.services.current_mail_intent_policy import (
    is_current_mail_direct_fact_request,
    is_current_mail_cause_analysis_request,
    is_current_mail_solution_request,
    is_current_mail_translation_request,
    render_current_mail_grounded_safe_message,
    resolve_current_mail_issue_sections,
    should_apply_current_mail_grounded_safe_guard,
)


class CurrentMailRequestIntentTest(unittest.TestCase):
    """현재메일 원인/해결 요청 판별 유틸을 검증한다."""

    def test_detects_cause_request_for_current_mail(self) -> None:
        """현재메일 발신 실패 이유 설명 요청은 원인 분석 요청으로 판별되어야 한다."""
        self.assertTrue(
            is_current_mail_cause_analysis_request(
                user_message="현재메일에서 메일 발신 실패 이유를 설명해줘"
            )
        )

    def test_detects_cause_request_for_selected_mail_phrase(self) -> None:
        """현재 선택 메일 표현도 현재메일 원인 분석 요청으로 판별해야 한다."""
        self.assertTrue(
            is_current_mail_cause_analysis_request(
                user_message="현재 선택 메일에서 오류 원인을 설명해줘"
            )
        )

    def test_detects_cause_request_for_deictic_email_phrase(self) -> None:
        """지시대명사형 이메일 표현도 현재메일 원인 분석 요청으로 판별해야 한다."""
        self.assertTrue(
            is_current_mail_cause_analysis_request(
                user_message="이 이메일의 오류 원인을 설명해줘"
            )
        )

    def test_rejects_non_current_mail_cause_query(self) -> None:
        """현재메일 앵커가 없는 일반 장애 원인 질의는 판별 대상이 아니다."""
        self.assertFalse(
            is_current_mail_cause_analysis_request(
                user_message="메일 발신 실패 이유를 설명해줘"
            )
        )

    def test_detects_solution_request_for_current_mail(self) -> None:
        """현재메일 해결 요청은 해결 요청으로 판별되어야 한다."""
        self.assertTrue(
            is_current_mail_solution_request(
                user_message="현재 메일에서 이슈 대응 방안을 알려줘"
            )
        )

    def test_rejects_non_current_mail_solution_query(self) -> None:
        """현재메일 앵커가 없는 일반 해결 질의는 판별 대상이 아니다."""
        self.assertFalse(
            is_current_mail_solution_request(
                user_message="이 이슈 해결 방안을 알려줘"
            )
        )

    def test_resolve_issue_sections_cause_and_response(self) -> None:
        """원인+대응방안 요청은 영향 섹션 없이 2섹션 계약으로 계산되어야 한다."""
        sections = resolve_current_mail_issue_sections(
            user_message="현재메일에서 DB 연결 오류 원인과 대응방안을 설명해줘"
        )
        self.assertEqual(("cause", "response"), sections)

    def test_resolve_issue_sections_cause_only(self) -> None:
        """분석 질의는 decomposition 정책에 따라 기본 3섹션으로 계산되어야 한다."""
        sections = resolve_current_mail_issue_sections(
            user_message="현재메일에서 오류 원인 정리해줘"
        )
        self.assertEqual(("cause", "impact", "response"), sections)

    def test_detects_current_mail_direct_fact_request_for_problem_address(self) -> None:
        """문제 주소를 직접 묻는 현재메일 질의는 direct fact 요청으로 판별되어야 한다."""
        self.assertTrue(
            is_current_mail_direct_fact_request(
                user_message="현재메일에서 어떤 메일주소가 문제인거야?"
            )
        )

    def test_detects_current_mail_direct_fact_request_for_delivery_failure_phrase(self) -> None:
        """`안되는` 배송 실패 표현도 direct fact 요청으로 판별되어야 한다."""
        self.assertTrue(
            is_current_mail_direct_fact_request(
                user_message="현재메일에서 어떤 메일주소가 수신 발신이 안되는거야?"
            )
        )

    def test_detects_direct_fact_with_current_mail_context_without_anchor(self) -> None:
        """현재메일 앵커가 없어도 scope가 current_mail이면 direct fact로 판별되어야 한다."""
        self.assertTrue(
            is_current_mail_direct_fact_request(
                user_message="수신이 안되는 메일 주소가 뭐야?",
                has_current_mail_context=True,
            )
        )

    def test_rejects_non_entity_current_mail_problem_question_for_direct_fact(self) -> None:
        """항목 지정이 없는 문제 질의는 direct fact 요청으로 과판별하면 안 된다."""
        self.assertFalse(
            is_current_mail_direct_fact_request(
                user_message="현재메일에서 왜 문제가 생긴거야?"
            )
        )

    def test_detects_current_mail_direct_fact_request_for_ou_query(self) -> None:
        """OU 쿼리/명령어를 직접 묻는 현재메일 질의는 direct fact 요청으로 판별되어야 한다."""
        self.assertTrue(
            is_current_mail_direct_fact_request(
                user_message="현재메일에서 사용한 OU 쿼리를 알려줘"
            )
        )

    def test_detects_current_mail_contact_followup_as_direct_fact(self) -> None:
        """현재메일 문맥 후속질의의 문의처 질문은 direct fact 요청으로 판별되어야 한다."""
        self.assertTrue(
            is_current_mail_direct_fact_request(
                user_message="어디로 연락하면 돼?",
                has_current_mail_context=True,
            )
        )

    def test_rejects_direct_fact_when_decomposition_is_summary(self) -> None:
        """summary decomposition에서는 direct fact 토큰이 있어도 direct fact 분기를 허용하지 않아야 한다."""
        decomposition = IntentDecomposition(
            original_query="현재메일에서 어떤 메일주소가 문제인거야?",
            steps=[ExecutionStep.READ_CURRENT_MAIL, ExecutionStep.SUMMARIZE_MAIL],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.SUMMARY,
            output_format=IntentOutputFormat.STRUCTURED_TEMPLATE,
            confidence=0.7,
        )
        self.assertFalse(
            is_current_mail_direct_fact_request(
                user_message="현재메일에서 어떤 메일주소가 문제인거야?",
                decomposition=decomposition,
            )
        )

    def test_grounded_safe_guard_is_disabled_for_summary_focused_query(self) -> None:
        """현재메일 요약 중심 질의는 안전가드 대상에서 제외되어야 한다."""
        self.assertFalse(should_apply_current_mail_grounded_safe_guard("현재메일 요약해줘"))

    def test_grounded_safe_guard_is_enabled_for_role_query(self) -> None:
        """역할/담당자 분석 질의는 안전가드 대상이어야 한다."""
        self.assertTrue(should_apply_current_mail_grounded_safe_guard("수신자와 발신자의 역할을 분석해줘"))

    def test_grounded_safe_guard_is_disabled_for_reply_draft_query(self) -> None:
        """회신 본문 초안 작성 질의는 안전가드 대상에서 제외되어야 한다."""
        self.assertFalse(
            should_apply_current_mail_grounded_safe_guard(
                "현재메일 기준으로 바로 보낼 수 있는 회신 메일 본문 초안을 작성해줘"
            )
        )

    def test_render_grounded_safe_message_for_reason_query(self) -> None:
        """근거 부족 질의는 공통 안전 템플릿을 반환해야 한다."""
        rendered = render_current_mail_grounded_safe_message(
            user_message="왜 M365 라이선스 확인이 필요한가요?",
            summary_text="M365 및 AD 환경 구축 가견적 안내: 총 193,000,000원, 라이선스 확인 필요.",
        )
        self.assertIn("확인할 수 없습니다", rendered)

    def test_detects_current_mail_translation_request(self) -> None:
        """현재메일 번역 요청은 번역 의도로 판별되어야 한다."""
        self.assertTrue(is_current_mail_translation_request("현재메일 번역해줘"))
        self.assertTrue(is_current_mail_translation_request("translate current mail", has_current_mail_context=True))
        self.assertFalse(is_current_mail_translation_request("메일 요약해줘"))

    def test_rejects_translation_when_decomposition_is_action(self) -> None:
        """action decomposition에서는 번역 분기를 허용하지 않아야 한다."""
        decomposition = IntentDecomposition(
            original_query="현재메일 번역해줘",
            steps=[ExecutionStep.BOOK_CALENDAR_EVENT],
            summary_line_target=5,
            date_filter=DateFilter(mode=DateFilterMode.NONE),
            missing_slots=[],
            task_type=IntentTaskType.ACTION,
            output_format=IntentOutputFormat.GENERAL,
            confidence=0.7,
        )
        self.assertFalse(
            is_current_mail_translation_request(
                user_message="현재메일 번역해줘",
                has_current_mail_context=True,
                decomposition=decomposition,
            )
        )


if __name__ == "__main__":
    unittest.main()
