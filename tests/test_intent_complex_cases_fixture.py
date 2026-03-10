from __future__ import annotations

import unittest

from tests.fixtures.intent_complex_cases import INTENT_COMPLEX_CASES


class IntentComplexCasesFixtureTest(unittest.TestCase):
    """복합질의 평가 fixture 기본 계약을 검증한다."""

    def test_fixture_contains_twenty_cases(self) -> None:
        """복합질의 fixture는 20개 케이스를 제공해야 한다."""
        self.assertEqual(20, len(INTENT_COMPLEX_CASES))

    def test_each_case_has_required_steps(self) -> None:
        """모든 케이스는 필수 step 목록을 1개 이상 포함해야 한다."""
        for case in INTENT_COMPLEX_CASES:
            self.assertTrue(case["required_steps"])


if __name__ == "__main__":
    unittest.main()
