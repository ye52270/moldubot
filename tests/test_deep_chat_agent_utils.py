from __future__ import annotations

import unittest

from app.agents.deep_chat_agent_utils import extract_assistant_text


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


if __name__ == "__main__":
    unittest.main()
