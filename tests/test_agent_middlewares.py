from __future__ import annotations

import unittest

from app.middleware.agent_middlewares import (
    _extract_original_user_message_from_injected_text,
    _extract_text_from_model_content,
    _normalize_search_tool_call_args,
    _normalize_raw_model_content,
)
from langchain_core.messages import HumanMessage


class AgentMiddlewaresTextExtractionTest(unittest.TestCase):
    """모델 content block에서 텍스트 추출 규칙을 검증한다."""
    RAW_LIMIT_FOR_TEST = 1200

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
        long_text = "x" * (self.RAW_LIMIT_FOR_TEST + 100)
        raw = _normalize_raw_model_content(content={"type": "text", "text": long_text})
        self.assertIsInstance(raw, dict)
        self.assertEqual(long_text, raw["text"])

    def test_extract_original_user_message_from_scope_prefixed_text(self) -> None:
        """scope prefix만 있는 주입 텍스트에서도 원본 사용자 입력을 복원해야 한다."""
        message = "[질의 범위] 전체 메일함 기준으로 처리\n/메일요약"
        extracted = _extract_original_user_message_from_injected_text(message_text=message)
        self.assertEqual("/메일요약", extracted)

    def test_normalize_search_tool_call_args_overrides_month_date_slots(self) -> None:
        """search_mails 도구 호출은 사용자 원문의 월 슬롯으로 날짜를 보정해야 한다."""
        request = type(
            "DummyRequest",
            (),
            {
                "tool_call": {
                    "name": "search_mails",
                    "args": {
                        "query": "조영득",
                        "start_date": "2023-01-01",
                        "end_date": "2023-01-31",
                    },
                },
                "state": {"messages": [HumanMessage(content="1월 조영득 관련 메일 조회해줘")]},
            },
        )()

        _normalize_search_tool_call_args(request=request)

        args = request.tool_call["args"]
        self.assertEqual("조영득", args.get("person"))
        self.assertNotEqual("2023-01-01", args.get("start_date"))
        self.assertNotEqual("2023-01-31", args.get("end_date"))


if __name__ == "__main__":
    unittest.main()
