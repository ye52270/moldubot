from __future__ import annotations

import unittest

from app.models.response_contracts import RecipientRoleEntry
from app.services.recipient_roles_guard import sanitize_contract_recipient_roles


class RecipientRolesGuardTest(unittest.TestCase):
    """recipient_roles strict guard 동작을 검증한다."""

    def test_filters_sender_and_cc_and_low_quality_evidence(self) -> None:
        """발신자/참조/저품질 근거 행은 제거되어야 한다."""
        rows = [
            RecipientRoleEntry(
                recipient="박정호/AT Infra팀/SKB",
                role="메시지 발신 및 질문 제기",
                evidence="안녕하세요. 안내드립니다.",
            ),
            RecipientRoleEntry(
                recipient="이상수/AX Solution서비스4팀/SK",
                role="Redirect 후보 도메인 검토 담당",
                evidence="@박정호 회의 중 언급된 redirect 후보 도메인 목록 확인 요청",
            ),
            RecipientRoleEntry(
                recipient="박제영/AX Solution서비스5팀/SK",
                role="정보 공유 대상",
                evidence="참조: 박제영",
            ),
        ]
        mail_context = {
            "from_address": "eva1397@sk.com",
            "to_recipients": "이상수(LEE Sangsoo)/AX Solution서비스4팀/SK <ssl@skcc.com>; 김태호 <kimth@cnthoth.com>",
            "cc_recipients": "박제영(PARK Jaeyoung)/AX Solution서비스5팀/SK <izocuna@SKCC.COM>",
        }
        filtered = sanitize_contract_recipient_roles(rows=rows, mail_context=mail_context)
        self.assertEqual(1, len(filtered))
        self.assertEqual("이상수", filtered[0].recipient)


if __name__ == "__main__":
    unittest.main()
