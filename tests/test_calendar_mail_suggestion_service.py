from __future__ import annotations

import unittest

from app.services.calendar_mail_suggestion_service import suggest_calendar_plan_from_mail
from app.services.mail_service import MailRecord


class CalendarMailSuggestionServiceTest(unittest.TestCase):
    """현재메일 기반 일정 제안에서 summary 필드 우선 사용을 검증한다."""

    def test_uses_summary_text_without_postprocessing(self) -> None:
        """summary_text가 있으면 key_points/body에 원문 그대로 반영해야 한다."""
        mail = MailRecord(
            message_id="m1",
            subject="FW: M365 계정 점검 건",
            from_address="sender@example.com",
            received_date="2026-03-02T09:00:00Z",
            body_text="본문 원문",
            summary_text="요약 원문 1\n요약 원문 2",
            web_link="",
        )
        proposal = suggest_calendar_plan_from_mail(mail=mail)
        self.assertEqual("요약 원문 1\n요약 원문 2", proposal.get("summary_text"))
        self.assertEqual(["요약 원문 1\n요약 원문 2"], proposal.get("key_points"))
        self.assertIn("요약 원문 1\n요약 원문 2", str(proposal.get("body")))

    def test_fallback_when_summary_text_missing(self) -> None:
        """summary_text가 비면 본문에 안내 문구를 넣어야 한다."""
        mail = MailRecord(
            message_id="m2",
            subject="RE: 일정 확인",
            from_address="sender@example.com",
            received_date="2026-03-02T09:00:00Z",
            body_text="본문 원문",
            summary_text="",
            web_link="",
        )
        proposal = suggest_calendar_plan_from_mail(mail=mail)
        self.assertEqual("", proposal.get("summary_text"))
        self.assertEqual([], proposal.get("key_points"))
        self.assertIn("저장된 summary가 없습니다.", str(proposal.get("body")))


if __name__ == "__main__":
    unittest.main()
