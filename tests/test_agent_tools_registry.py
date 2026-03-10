from __future__ import annotations

import unittest

from app.agents.tools import get_agent_tools


class AgentToolsRegistryTest(unittest.TestCase):
    """
    에이전트 tool 레지스트리 구성을 검증한다.
    """

    def test_registry_is_latency_optimized(self) -> None:
        """
        메일 후속작업은 단일 tool(`run_mail_post_action`) 중심으로 노출되어야 한다.
        """
        tool_names = [tool.name for tool in get_agent_tools()]
        self.assertIn("run_mail_post_action", tool_names)
        self.assertIn("search_mails", tool_names)
        self.assertIn("current_date", tool_names)
        self.assertNotIn("read_current_mail", tool_names)
        self.assertNotIn("summarize_mail", tool_names)
        self.assertNotIn("extract_key_facts", tool_names)
        self.assertNotIn("extract_recipients", tool_names)
        self.assertEqual(
            [
                "run_mail_post_action",
                "search_mails",
                "search_meeting_schedule",
                "current_date",
                "search_meeting_rooms",
                "book_meeting_room",
                "create_outlook_calendar_event",
                "create_outlook_todo",
            ],
            tool_names,
        )


if __name__ == "__main__":
    unittest.main()
