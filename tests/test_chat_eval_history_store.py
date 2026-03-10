from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.services import chat_eval_history_store


class ChatEvalHistoryStoreTest(unittest.TestCase):
    """Chat Eval SQLite 이력 저장소를 검증한다."""

    def test_record_and_load_run(self) -> None:
        """리포트 저장 후 목록/상세 조회가 가능해야 한다."""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "chat_eval_history.sqlite3"
            original_db_path = chat_eval_history_store.DB_PATH
            chat_eval_history_store.DB_PATH = db_path
            try:
                sample_report = {
                    "meta": {
                        "started_at": "2026-03-08T00:00:00+00:00",
                        "finished_at": "2026-03-08T00:01:00+00:00",
                        "chat_url": "http://testserver/search/chat",
                        "judge_model": "anthropic:claude-haiku-4-5-20251001",
                        "selected_case_count": 1,
                    },
                    "summary": {
                        "judge_pass_rate": 100.0,
                        "avg_judge_score": 5.0,
                    },
                    "cases": [
                        {
                            "case_id": "q1",
                            "query": "질문",
                            "expectation": "기대",
                            "requires_current_mail": False,
                            "answer": "답변",
                            "error": "",
                            "chat_elapsed_ms": 100.1,
                            "judge_elapsed_ms": 200.2,
                            "judge": {"pass": True, "score": 5, "reason": "ok"},
                        }
                    ],
                }

                run_no = chat_eval_history_store.record_chat_eval_run(report=sample_report)
                self.assertGreaterEqual(run_no, 1)

                runs = chat_eval_history_store.list_chat_eval_runs(limit=10)
                self.assertEqual(1, len(runs))
                self.assertEqual(run_no, runs[0]["run_no"])

                loaded = chat_eval_history_store.get_chat_eval_run(run_no=run_no)
                self.assertIsInstance(loaded, dict)
                self.assertEqual("q1", loaded.get("cases", [{}])[0].get("case_id"))
            finally:
                chat_eval_history_store.DB_PATH = original_db_path


if __name__ == "__main__":
    unittest.main()
