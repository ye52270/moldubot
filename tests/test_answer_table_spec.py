from __future__ import annotations

import unittest

from app.services.answer_table_spec import (
    is_current_mail_people_roles_table_request,
    render_current_mail_people_roles_table,
)


class AnswerTableSpecTest(unittest.TestCase):
    """현재메일 인물 역할 동적 테이블 스펙 렌더링을 검증한다."""

    def test_people_roles_table_request_detection(self) -> None:
        """현재메일+표+역할 조합은 인물 역할 테이블 요청으로 인식해야 한다."""
        self.assertTrue(
            is_current_mail_people_roles_table_request(
                "현재메일에서 수신자별 역할을 표 형식으로 정리해줘"
            )
        )
        self.assertFalse(is_current_mail_people_roles_table_request("현재메일 수신자 알려줘"))

    def test_to_recipient_roles_table_uses_recipient_headers(self) -> None:
        """수신자 역할 질의는 수신자 중심 컬럼으로 렌더링해야 한다."""
        rendered = render_current_mail_people_roles_table(
            user_message="현재메일에서 수신자별 역할을 표 형식으로 정리해줘",
            mail_context={
                "to_recipients": "alpha@example.com; beta@example.com",
                "body_excerpt": "To: alpha@example.com; beta@example.com\nSubject: 테스트",
            },
        )
        self.assertIn("## 수신자 역할 정리", rendered)
        self.assertIn("| 수신자 | 역할 추정 | 근거 |", rendered)
        self.assertIn("| alpha@example.com | 수신/실행 대상 | 메일 헤더 TO |", rendered)

    def test_cc_roles_table_uses_cc_headers(self) -> None:
        """참조자 역할 질의는 참조(CC) 컬럼으로 렌더링해야 한다."""
        rendered = render_current_mail_people_roles_table(
            user_message="현재메일에서 참조에 있는 사람들의 역할을 표로 정리해줘",
            mail_context={
                "cc_recipients": ["leader@example.com", "observer@example.com"],
                "body_excerpt": "Cc: leader@example.com; observer@example.com",
            },
        )
        self.assertIn("## 참조자 역할 정리", rendered)
        self.assertIn("| 참조자(CC) | 역할 추정 | 근거 |", rendered)
        self.assertIn("| leader@example.com | 공유 대상 | 메일 헤더 CC |", rendered)

    def test_body_people_roles_table_infers_roles_from_lines(self) -> None:
        """본문 인물 역할 질의는 본문 근거 라인에서 역할을 추정해야 한다."""
        rendered = render_current_mail_people_roles_table(
            user_message="현재메일 본문에 명시된 사람들의 역할을 표 형태로 정리해줘",
            mail_context={
                "body_excerpt": (
                    "김민수님이 일정 변경 검토를 요청했습니다.\n"
                    "park.pm@example.com이 배포 조치를 진행합니다."
                )
            },
        )
        self.assertIn("## 인물 역할 정리", rendered)
        self.assertIn("| 이름/주소 | 역할 추정 | 근거 |", rendered)
        self.assertIn("| 김민수 | 검토 담당 |", rendered)
        self.assertIn("| park.pm@example.com | 실행 담당 |", rendered)

    def test_to_recipient_roles_prefers_name_and_removes_html_artifacts(self) -> None:
        """수신자 표시는 이름 우선, 이메일 fallback, HTML 찌꺼기 제거 규칙을 따라야 한다."""
        rendered = render_current_mail_people_roles_table(
            user_message="현재메일 수신자를 분석해서 각각 역할을 표로 정리해줘",
            mail_context={
                "to_recipients": (
                    "이상수(LEE Sangsoo)/AX Solution서비스4팀/SK &ltlsangsoo@sk.com&gt;; "
                    "ssl@skcc.com; 김태호 &ltkimth@cnthoth.com&gt"
                ),
            },
        )
        self.assertIn("| 이상수 | 수신/실행 대상 | 메일 헤더 TO |", rendered)
        self.assertIn("| ssl@skcc.com | 수신/실행 대상 | 메일 헤더 TO |", rendered)
        self.assertIn("| 김태호 | 수신/실행 대상 | 메일 헤더 TO |", rendered)
        self.assertNotIn("&lt", rendered)
        self.assertNotIn("&gt", rendered)

    def test_to_recipient_roles_use_body_evidence_when_person_is_mentioned(self) -> None:
        """수신자가 본문에 명시되면 사람별 역할/근거를 본문 단서로 추론해야 한다."""
        rendered = render_current_mail_people_roles_table(
            user_message="현재메일 수신자를 분석해서 각각 역할을 표로 정리해줘",
            mail_context={
                "to_recipients": "김태호 <kimth@cnthoth.com>; 이상수 <lsangsoo@sk.com>",
                "body_excerpt": (
                    "김태호님이 API 수정 조치를 오늘 진행합니다.\n"
                    "이상수님은 보안정책 검토 후 승인 요청 예정입니다."
                ),
            },
        )
        self.assertIn("| 김태호 | 실행 담당 | 김태호님이 API 수정 조치를 오늘 진행합니다. |", rendered)
        self.assertIn("| 이상수 | 검토 담당 | 이상수님은 보안정책 검토 후 승인 요청 예정입니다. |", rendered)

    def test_to_recipient_candidate_collection_avoids_body_header_duplication(self) -> None:
        """to_recipients가 존재하면 본문 To 헤더를 중복 후보로 추가하지 않아야 한다."""
        rendered = render_current_mail_people_roles_table(
            user_message="현재메일 수신자를 분석해서 각각 역할을 표로 정리해줘",
            mail_context={
                "to_recipients": "김태호 <kimth@cnthoth.com>",
                "body_excerpt": "To: kimth@cnthoth.com\nSubject: 테스트",
            },
        )
        self.assertEqual(1, rendered.count("| 김태호 |"))


if __name__ == "__main__":
    unittest.main()
