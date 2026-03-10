from __future__ import annotations

import json
import unittest

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.middleware.agent_middlewares import _extract_latest_tool_payload


class AgentMiddlewaresToolPayloadTest(unittest.TestCase):
    """after_model tool payload 선택이 현재 턴 기준으로 동작하는지 검증한다."""

    def test_prefers_mail_search_from_current_turn_only(self) -> None:
        """이전 턴 mail_search가 있어도 현재 턴의 mail_search payload를 선택해야 한다."""
        previous_turn_payload = {"action": "mail_search", "query": "조영득", "count": 3}
        current_turn_payload = {"action": "mail_search", "query": "박준용", "count": 5}
        messages = [
            HumanMessage(content="이전 요청"),
            ToolMessage(content=json.dumps(previous_turn_payload), tool_call_id="old-1"),
            AIMessage(content="이전 응답"),
            HumanMessage(content="현재 요청"),
            ToolMessage(content=json.dumps(current_turn_payload), tool_call_id="new-1"),
            AIMessage(content="현재 응답"),
        ]

        payload = _extract_latest_tool_payload(
            messages=messages,
            ai_index=len(messages) - 1,
            user_message="박준용 관련 메일 조회",
        )

        self.assertEqual("박준용", payload.get("query"))
        self.assertEqual(5, payload.get("count"))

    def test_returns_empty_when_turn_tool_missing(self) -> None:
        """현재 턴에 tool이 없으면 과거 턴 payload를 재사용하지 않고 빈 payload를 반환해야 한다."""
        messages = [
            HumanMessage(content="요청 1"),
            ToolMessage(content=json.dumps({"action": "mail_search", "query": "조영득"}), tool_call_id="t-1"),
            AIMessage(content="응답 1"),
            HumanMessage(content="요청 2"),
            AIMessage(content="응답 2"),
        ]

        payload = _extract_latest_tool_payload(
            messages=messages,
            ai_index=len(messages) - 1,
            user_message="박준용 관련 메일 조회",
        )

        self.assertEqual({}, payload)


if __name__ == "__main__":
    unittest.main()
