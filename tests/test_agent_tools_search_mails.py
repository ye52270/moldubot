from __future__ import annotations

import unittest
from unittest.mock import patch

from app.agents.tools import (
    reset_search_scope_contract,
    search_mails,
    search_meeting_schedule,
    set_search_scope_contract,
)


class AgentToolsSearchMailsTest(unittest.TestCase):
    """
    `search_mails` 질의 분기(일반/기술키워드 fan-out)를 검증한다.
    """

    def test_search_mails_fanouts_comma_separated_tech_keywords(self) -> None:
        """
        기술 키워드 콤마 질의는 키워드별 검색으로 fan-out 후 병합되어야 한다.
        """
        side_effect_payloads = [
            {
                "action": "mail_search",
                "status": "completed",
                "query": "장애",
                "aggregated_summary": ["장애 관련 대응 필요"],
                "results": [
                    {
                        "message_id": "m-1",
                        "summary_text": "장애 관련 대응 필요",
                        "subject": "장애 메일",
                        "received_date": "2026-03-01T00:00:00Z",
                        "sender_names": "kim",
                        "web_link": "https://example.com/m-1",
                    }
                ],
            },
            {
                "action": "mail_search",
                "status": "completed",
                "query": "오류",
                "aggregated_summary": ["오류 재현 로그 확인"],
                "results": [
                    {
                        "message_id": "m-2",
                        "summary_text": "오류 재현 로그 확인",
                        "subject": "오류 메일",
                        "received_date": "2026-03-02T00:00:00Z",
                        "sender_names": "lee",
                        "web_link": "https://example.com/m-2",
                    }
                ],
            },
            {
                "action": "mail_search",
                "status": "completed",
                "query": "보안",
                "aggregated_summary": [],
                "results": [],
            },
        ]
        with patch("app.agents.tools._MAIL_SEARCH_SERVICE.search", side_effect=side_effect_payloads) as mocked:
            payload = search_mails.func(query="장애, 오류, 보안", limit=5)
        self.assertEqual(3, mocked.call_count)
        self.assertEqual("mail_search", payload.get("action"))
        self.assertEqual(2, payload.get("count"))
        self.assertEqual(2, len(payload.get("results", [])))
        query_summaries = payload.get("query_summaries")
        self.assertIsInstance(query_summaries, list)
        self.assertEqual(["장애", "오류"], [row["query"] for row in query_summaries[:2]])

    def test_search_mails_keeps_single_query_for_general_request(self) -> None:
        """
        일반 질의는 fan-out 없이 단일 검색으로 처리되어야 한다.
        """
        payload = {
            "action": "mail_search",
            "status": "completed",
            "query": "M365 프로젝트 진행",
            "aggregated_summary": [],
            "results": [],
            "count": 0,
        }
        with patch("app.agents.tools._MAIL_SEARCH_SERVICE.search", return_value=payload) as mocked:
            result = search_mails.func(query="M365 프로젝트 진행", limit=5)
        self.assertEqual(1, mocked.call_count)
        self.assertEqual(payload, result)

    def test_search_mails_blocks_in_current_mail_scope(self) -> None:
        """
        current_mail scope 계약에서는 사서함 검색이 차단되어야 한다.
        """
        token = set_search_scope_contract({"mode": "current_mail"})
        try:
            payload = search_mails.func(query="M365 프로젝트", limit=5)
        finally:
            reset_search_scope_contract(token)
        self.assertEqual("failed", payload.get("status"))
        self.assertEqual(0, payload.get("count"))
        self.assertEqual([], payload.get("results"))

    def test_search_mails_prefixes_anchor_for_tech_issue_query(self) -> None:
        """
        기술 이슈 축 질의는 scope anchor와 결합된 질의로 보정되어야 한다.
        """
        base_payload = {
            "action": "mail_search",
            "status": "completed",
            "query": "",
            "aggregated_summary": [],
            "results": [],
            "count": 0,
        }
        token = set_search_scope_contract({"mode": "global_search", "anchor_query": "M365 프로젝트"})
        try:
            with patch("app.agents.tools._MAIL_SEARCH_SERVICE.search", return_value=base_payload) as mocked:
                search_mails.func(query="기술적 이슈", limit=5)
        finally:
            reset_search_scope_contract(token)
        self.assertEqual(1, mocked.call_count)
        kwargs = mocked.call_args.kwargs
        self.assertEqual("M365 프로젝트 기술적 이슈", kwargs.get("query"))

    def test_search_meeting_schedule_blocks_in_current_mail_scope(self) -> None:
        """
        current_mail scope 계약에서는 일정 검색도 차단되어야 한다.
        """
        token = set_search_scope_contract({"mode": "current_mail"})
        try:
            payload = search_meeting_schedule.func(query="M365 일정", limit=5)
        finally:
            reset_search_scope_contract(token)
        self.assertEqual("failed", payload.get("status"))
        self.assertEqual([], payload.get("results"))


if __name__ == "__main__":
    unittest.main()
