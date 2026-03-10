from __future__ import annotations

import unittest

from app.services.answer_postprocessor_code_review import (
    MAX_CODE_CHARS,
    render_current_mail_code_review_response,
)


class AnswerPostprocessorCodeReviewTest(unittest.TestCase):
    """코드 리뷰 결정론 렌더 테스트."""

    def test_renders_code_review_template_with_code_block(self) -> None:
        """코드 스니펫 분석 질의는 코드 분석/코드 리뷰 템플릿으로 렌더링되어야 한다."""
        rendered = render_current_mail_code_review_response(
            user_message="현재메일 본문 코드 스니펫을 분석해서 코드 리뷰해줘",
            answer="간단 분석",
            tool_payload={
                "mail_context": {
                    "body_excerpt": (
                        "<form id=\"loginForm\" method=\"post\">\n"
                        "<input type=\"password\" name=\"password\" />\n"
                        "</form>"
                    )
                }
            },
        )
        self.assertIn("## 코드 분석", rendered)
        self.assertIn("## 코드 리뷰", rendered)
        self.assertIn("```html", rendered)
        self.assertIn("<form id=\"loginForm\"", rendered)

    def test_returns_empty_for_non_code_request(self) -> None:
        """코드 분석 질의가 아니면 강제 렌더링하지 않아야 한다."""
        rendered = render_current_mail_code_review_response(
            user_message="현재메일 요약해줘",
            answer="요약",
            tool_payload={"mail_context": {"body_excerpt": "x = 1"}},
        )
        self.assertEqual("", rendered)

    def test_returns_no_snippet_message_when_code_absent(self) -> None:
        """코드가 없으면 코드 없음 안내를 반환해야 한다."""
        rendered = render_current_mail_code_review_response(
            user_message="코드 리뷰해줘",
            answer="요약",
            tool_payload={"mail_context": {"body_excerpt": "회의 일정 공유드립니다."}},
        )
        self.assertEqual("코드 스니펫이 없습니다.", rendered)

    def test_excludes_mail_headers_and_keeps_program_code(self) -> None:
        """메일 헤더 라인은 제외하고 프로그램 코드만 코드블록에 포함해야 한다."""
        rendered = render_current_mail_code_review_response(
            user_message="코드 스니펫 리뷰해줘",
            answer="요약",
            tool_payload={
                "mail_context": {
                    "body_excerpt": (
                        "From: 박제영 <test@sk.com>\n"
                        "Sent: Thursday, February 19, 2026 7:20 AM\n"
                        "To: 누군가 <a@sk.com>\n"
                        "Subject: FW: login form\n\n"
                        "<form id=\"loginForm\" method=\"post\">\n"
                        "<input type=\"text\" name=\"userId\" />\n"
                        "<input type=\"password\" name=\"password\" />\n"
                        "</form>\n"
                    )
                }
            },
        )
        self.assertNotIn("From:", rendered)
        self.assertNotIn("Sent:", rendered)
        self.assertIn("<form id=\"loginForm\"", rendered)

    def test_prefers_body_code_excerpt_when_body_excerpt_has_no_code(self) -> None:
        """body_excerpt에 코드가 없어도 body_code_excerpt의 코드를 우선 추출해야 한다."""
        rendered = render_current_mail_code_review_response(
            user_message="코드 리뷰해줘",
            answer="요약",
            tool_payload={
                "mail_context": {
                    "body_excerpt": "회의 일정 공유드립니다.",
                    "body_code_excerpt": (
                        "<logic:equal value=\"true\" name=\"ISAUTHN\">\n"
                        "<button type=\"button\" onclick=\"doLogout()\">logout</button>\n"
                        "</logic:equal>"
                    ),
                }
            },
        )
        self.assertIn("## 코드 리뷰", rendered)
        self.assertIn("```html", rendered)
        self.assertIn("doLogout()", rendered)

    def test_salvages_code_tail_when_header_and_code_are_in_same_line(self) -> None:
        """From/Subject 헤더 라인 뒤에 코드가 붙은 1라인 본문에서도 코드 꼬리를 추출해야 한다."""
        rendered = render_current_mail_code_review_response(
            user_message="코드 스니펫 분석해줘",
            answer="요약",
            tool_payload={
                "mail_context": {
                    "body_code_excerpt": (
                        "From: user@example.com Subject: login form "
                        "<%@include file=\"../../taglibs.jsp\" %><div class=\"login\">"
                    )
                }
            },
        )
        self.assertNotEqual("코드 스니펫이 없습니다.", rendered)
        self.assertIn("taglibs.jsp", rendered)

    def test_restores_multiline_from_inline_jsp_html_block(self) -> None:
        """한 줄 인라인 JSP/HTML 코드도 줄복원되어 코드블록에 2줄 이상 노출되어야 한다."""
        rendered = render_current_mail_code_review_response(
            user_message="현재메일 코드 리뷰해줘",
            answer="요약",
            tool_payload={
                "mail_context": {
                    "body_code_excerpt": (
                        "<%@include file=\"../../taglibs.jsp\" %>"
                        "<div class=\"login\"><input type=\"password\" name=\"password\"/></div>"
                    )
                }
            },
        )
        self.assertIn("```jsp", rendered)
        self.assertIn("<%@include file=\"../../taglibs.jsp\" %>", rendered)
        self.assertIn("<div class=\"login\">", rendered)
        self.assertIn("\n<input type=\"password\" name=\"password\"/>", rendered)

    def test_ignores_json_contract_noise_for_analysis_lines(self) -> None:
        """모델 답이 JSON 계약 문자열일 때 코드 분석 섹션에 JSON 원문을 노출하면 안 된다."""
        rendered = render_current_mail_code_review_response(
            user_message="코드 리뷰해줘",
            answer='{"format_type":"summary","summary_lines":[],"major_points":["x"]}',
            tool_payload={
                "mail_context": {
                    "body_code_excerpt": "<form id=\"loginForm\"><input type=\"password\" name=\"password\"/></form>"
                }
            },
        )
        self.assertIn("## 코드 분석", rendered)
        self.assertNotIn('"format_type"', rendered)
        self.assertIn("입력값 검증", rendered)

    def test_truncates_code_snippet_to_max_chars(self) -> None:
        """코드 스니펫은 최대 2200자 제한을 준수해야 한다."""
        long_line = "<div class=\"item\">aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa</div>"
        long_code = "\n".join([long_line for _ in range(120)])
        rendered = render_current_mail_code_review_response(
            user_message="코드 리뷰해줘",
            answer="요약",
            tool_payload={"mail_context": {"body_excerpt": long_code}},
        )
        self.assertIn("// ...(truncated)", rendered)
        start = rendered.find("```")
        end = rendered.rfind("```")
        self.assertGreater(end, start)
        code_body = rendered[start + rendered[start:].find("\n") + 1 : end].strip()
        self.assertLessEqual(len(code_body), MAX_CODE_CHARS + 32)


if __name__ == "__main__":
    unittest.main()
