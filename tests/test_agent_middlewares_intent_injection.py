from __future__ import annotations

import unittest
from unittest.mock import patch

from langchain_core.messages import HumanMessage, SystemMessage

from app.middleware.agent_middlewares import _inject_intent_decomposition_context_impl
from app.middleware.policies import INTENT_SYSTEM_CONTEXT_PREFIX


class AgentMiddlewaresIntentInjectionTest(unittest.TestCase):
    """before_model intent 컨텍스트 주입 동작을 검증한다."""

    def test_injects_system_context_without_mutating_human_message(self) -> None:
        """의도 주입 시 Human 본문은 유지하고 SystemMessage를 삽입해야 한다."""
        original_user = "현재메일에서 오류 원인 정리해줘"
        state = {"messages": [HumanMessage(content=original_user)]}
        with (
            patch("app.middleware.agent_middlewares.should_inject_intent_context", return_value=True),
            patch(
                "app.middleware.agent_middlewares.compose_intent_system_context",
                return_value=f"{INTENT_SYSTEM_CONTEXT_PREFIX}\n- 테스트 컨텍스트",
            ),
        ):
            result = _inject_intent_decomposition_context_impl(state=state, runtime=None)

        self.assertIsNone(result)
        messages = state.get("messages", [])
        self.assertEqual(2, len(messages))
        self.assertIsInstance(messages[0], SystemMessage)
        self.assertTrue(str(messages[0].content).startswith(INTENT_SYSTEM_CONTEXT_PREFIX))
        self.assertIsInstance(messages[1], HumanMessage)
        self.assertEqual(original_user, str(messages[1].content))

    def test_skips_duplicate_system_context_in_same_turn(self) -> None:
        """기존 intent system 컨텍스트는 제거 후 선두 system 블록으로 재주입해야 한다."""
        original_user = "현재메일에서 오류 원인 정리해줘"
        state = {
            "messages": [
                HumanMessage(content=original_user),
                SystemMessage(content=f"{INTENT_SYSTEM_CONTEXT_PREFIX}\n- 기존 컨텍스트"),
            ]
        }
        with (
            patch("app.middleware.agent_middlewares.should_inject_intent_context", return_value=True),
            patch(
                "app.middleware.agent_middlewares.compose_intent_system_context",
                return_value=f"{INTENT_SYSTEM_CONTEXT_PREFIX}\n- 신규 컨텍스트",
            ),
        ):
            result = _inject_intent_decomposition_context_impl(state=state, runtime=None)

        self.assertIsNone(result)
        messages = state.get("messages", [])
        self.assertEqual(2, len(messages))
        self.assertIsInstance(messages[0], SystemMessage)
        self.assertEqual(f"{INTENT_SYSTEM_CONTEXT_PREFIX}\n- 신규 컨텍스트", str(messages[0].content))
        self.assertIsInstance(messages[1], HumanMessage)
        self.assertEqual(original_user, str(messages[1].content))

    def test_normalizes_non_consecutive_system_context_from_history(self) -> None:
        """히스토리 중간의 intent system 메시지를 제거하고 선두 블록으로 정규화해야 한다."""
        original_user = "현재메일 요약해줘"
        state = {
            "messages": [
                HumanMessage(content="이전 턴 질문"),
                SystemMessage(content=f"{INTENT_SYSTEM_CONTEXT_PREFIX}\n- 이전 컨텍스트"),
                HumanMessage(content=original_user),
            ]
        }
        with (
            patch("app.middleware.agent_middlewares.should_inject_intent_context", return_value=True),
            patch(
                "app.middleware.agent_middlewares.compose_intent_system_context",
                return_value=f"{INTENT_SYSTEM_CONTEXT_PREFIX}\n- 신규 컨텍스트",
            ),
        ):
            result = _inject_intent_decomposition_context_impl(state=state, runtime=None)

        self.assertIsNone(result)
        messages = state.get("messages", [])
        self.assertEqual(3, len(messages))
        self.assertIsInstance(messages[0], SystemMessage)
        self.assertEqual(f"{INTENT_SYSTEM_CONTEXT_PREFIX}\n- 신규 컨텍스트", str(messages[0].content))
        self.assertEqual("이전 턴 질문", str(messages[1].content))
        self.assertEqual(original_user, str(messages[2].content))


if __name__ == "__main__":
    unittest.main()
