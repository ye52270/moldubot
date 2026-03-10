from __future__ import annotations

import unittest

from app.services.answer_postprocessor_code_review_annotated import (
    render_current_mail_code_review_annotated_response,
)


class AnswerPostprocessorCodeReviewAnnotatedTest(unittest.TestCase):
    """코드리뷰 주석형 렌더러 동작을 검증한다."""

    def test_renders_segmented_code_review_with_comments(self) -> None:
        """코드리뷰 요청은 핵심 구간 단위 코드+주석 포맷으로 렌더링되어야 한다."""
        rendered = render_current_mail_code_review_annotated_response(
            user_message="현재메일 코드 리뷰해줘",
            answer="분석",
            tool_payload={
                "mail_context": {
                    "body_code_excerpt": (
                        "<form id=\"loginForm\" method=\"post\">\n"
                        "<input type=\"text\" name=\"userId\" />\n"
                        "<input type=\"password\" name=\"password\" />\n"
                        "<button type=\"button\" onclick=\"doLogout()\">logout</button>\n"
                        "</form>\n"
                    )
                }
            },
        )
        self.assertIn("## 코드 분석", rendered)
        self.assertIn("## 주석 리뷰 (핵심 구간)", rendered)
        self.assertIn("### 구간 1", rendered)
        self.assertIn("- 주석:", rendered)
        self.assertIn("- 개선:", rendered)
        self.assertNotIn("- ## 코드 분석", rendered)

    def test_returns_empty_for_non_code_review_query(self) -> None:
        """코드리뷰 질의가 아니면 빈 문자열을 반환해야 한다."""
        rendered = render_current_mail_code_review_annotated_response(
            user_message="현재메일 요약해줘",
            answer="요약",
            tool_payload={"mail_context": {"body_code_excerpt": "<input name='id'/>"}},
        )
        self.assertEqual("", rendered)

    def test_segment_improvement_is_risk_specific_not_generic_fixed_text(self) -> None:
        """위험 유형이 감지되면 개선 문구가 범용 고정문구가 아니라 유형별 문구여야 한다."""
        rendered = render_current_mail_code_review_annotated_response(
            user_message="코드 리뷰해줘",
            answer="분석",
            tool_payload={
                "mail_context": {
                    "body_code_excerpt": (
                        "<input type=\"password\" name=\"password\" />\n"
                        "<button type=\"button\" onclick=\"doLogout()\">logout</button>\n"
                        "<logic:equal value=\"true\" name=\"ISAUTHN\">\n"
                        "</logic:equal>\n"
                    )
                }
            },
        )
        self.assertIn("autocomplete 정책", rendered)
        self.assertNotIn("서버 측 입력 검증/출력 이스케이프/에러 처리 정책을 적용하세요.", rendered)


if __name__ == "__main__":
    unittest.main()
