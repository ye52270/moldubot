from __future__ import annotations

import sqlite3
import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.mail_summary_queue_service import MailSummaryQueueService
from app.services.mail_summary_queue_worker import MailSummaryQueueWorker


class MailSummaryQueueServiceTest(unittest.TestCase):
    """
    mail summary queue 서비스/worker 핵심 동작을 검증한다.
    """

    def test_enqueue_backfill_only_missing(self) -> None:
        """
        기본 backfill enqueue는 summary 누락 메일만 큐에 넣어야 한다.
        """
        db_path = self._build_db()
        service = MailSummaryQueueService(db_path=db_path)
        result = service.enqueue_backfill(limit=0, include_existing=False)
        self.assertEqual(1, result.enqueued)
        self.assertEqual(1, result.scanned)

    @patch.dict(os.environ, {"MOLDUBOT_MAIL_VECTOR_INDEX_ENABLED": "0"}, clear=False)
    def test_worker_process_once_updates_summary_and_category(self) -> None:
        """
        worker가 queue 작업을 처리하면 emails.summary/category가 갱신되어야 한다.
        """
        db_path = self._build_db()
        service = MailSummaryQueueService(db_path=db_path)
        service.enqueue_message(message_id="m-empty", requested_by="test")
        worker = MailSummaryQueueWorker(db_path=db_path)
        handled = worker.process_once()
        self.assertTrue(handled)
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT COALESCE(summary, ''), COALESCE(category, ''), message_id FROM emails WHERE message_id = ?",
                ("m-empty",),
            ).fetchone()
            job_row = conn.execute(
                "SELECT status FROM mail_summary_queue WHERE message_id = ?",
                ("m-empty",),
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)
        assert row is not None
        self.assertTrue(bool(str(row[0]).strip()))
        self.assertIn(str(row[1]), {"일반", "긴급", "회신필요"})
        self.assertIsNotNone(job_row)
        assert job_row is not None
        self.assertEqual("completed", str(job_row[0]))

    @patch.dict(os.environ, {"MOLDUBOT_MAIL_VECTOR_INDEX_ENABLED": "0"}, clear=False)
    def test_enqueue_backfill_include_existing_requeues_completed_jobs(self) -> None:
        """
        include_existing=True면 완료된 기존 queue 작업도 pending으로 재큐잉해야 한다.
        """
        db_path = self._build_db()
        service = MailSummaryQueueService(db_path=db_path)
        first = service.enqueue_backfill(limit=0, include_existing=False)
        self.assertEqual(1, first.enqueued)
        worker = MailSummaryQueueWorker(db_path=db_path)
        worker.process_many(max_jobs=10)
        second = service.enqueue_backfill(limit=0, include_existing=True)
        self.assertEqual(2, second.enqueued)

    @patch.dict(os.environ, {"MOLDUBOT_MAIL_VECTOR_INDEX_ENABLED": "0"}, clear=False)
    def test_worker_calls_vector_index_upsert_with_summary_result(self) -> None:
        """
        worker 처리 시 벡터 인덱스 upsert가 호출되어야 한다.
        """
        db_path = self._build_db()
        service = MailSummaryQueueService(db_path=db_path)
        service.enqueue_message(message_id="m-empty", requested_by="test")
        worker = MailSummaryQueueWorker(db_path=db_path)
        worker._vector_index_service.upsert_mail_document = MagicMock(return_value=True)  # type: ignore[attr-defined]
        handled = worker.process_once()
        self.assertTrue(handled)
        worker._vector_index_service.upsert_mail_document.assert_called_once()  # type: ignore[attr-defined]

    def _build_db(self) -> Path:
        """
        queue 테스트용 emails DB를 생성한다.

        Returns:
            생성된 DB 파일 경로
        """
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        db_path = Path(temp_dir.name) / "emails.db"
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
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
            conn.execute(
                "INSERT INTO emails VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "m-empty",
                    "회신 부탁드립니다",
                    "a@example.com",
                    "2026-03-07T00:00:00Z",
                    "",
                    "",
                    "검토 후 회신 부탁드립니다.",
                    "",
                    "",
                ),
            )
            conn.execute(
                "INSERT INTO emails VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "m-filled",
                    "기존 요약",
                    "b@example.com",
                    "2026-03-06T00:00:00Z",
                    "",
                    "",
                    "본문",
                    "기존 summary",
                    "일반",
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return db_path


if __name__ == "__main__":
    unittest.main()
