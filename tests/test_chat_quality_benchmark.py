from __future__ import annotations

import unittest

from app.services.chat_quality_benchmark import aggregate_benchmark_runs, build_per_case_stats, percentile


class ChatQualityBenchmarkTest(unittest.TestCase):
    """
    채팅 품질 벤치마크 집계 로직을 검증한다.
    """

    def test_aggregate_benchmark_runs_returns_top_slow_cases(self) -> None:
        """
        반복 실행 결과에서 느린 케이스 상위 목록과 기본 집계값을 계산해야 한다.
        """
        runs = [
            {
                "summary": {"avg_elapsed_ms": 5000.0},
                "cases": [
                    {"case_id": 1, "elapsed_ms": 3000.0, "pattern": "A", "utterance": "a"},
                    {"case_id": 2, "elapsed_ms": 7000.0, "pattern": "B", "utterance": "b"},
                ],
            },
            {
                "summary": {"avg_elapsed_ms": 7000.0},
                "cases": [
                    {"case_id": 1, "elapsed_ms": 4000.0, "pattern": "A", "utterance": "a"},
                    {"case_id": 2, "elapsed_ms": 9000.0, "pattern": "B", "utterance": "b"},
                ],
            },
        ]
        result = aggregate_benchmark_runs(measured_runs=runs, top_n=1)
        self.assertEqual(2, result["run_count"])
        self.assertEqual(6000.0, result["avg_elapsed_ms_mean"])
        self.assertEqual(5000.0, result["avg_elapsed_ms_min"])
        self.assertEqual(7000.0, result["avg_elapsed_ms_max"])
        self.assertEqual(1, len(result["top_slow_cases"]))
        self.assertEqual("2", result["top_slow_cases"][0]["case_id"])

    def test_build_per_case_stats_computes_case_averages(self) -> None:
        """
        케이스별 샘플 평균/최대/최소를 계산해야 한다.
        """
        runs = [
            {"cases": [{"case_id": "1", "elapsed_ms": 1000.0, "pattern": "A", "utterance": "x"}]},
            {"cases": [{"case_id": "1", "elapsed_ms": 3000.0, "pattern": "A", "utterance": "x"}]},
        ]
        stats = build_per_case_stats(measured_runs=runs)
        self.assertEqual(1, len(stats))
        self.assertEqual(2000.0, stats[0]["avg_elapsed_ms"])
        self.assertEqual(3000.0, stats[0]["max_elapsed_ms"])
        self.assertEqual(1000.0, stats[0]["min_elapsed_ms"])
        self.assertEqual(2, stats[0]["sample_count"])

    def test_percentile_handles_empty_values(self) -> None:
        """
        빈 입력 분위수는 0.0이어야 한다.
        """
        self.assertEqual(0.0, percentile(values=[], percent=95))


if __name__ == "__main__":
    unittest.main()
