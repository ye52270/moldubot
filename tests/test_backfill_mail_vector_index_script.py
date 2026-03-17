from __future__ import annotations

import json
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path


class BackfillMailVectorIndexScriptTest(unittest.TestCase):
    """벡터 인덱스 재색인 스크립트 동작을 검증한다."""

    def test_script_indexes_existing_emails_into_fallback_store(self) -> None:
        """재색인 스크립트는 기존 emails 행을 fallback 벡터 인덱스로 저장해야 한다."""
        script_path = Path(__file__).resolve().parents[1] / "scripts" / "backfill_mail_vector_index.py"
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "emails.db"
            vector_dir = Path(tmp_dir) / "vectors"
            self._seed_emails_db(db_path=db_path)
            result = subprocess.run(
                [
                    str(Path(__file__).resolve().parents[1] / ".venv" / "bin" / "python"),
                    str(script_path),
                    "--db-path",
                    str(db_path),
                    "--vector-dir",
                    str(vector_dir),
                ],
                cwd=tmp_dir,
                capture_output=True,
                text=True,
                check=False,
            )
            payload = json.loads(result.stdout)
            indexed = self._count_fallback_rows(vector_dir / "mail_vector_fallback.sqlite3")
        self.assertEqual(0, result.returncode, msg=result.stderr)
        self.assertEqual(2, payload["indexed"])
        self.assertEqual(2, indexed)

    def _seed_emails_db(self, db_path: Path) -> None:
        """재색인 테스트용 emails 테이블을 생성한다."""
        connection = sqlite3.connect(str(db_path))
        try:
            connection.execute(
                "CREATE TABLE emails ("
                "message_id TEXT PRIMARY KEY, "
                "subject TEXT, "
                "from_address TEXT, "
                "received_date TEXT, "
                "body_preview TEXT, "
                "body_full TEXT, "
                "body_clean TEXT, "
                "summary TEXT, "
                "category TEXT)"
            )
            connection.executemany(
                "INSERT INTO emails VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    ("m-1", "제목1", "a@example.com", "2026-03-17T00:00:00Z", "", "본문1", "본문1", "요약1", "일반"),
                    ("m-2", "제목2", "b@example.com", "2026-03-17T01:00:00Z", "", "본문2", "본문2", "요약2", "긴급"),
                ],
            )
            connection.commit()
        finally:
            connection.close()

    def _count_fallback_rows(self, db_path: Path) -> int:
        """fallback 벡터 인덱스 저장 행 수를 반환한다."""
        connection = sqlite3.connect(str(db_path))
        try:
            return int(connection.execute("SELECT COUNT(*) FROM mail_vector_index").fetchone()[0])
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
