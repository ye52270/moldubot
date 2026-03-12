from __future__ import annotations

import unittest

from app.api.search_chat_flow_helpers import decide_postprocess_execution_policy


class SearchChatFlowHelpersPolicyTest(unittest.TestCase):
    """
    search_chat postprocess 실행 정책 단위 테스트.
    """

    def test_current_mail_mail_search_keeps_web_policy_open(self) -> None:
        """
        current_mail 범위라도 웹 출처 판단은 하위 정책 함수에서 결정해야 한다.
        """
        policy = decide_postprocess_execution_policy(
            intent_output_format="general",
            tool_action="mail_search",
            resolved_scope="current_mail",
        )
        self.assertFalse(policy.skip_web_sources)
        self.assertFalse(policy.skip_related_mail_enrichment)

    def test_global_mail_search_keeps_web_sources(self) -> None:
        """
        전역 mail_search는 기존처럼 웹 출처 검색 허용 정책을 유지해야 한다.
        """
        policy = decide_postprocess_execution_policy(
            intent_output_format="general",
            tool_action="mail_search",
            resolved_scope="global_search",
        )
        self.assertFalse(policy.skip_web_sources)
        self.assertFalse(policy.skip_related_mail_enrichment)

    def test_general_non_mail_search_skips_expensive_steps(self) -> None:
        """
        일반 non-mail 액션은 고비용 후처리를 스킵해야 한다.
        """
        policy = decide_postprocess_execution_policy(
            intent_output_format="general",
            tool_action="analysis",
            resolved_scope="global_search",
        )
        self.assertTrue(policy.skip_web_sources)
        self.assertTrue(policy.skip_related_mail_enrichment)


if __name__ == "__main__":
    unittest.main()
