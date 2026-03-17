from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.agents.tools import _clear_post_action_cache, run_mail_post_action


class AgentToolsPostActionCacheTest(unittest.TestCase):
    """
    run_mail_post_action 캐시 동작을 검증한다.
    """

    def setUp(self) -> None:
        _clear_post_action_cache()

    def test_run_mail_post_action_reuses_cached_result_for_same_mail_and_action(self) -> None:
        """
        동일 메일/액션 조합은 캐시되어 run_post_action 재호출을 생략해야 한다.
        """
        fake_mail = SimpleNamespace(message_id="mail-1")
        fake_payload = {"action": "summary", "status": "context_only", "mail_context": {"subject": "테스트"}}
        with patch("app.agents.tools._MAIL_SERVICE") as mail_service:
            mail_service.get_current_mail.return_value = fake_mail
            mail_service.run_post_action.return_value = fake_payload

            first = run_mail_post_action.func(action="summary", summary_line_target=5)
            second = run_mail_post_action.func(action="summary", summary_line_target=5)

        self.assertEqual("context_only", first["status"])
        self.assertEqual(first, second)
        mail_service.run_post_action.assert_called_once_with(action="summary")

    def test_run_mail_post_action_does_not_reuse_cache_when_mail_changes(self) -> None:
        """
        메일 ID가 변경되면 캐시를 재사용하지 않고 새로 실행해야 한다.
        """
        first_mail = SimpleNamespace(message_id="mail-1")
        second_mail = SimpleNamespace(message_id="mail-2")
        with patch("app.agents.tools._MAIL_SERVICE") as mail_service:
            mail_service.get_current_mail.side_effect = [first_mail, second_mail]
            mail_service.run_post_action.side_effect = [
                {"action": "summary", "status": "context_only", "mail_context": {"subject": "A"}},
                {"action": "summary", "status": "context_only", "mail_context": {"subject": "B"}},
            ]

            first = run_mail_post_action.func(action="summary", summary_line_target=5)
            second = run_mail_post_action.func(action="summary", summary_line_target=5)

        self.assertEqual("A", first["mail_context"]["subject"])
        self.assertEqual("B", second["mail_context"]["subject"])
        self.assertEqual(2, mail_service.run_post_action.call_count)


if __name__ == "__main__":
    unittest.main()
