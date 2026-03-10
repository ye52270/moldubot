from __future__ import annotations

import unittest

from app.services.person_identity_parser import normalize_person_identity


class PersonIdentityParserTest(unittest.TestCase):
    """인물 토큰 정규화 규칙을 검증한다."""

    def test_prefers_korean_name_when_name_and_email_are_both_present(self) -> None:
        """이름+이메일 토큰은 이름을 우선 반환해야 한다."""
        token = "이상수(LEE Sangsoo)/AX Solution서비스4팀/SK &ltlsangsoo@sk.com&gt"
        self.assertEqual("이상수", normalize_person_identity(token=token))

    def test_returns_email_when_name_is_missing(self) -> None:
        """이름이 없으면 이메일 주소를 반환해야 한다."""
        token = "&ltssl@skcc.com&gt"
        self.assertEqual("ssl@skcc.com", normalize_person_identity(token=token))

    def test_removes_html_artifacts(self) -> None:
        """찌꺼기 토큰은 빈 문자열로 정리해야 한다."""
        self.assertEqual("", normalize_person_identity(token="&lt"))
        self.assertEqual("", normalize_person_identity(token="&gt"))


if __name__ == "__main__":
    unittest.main()
