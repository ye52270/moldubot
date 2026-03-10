from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services.answer_postprocessor import postprocess_final_answer


class AnswerPostprocessorRawModelContentTest(unittest.TestCase):
    """후처리 파서가 raw_model_content를 우선 파싱하는지 검증한다."""

    def test_postprocess_uses_raw_model_content_for_contract_parse(self) -> None:
        """answer 문자열과 별개로 raw_model_content가 parse 입력으로 전달되어야 한다."""
        raw_model_content = [{"type": "text", "text": "```json\n{\"format_type\":\"general\",\"answer\":\"x\"}\n```"}]

        with patch("app.services.answer_postprocessor.parse_llm_response_contract") as parse_contract:
            parse_contract.return_value = None
            postprocess_final_answer(
                user_message="현재메일 요약해줘",
                answer="plain answer",
                tool_payload={"action": "current_mail"},
                raw_model_content=raw_model_content,
            )

        parse_contract.assert_called_once_with(raw_answer=raw_model_content)


if __name__ == "__main__":
    unittest.main()
