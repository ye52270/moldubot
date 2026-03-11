from __future__ import annotations

import unittest

from app.services.answer_postprocessor import postprocess_final_answer


class AnswerPostprocessorChatModeTest(unittest.TestCase):
    """freeform/skill 모드별 후처리 분기 동작을 검증한다."""

    def test_freeform_mode_preserves_plain_llm_answer(self) -> None:
        """freeform 모드에서는 direct-value 강제 렌더를 적용하지 않아야 한다."""
        llm_answer = "차단된 주소는 grafana-reporter@relay.skbroadband.com 입니다."
        result = postprocess_final_answer(
            user_message="차단되는 메일 주소가 뭐야?",
            answer=llm_answer,
            tool_payload={
                "action": "current_mail",
                "mail_context": {
                    "body_excerpt": (
                        "From: 공재환_SKB <jhkong72@skbroadband.com>\n"
                        "To: 박제영 <izocuna@SKCC.COM>\n"
                        "SMTP error from remote mail server after end of data:\n"
                        "550-5.7.1 From header is not in RFC 5322 format\n"
                    )
                },
            },
            chat_mode="freeform",
        )
        self.assertEqual(llm_answer, result)

    def test_skill_mode_keeps_deterministic_direct_value_render(self) -> None:
        """skill 모드에서는 기존 direct-value 강제 렌더를 유지해야 한다."""
        result = postprocess_final_answer(
            user_message="차단되는 메일 주소가 뭐야?",
            answer="임시 응답",
            tool_payload={
                "action": "current_mail",
                "mail_context": {
                    "body_excerpt": (
                        "From: 공재환_SKB <jhkong72@skbroadband.com>\n"
                        "To: 박제영 <izocuna@SKCC.COM>\n"
                    )
                },
            },
            chat_mode="skill",
        )
        self.assertIn("현재메일 본문에서 확인된 값", result)

    def test_freeform_mode_recovers_plain_text_from_json_contract(self) -> None:
        """freeform 모드에서 JSON 계약 응답은 자연어 문장으로 복원되어야 한다."""
        raw_contract = (
            '{"format_type":"summary","title":"","answer":"","summary_lines":'
            '["partner.BP004355@partner.sk.com 관련 실패 건이 확인됩니다.",'
            '"izocuna@sk.com 관련 실패 문의가 존재합니다."],"key_points":[],"action_items":[]}'
        )
        result = postprocess_final_answer(
            user_message="수신실패되는 메일 주소가 뭔지 알려줘",
            answer=raw_contract,
            tool_payload={},
            chat_mode="freeform",
        )
        self.assertNotIn('"format_type"', result)
        self.assertIn("partner.BP004355@partner.sk.com", result)


if __name__ == "__main__":
    unittest.main()
