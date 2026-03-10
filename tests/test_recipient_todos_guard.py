from __future__ import annotations

import unittest

from app.models.response_contracts import RecipientTodoEntry
from app.services.recipient_todos_guard import sanitize_contract_recipient_todos


class RecipientTodosGuardTest(unittest.TestCase):
    """recipient_todos strict guard 동작을 검증한다."""

    def test_filters_non_to_recipients_and_normalizes_due_date(self) -> None:
        """To 범위 외 수신자를 제거하고 마감일 형식을 정규화해야 한다."""
        rows = [
            RecipientTodoEntry(
                recipient="박정호",
                todo="문의 전달",
                due_date="2026/03/07",
                due_date_basis="안녕하세요",
            ),
            RecipientTodoEntry(
                recipient="김태호",
                todo="Redirect 도메인 검토",
                due_date="2026-03-07T10:00:00Z",
                due_date_basis="@김태호 검토 부탁드립니다.",
            ),
        ]
        mail_context = {
            "to_recipients": "김태호 <kimth@cnthoth.com>",
            "from_address": "eva1397@sk.com",
            "cc_recipients": "박제영 <izocuna@skcc.com>",
        }
        filtered = sanitize_contract_recipient_todos(rows=rows, mail_context=mail_context)
        self.assertEqual(1, len(filtered))
        self.assertEqual("김태호", filtered[0].recipient)
        self.assertEqual("미정", filtered[0].due_date)

    def test_due_date_is_forced_to_unknown_when_basis_has_no_schedule_signal(self) -> None:
        """기한 근거에 일정 단서가 없으면 due_date는 미정으로 강제되어야 한다."""
        rows = [
            RecipientTodoEntry(
                recipient="김태호",
                todo="Redirect 도메인 검토",
                due_date="2026-03-07",
                due_date_basis="검토 부탁드립니다.",
            ),
        ]
        mail_context = {"to_recipients": "김태호 <kimth@cnthoth.com>"}
        filtered = sanitize_contract_recipient_todos(rows=rows, mail_context=mail_context)
        self.assertEqual("미정", filtered[0].due_date)


if __name__ == "__main__":
    unittest.main()
