from __future__ import annotations

import unittest
from unittest.mock import patch

from app.agents.tools import run_mail_post_action


class AgentToolsCurrentMailGuardTest(unittest.TestCase):
    """
    현재메일 후속작업 도구의 컨텍스트 가드 동작을 검증한다.
    """

    def test_run_mail_post_action_requires_primed_current_mail(self) -> None:
        """
        현재메일 컨텍스트가 없으면 DB fallback 없이 즉시 실패해야 한다.
        """
        with patch("app.agents.tools._MAIL_SERVICE") as mail_service:
            mail_service.get_current_mail.return_value = None

            payload = run_mail_post_action.func(action="current_mail", summary_line_target=5)

        self.assertEqual("failed", payload["status"])
        self.assertIn("현재 메일을 찾지 못했습니다", payload["reason"])
        mail_service.read_current_mail.assert_not_called()
        mail_service.run_post_action.assert_not_called()


if __name__ == "__main__":
    unittest.main()
