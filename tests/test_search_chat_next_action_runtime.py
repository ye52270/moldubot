from __future__ import annotations

import unittest

from app.api.search_chat_flow import (
    normalize_next_action_id,
    resolve_forced_next_action_query,
    should_suppress_internal_mail_evidence,
    should_suppress_web_sources,
)


class SearchChatNextActionRuntimeTest(unittest.TestCase):
    """
    next action 런타임 강제 질의 매핑 유틸을 검증한다.
    """

    def test_normalize_next_action_id_accepts_supported_action(self) -> None:
        """
        허용된 next action 식별자는 소문자 정규화 후 반환해야 한다.
        """
        result = normalize_next_action_id({"next_action_id": "CREATE_TODO"})
        self.assertEqual("create_todo", result)

    def test_normalize_next_action_id_accepts_web_search(self) -> None:
        """
        `web_search`도 next action 강제 매핑 대상이어야 한다.
        """
        result = normalize_next_action_id({"next_action_id": "web_search"})
        self.assertEqual("web_search", result)

    def test_resolve_forced_next_action_query_uses_canonical_prompt(self) -> None:
        """
        지원 액션 식별자가 있으면 원본 질의 대신 고정 템플릿 질의를 반환해야 한다.
        """
        fallback = "임의 텍스트"
        result = resolve_forced_next_action_query(
            next_action_id="book_meeting_room",
            fallback_query=fallback,
        )
        self.assertEqual("현재메일 기준으로 회의실 예약해줘", result)

    def test_resolve_forced_query_for_related_mails_uses_mail_keywords(self) -> None:
        """
        관련 메일 조회 액션은 현재 메일 제목/발신자 키워드를 포함한 질의를 생성해야 한다.
        """
        result = resolve_forced_next_action_query(
            next_action_id="search_related_mails",
            fallback_query="원본",
            current_mail_subject="FW: [메일서버] Grafana Daily Report 미수신 확인 요청",
            current_mail_from="izocuna@sk.com",
        )
        self.assertIn("grafana", result.lower())
        self.assertIn("관련 메일 최근순으로 5개 조회해줘", result)

    def test_resolve_forced_query_for_web_search_uses_mail_keywords(self) -> None:
        """
        외부 정보 검색 액션은 현재 메일 키워드 기반 외부 검색 질의를 생성해야 한다.
        """
        result = resolve_forced_next_action_query(
            next_action_id="web_search",
            fallback_query="원본",
            current_mail_subject="FW: [메일서버] Grafana Daily Report 미수신 확인 요청",
            current_mail_from="izocuna@sk.com",
        )
        self.assertIn("grafana", result.lower())
        self.assertIn("외부 정보", result)

    def test_should_suppress_internal_mail_evidence_for_web_search(self) -> None:
        """
        외부 정보 검색 액션은 내부 유사메일 근거를 숨겨야 한다.
        """
        self.assertTrue(should_suppress_internal_mail_evidence("web_search"))
        self.assertFalse(should_suppress_internal_mail_evidence("search_related_mails"))

    def test_should_suppress_web_sources_for_related_mail_action(self) -> None:
        """
        관련 메일 조회 액션에서는 웹 출처 블록을 숨겨야 한다.
        """
        self.assertTrue(should_suppress_web_sources("search_related_mails"))
        self.assertFalse(should_suppress_web_sources("web_search"))


if __name__ == "__main__":
    unittest.main()
