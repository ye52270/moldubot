from __future__ import annotations

import unittest

from app.middleware.agent_middlewares import (
    TRACE_MAX_CONTENT_CHARS,
    TRACE_TRUNCATION_SUFFIX,
    _extract_original_user_message_from_injected_text,
    _extract_text_from_model_content,
    _normalize_raw_model_content,
    _normalize_trace_content,
)


class AgentMiddlewaresTextExtractionTest(unittest.TestCase):
    """모델 content block에서 텍스트 추출 규칙을 검증한다."""

    def test_extract_text_from_block_list(self) -> None:
        """list content에서는 text 블록만 추출해 줄바꿈 결합해야 한다."""
        content = [
            {"type": "text", "text": "첫 줄"},
            {"type": "tool_use", "name": "run_mail_post_action"},
            {"type": "text", "text": "둘째 줄"},
        ]

        extracted = _extract_text_from_model_content(content=content)

        self.assertEqual("첫 줄\n둘째 줄", extracted)

    def test_extract_text_from_block_dict(self) -> None:
        """dict content의 text 필드는 그대로 추출해야 한다."""
        extracted = _extract_text_from_model_content(content={"type": "text", "text": "단일 텍스트"})
        self.assertEqual("단일 텍스트", extracted)

    def test_extract_text_from_plain_string(self) -> None:
        """문자열 content는 trim 후 그대로 반환해야 한다."""
        extracted = _extract_text_from_model_content(content="  plain text  ")
        self.assertEqual("plain text", extracted)

    def test_normalize_raw_model_content_keeps_full_text(self) -> None:
        """raw_model_content 저장 경로는 문자열을 절단하지 않아야 한다."""
        long_text = "x" * (TRACE_MAX_CONTENT_CHARS + 100)
        raw = _normalize_raw_model_content(content={"type": "text", "text": long_text})
        self.assertIsInstance(raw, dict)
        self.assertEqual(long_text, raw["text"])

    def test_normalize_trace_content_truncates_long_text_for_logs(self) -> None:
        """trace 로그 경로는 긴 문자열을 절단해야 한다."""
        long_text = "x" * (TRACE_MAX_CONTENT_CHARS + 100)
        traced = _normalize_trace_content(content={"type": "text", "text": long_text})
        self.assertIsInstance(traced, dict)
        self.assertTrue(str(traced["text"]).endswith(TRACE_TRUNCATION_SUFFIX))

    def test_extract_original_user_message_from_scope_prefixed_text(self) -> None:
        """scope prefix만 있는 주입 텍스트에서도 원본 사용자 입력을 복원해야 한다."""
        message = "[질의 범위] 전체 메일함 기준으로 처리\n/메일요약"
        extracted = _extract_original_user_message_from_injected_text(message_text=message)
        self.assertEqual("/메일요약", extracted)


if __name__ == "__main__":
    unittest.main()
