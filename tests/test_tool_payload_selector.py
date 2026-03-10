from __future__ import annotations

import json
import unittest

from app.agents.tool_payload_selector import extract_preferred_tool_payload_from_messages


class ToolPayloadSelectorTest(unittest.TestCase):
    """tool payload selector 공통 규칙을 검증한다."""

    def test_returns_latest_payload_without_preferred_action(self) -> None:
        """preferred_action이 없으면 최신 payload를 반환해야 한다."""
        messages = [
            {"role": "tool", "content": json.dumps({"action": "mail_search", "count": 3})},
            {"role": "tool", "content": json.dumps({"action": "current_date", "date": "2026-03-01"})},
        ]

        payload = extract_preferred_tool_payload_from_messages(messages=messages)

        self.assertEqual("current_date", payload.get("action"))

    def test_prefers_matching_action_if_present(self) -> None:
        """선호 action이 존재하면 최신 payload가 아니어도 우선 선택해야 한다."""
        messages = [
            {"role": "tool", "content": json.dumps({"action": "mail_search", "count": 3})},
            {"role": "tool", "content": json.dumps({"action": "current_date", "date": "2026-03-01"})},
        ]

        payload = extract_preferred_tool_payload_from_messages(
            messages=messages,
            preferred_action="mail_search",
        )

        self.assertEqual("mail_search", payload.get("action"))

    def test_ignores_invalid_tool_content(self) -> None:
        """잘못된 JSON content는 무시하고 유효 payload를 선택해야 한다."""
        messages = [
            {"role": "tool", "content": "{broken"},
            {"role": "tool", "content": json.dumps({"action": "mail_search", "count": 1})},
        ]

        payload = extract_preferred_tool_payload_from_messages(messages=messages, preferred_action="mail_search")

        self.assertEqual("mail_search", payload.get("action"))

    def test_merges_multiple_mail_search_payloads_when_preferred(self) -> None:
        """동일 턴 mail_search가 여러 번 있으면 결과/요약을 병합해야 한다."""
        messages = [
            {
                "role": "tool",
                "content": json.dumps(
                    {
                        "action": "mail_search",
                        "results": [
                            {"message_id": "m1", "subject": "첫째", "summary_text": "첫째 요약"},
                            {"message_id": "m2", "subject": "둘째", "summary_text": "둘째 요약"},
                        ],
                        "aggregated_summary": ["첫째 요약", "둘째 요약"],
                    }
                ),
            },
            {
                "role": "tool",
                "content": json.dumps(
                    {
                        "action": "mail_search",
                        "results": [
                            {"message_id": "m2", "subject": "둘째", "summary_text": "둘째 요약"},
                            {"message_id": "m3", "subject": "셋째", "summary_text": "셋째 요약"},
                        ],
                        "aggregated_summary": ["셋째 요약"],
                    }
                ),
            },
        ]
        payload = extract_preferred_tool_payload_from_messages(messages=messages, preferred_action="mail_search")
        self.assertEqual("mail_search", payload.get("action"))
        self.assertEqual(3, payload.get("count"))
        results = payload.get("results")
        self.assertIsInstance(results, list)
        self.assertEqual(["m1", "m2", "m3"], [item.get("message_id") for item in results])
        self.assertEqual(["첫째 요약", "둘째 요약", "셋째 요약"], payload.get("aggregated_summary"))
        query_summaries = payload.get("query_summaries")
        self.assertIsInstance(query_summaries, list)

    def test_preserves_query_summaries_when_aggregated_summary_missing(self) -> None:
        """aggregated_summary가 없어도 summary_text 기반 query_summaries를 보존해야 한다."""
        messages = [
            {
                "role": "tool",
                "content": json.dumps(
                    {
                        "action": "mail_search",
                        "query": "M365 프로젝트 진행",
                        "results": [
                            {"message_id": "m1", "summary_text": "프로젝트 일정 협의 메일"},
                        ],
                    }
                ),
            },
            {
                "role": "tool",
                "content": json.dumps(
                    {
                        "action": "mail_search",
                        "query": "기술적 이슈",
                        "results": [
                            {"message_id": "m2", "summary_text": "긴급 장애 대응 회의 요청"},
                        ],
                    }
                ),
            },
        ]

        payload = extract_preferred_tool_payload_from_messages(messages=messages, preferred_action="mail_search")

        self.assertEqual("mail_search", payload.get("action"))
        query_summaries = payload.get("query_summaries")
        self.assertIsInstance(query_summaries, list)
        self.assertEqual(2, len(query_summaries))
        self.assertEqual("M365 프로젝트 진행", query_summaries[0].get("query"))
        self.assertEqual("기술적 이슈", query_summaries[1].get("query"))

    def test_parses_wrapped_json_object_from_tool_content(self) -> None:
        """tool content가 설명 텍스트로 감싸져 있어도 첫 JSON 객체를 파싱해야 한다."""
        messages = [
            {
                "role": "tool",
                "content": (
                    "subagent_result:\n"
                    '{"action":"mail_search","query":"기술적 이슈","query_summaries":[{"query":"기술적 이슈","lines":["장애 영향 검토 필요"]}]}'
                    "\n(end)"
                ),
            }
        ]
        payload = extract_preferred_tool_payload_from_messages(messages=messages, preferred_action="mail_search")
        self.assertEqual("mail_search", payload.get("action"))
        self.assertEqual("기술적 이슈", payload.get("query"))


if __name__ == "__main__":
    unittest.main()
