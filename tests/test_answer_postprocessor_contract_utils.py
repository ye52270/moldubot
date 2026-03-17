from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services.answer_postprocessor_contract_utils import parse_llm_response_contract
from app.services.answer_postprocessor_contract_utils import augment_contract_with_tool_payload


class AnswerPostprocessorContractUtilsTest(unittest.TestCase):
    """
    응답 계약 파서의 로그 제어 동작을 검증한다.
    """

    def test_parse_llm_response_contract_suppresses_warning_when_log_failures_disabled(self) -> None:
        """
        JSON이 없는 응답이라도 `log_failures=False`면 경고 로그를 남기지 않아야 한다.
        """
        with patch("app.services.answer_postprocessor_contract_utils.logger.warning") as mocked_warning:
            contract = parse_llm_response_contract(raw_answer="## 📌 주요 내용\n- 텍스트 응답", log_failures=False)
        self.assertIsNone(contract)
        mocked_warning.assert_not_called()

    def test_parse_llm_response_contract_logs_warning_by_default(self) -> None:
        """
        기본 동작에서는 JSON 파싱 실패 경고 로그를 남겨야 한다.
        """
        with patch("app.services.answer_postprocessor_contract_utils.logger.warning") as mocked_warning:
            contract = parse_llm_response_contract(raw_answer="## 📌 주요 내용\n- 텍스트 응답")
        self.assertIsNone(contract)
        mocked_warning.assert_called()

    def test_parse_llm_response_contract_from_content_block_list(self) -> None:
        """
        content block(list) 입력에서도 text 블록의 JSON을 파싱해야 한다.
        """
        raw_answer = [
            {"type": "text", "text": "```json\n{\"format_type\":\"general\",\"answer\":\"ok\"}\n```"},
            {"type": "tool_use", "name": "run_mail_post_action", "input": {"action": "current_mail"}},
        ]

        contract = parse_llm_response_contract(raw_answer=raw_answer)

        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("general", contract.format_type)
        self.assertEqual("ok", contract.answer)

    def test_parse_llm_response_contract_from_single_content_block_dict(self) -> None:
        """
        content block(dict) 입력에서도 text 필드를 파싱해야 한다.
        """
        raw_answer = {"type": "text", "text": "```json\n{\"format_type\":\"summary\",\"summary_lines\":[\"a\"]}\n```"}

        contract = parse_llm_response_contract(raw_answer=raw_answer)

        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("summary", contract.format_type)
        self.assertEqual(["a"], contract.summary_lines)

    def test_parse_llm_response_contract_repairs_trailing_comma(self) -> None:
        """
        후행 콤마가 있는 JSON도 관용 보정 후 파싱해야 한다.
        """
        raw_answer = "```json\n{\"format_type\":\"general\",\"answer\":\"ok\",}\n```"

        contract = parse_llm_response_contract(raw_answer=raw_answer)

        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("ok", contract.answer)

    def test_parse_llm_response_contract_returns_none_for_non_json_text(self) -> None:
        """순수 텍스트 응답은 계약 파싱 없이 None을 반환해야 한다."""
        contract = parse_llm_response_contract(raw_answer="요약 결과:\n1. 핵심 A\n2. 핵심 B")
        self.assertIsNone(contract)

    def test_augment_contract_with_tool_payload_overrides_route_flow_with_mail_context(self) -> None:
        """
        커뮤니케이션 흐름은 모델값보다 mail_context route_flow를 우선 사용해야 한다.
        """
        raw_answer = (
            "```json\n"
            "{\"format_type\":\"standard_summary\",\"basic_info\":{\"커뮤니케이션 흐름\":\"박철환=>-\"}}\n"
            "```"
        )
        contract = parse_llm_response_contract(raw_answer=raw_answer)
        assert contract is not None
        augmented = augment_contract_with_tool_payload(
            user_message="현재메일 요약해줘",
            contract=contract,
            tool_payload={
                "mail_context": {
                    "route_flow": "2026-02-26::조성준=>박철환%%2026-02-26::정유정=>강민창",
                }
            },
        )
        self.assertEqual(
            "2026-02-26::조성준=>박철환%%2026-02-26::정유정=>강민창",
            str(augmented.basic_info.get("커뮤니케이션 흐름") or ""),
        )


if __name__ == "__main__":
    unittest.main()
