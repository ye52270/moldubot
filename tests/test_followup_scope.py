from __future__ import annotations

import unittest

from app.api.followup_scope import (
    SCOPE_CURRENT_MAIL,
    SCOPE_PREVIOUS_RESULTS,
    SCOPE_GLOBAL_SEARCH,
    apply_scope_instruction,
    build_scope_clarification,
    remember_followup_search_result,
    parse_requested_scope,
    resolve_default_scope,
    resolve_effective_scope,
    reset_followup_scope_state_for_test,
)


class FollowupScopeTest(unittest.TestCase):
    """Follow-up scope 판별/상태 저장 규칙을 검증한다."""

    def setUp(self) -> None:
        """테스트 간 상태 오염을 막기 위해 저장소를 초기화한다."""
        reset_followup_scope_state_for_test()

    def test_parse_requested_scope_accepts_only_allowed_values(self) -> None:
        """runtime_options.scope는 허용값일 때만 반영되어야 한다."""
        self.assertEqual(SCOPE_CURRENT_MAIL, parse_requested_scope({"scope": "current_mail"}))
        self.assertEqual("", parse_requested_scope({"scope": "invalid"}))
        self.assertEqual("", parse_requested_scope(None))

    def test_resolve_effective_scope_prefers_explicit_text(self) -> None:
        """요청 옵션이 없을 때 명시 표현으로 scope를 결정해야 한다."""
        self.assertEqual(SCOPE_CURRENT_MAIL, resolve_effective_scope("현재메일 이슈 알려줘", ""))
        self.assertEqual(SCOPE_GLOBAL_SEARCH, resolve_effective_scope("전체 메일에서 다시 찾아줘", ""))
        self.assertEqual(SCOPE_GLOBAL_SEARCH, resolve_effective_scope("현재메일 말고 일반 질문 할게", ""))
        self.assertEqual(SCOPE_GLOBAL_SEARCH, resolve_effective_scope("저 LDAP 쿼리에 대해 외부 검색해줘", ""))
        self.assertEqual(SCOPE_CURRENT_MAIL, resolve_effective_scope("현재메일 LDAP 쿼리를 인터넷 검색해줘", ""))

    def test_build_scope_clarification_for_ambiguous_mail_search(self) -> None:
        """메일 검색 질의가 모호하면 현재/전체 scope 선택이 필요하다."""
        clarification = build_scope_clarification(
            user_message="M365 관련 메일 찾아서 요약해줘",
            requested_scope="",
            thread_id="thread-1",
            selected_mail_available=True,
        )
        self.assertIsNotNone(clarification)
        self.assertTrue(bool(clarification.get("required")))
        options = clarification.get("options", [])
        scopes = [str(option.get("scope")) for option in options]
        self.assertIn(SCOPE_CURRENT_MAIL, scopes)
        self.assertIn(SCOPE_GLOBAL_SEARCH, scopes)
        self.assertEqual(2, len(scopes))

    def test_build_scope_clarification_for_hybrid_related_query(self) -> None:
        """현재메일+유사검색 하이브리드 문장은 명시 current_mail이어도 선택을 요구해야 한다."""
        clarification = build_scope_clarification(
            user_message="현재메일과 유사한 메일을 조회해줘",
            requested_scope="",
            thread_id="thread-1",
            selected_mail_available=True,
        )
        self.assertIsNotNone(clarification)
        options = clarification.get("options", [])
        scopes = [str(option.get("scope")) for option in options]
        self.assertIn(SCOPE_CURRENT_MAIL, scopes)
        self.assertIn(SCOPE_GLOBAL_SEARCH, scopes)
        self.assertEqual(2, len(scopes))

    def test_apply_scope_instruction_embeds_scope_context(self) -> None:
        """scope 선택 시 모델 입력 앞에 범위 지시문이 주입되어야 한다."""
        scoped_message = apply_scope_instruction(
            user_message="이슈에 대해 알려줘",
            resolved_scope="previous_results",
            thread_id="thread-2",
        )
        self.assertIn("직전 조회 결과", scoped_message)
        self.assertIn("이슈에 대해 알려줘", scoped_message)

    def test_followup_reference_clarification_includes_previous_results_option(self) -> None:
        """직전 조회 컨텍스트가 있을 때 모호 후속질의는 previous_results 옵션을 포함해야 한다."""
        remember_followup_search_result(thread_id="thread-3", search_result_count=4)
        clarification = build_scope_clarification(
            user_message="그거 이슈 정리해줘",
            requested_scope="",
            thread_id="thread-3",
            selected_mail_available=True,
        )
        self.assertIsNotNone(clarification)
        options = clarification.get("options", [])
        scopes = [str(option.get("scope")) for option in options]
        self.assertIn(SCOPE_CURRENT_MAIL, scopes)
        self.assertIn(SCOPE_PREVIOUS_RESULTS, scopes)
        self.assertIn(SCOPE_GLOBAL_SEARCH, scopes)

    def test_resolve_default_scope_uses_query_mode(self) -> None:
        """명시 scope가 없으면 현재메일 질의 여부로 기본값을 결정해야 한다."""
        self.assertEqual(SCOPE_CURRENT_MAIL, resolve_default_scope(is_current_mail_mode=True))
        self.assertEqual(SCOPE_GLOBAL_SEARCH, resolve_default_scope(is_current_mail_mode=False))


if __name__ == "__main__":
    unittest.main()
