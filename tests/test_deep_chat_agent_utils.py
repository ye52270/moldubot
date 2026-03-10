from __future__ import annotations

import unittest

from app.agents.deep_chat_agent_utils import extract_assistant_text, extract_stream_token_text


class DeepChatAgentUtilsTest(unittest.TestCase):
    """
    deep_chat_agent_utils의 텍스트 추출 계약을 검증한다.
    """

    def test_extract_assistant_text_accepts_ai_role_mapping(self) -> None:
        """
        role='ai' 매핑 메시지에서도 text block을 추출해야 한다.
        """
        result = {
            "messages": [
                {"role": "human", "content": "질문"},
                {
                    "role": "ai",
                    "content": [
                        {"type": "text", "text": "대상 시스템 요약"},
                    ],
                },
            ]
        }
        self.assertEqual("대상 시스템 요약", extract_assistant_text(result=result))

    def test_extract_stream_token_text_accepts_ai_role_mapping(self) -> None:
        """
        스트림 아이템의 role='ai' 매핑에서도 토큰 텍스트를 추출해야 한다.
        """
        stream_item = {"role": "ai", "content": [{"type": "text", "text": "토큰"}]}
        self.assertEqual("토큰", extract_stream_token_text(stream_item=stream_item))


if __name__ == "__main__":
    unittest.main()
