from __future__ import annotations

import unittest

from app.services.mail_service import MailRecord
from app.services.meeting_mail_suggestion_service import suggest_meeting_plan_from_mail


class MeetingMailSuggestionServiceTest(unittest.TestCase):
    """현재메일 기반 회의 제안의 시간 후보 생성 규칙을 검증한다."""

    def test_ignores_forwarded_mail_header_time(self) -> None:
        """전달 메일 헤더의 Sent 시각은 시간 후보 단서에서 제외해야 한다."""
        mail = MailRecord(
            message_id="m-1",
            subject="FW: M365 구축 일정",
            from_address="sender@example.com",
            received_date="2026-03-03T01:00:00Z",
            body_text=(
                "From: A <a@example.com>\n"
                "Sent: Thursday, February 26, 2026 4:17 AM\n"
                "To: B <b@example.com>\n"
                "Subject: FW: M365 구축 일정\n"
                "본문에는 시간 언급이 없습니다."
            ),
            summary_text="M365 구축 일정 협의 필요",
        )
        proposal = suggest_meeting_plan_from_mail(mail=mail, rooms=[])
        first = proposal.get("time_candidates", [{}])[0]
        self.assertEqual("10:00", first.get("start_time"))
        self.assertEqual("11:00", first.get("end_time"))

    def test_keeps_explicit_business_hour_range(self) -> None:
        """본문에 명시된 업무시간대 범위는 첫 시간 후보로 유지해야 한다."""
        mail = MailRecord(
            message_id="m-2",
            subject="M365 구축 일정",
            from_address="sender@example.com",
            received_date="2026-03-03T01:00:00Z",
            body_text="오늘 15:00~16:00에 점검 회의 가능 여부 확인 부탁드립니다.",
            summary_text="점검 회의 일정 확인 필요",
        )
        proposal = suggest_meeting_plan_from_mail(mail=mail, rooms=[])
        first = proposal.get("time_candidates", [{}])[0]
        self.assertEqual("15:00", first.get("start_time"))
        self.assertEqual("16:00", first.get("end_time"))

    def test_rejects_non_business_hour_time_and_falls_back_to_defaults(self) -> None:
        """업무시간 외 단서 시각은 무시하고 정시 기본 슬롯을 사용해야 한다."""
        mail = MailRecord(
            message_id="m-3",
            subject="M365 구축 일정",
            from_address="sender@example.com",
            received_date="2026-03-03T01:00:00Z",
            body_text="04:17에 점검했습니다.",
            summary_text="점검 완료",
        )
        proposal = suggest_meeting_plan_from_mail(mail=mail, rooms=[])
        first = proposal.get("time_candidates", [{}])[0]
        self.assertEqual("10:00", first.get("start_time"))
        self.assertEqual("11:00", first.get("end_time"))


if __name__ == "__main__":
    unittest.main()
