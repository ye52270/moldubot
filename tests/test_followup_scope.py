from __future__ import annotations

import unittest

from app.api.followup_scope import (
    SCOPE_CURRENT_MAIL,
    SCOPE_GLOBAL_SEARCH,
    get_recent_search_result_count,
    remember_followup_search_result,
    resolve_default_scope,
    reset_followup_scope_state_for_test,
)


class FollowupScopeTest(unittest.TestCase):
    """Follow-up 상태 저장 규칙을 검증한다."""

    def setUp(self) -> None:
        """테스트 간 상태 오염을 막기 위해 저장소를 초기화한다."""
        reset_followup_scope_state_for_test()

    def test_remember_followup_search_result_stores_recent_count(self) -> None:
        """최근 검색 건수가 저장되면 동일 thread_id로 조회되어야 한다."""
        remember_followup_search_result(thread_id="thread-1", search_result_count=4)
        self.assertEqual(4, get_recent_search_result_count(thread_id="thread-1"))

    def test_remember_followup_search_result_removes_state_on_zero(self) -> None:
        """검색 건수가 0이면 기존 상태가 제거되어야 한다."""
        remember_followup_search_result(thread_id="thread-1", search_result_count=3)
        remember_followup_search_result(thread_id="thread-1", search_result_count=0)
        self.assertEqual(0, get_recent_search_result_count(thread_id="thread-1"))

    def test_resolve_default_scope_uses_query_mode(self) -> None:
        """명시 scope가 없으면 현재메일 질의 여부로 기본값을 결정해야 한다."""
        self.assertEqual(SCOPE_CURRENT_MAIL, resolve_default_scope(is_current_mail_mode=True))
        self.assertEqual(SCOPE_GLOBAL_SEARCH, resolve_default_scope(is_current_mail_mode=False))


if __name__ == "__main__":
    unittest.main()
