from __future__ import annotations

import unittest

from app.services.next_action_contract_extractor import resolve_next_actions_from_model_content


class NextActionContractExtractorTest(unittest.TestCase):
    """모델 출력에서 후속 action_id 복원 규칙을 검증한다."""

    def test_resolve_from_json_contract(self) -> None:
        """JSON 계약 suggested_action_ids를 우선 복원해야 한다."""
        actions = resolve_next_actions_from_model_content(
            raw_model_content='{"format_type":"general","answer":"ok","suggested_action_ids":["create_todo"]}',
            tool_payload={"action": "current_mail", "mail_context": {"message_id": "m1"}},
        )
        self.assertEqual("create_todo", actions[0]["action_id"])

    def test_resolve_from_freeform_tag(self) -> None:
        """freeform 메타 태그에서도 action_id를 복원해야 한다."""
        actions = resolve_next_actions_from_model_content(
            raw_model_content="답변 본문\n[[suggested_action_ids:create_todo,web_search]]",
            tool_payload={"action": "current_mail", "mail_context": {"message_id": "m1"}},
        )
        self.assertEqual("create_todo", actions[0]["action_id"])
        self.assertEqual("web_search", actions[1]["action_id"])

    def test_ignores_invalid_action_ids_in_tag(self) -> None:
        """태그의 미허용/비정상 ID는 무시되어야 한다."""
        actions = resolve_next_actions_from_model_content(
            raw_model_content="답변\n[[suggested_action_ids:@@@,unknown_action,create_todo]]",
            tool_payload={"action": "current_mail", "mail_context": {"message_id": "m1"}},
        )
        self.assertEqual(1, len(actions))
        self.assertEqual("create_todo", actions[0]["action_id"])


if __name__ == "__main__":
    unittest.main()
