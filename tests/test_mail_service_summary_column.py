from __future__ import annotations

import sqlite3
import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch

from app.services.mail_service import MailRecord, MailService


class MailServiceSummaryColumnTest(unittest.TestCase):
    """
    emails.summary 컬럼이 있을 때 MailRecord.summary_text 매핑을 검증한다.
    """

    def test_read_mail_by_message_id_maps_summary_text_when_column_exists(self) -> None:
        """
        summary 컬럼이 존재하면 해당 값을 summary_text로 읽어야 한다.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "emails.db"
            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute(
                    "CREATE TABLE emails ("
                    "message_id TEXT, "
                    "subject TEXT, "
                    "from_address TEXT, "
                    "received_date TEXT, "
                    "body_clean TEXT, "
                    "body_full TEXT, "
                    "body_preview TEXT, "
                    "summary TEXT)"
                )
                conn.execute(
                    "INSERT INTO emails VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "m-1",
                        "요약 테스트",
                        "sender@example.com",
                        "2026-03-01 00:00:00",
                        "본문",
                        None,
                        None,
                        "요약 결과: 1. DB 저장 요약",
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            service = MailService(db_path=db_path)
            mail = service.read_mail_by_message_id(message_id="m-1")

        self.assertIsNotNone(mail)
        assert mail is not None
        self.assertEqual("요약 결과: 1. DB 저장 요약", mail.summary_text)

    @patch.dict(
        os.environ,
        {"MOLDUBOT_SUMMARY_SYNC_ON_UPSERT": "1", "MOLDUBOT_MAIL_VECTOR_INDEX_ENABLED": "0"},
        clear=False,
    )
    def test_upsert_mail_record_processes_summary_job_when_summary_missing(self) -> None:
        """
        summary가 비어 있으면 upsert 직후 summary/category가 채워지고 queue가 완료되어야 한다.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "emails.db"
            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute(
                    "CREATE TABLE emails ("
                    "message_id TEXT PRIMARY KEY, "
                    "subject TEXT, "
                    "from_address TEXT, "
                    "received_date TEXT, "
                    "body_clean TEXT, "
                    "body_full TEXT, "
                    "body_preview TEXT, "
                    "summary TEXT, "
                    "web_link TEXT)"
                )
                conn.commit()
            finally:
                conn.close()

            service = MailService(db_path=db_path)
            service.upsert_mail_record(
                mail=MailRecord(
                    message_id="m-2",
                    subject="업서트 요약",
                    from_address="sender@example.com",
                    received_date="2026-03-07T00:00:00Z",
                    body_text="핵심 이슈는 인증 실패입니다. 조치로 DNS 레코드 수정이 필요합니다. 완료 후 재점검 예정입니다.",
                    web_link="https://outlook.live.com/owa/?ItemID=m-2",
                )
            )
            saved = service.read_mail_by_message_id(message_id="m-2")
            conn = sqlite3.connect(str(db_path))
            try:
                queue_row = conn.execute(
                    "SELECT message_id, status FROM mail_summary_queue WHERE message_id = ? LIMIT 1",
                    ("m-2",),
                ).fetchone()
            finally:
                conn.close()

        self.assertIsNotNone(saved)
        assert saved is not None
        self.assertTrue(bool(saved.summary_text.strip()))
        self.assertIsNotNone(queue_row)
        assert queue_row is not None
        self.assertEqual("m-2", str(queue_row[0]))
        self.assertEqual("completed", str(queue_row[1]))

    def test_upsert_mail_record_uses_given_summary_when_present(self) -> None:
        """
        MailRecord.summary_text가 제공되면 자동 생성 대신 해당 값을 저장해야 한다.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "emails.db"
            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute(
                    "CREATE TABLE emails ("
                    "message_id TEXT PRIMARY KEY, "
                    "subject TEXT, "
                    "from_address TEXT, "
                    "received_date TEXT, "
                    "body_clean TEXT, "
                    "body_full TEXT, "
                    "body_preview TEXT, "
                    "summary TEXT)"
                )
                conn.commit()
            finally:
                conn.close()

            service = MailService(db_path=db_path)
            service.upsert_mail_record(
                mail=MailRecord(
                    message_id="m-3",
                    subject="업서트 요약 우선",
                    from_address="sender@example.com",
                    received_date="2026-03-07T00:00:00Z",
                    body_text="본문 원문",
                    summary_text="명시 요약 텍스트",
                )
            )
            saved = service.read_mail_by_message_id(message_id="m-3")

        self.assertIsNotNone(saved)
        assert saved is not None
        self.assertEqual("명시 요약 텍스트", saved.summary_text)


if __name__ == "__main__":
    unittest.main()
