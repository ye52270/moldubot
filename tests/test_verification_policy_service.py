from __future__ import annotations

import unittest

from app.services.verification_policy_service import decide_web_verification


class VerificationPolicyServiceTest(unittest.TestCase):
    """웹 검증 정책 판단을 검증한다."""

    def test_blocks_current_mail_without_explicit_verification(self) -> None:
        """current_mail 범위에서는 명시 요청이 없으면 웹 검증을 차단해야 한다."""
        decision = decide_web_verification(
            user_message="현재메일에서 DB 오류 원인 알려줘",
            intent_task_type="analysis",
            resolved_scope="current_mail",
            tool_payload={"action": "current_mail"},
            intent_confidence=0.91,
            model_answer="원인은 인증서 체인 누락으로 보입니다.",
        )
        self.assertFalse(decision.enabled)
        self.assertIn("blocked_by_current_mail_scope", decision.reasons)

    def test_allows_current_mail_with_explicit_verification(self) -> None:
        """current_mail 범위라도 검증 명시 요청이면 웹 검증을 허용해야 한다."""
        decision = decide_web_verification(
            user_message="현재메일 기준으로 이 답변이 맞는지 근거와 출처 검증해줘",
            intent_task_type="analysis",
            resolved_scope="current_mail",
            tool_payload={"action": "current_mail"},
            intent_confidence=0.91,
            model_answer="원인은 인증서 체인 누락으로 보입니다.",
        )
        self.assertTrue(decision.enabled)
        self.assertIn("explicit_verification_request", decision.reasons)

    def test_requires_explicit_external_request_in_global_scope(self) -> None:
        """global 범위에서는 명시 외부근거 요청이 있어야 웹 검증을 허용해야 한다."""
        decision = decide_web_verification(
            user_message="원인과 대응 정리해줘",
            intent_task_type="analysis",
            resolved_scope="global_search",
            tool_payload={},
            intent_confidence=0.44,
            model_answer="추정입니다.",
        )
        self.assertFalse(decision.enabled)
        self.assertIn("policy_not_matched", decision.reasons)

    def test_blocks_external_search_when_user_requests_internal_only(self) -> None:
        """명시적으로 외부검색 제외를 요청하면 웹 검증을 차단해야 한다."""
        decision = decide_web_verification(
            user_message="현재메일 기준으로 외부 검색 없이 내부메일만 정리해줘",
            intent_task_type="analysis",
            resolved_scope="global_search",
            tool_payload={},
            intent_confidence=0.92,
            model_answer="",
        )
        self.assertFalse(decision.enabled)
        self.assertIn("explicit_internal_only_request", decision.reasons)


if __name__ == "__main__":
    unittest.main()
