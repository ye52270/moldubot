from __future__ import annotations

import unittest

from app.api.search_chat_flow import (
    _build_agent_thread_id,
    _extract_overlap_tokens,
    _should_retry_current_mail_summary_json,
    _use_fresh_agent_thread_for_current_mail_summary,
)


class SearchChatFlowOverlapTokensTest(unittest.TestCase):
    """search_chat_flow 토큰 추출 유틸 회귀를 검증한다."""

    def test_extract_overlap_tokens_returns_normalized_tokens(self) -> None:
        """한글/영문/숫자 토큰을 2글자 이상 기준으로 추출해야 한다."""
        tokens = _extract_overlap_tokens("Grafana Daily Report 미수신 확인 요청")
        self.assertIn("grafana", tokens)
        self.assertIn("daily", tokens)
        self.assertIn("report", tokens)
        self.assertIn("미수신", tokens)
        self.assertNotIn("a", tokens)

    def test_use_fresh_agent_thread_for_current_mail_summary_true(self) -> None:
        """`/메일요약` 요청은 fresh agent thread를 사용해야 한다."""
        should_use = _use_fresh_agent_thread_for_current_mail_summary(
            user_message="/메일요약",
            resolved_scope="current_mail",
            selected_message_id="AQMk_test_message_id",
        )
        self.assertTrue(should_use)

    def test_build_agent_thread_id_appends_current_mail_summary_suffix(self) -> None:
        """fresh 모드에서는 base thread와 분리된 실행용 thread_id를 구성해야 한다."""
        built = _build_agent_thread_id(
            thread_id="thread-1",
            selected_message_id="AQMk_test_message_id",
            use_fresh_thread=True,
        )
        self.assertIn("thread-1::cms::AQMk_test_message_id", built)

    def test_should_retry_current_mail_summary_json_when_contract_parse_fails(self) -> None:
        """`/메일요약`에서 raw_model_content가 JSON 계약이 아니면 재시도해야 한다."""
        should_retry = _should_retry_current_mail_summary_json(
            user_message="/메일요약",
            resolved_scope="current_mail",
            tool_payload={"action": "current_mail"},
            final_answer="```json\n{\"format_type\":\"standard_summary\"}\n```",
            raw_model_content="### markdown summary only",
        )
        self.assertTrue(should_retry)

    def test_should_retry_current_mail_summary_json_false_for_rendered_summary(self) -> None:
        """최종 답변이 이미 렌더된 요약 마크다운이면 재시도하지 않아야 한다."""
        should_retry = _should_retry_current_mail_summary_json(
            user_message="/메일요약",
            resolved_scope="current_mail",
            tool_payload={"action": "current_mail"},
            final_answer="### 🧾 제목\n\n메일 제목\n",
            raw_model_content="### markdown summary only",
        )
        self.assertFalse(should_retry)


if __name__ == "__main__":
    unittest.main()
