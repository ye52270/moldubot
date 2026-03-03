from __future__ import annotations

import unittest

from app.services.chat_eval_quality_metrics import build_quality_metrics


class ChatQualityMetricsTest(unittest.TestCase):
    """
    채팅 품질 자동지표 계산 로직을 검증한다.
    """

    def test_build_quality_metrics_computes_expected_rates(self) -> None:
        """
        요약/보고서/예약 지표가 케이스별 규칙에 따라 계산되어야 한다.
        """
        cases = [
            {
                "utterance": "현재 메일 3줄 요약해줘",
                "answer": "요약 결과:\n1. A\n2. B\n3. C",
            },
            {
                "utterance": "현재 메일 보고서 작성해줘",
                "answer": "보고서\n- 항목",
            },
            {
                "utterance": "회의실 예약해줘",
                "answer": "예약 실패: 과거 날짜로는 예약할 수 없습니다.",
            },
            {
                "utterance": "현재 메일 2줄 요약해줘",
                "answer": "1. A\n2. B\n3. C",
            },
        ]

        result = build_quality_metrics(per_case=cases)
        self.assertEqual(50.0, result["summary_line_compliance_rate"])
        self.assertEqual(2, result["summary_line_checked_cases"])
        self.assertEqual(100.0, result["report_format_compliance_rate"])
        self.assertEqual(1, result["report_format_checked_cases"])
        self.assertEqual(100.0, result["booking_failure_reason_compliance_rate"])
        self.assertEqual(1, result["booking_failure_reason_checked_cases"])


if __name__ == "__main__":
    unittest.main()
