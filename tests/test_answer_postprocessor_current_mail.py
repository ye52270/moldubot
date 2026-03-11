from __future__ import annotations

import unittest

from app.services.answer_postprocessor_current_mail import (
    render_current_mail_direct_value_from_tool_payload,
    render_current_mail_grounded_safe_response,
)


class AnswerPostprocessorCurrentMailTest(unittest.TestCase):
    """현재메일 근거 안전 가드를 검증한다."""

    def test_render_current_mail_direct_value_from_tool_payload_extracts_query_lines(self) -> None:
        """현재메일 direct-value 질의는 본문의 쿼리/식별 라인을 우선 추출해야 한다."""
        rendered = render_current_mail_direct_value_from_tool_payload(
            user_message="현재메일에서 사용한 OU 쿼리를 알려줘",
            tool_payload={
                "action": "current_mail",
                "mail_context": {
                    "body_code_excerpt": (
                        "ldapsearch -x -b \"OU=SKB,DC=example,DC=com\" \"(cn=SKB.ZN997)\"\n"
                        "objectClass=group"
                    ),
                    "body_excerpt": "쿼리 가이드 요청",
                },
            },
        )
        self.assertIn("현재메일 본문에서 확인된 값:", rendered)
        self.assertIn("OU=SKB,DC=example,DC=com", rendered)
        self.assertIn("(cn=SKB.ZN997)", rendered)

    def test_render_current_mail_direct_value_from_tool_payload_returns_not_found_message(self) -> None:
        """직접값 후보가 없으면 명시적 미검출 응답을 반환해야 한다."""
        rendered = render_current_mail_direct_value_from_tool_payload(
            user_message="현재메일에서 사용한 OU 쿼리를 알려줘",
            tool_payload={
                "action": "current_mail",
                "mail_context": {
                    "body_excerpt": "안녕하세요. 오늘 회의 일정 공유드립니다.",
                    "body_preview": "프로젝트 진행 상황 보고",
                },
            },
        )
        self.assertEqual("현재메일 본문에서 요청한 직접값을 확인하지 못했습니다.", rendered)

    def test_render_current_mail_direct_value_from_tool_payload_skips_translation_request(self) -> None:
        """현재메일 번역 요청은 direct-value 강제 렌더를 수행하면 안 된다."""
        rendered = render_current_mail_direct_value_from_tool_payload(
            user_message="현재메일 번역해줘",
            tool_payload={
                "action": "current_mail",
                "mail_context": {
                    "body_excerpt": "We are pleased to inform you that your subscription ...",
                    "body_code_excerpt": "subscription 140dacee-7eb0-4146-9e9c-db9cd411cd08",
                },
            },
        )
        self.assertEqual("", rendered)

    def test_render_current_mail_direct_value_from_tool_payload_skips_major_issue_request(self) -> None:
        """현재메일 주요 이슈 질의는 direct-value 강제 렌더를 수행하면 안 된다."""
        rendered = render_current_mail_direct_value_from_tool_payload(
            user_message="현재메일의 주요 이슈가 뭐야?",
            tool_payload={
                "action": "current_mail",
                "mail_context": {
                    "body_excerpt": "Grafana Daily Report 수신 차단 이슈가 발생했습니다.",
                    "body_code_excerpt": "From: a@example.com\nTo: b@example.com",
                },
            },
        )
        self.assertEqual("", rendered)

    def test_render_current_mail_direct_value_respects_policy_metadata_decision(self) -> None:
        """후처리 정책 metadata에서 direct fact 비허용이면 direct-value 렌더를 생략해야 한다."""
        rendered = render_current_mail_direct_value_from_tool_payload(
            user_message="현재메일에서 어떤 메일주소가 문제인거야?",
            tool_payload={
                "action": "current_mail",
                "mail_context": {
                    "body_code_excerpt": "From: sender@example.com",
                    "body_excerpt": "메일 반송이 발생했습니다.",
                },
                "postprocess_policy": {
                    "direct_fact_decision": False,
                },
            },
        )
        self.assertEqual("", rendered)

    def test_render_current_mail_grounded_safe_response_for_sparse_evidence(self) -> None:
        """근거가 summary 1줄 수준이면 안전 템플릿으로 강제 응답해야 한다."""
        rendered = render_current_mail_grounded_safe_response(
            user_message="현재 메일에서 파악되는 문제점이나 누락된 항목은 무엇인가요?",
            answer="문제점은 A, B, C이며 상세 작업 범위는 ...",
            tool_payload={
                "action": "current_mail",
                "mail_context": {
                    "summary_text": "M365 및 AD 환경 구축 가견적 안내: 총 193,000,000원, 라이선스 확인 필요.",
                    "body_excerpt": "M365 및 AD 환경 구축 가견적 안내",
                },
            },
        )
        self.assertIn("현재 메일 근거에서 확인되는 내용", rendered)
        self.assertIn("확인할 수 없습니다", rendered)

    def test_render_current_mail_grounded_safe_response_skips_when_body_evidence_rich(self) -> None:
        """본문 근거가 충분하면 안전 템플릿을 강제하면 안 된다."""
        rendered = render_current_mail_grounded_safe_response(
            user_message="현재 메일에서 주요 이슈를 알려줘",
            answer="기존 답변",
            tool_payload={
                "action": "current_mail",
                "mail_context": {
                    "summary_text": "요약",
                    "body_excerpt": "A" * 400,
                },
            },
        )
        self.assertEqual("", rendered)

    def test_render_current_mail_grounded_safe_response_skips_for_summary_request(self) -> None:
        """현재메일 요약 질의는 공통 정책상 안전가드를 적용하지 않아야 한다."""
        rendered = render_current_mail_grounded_safe_response(
            user_message="현재메일 요약해줘",
            answer="요약 결과입니다.",
            tool_payload={
                "action": "current_mail",
                "mail_context": {
                    "summary_text": "M365 및 AD 환경 구축 가견적 안내: 총 193,000,000원, 라이선스 확인 필요.",
                    "body_excerpt": "M365 및 AD 환경 구축 가견적 안내",
                },
            },
        )
        self.assertEqual("", rendered)

    def test_render_current_mail_grounded_safe_response_for_low_overlap_hallucination(self) -> None:
        """근거 대비 토큰 겹침이 낮고 수치/인명이 많은 답변은 안전 템플릿으로 차단해야 한다."""
        rendered = render_current_mail_grounded_safe_response(
            user_message="이 메일의 주요 이슈를 정리해 주세요.",
            answer=(
                "정종석 수석 확인 항목과 AD join tool 48,000,000원, "
                "SK.com 17,000,000원, 인건비 8,000,000원 등 세부 항목이 포함됩니다."
            ),
            tool_payload={
                "action": "current_mail",
                "mail_context": {
                    "summary_text": "M365 및 AD 환경 구축 가견적 안내: 총 193,000,000원, 라이선스 확인 필요.",
                    "body_excerpt": "M365 및 AD 환경 구축에 대한 가견적 금액 안내",
                },
            },
        )
        self.assertIn("현재 메일 근거에서 확인되는 내용", rendered)
        self.assertIn("확인할 수 없습니다", rendered)

    def test_render_current_mail_grounded_safe_response_for_role_question(self) -> None:
        """역할 질문도 공통 안전 템플릿을 반환해야 한다."""
        rendered = render_current_mail_grounded_safe_response(
            user_message="수신자와 발신자의 역할을 분석해 주세요.",
            answer="박제영은 요청자이고 남슬기는 공급사 담당자입니다.",
            tool_payload={
                "action": "current_mail",
                "mail_context": {
                    "summary_text": "M365 및 AD 환경 구축 가견적 안내: 총 193,000,000원, 라이선스 확인 필요.",
                    "body_excerpt": "M365 및 AD 환경 구축 가견적 안내",
                },
            },
        )
        self.assertIn("확인할 수 없습니다", rendered)

    def test_render_current_mail_grounded_safe_response_for_reason_question(self) -> None:
        """이유 질문도 공통 안전 템플릿을 반환해야 한다."""
        rendered = render_current_mail_grounded_safe_response(
            user_message="M365 라이선스 비용을 별도로 확인해야 하는 이유는 무엇인가요?",
            answer="정종석 수석 검토가 필요하기 때문입니다.",
            tool_payload={
                "action": "current_mail",
                "mail_context": {
                    "summary_text": "M365 및 AD 환경 구축 가견적 안내: 총 193,000,000원, 라이선스 확인 필요.",
                    "body_excerpt": "M365 및 AD 환경 구축 가견적 안내",
                },
            },
        )
        self.assertIn("확인할 수 없습니다", rendered)

    def test_render_current_mail_grounded_safe_response_skips_for_reply_draft_request(self) -> None:
        """회신 본문 초안 작성 질의는 안전가드를 적용하면 안 된다."""
        rendered = render_current_mail_grounded_safe_response(
            user_message="현재메일 기준으로 바로 보낼 수 있는 회신 메일 본문 초안을 작성해줘",
            answer=(
                "안녕하세요.\n\n요청하신 CI 적용안 확인했습니다. "
                "흰색 테두리 적용 방향으로 진행하겠습니다.\n\n감사합니다."
            ),
            tool_payload={
                "action": "current_mail",
                "mail_context": {
                    "summary_text": "브로드넷 서비스에이스 CI 변경 요청, 회신 필요.",
                    "body_excerpt": "개발서버 적용 후 배경/글자 색상 검토 요청",
                },
            },
        )
        self.assertEqual("", rendered)


if __name__ == "__main__":
    unittest.main()
