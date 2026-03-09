from __future__ import annotations

import unittest

from app.services.answer_postprocessor import postprocess_final_answer


class AnswerPostprocessorReplyDraftTest(unittest.TestCase):
    """회신 초안 JSON 응답의 후처리 복구를 검증한다."""

    def test_reply_draft_field_is_preferred_over_answer(self) -> None:
        """JSON 파싱 성공 시 `reply_draft` 본문이 최종 응답으로 우선 노출되어야 한다."""
        answer = """```json
{
  "format_type": "general",
  "title": "회신 본문",
  "answer": "정유정님께 드리는 회신 메일 본문입니다.",
  "summary_lines": [],
  "key_points": [],
  "action_items": [],
  "basic_info": {},
  "core_issue": "",
  "major_points": [],
  "required_actions": [],
  "one_line_summary": "",
  "recipient_roles": [],
  "recipient_todos": [],
  "reply_draft": "안녕하세요.\\n\\n검토 결과 회신드립니다.\\n\\n감사합니다."
}
```"""
        rendered = postprocess_final_answer(
            user_message="현재메일 기준으로 바로 보낼 수 있는 회신 메일 본문 초안을 작성해줘",
            answer=answer,
            tool_payload={"action": "current_mail", "mail_context": {"summary_text": "요약"}},
            raw_model_content=answer,
        )
        self.assertIn("안녕하세요.", rendered)
        self.assertIn("검토 결과 회신드립니다.", rendered)
        self.assertNotIn("정유정님께 드리는 회신 메일 본문입니다.", rendered)

    def test_draft_answer_alias_is_supported(self) -> None:
        """`draft_answer` 필드도 회신 본문으로 동일 처리되어야 한다."""
        answer = """```json
{
  "format_type": "general",
  "answer": "요약 문장",
  "draft_answer": "안녕하세요.\\n\\nalias 본문입니다.\\n\\n감사합니다."
}
```"""
        rendered = postprocess_final_answer(
            user_message="현재메일 기준으로 회신 본문 초안 작성해줘",
            answer=answer,
            tool_payload={"action": "current_mail", "mail_context": {"summary_text": "요약"}},
            raw_model_content=answer,
        )
        self.assertEqual("안녕하세요.\n\nalias 본문입니다.\n\n감사합니다.", rendered)

    def test_reply_request_uses_answer_when_reply_draft_missing(self) -> None:
        """회신 요청에서 `reply_draft`가 없으면 `answer`를 본문으로 사용해야 한다."""
        answer = """```json
{
  "format_type": "general",
  "title": "회신 메일 초안",
  "answer": "안녕하세요, 공재환님.\\n\\n원인 분석 감사합니다.\\n\\n감사합니다."
}
```"""
        rendered = postprocess_final_answer(
            user_message="현재메일 기준으로 답변하기 초안 작성",
            answer=answer,
            tool_payload={"action": "current_mail", "mail_context": {"summary_text": "요약"}},
            raw_model_content=answer,
        )
        self.assertTrue(rendered.startswith("안녕하세요, 공재환님."))
        self.assertIn("원인 분석 감사합니다.", rendered)

    def test_reply_request_uses_additional_body_alias(self) -> None:
        """`additional_body` 필드가 오면 회신 본문으로 렌더링되어야 한다."""
        answer = """{
  "format_type": "general",
  "title": "회신 메일 초안",
  "answer": "",
  "additional_body": "안녕하세요, 공재환님.\\n\\n추가 본문입니다.\\n\\n감사합니다."
}"""
        rendered = postprocess_final_answer(
            user_message="답변하기",
            answer=answer,
            tool_payload={"action": "current_mail", "mail_context": {"summary_text": "요약"}},
            raw_model_content=answer,
        )
        self.assertTrue(rendered.startswith("안녕하세요, 공재환님."))
        self.assertIn("추가 본문입니다.", rendered)

    def test_reply_request_uses_reply_body_alias(self) -> None:
        """`reply_body` 필드도 회신 본문 alias로 처리되어야 한다."""
        answer = """{
  "format_type": "general",
  "title": "회신 메일 초안",
  "answer": "",
  "reply_body": "안녕하세요, 공재환님.\\n\\nreply_body 본문입니다.\\n\\n감사합니다."
}"""
        rendered = postprocess_final_answer(
            user_message="답변하기",
            answer=answer,
            tool_payload={"action": "current_mail", "mail_context": {"summary_text": "요약"}},
            raw_model_content=answer,
        )
        self.assertTrue(rendered.startswith("안녕하세요, 공재환님."))
        self.assertIn("reply_body 본문입니다.", rendered)

    def test_reply_body_is_rendered_even_if_user_message_is_not_reply_text(self) -> None:
        """회신 버튼 문구가 아니어도 JSON에 `reply_body`가 있으면 본문을 우선 렌더링해야 한다."""
        answer = """{
  "format_type": "general",
  "title": "회신 메일 초안",
  "answer": "",
  "reply_body": "안녕하세요, 공재환님.\\n\\n비의도 문구에서도 본문 복구됩니다.\\n\\n감사합니다."
}"""
        rendered = postprocess_final_answer(
            user_message="회신 톤 선택: 기본",
            answer=answer,
            tool_payload={"action": "current_mail", "mail_context": {"summary_text": "요약"}},
            raw_model_content=answer,
        )
        self.assertTrue(rendered.startswith("안녕하세요, 공재환님."))
        self.assertIn("비의도 문구에서도 본문 복구됩니다.", rendered)

    def test_reply_request_uses_response_body_alias(self) -> None:
        """`response_body` 필드도 회신 본문 alias로 처리되어야 한다."""
        answer = """{
  "format_type": "general",
  "title": "회신 메일 초안",
  "answer": "",
  "response_body": "안녕하세요, 공재환님.\\n\\nresponse_body 본문입니다.\\n\\n감사합니다."
}"""
        rendered = postprocess_final_answer(
            user_message="회신 톤 선택: 기본",
            answer=answer,
            tool_payload={"action": "current_mail", "mail_context": {"summary_text": "요약"}},
            raw_model_content=answer,
        )
        self.assertTrue(rendered.startswith("안녕하세요, 공재환님."))
        self.assertIn("response_body 본문입니다.", rendered)

    def test_reply_body_converts_escaped_newline_literals_to_real_newlines(self) -> None:
        """회신 본문의 `\\n` 리터럴은 실제 개행으로 변환되어야 한다."""
        answer = """{
  "format_type": "general",
  "title": "회신 메일 초안",
  "answer": "",
  "reply_body": "안녕하세요, 공재환님.\\\\n\\\\n개행 테스트입니다.\\\\n\\\\n감사합니다."
}"""
        rendered = postprocess_final_answer(
            user_message="답변하기",
            answer=answer,
            tool_payload={"action": "current_mail", "mail_context": {"summary_text": "요약"}},
            raw_model_content=answer,
        )
        self.assertIn("안녕하세요, 공재환님.\n\n개행 테스트입니다.\n\n감사합니다.", rendered)

    def test_reply_draft_recovery_when_json_contract_parse_fails(self) -> None:
        """JSON 객체 파싱이 실패해도 `reply_draft` 값은 복구되어야 한다."""
        malformed = """```json
{"format_type":"general","answer":"설명 문구","reply_draft":"안녕하세요.\\n\\n본문입니다.\\n\\n감사합니다.","major_points":[}
```"""
        rendered = postprocess_final_answer(
            user_message="회신 초안 작성해줘",
            answer=malformed,
            tool_payload={"action": "current_mail", "mail_context": {"summary_text": "요약"}},
            raw_model_content=malformed,
        )
        self.assertEqual("안녕하세요.\n\n본문입니다.\n\n감사합니다.", rendered)

    def test_reply_draft_recovery_from_plain_text_with_code_fence(self) -> None:
        """설명 문구 + 코드펜스 응답은 코드펜스 내부 회신 본문만 반환해야 한다."""
        plain = """메일 내용을 확인했습니다. 다음은 바로 보낼 수 있는 회신 본문 초안입니다:

```
공재환님께,

신속한 원인 분석 결과 공유 감사합니다.

1. 도메인 설정 검토
2. 정책 호환성 검증

감사합니다.
```"""
        rendered = postprocess_final_answer(
            user_message="현재메일 기준으로 회신 본문 초안 작성해줘",
            answer=plain,
            tool_payload={"action": "current_mail", "mail_context": {"summary_text": "요약"}},
            raw_model_content=plain,
        )
        self.assertTrue(rendered.startswith("공재환님께,"))
        self.assertNotIn("메일 내용을 확인했습니다", rendered)
        self.assertIn("1. 도메인 설정 검토", rendered)

    def test_reply_draft_prefers_plain_body_when_json_answer_is_summary(self) -> None:
        """plain 본문 + trailing JSON(summary answer) 혼합 응답에서도 본문이 우선되어야 한다."""
        mixed = """회신 메일 본문 초안입니다:

---

공재환님께,

원인 분석 결과 공유 감사합니다.

다음과 같이 조치하겠습니다.
1) 설정 검토
2) 정책 확인

감사합니다.

---

```json
{
  "format_type": "general",
  "title": "요약 제목",
  "answer": "요약 문장",
  "summary_lines": [],
  "key_points": [],
  "action_items": [],
  "basic_info": {},
  "core_issue": "",
  "major_points": [],
  "required_actions": [],
  "one_line_summary": "",
  "recipient_roles": [],
  "recipient_todos": []
}
```"""
        rendered = postprocess_final_answer(
            user_message="현재메일 기준으로 회신 메일 본문 초안 작성해줘",
            answer=mixed,
            tool_payload={"action": "current_mail", "mail_context": {"summary_text": "요약"}},
            raw_model_content=mixed,
        )
        self.assertTrue(rendered.startswith("공재환님께,"))
        self.assertIn("다음과 같이 조치하겠습니다.", rendered)
        self.assertNotIn("요약 문장", rendered)


if __name__ == "__main__":
    unittest.main()
