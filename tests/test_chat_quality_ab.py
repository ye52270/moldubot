from __future__ import annotations

import unittest

from tests.eval_chat_quality_ab import build_ab_delta


class ChatQualityABMetricsTest(unittest.TestCase):
    """A/B 품질 비교 지표 계산을 검증한다."""

    def test_build_ab_delta_computes_expected_values(self) -> None:
        baseline = {
            "summary": {
                "success_rate": 90.0,
                "avg_elapsed_ms": 5000.0,
                "summary_line_compliance_rate": 80.0,
                "report_format_compliance_rate": 70.0,
                "booking_failure_reason_compliance_rate": 60.0,
            }
        }
        candidate = {
            "summary": {
                "success_rate": 95.0,
                "avg_elapsed_ms": 4600.0,
                "summary_line_compliance_rate": 90.0,
                "report_format_compliance_rate": 75.0,
                "booking_failure_reason_compliance_rate": 65.0,
            }
        }

        delta = build_ab_delta(baseline=baseline, candidate=candidate)

        self.assertEqual(5.0, delta["delta_success_rate"])
        self.assertEqual(-400.0, delta["delta_avg_elapsed_ms"])
        self.assertEqual(10.0, delta["delta_summary_line_compliance_rate"])
        self.assertEqual(5.0, delta["delta_report_format_compliance_rate"])
        self.assertEqual(5.0, delta["delta_booking_failure_reason_compliance_rate"])


if __name__ == "__main__":
    unittest.main()
