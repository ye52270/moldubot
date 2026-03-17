from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.agents.subagents import get_agent_subagents


class AgentSubagentsTest(unittest.TestCase):
    """deep agent 서브에이전트 구성을 검증한다."""

    def tearDown(self) -> None:
        """테스트 간 환경변수 오염을 정리한다."""
        os.environ.pop("MOLDUBOT_ENABLE_MAIL_SUBAGENTS", None)

    def test_includes_code_review_subagent(self) -> None:
        """코드리뷰 전용 서브에이전트가 등록되어야 한다."""
        subagents = get_agent_subagents()
        self.assertGreaterEqual(len(subagents), 1)
        code_review = next((item for item in subagents if item.get("name") == "code-review-agent"), None)
        self.assertIsNotNone(code_review)
        self.assertIn("리뷰", str(code_review.get("description") or ""))
        tools = code_review.get("tools") or []
        tool_names = [str(getattr(tool, "name", getattr(tool, "__name__", ""))) for tool in tools]
        self.assertIn("run_mail_post_action", tool_names)

    def test_keeps_only_code_review_subagent_when_mail_subagents_disabled(self) -> None:
        """메일 subagent 플래그가 꺼져 있으면 코드리뷰 subagent만 노출되어야 한다."""
        with patch.dict(os.environ, {"MOLDUBOT_ENABLE_MAIL_SUBAGENTS": "0"}, clear=False):
            subagents = get_agent_subagents()
        names = [str(item.get("name") or "") for item in subagents]
        self.assertEqual(["code-review-agent"], names)

    def test_includes_mail_subagents_when_flag_enabled(self) -> None:
        """메일 subagent 플래그가 켜지면 조회/기술이슈 subagent가 함께 노출되어야 한다."""
        with patch.dict(os.environ, {"MOLDUBOT_ENABLE_MAIL_SUBAGENTS": "1"}, clear=False):
            subagents = get_agent_subagents()
        names = [str(item.get("name") or "") for item in subagents]
        self.assertIn("code-review-agent", names)
        self.assertIn("mail-retrieval-summary-agent", names)
        self.assertIn("mail-tech-issue-agent", names)
        retrieval_agent = next(item for item in subagents if item.get("name") == "mail-retrieval-summary-agent")
        retrieval_tools = retrieval_agent.get("tools") or []
        retrieval_tool_names = [str(getattr(tool, "name", getattr(tool, "__name__", ""))) for tool in retrieval_tools]
        self.assertIn("search_mails", retrieval_tool_names)
        self.assertIn("search_meeting_schedule", retrieval_tool_names)

    def test_custom_subagents_receive_skills_when_configured(self) -> None:
        """custom subagent는 메인 skills를 상속하지 않으므로 명시적으로 skills를 가져야 한다."""
        with patch.dict(
            os.environ,
            {
                "MOLDUBOT_ENABLE_MAIL_SUBAGENTS": "1",
                "MOLDUBOT_AGENT_SKILLS_PATHS": "/skills/core,/skills/mail",
            },
            clear=False,
        ):
            subagents = get_agent_subagents()

        for subagent in subagents:
            self.assertEqual(["/skills/core", "/skills/mail"], subagent.get("skills"))


if __name__ == "__main__":
    unittest.main()
