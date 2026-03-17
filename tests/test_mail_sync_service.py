from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.integrations.microsoft_graph.mail_client import GraphMailMessage
from app.services.mail_sync_service import MailSyncService


class FakeGraphListClient:
    """
    MailSyncService 테스트용 Graph 목록 조회 더블.
    """

    def __init__(self, messages: list[GraphMailMessage]) -> None:
        """반환할 메시지 목록을 저장한다."""
        self._messages = messages
        self.called_limits: list[int] = []

    def list_recent_messages(self, limit: int = 20) -> list[GraphMailMessage]:
        """
        최근 메일 목록 조회를 모사한다.

        Args:
            limit: 조회 요청 limit

        Returns:
            설정된 메시지 목록
        """
        self.called_limits.append(limit)
        return list(self._messages)


class MailSyncServiceTest(unittest.TestCase):
    """Graph 최근 메일 pull sync 동작을 검증한다."""

    @patch.dict(os.environ, {"MOLDUBOT_SUMMARY_SYNC_ON_UPSERT": "0"}, clear=False)
    def test_sync_recent_mail_upserts_new_messages_and_enqueues_summary(self) -> None:
        """신규 Graph 메일은 DB에 upsert되고 summary queue에 적재되어야 한다."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = self._create_db(Path(tmp_dir))
            service = MailSyncService(
                db_path=db_path,
                graph_client=FakeGraphListClient(
                    [
                        GraphMailMessage(
                            message_id="m-11",
                            subject="새 메일",
                            from_address="new@example.com",
                            received_date="2026-03-17T10:00:00Z",
                            body_text="본문",
                            internet_message_id="<m-11@example.com>",
                            web_link="https://example.com/m-11",
                        ),
                        GraphMailMessage(
                            message_id="m-10",
                            subject="기존 메일 업데이트",
                            from_address="old@example.com",
                            received_date="2026-03-16T10:00:00Z",
                            body_text="본문2",
                            internet_message_id="<m-10@example.com>",
                            web_link="https://example.com/m-10",
                        ),
                    ]
                ),
            )
            result = service.sync_recent_messages(limit=10)
            connection = sqlite3.connect(str(db_path))
            try:
                email_count = connection.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
                queue_count = connection.execute("SELECT COUNT(*) FROM mail_summary_queue").fetchone()[0]
            finally:
                connection.close()
        self.assertEqual(2, result.fetched)
        self.assertEqual(1, result.inserted)
        self.assertEqual(1, result.updated)
        self.assertEqual(2, email_count)
        self.assertEqual(2, queue_count)

    @patch.dict(os.environ, {"MOLDUBOT_SUMMARY_SYNC_ON_UPSERT": "0"}, clear=False)
    def test_sync_recent_mail_skips_older_than_latest_received_date(self) -> None:
        """로컬 최신 수신시각보다 오래된 메일은 신규 insert 대상으로 세지지 않아야 한다."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = self._create_db(Path(tmp_dir))
            service = MailSyncService(
                db_path=db_path,
                graph_client=FakeGraphListClient(
                    [
                        GraphMailMessage(
                            message_id="m-09",
                            subject="오래된 메일",
                            from_address="old@example.com",
                            received_date="2026-03-15T10:00:00Z",
                            body_text="본문",
                            internet_message_id="<m-09@example.com>",
                            web_link="https://example.com/m-09",
                        )
                    ]
                ),
            )
            result = service.sync_recent_messages(limit=5)
        self.assertEqual(1, result.fetched)
        self.assertEqual(0, result.inserted)
        self.assertEqual(0, result.updated)
        self.assertEqual(1, result.skipped_older)

    def _create_db(self, root: Path) -> Path:
        """동기화 테스트용 최소 emails DB를 생성한다."""
        db_path = root / "emails.db"
        connection = sqlite3.connect(str(db_path))
        try:
            connection.execute(
                "CREATE TABLE emails ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "message_id TEXT, "
                "subject TEXT, "
                "from_address TEXT, "
                "received_date TEXT, "
                "body_preview TEXT, "
                "body_full TEXT, "
                "body_clean TEXT, "
                "summary TEXT, "
                "web_link TEXT)"
            )
            connection.execute(
                "INSERT INTO emails (message_id, subject, from_address, received_date, body_preview, body_full, body_clean, summary, web_link) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "m-10",
                    "기존 메일",
                    "old@example.com",
                    "2026-03-16T10:00:00Z",
                    "본문",
                    "본문",
                    "본문",
                    "",
                    "https://example.com/m-10",
                ),
            )
            connection.commit()
        finally:
            connection.close()
        return db_path


if __name__ == "__main__":
    unittest.main()
