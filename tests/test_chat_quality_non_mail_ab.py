from __future__ import annotations

import unittest

from tests.eval_chat_quality_non_mail_ab import build_ab_delta


class NonMailABMetricsTest(unittest.TestCase):
    """비메일 A/B 품질 비교 지표 계산을 검증한다."""

    def test_build_ab_delta_computes_expected_values(self) -> None:
        baseline = {
            "summary": {
                "success_rate": 90.0,
                "avg_elapsed_ms": 2000.0,
                "avg_answer_length": 120.0,
                "failure_pattern_rate": 20.0,
            }
        }
        candidate = {
            "summary": {
                "success_rate": 95.0,
                "avg_elapsed_ms": 1800.0,
                "avg_answer_length": 140.0,
                "failure_pattern_rate": 5.0,
            }
        }

        delta = build_ab_delta(baseline=baseline, candidate=candidate)

        self.assertEqual(5.0, delta["delta_success_rate"])
        self.assertEqual(-200.0, delta["delta_avg_elapsed_ms"])
        self.assertEqual(20.0, delta["delta_avg_answer_length"])
        self.assertEqual(-15.0, delta["delta_failure_pattern_rate"])


if __name__ == "__main__":
    unittest.main()
