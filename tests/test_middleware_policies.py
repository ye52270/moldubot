from __future__ import annotations

import unittest

from app.middleware.policies import should_inject_intent_context


class MiddlewarePoliciesTest(unittest.TestCase):
    """
    미들웨어 intent 컨텍스트 주입 정책을 검증한다.
    """

    def test_should_skip_intent_context_for_simple_mail_search(self) -> None:
        """
        단순 메일 조회 질의는 컨텍스트 주입을 생략해야 한다.
        """
        self.assertFalse(should_inject_intent_context("박준용 관련 2월 메일"))

    def test_should_inject_intent_context_for_mail_search_with_summary(self) -> None:
        """
        조회+요약 복합 질의는 컨텍스트 주입이 필요하다.
        """
        self.assertTrue(should_inject_intent_context("조영득 관련 2월 메일 요약"))


if __name__ == "__main__":
    unittest.main()
