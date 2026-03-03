from __future__ import annotations

import unittest

from app.core.chat_eval_cases import CHAT_EVAL_CASES


class ChatEvalCasesTest(unittest.TestCase):
    """E2E 채팅 평가 케이스 기본 계약을 검증한다."""

    def test_case_count_and_required_fields(self) -> None:
        """케이스는 13개이며 필수 필드를 모두 가져야 한다."""
        self.assertEqual(13, len(CHAT_EVAL_CASES))
        for case in CHAT_EVAL_CASES:
            self.assertTrue(case["case_id"])
            self.assertTrue(case["query"])
            self.assertTrue(case["expectation"])
            self.assertIn("requires_current_mail", case)


if __name__ == "__main__":
    unittest.main()
