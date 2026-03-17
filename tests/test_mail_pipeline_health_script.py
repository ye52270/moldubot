from __future__ import annotations

import json
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path


class MailPipelineHealthScriptTest(unittest.TestCase):
    """메일 파이프라인 상태 점검 스크립트의 JSON 출력을 검증한다."""

    def test_script_reports_queue_subscription_and_vector_status(self) -> None:
        """스크립트는 DB 집계값과 Graph subscription 만료 정보를 JSON으로 반환해야 한다."""
        script_path = Path(__file__).resolve().parents[1] / "scripts" / "check_mail_pipeline_health.py"
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "emails.db"
            self._seed_database(db_path=db_path)
            result = subprocess.run(
                [
                    str(Path(__file__).resolve().parents[1] / ".venv" / "bin" / "python"),
                    str(script_path),
                    "--db-path",
                    str(db_path),
                ],
                cwd=tmp_dir,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(0, result.returncode, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(2, payload["emails"]["count"])
        self.assertEqual(1, payload["emails"]["missing_summary_count"])
        self.assertEqual(1, payload["queue"]["by_status"]["completed"])
        self.assertEqual(1, payload["queue"]["by_status"]["pending"])
        self.assertEqual(
            "2026-02-28T03:07:31Z",
            payload["graph_subscription"]["mail_subscription_expiration"],
        )
        self.assertIn("enabled", payload["vector_index"])
        self.assertIn("reason", payload["vector_index"])

    def _seed_database(self, db_path: Path) -> None:
        """점검 스크립트 테스트에 필요한 최소 스키마와 데이터를 생성한다."""
        connection = sqlite3.connect(str(db_path))
        try:
            connection.execute(
                """
                CREATE TABLE emails (
                    message_id TEXT PRIMARY KEY,
                    subject TEXT,
                    received_date TEXT,
                    summary TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE mail_summary_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT,
                    status TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE sync_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
                """
            )
            connection.executemany(
                "INSERT INTO emails (message_id, subject, received_date, summary) VALUES (?, ?, ?, ?)",
                [
                    ("m-1", "subject-1", "2026-03-13T07:44:12Z", "done"),
                    ("m-2", "subject-2", "2026-03-14T07:44:12Z", ""),
                ],
            )
            connection.executemany(
                "INSERT INTO mail_summary_queue (message_id, status) VALUES (?, ?)",
                [("m-1", "completed"), ("m-2", "pending")],
            )
            connection.executemany(
                "INSERT INTO sync_settings (key, value) VALUES (?, ?)",
                [
                    ("mail_subscription_expiration", "2026-02-28T03:07:31Z"),
                    ("mail_subscription_notification_url", "https://example.ngrok.dev/webhooks/graph/mail/"),
                ],
            )
            connection.commit()
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
