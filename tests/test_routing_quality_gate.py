from __future__ import annotations

import unittest

from app.services.routing_quality_gate import evaluate_routing_quality_gate


class RoutingQualityGateTest(unittest.TestCase):
    """
    KPI 회귀 게이트 판정 로직을 검증한다.
    """

    def test_gate_passes_when_all_metrics_meet_thresholds(self) -> None:
        """
        모든 지표가 임계치를 만족하면 통과해야 한다.
        """
        intent_summary = {"required_steps_pass_rate": 99.0, "parse_success_rate": 100.0}
        chat_summary = {
            "summary_line_compliance_rate": 100.0,
            "report_format_compliance_rate": 95.0,
            "booking_failure_reason_compliance_rate": 95.0,
            "success_rate": 98.0,
            "avg_elapsed_ms": 3200.0,
        }
        result = evaluate_routing_quality_gate(intent_summary=intent_summary, chat_summary=chat_summary)
        self.assertTrue(result["passed"])
        self.assertEqual([], result["breaches"])

    def test_gate_fails_when_any_metric_breaches_threshold(self) -> None:
        """
        임계치 미달/초과 지표가 있으면 실패해야 한다.
        """
        intent_summary = {"required_steps_pass_rate": 80.0, "parse_success_rate": 98.0}
        chat_summary = {
            "summary_line_compliance_rate": 85.0,
            "report_format_compliance_rate": 95.0,
            "booking_failure_reason_compliance_rate": 95.0,
            "success_rate": 98.0,
            "avg_elapsed_ms": 9100.0,
        }
        result = evaluate_routing_quality_gate(intent_summary=intent_summary, chat_summary=chat_summary)
        self.assertFalse(result["passed"])
        metrics = {item["metric"] for item in result["breaches"]}
        self.assertIn("intent_required_steps_pass_rate", metrics)
        self.assertIn("summary_line_compliance_rate", metrics)
        self.assertIn("avg_latency_ms", metrics)


if __name__ == "__main__":
    unittest.main()
