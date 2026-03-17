from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class MailSummaryScriptsTest(unittest.TestCase):
    """summary queue 스크립트의 standalone 실행 계약을 검증한다."""

    def test_process_mail_summary_queue_runs_without_import_error(self) -> None:
        """repo 밖 cwd에서도 worker 스크립트가 `app` import 오류 없이 실행되어야 한다."""
        script_path = Path(__file__).resolve().parents[1] / "scripts" / "process_mail_summary_queue.py"
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--db-path",
                    str(Path(tmp_dir) / "missing.db"),
                    "--max-jobs",
                    "1",
                ],
                cwd=tmp_dir,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, msg=result.stderr)
        self.assertNotIn("ModuleNotFoundError: No module named 'app'", result.stderr)

    def test_backfill_email_summary_runs_without_import_error(self) -> None:
        """repo 밖 cwd에서도 backfill 스크립트가 `app` import 오류 없이 실행되어야 한다."""
        script_path = Path(__file__).resolve().parents[1] / "scripts" / "backfill_email_summary.py"
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--db-path",
                    str(Path(tmp_dir) / "missing.db"),
                    "--limit",
                    "1",
                ],
                cwd=tmp_dir,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, msg=result.stderr)
        self.assertNotIn("ModuleNotFoundError: No module named 'app'", result.stderr)


if __name__ == "__main__":
    unittest.main()
