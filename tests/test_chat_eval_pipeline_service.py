from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import chat_eval_pipeline_service


class ChatEvalPipelineServiceTest(unittest.TestCase):
    """chat_eval pipeline 실행/비교/게이트/저장 계약을 검증한다."""

    def test_run_chat_eval_pipeline_builds_report_and_persists_files(self) -> None:
        """파이프라인 실행 시 latest/stamped/history 파일이 저장되어야 한다."""
        baseline = {
            "summary": {"judge_pass_rate": 90.0, "avg_judge_score": 4.0},
            "cases": [
                {"case_id": "mail-01", "judge": {"pass": True}},
                {"case_id": "mail-02", "judge": {"pass": True}},
            ],
        }
        current = {
            "summary": {"judge_pass_rate": 80.0, "avg_judge_score": 3.2},
            "cases": [
                {"case_id": "mail-01", "judge": {"pass": True}},
                {"case_id": "mail-02", "judge": {"pass": False}},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            reports_dir = Path(tmp_dir)
            latest_path = reports_dir / "chat_eval_pipeline_latest.json"
            history_path = reports_dir / "chat_eval_pipeline_history.ndjson"
            original_reports = chat_eval_pipeline_service.REPORTS_DIR
            original_latest = chat_eval_pipeline_service.PIPELINE_LATEST_PATH
            original_history = chat_eval_pipeline_service.PIPELINE_HISTORY_PATH
            chat_eval_pipeline_service.REPORTS_DIR = reports_dir
            chat_eval_pipeline_service.PIPELINE_LATEST_PATH = latest_path
            chat_eval_pipeline_service.PIPELINE_HISTORY_PATH = history_path
            try:
                with patch("app.services.chat_eval_pipeline_service.load_latest_chat_eval_report", return_value=baseline):
                    with patch("app.services.chat_eval_pipeline_service.run_chat_eval_session", return_value=current):
                        report = chat_eval_pipeline_service.run_chat_eval_pipeline(
                            chat_url="http://testserver/search/chat",
                            min_pass_rate=85.0,
                            min_avg_score=3.5,
                            allow_regression_cases=0,
                        )
            finally:
                chat_eval_pipeline_service.REPORTS_DIR = original_reports
                chat_eval_pipeline_service.PIPELINE_LATEST_PATH = original_latest
                chat_eval_pipeline_service.PIPELINE_HISTORY_PATH = original_history
            self.assertFalse(report["quality_gate"]["passed"])
            self.assertIn("pass_rate_ok", report["quality_gate"]["failed_checks"])
            self.assertIn("avg_score_ok", report["quality_gate"]["failed_checks"])
            self.assertIn("regression_ok", report["quality_gate"]["failed_checks"])
            self.assertEqual(["mail-02"], report["comparison"]["regression_cases"])
            self.assertTrue(latest_path.exists())
            self.assertTrue(history_path.exists())
            saved = json.loads(latest_path.read_text(encoding="utf-8"))
            self.assertEqual(False, saved["quality_gate"]["passed"])

    def test_render_pipeline_report_markdown_contains_gate_summary(self) -> None:
        """Markdown 렌더는 게이트 요약과 회귀 케이스를 포함해야 한다."""
        report = {
            "meta": {"generated_at": "2026-03-08T00:00:00+00:00"},
            "quality_gate": {"passed": False, "failed_checks": ["pass_rate_ok"]},
            "comparison": {"regression_count": 1, "regression_cases": ["mail-02"]},
            "report": {"summary": {"judge_pass_rate": 70.0, "avg_judge_score": 3.0}},
        }
        rendered = chat_eval_pipeline_service.render_pipeline_report_markdown(report=report)
        self.assertIn("# Chat Eval Pipeline Report", rendered)
        self.assertIn("gate_passed: False", rendered)
        self.assertIn("mail-02", rendered)


if __name__ == "__main__":
    unittest.main()
