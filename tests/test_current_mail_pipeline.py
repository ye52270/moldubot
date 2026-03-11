from __future__ import annotations

import unittest

from app.api.current_mail_pipeline import (
    remember_sticky_current_mail,
    reset_sticky_current_mail_state_for_test,
    resolve_current_mail_mode,
)


class CurrentMailPipelineTest(unittest.TestCase):
    """현재메일 암시적 후속 질의 판별 규칙을 검증한다."""

    def setUp(self) -> None:
        """테스트 간 sticky 상태를 초기화한다."""
        reset_sticky_current_mail_state_for_test()

    def test_explicit_current_mail_query_is_always_current_mail_mode(self) -> None:
        """`현재메일` 명시 질의는 항상 현재메일 모드여야 한다."""
        result = resolve_current_mail_mode(
            user_message="현재메일 요약해줘",
            thread_id="thread-1",
            selected_mail_available=True,
            requested_scope="",
        )
        self.assertTrue(result)

    def test_implicit_followup_uses_sticky_anchor(self) -> None:
        """직전 현재메일 고정 상태가 있으면 암시 질의도 현재메일 모드여야 한다."""
        remember_sticky_current_mail(
            thread_id="thread-2",
            user_message="현재메일 요약해줘",
            requested_scope="",
            selected_mail_available=True,
            is_current_mail_mode=True,
        )
        result = resolve_current_mail_mode(
            user_message="구축 금액 정리해줘",
            thread_id="thread-2",
            selected_mail_available=True,
            requested_scope="",
        )
        self.assertTrue(result)

    def test_implicit_followup_with_selected_mail_defaults_to_current_mail(self) -> None:
        """선택 메일이 있는 암시적 분석 질의는 sticky 없이도 현재메일 모드여야 한다."""
        result = resolve_current_mail_mode(
            user_message="이 견적서에서 M365 라이선스 비용을 왜 따로 봐야 해?",
            thread_id="thread-2b",
            selected_mail_available=True,
            requested_scope="",
        )
        self.assertTrue(result)

    def test_explicit_global_query_turns_off_sticky_followup(self) -> None:
        """전체/검색 명시 질의가 오면 sticky current-mail 후속은 비활성화되어야 한다."""
        remember_sticky_current_mail(
            thread_id="thread-3",
            user_message="현재메일 요약해줘",
            requested_scope="",
            selected_mail_available=True,
            is_current_mail_mode=True,
        )
        remember_sticky_current_mail(
            thread_id="thread-3",
            user_message="전체 메일에서 찾아줘",
            requested_scope="",
            selected_mail_available=True,
            is_current_mail_mode=False,
        )
        result = resolve_current_mail_mode(
            user_message="구축 금액 정리해줘",
            thread_id="thread-3",
            selected_mail_available=True,
            requested_scope="",
        )
        self.assertFalse(result)

    def test_sticky_followup_requires_selected_mail(self) -> None:
        """선택 메일이 없으면 sticky 상태여도 현재메일 모드로 해석하면 안 된다."""
        remember_sticky_current_mail(
            thread_id="thread-4",
            user_message="현재메일 요약해줘",
            requested_scope="",
            selected_mail_available=True,
            is_current_mail_mode=True,
        )
        result = resolve_current_mail_mode(
            user_message="구축 금액 정리해줘",
            thread_id="thread-4",
            selected_mail_available=False,
            requested_scope="",
        )
        self.assertFalse(result)

    def test_requested_scope_overrides_sticky_mode(self) -> None:
        """UI scope 지정값은 sticky 판별보다 우선해야 한다."""
        remember_sticky_current_mail(
            thread_id="thread-5",
            user_message="현재메일 요약해줘",
            requested_scope="",
            selected_mail_available=True,
            is_current_mail_mode=True,
        )
        self.assertFalse(
            resolve_current_mail_mode(
                user_message="구축 금액 정리해줘",
                thread_id="thread-5",
                selected_mail_available=True,
                requested_scope="global_search",
            )
        )
        self.assertTrue(
            resolve_current_mail_mode(
                user_message="구축 금액 정리해줘",
                thread_id="thread-5",
                selected_mail_available=True,
                requested_scope="current_mail",
            )
        )

    def test_explicit_hub_query_disables_current_mail_mode(self) -> None:
        """메일 무관 명시 질의는 sticky 상태여도 current_mail 모드를 비활성화해야 한다."""
        remember_sticky_current_mail(
            thread_id="thread-6",
            user_message="현재메일 요약해줘",
            requested_scope="",
            selected_mail_available=True,
            is_current_mail_mode=True,
        )
        result = resolve_current_mail_mode(
            user_message="메일과 상관없이 파이썬 리스트 컴프리헨션 설명해줘",
            thread_id="thread-6",
            selected_mail_available=True,
            requested_scope="",
        )
        self.assertFalse(result)

    def test_explicit_hub_query_clears_sticky_followup(self) -> None:
        """메일 무관 명시 질의 이후에는 암시 후속 질의가 current_mail 모드로 유지되면 안 된다."""
        remember_sticky_current_mail(
            thread_id="thread-7",
            user_message="현재메일 요약해줘",
            requested_scope="",
            selected_mail_available=True,
            is_current_mail_mode=True,
        )
        remember_sticky_current_mail(
            thread_id="thread-7",
            user_message="메일 말고 일반 질문 할게",
            requested_scope="",
            selected_mail_available=True,
            is_current_mail_mode=False,
        )
        result = resolve_current_mail_mode(
            user_message="구축 금액 정리해줘",
            thread_id="thread-7",
            selected_mail_available=True,
            requested_scope="",
        )
        self.assertFalse(result)

    def test_multi_mail_analysis_query_prefers_global_scope(self) -> None:
        """다건 메일 비교/패턴 질의는 선택 메일이 있어도 global_search를 우선해야 한다."""
        result = resolve_current_mail_mode(
            user_message="관련 메일들 비교해서 일정 리스크 패턴 분석해줘",
            thread_id="thread-8",
            selected_mail_available=True,
            requested_scope="",
        )
        self.assertFalse(result)

    def test_multi_mail_analysis_query_overrides_explicit_current_mail_phrase(self) -> None:
        """현재메일 문구가 포함돼도 다건 비교 의도가 명확하면 global_search를 우선해야 한다."""
        result = resolve_current_mail_mode(
            user_message="현재 메일과 관련 메일들 비교해서 추이 분석해줘",
            thread_id="thread-9",
            selected_mail_available=True,
            requested_scope="",
        )
        self.assertFalse(result)

    def test_external_search_query_disables_current_mail_mode(self) -> None:
        """외부 검색 명시 질의는 선택 메일이 있어도 current_mail 모드를 비활성화해야 한다."""
        result = resolve_current_mail_mode(
            user_message="저 LDAP 쿼리에 대해 외부 검색을 해줘",
            thread_id="thread-10",
            selected_mail_available=True,
            requested_scope="",
        )
        self.assertFalse(result)

    def test_current_mail_external_search_query_keeps_current_mail_mode(self) -> None:
        """현재메일이 명시된 외부 검색 질의는 current_mail 모드를 유지해야 한다."""
        result = resolve_current_mail_mode(
            user_message="현재메일 LDAP 쿼리에 대해 인터넷 검색해줘",
            thread_id="thread-11",
            selected_mail_available=True,
            requested_scope="",
        )
        self.assertTrue(result)

    def test_mail_summary_skill_query_keeps_current_mail_mode_with_selected_mail(self) -> None:
        """`/메일요약` 스킬 질의는 선택 메일이 있으면 current_mail 모드를 유지해야 한다."""
        result = resolve_current_mail_mode(
            user_message="/메일요약",
            thread_id="thread-12",
            selected_mail_available=True,
            requested_scope="",
        )
        self.assertTrue(result)

    def test_selected_mail_defaults_to_current_mail_for_plain_followup(self) -> None:
        """선택 메일이 있으면 명시 반대 신호가 없는 일반 후속 질의는 current_mail로 본다."""
        result = resolve_current_mail_mode(
            user_message="수신실패되는 메일 주소가 뭔지 알려줘",
            thread_id="thread-13",
            selected_mail_available=True,
            requested_scope="",
        )
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
