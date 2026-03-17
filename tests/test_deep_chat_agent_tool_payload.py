from __future__ import annotations

import json
import unittest
from contextvars import ContextVar

from app.agents.deep_chat_agent import (
    DeepChatAgent,
    _extract_latest_tool_payload,
    _get_agent_checkpointer,
    _resolve_thread_id,
)


class DeepChatAgentToolPayloadTest(unittest.TestCase):
    """deep_chat_agent의 tool payload 선택 우선순위를 검증한다."""

    def test_prefers_latest_payload_when_query_is_not_mail_search(self) -> None:
        """메일검색 질의가 아니면 최신 tool payload를 우선 선택해야 한다."""
        result = {
            "messages": [
                {
                    "role": "tool",
                    "content": json.dumps({"action": "mail_search", "results": [{"message_id": "m-1"}]}),
                },
                {
                    "role": "tool",
                    "content": json.dumps({"action": "current_date", "today": "2026-03-01"}),
                },
            ]
        }

        payload = _extract_latest_tool_payload(result=result, user_message="오늘 날짜 알려줘")

        self.assertEqual("current_date", payload.get("action"))

    def test_prefers_mail_search_payload_when_query_is_mail_search(self) -> None:
        """메일검색 질의면 최신 payload가 아니어도 mail_search payload를 우선 선택해야 한다."""
        result = {
            "messages": [
                {
                    "role": "tool",
                    "content": json.dumps({"action": "mail_search", "results": [{"message_id": "m-10"}]}),
                },
                {
                    "role": "tool",
                    "content": json.dumps({"action": "current_date", "today": "2026-03-01"}),
                },
            ]
        }

        payload = _extract_latest_tool_payload(result=result, user_message="M365 관련 메일 조회해줘")

        self.assertEqual("mail_search", payload.get("action"))

    def test_falls_back_to_latest_payload_when_mail_search_missing(self) -> None:
        """mail_search payload가 없으면 최신 payload를 반환해야 한다."""
        result = {
            "messages": [
                {"role": "tool", "content": json.dumps({"action": "search_meeting_schedule"})},
                {"role": "tool", "content": json.dumps({"action": "current_date", "today": "2026-03-01"})},
            ]
        }

        payload = _extract_latest_tool_payload(result=result, user_message="지난주 회의 일정 알려줘")

        self.assertEqual("current_date", payload.get("action"))

    def test_ignores_invalid_tool_content(self) -> None:
        """파싱 불가능한 tool content는 무시하고 유효 payload를 찾아야 한다."""
        result = {
            "messages": [
                {"role": "tool", "content": "{invalid json"},
                {"role": "tool", "content": json.dumps({"action": "mail_search", "results": []})},
            ]
        }

        payload = _extract_latest_tool_payload(result=result, user_message="메일 검색")

        self.assertEqual("mail_search", payload.get("action"))

    def test_resolve_thread_id_returns_input_when_present(self) -> None:
        """thread_id가 전달되면 동일 값을 반환해야 한다."""
        self.assertEqual("thread-1", _resolve_thread_id(thread_id="thread-1"))

    def test_resolve_thread_id_generates_when_missing(self) -> None:
        """thread_id가 비어 있으면 기본 접두사 값으로 생성해야 한다."""
        generated = _resolve_thread_id(thread_id="")
        self.assertTrue(generated.startswith("outlook_"))

    def test_checkpointer_isolated_by_prompt_variant(self) -> None:
        """프롬프트 variant가 다르면 checkpointer 인스턴스가 분리되어야 한다."""
        summary_cp = _get_agent_checkpointer("quality_structured")
        review_cp = _get_agent_checkpointer("code_review_expert")
        self.assertIsNot(summary_cp, review_cp)

    def test_build_turn_response_allows_missing_user_message_for_resume_path(self) -> None:
        """resume 경로처럼 user_message 없이 호출되어도 TypeError 없이 처리되어야 한다."""
        agent = DeepChatAgent.__new__(DeepChatAgent)
        agent._last_tool_payload_ctx = ContextVar("test_last_tool_payload", default={})
        agent._last_assistant_answer_ctx = ContextVar("test_last_answer", default="")
        response = agent._build_turn_response(
            result={"messages": []},
            thread_id="thread-confirm-1",
        )
        self.assertIn(response.get("status"), ("completed", "failed"))
        self.assertEqual("thread-confirm-1", response.get("thread_id"))

    def test_build_resume_decisions_falls_back_on_single_pending_interrupt_when_token_mismatch(self) -> None:
        """pending interrupt가 1개면 confirm_token 불일치여도 승인 결정을 생성해야 한다."""
        agent = DeepChatAgent.__new__(DeepChatAgent)

        class _Interrupt:
            def __init__(self, interrupt_id: str) -> None:
                self.id = interrupt_id
                self.value = {"action_requests": [{"name": "create_outlook_calendar_event"}]}

        class _State:
            interrupts = [_Interrupt("interrupt-a")]

        class _Graph:
            @staticmethod
            def get_state(config: object) -> object:
                del config
                return _State()

        agent._graph = _Graph()
        decisions = agent._build_resume_decisions(
            thread_id="thread-1",
            approved=True,
            confirm_token="interrupt-b",
        )
        self.assertEqual([{"type": "approve"}], decisions)

    def test_build_resume_decisions_returns_empty_when_multiple_pending_and_token_mismatch(self) -> None:
        """pending interrupt가 여러 개면 confirm_token 불일치 시 결정을 만들지 않아야 한다."""
        agent = DeepChatAgent.__new__(DeepChatAgent)

        class _Interrupt:
            def __init__(self, interrupt_id: str) -> None:
                self.id = interrupt_id
                self.value = {"action_requests": [{"name": "tool-x"}]}

        class _State:
            interrupts = [_Interrupt("interrupt-a"), _Interrupt("interrupt-c")]

        class _Graph:
            @staticmethod
            def get_state(config: object) -> object:
                del config
                return _State()

        agent._graph = _Graph()
        decisions = agent._build_resume_decisions(
            thread_id="thread-2",
            approved=True,
            confirm_token="interrupt-b",
        )
        self.assertEqual([], decisions)

    def test_build_resume_decisions_supports_edit_action(self) -> None:
        """edit 결정이면 edited_action을 decision payload에 포함해야 한다."""
        agent = DeepChatAgent.__new__(DeepChatAgent)

        class _Interrupt:
            def __init__(self, interrupt_id: str) -> None:
                self.id = interrupt_id
                self.value = {"action_requests": [{"name": "create_outlook_calendar_event"}]}

        class _State:
            interrupts = [_Interrupt("interrupt-a")]

        class _Graph:
            @staticmethod
            def get_state(config: object) -> object:
                del config
                return _State()

        agent._graph = _Graph()
        edited_action = {
            "name": "create_outlook_calendar_event",
            "args": {"subject": "수정된 일정"},
        }
        decisions = agent._build_resume_decisions(
            thread_id="thread-3",
            approved=False,
            confirm_token="interrupt-a",
            decision_type="edit",
            edited_action=edited_action,
        )
        self.assertEqual(
            [{"type": "edit", "edited_action": edited_action}],
            decisions,
        )

if __name__ == "__main__":
    unittest.main()
