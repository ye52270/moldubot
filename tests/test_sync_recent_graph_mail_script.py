from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class SyncRecentGraphMailScriptTest(unittest.TestCase):
    """최근 Graph 메일 sync 스크립트 기본 동작을 검증한다."""

    def test_script_supports_dry_run_without_import_error(self) -> None:
        """repo 밖 cwd에서도 dry-run 실행이 import 오류 없이 JSON을 반환해야 한다."""
        script_path = Path(__file__).resolve().parents[1] / "scripts" / "sync_recent_graph_mail.py"
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "emails.db"
            result = subprocess.run(
                [
                    str(Path(__file__).resolve().parents[1] / ".venv" / "bin" / "python"),
                    str(script_path),
                    "--db-path",
                    str(db_path),
                    "--limit",
                    "5",
                    "--dry-run",
                ],
                cwd=tmp_dir,
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "MICROSOFT_APP_ID": ""},
            )
        self.assertEqual(0, result.returncode, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["dry_run"])
        self.assertEqual(5, payload["limit"])
        self.assertEqual(str(db_path), payload["db_path"])


if __name__ == "__main__":
    unittest.main()
