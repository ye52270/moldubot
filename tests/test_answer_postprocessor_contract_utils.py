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

    def test_parse_llm_response_contract_removes_control_chars(self) -> None:
        """
        제어문자가 섞여 있어도 제거 후 JSON 파싱에 성공해야 한다.
        """
        raw_answer = "```json\n{\"format_type\":\"general\",\x0b\"answer\":\"ok\"}\n```"

        contract = parse_llm_response_contract(raw_answer=raw_answer)

        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("ok", contract.answer)

    def test_parse_llm_response_contract_unwraps_double_braces(self) -> None:
        """
        이중 중괄호(`{{...}}`) 래핑도 언랩 후 파싱해야 한다.
        """
        raw_answer = "```json\n{{\"format_type\":\"general\",\"answer\":\"ok\"}}\n```"

        contract = parse_llm_response_contract(raw_answer=raw_answer)

        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("ok", contract.answer)

    def test_parse_llm_response_contract_removes_invisible_unicode_controls(self) -> None:
        """
        JSON 객체 내부의 zero-width 제어문자도 제거 후 파싱해야 한다.
        """
        raw_answer = "```json\n{\u200b\"format_type\":\"general\",\"answer\":\"ok\"}\n```"

        contract = parse_llm_response_contract(raw_answer=raw_answer)

        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("ok", contract.answer)

    def test_parse_llm_response_contract_decodes_escaped_json_candidate_once(self) -> None:
        """
        `{\\n \"...\"}` 형태의 이스케이프 JSON 문자열도 1회 복원 후 파싱해야 한다.
        """
        raw_answer = "```json\n{\\n  \\\"format_type\\\":\\\"general\\\",\\n  \\\"answer\\\":\\\"ok\\\"\\n}\n```"

        contract = parse_llm_response_contract(raw_answer=raw_answer)

        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("general", contract.format_type)
        self.assertEqual("ok", contract.answer)

    def test_parse_llm_response_contract_repairs_invalid_backslash_escape(self) -> None:
        """
        유효하지 않은 백슬래시 이스케이프가 있어도 보정 후 파싱해야 한다.
        """
        raw_answer = "```json\n{\"format_type\":\"general\",\"answer\":\"path \\\\q\"}\n```"

        contract = parse_llm_response_contract(raw_answer=raw_answer)

        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("general", contract.format_type)
        self.assertIn("path", contract.answer)

    def test_parse_llm_response_contract_from_python_literal_text_block_string(self) -> None:
        """
        `{'type': 'text', 'text': '{...json...'}` 형태 문자열도 text를 복원해 파싱해야 한다.
        """
        raw_answer = (
            "{'type': 'text', 'text': '{\\n"
            "  \"format_type\": \"standard_summary\",\\n"
            "  \"core_issue\": \"테스트 이슈\",\\n"
            "  \"major_points\": [\"포인트1\", \"포인트2\"],\\n"
            "  \"required_actions\": [\"조치1\"]\\n"
            "}'}"
        )

        contract = parse_llm_response_contract(raw_answer=raw_answer)

        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("standard_summary", contract.format_type)
        self.assertEqual("테스트 이슈", contract.core_issue)
        self.assertEqual(["포인트1", "포인트2"], contract.major_points)
        self.assertEqual(["조치1"], contract.required_actions)

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
