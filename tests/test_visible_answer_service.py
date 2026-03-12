from __future__ import annotations

import unittest

from app.services.visible_answer_service import iter_answer_stream_chunks, sanitize_visible_answer_text


class VisibleAnswerServiceTest(unittest.TestCase):
    """사용자 노출 답변 정규화/스트림 청크 규칙을 검증한다."""

    def test_sanitize_visible_answer_text_removes_structured_prefix(self) -> None:
        """선행 intent blob은 제거하고 본문만 남겨야 한다."""
        source = '{"original_query":"q","steps":["search_mails"],"task_type":"retrieval","output_format":"general","focus_topics":["mail_general"]}결과는 3건입니다.'
        self.assertEqual('결과는 3건입니다.', sanitize_visible_answer_text(source))

    def test_iter_answer_stream_chunks_preserves_spaces(self) -> None:
        """청크 분해 시 공백이 보존되어야 단어가 붙지 않는다."""
        chunks = iter_answer_stream_chunks('첫 문장 입니다. 다음 문장')
        self.assertEqual(''.join(chunks), '첫 문장 입니다. 다음 문장')
        self.assertGreaterEqual(len(chunks), 2)


if __name__ == '__main__':
    unittest.main()
