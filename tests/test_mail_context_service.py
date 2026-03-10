from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.integrations.microsoft_graph.mail_client import GraphMailMessage
from app.services.mail_context_service import MailContextService


class FakeGraphClient:
    """
    MailContextService 테스트용 Graph 클라이언트 더블.
    """

    def __init__(self, message: GraphMailMessage | None) -> None:
        """
        테스트 더블을 초기화한다.

        Args:
            message: 반환할 Graph 메일
        """
        self._message = message
        self.called = 0

    def get_message(self, mailbox_user: str, message_id: str) -> GraphMailMessage | None:
        """
        Graph 조회 호출을 모사한다.

        Args:
            mailbox_user: 조회 대상 사용자
            message_id: 메시지 식별자

        Returns:
            사전에 설정한 메시지
        """
        self.called += 1
        return self._message


class MailContextServiceTest(unittest.TestCase):
    """
    선택 메일 컨텍스트 조회 서비스 동작을 검증한다.
    """

    def _create_db(self, root: Path) -> Path:
        """
        테스트용 emails 테이블을 생성한다.

        Args:
            root: 임시 디렉터리 경로

        Returns:
            DB 파일 경로
        """
        db_path = root / "emails.db"
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "CREATE TABLE emails ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "message_id TEXT, "
                "subject TEXT, "
                "from_address TEXT, "
                "received_date TEXT, "
                "body_preview TEXT, "
                "body_full TEXT, "
                "body_clean TEXT)"
            )
            conn.commit()
        finally:
            conn.close()
        return db_path

    def test_get_mail_context_uses_db_cache(self) -> None:
        """
        DB 캐시 hit 시 Graph 호출 없이 캐시를 반환해야 한다.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = self._create_db(root=Path(tmp_dir))
            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute(
                    "INSERT INTO emails (message_id, subject, from_address, received_date, body_clean, body_full) VALUES (?, ?, ?, ?, ?, ?)",
                    ("m-1", "제목", "a@example.com", "2026-01-01T00:00:00Z", "본문", "<div>본문</div>"),
                )
                conn.commit()
            finally:
                conn.close()

            fake_graph = FakeGraphClient(message=None)
            service = MailContextService(db_path=db_path, graph_client=fake_graph)  # type: ignore[arg-type]
            result = service.get_mail_context(message_id="m-1", mailbox_user="user@example.com")

        self.assertEqual("completed", result.status)
        self.assertEqual("db-cache", result.source)
        self.assertIsNotNone(result.mail)
        self.assertEqual(0, fake_graph.called)

    def test_get_mail_context_refreshes_graph_when_body_full_missing(self) -> None:
        """
        캐시가 body_clean만 있고 body_full이 비어 있으면 Graph 재조회로 보정해야 한다.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = self._create_db(root=Path(tmp_dir))
            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute(
                    "INSERT INTO emails (message_id, subject, from_address, received_date, body_clean) VALUES (?, ?, ?, ?, ?)",
                    ("m-3", "캐시 제목", "cached@example.com", "2026-01-03T00:00:00Z", "정제 본문"),
                )
                conn.commit()
            finally:
                conn.close()
            fake_graph = FakeGraphClient(
                message=GraphMailMessage(
                    message_id="m-3",
                    subject="그래프 제목",
                    from_address="graph@example.com",
                    received_date="2026-01-03T00:00:00Z",
                    body_text="<form id=\"loginForm\"></form>",
                    internet_message_id="<m-3@example.com>",
                    web_link="https://example.com/m-3",
                )
            )
            service = MailContextService(db_path=db_path, graph_client=fake_graph)  # type: ignore[arg-type]
            result = service.get_mail_context(message_id="m-3", mailbox_user="user@example.com")

        self.assertEqual("completed", result.status)
        self.assertEqual("graph-api", result.source)
        self.assertEqual(1, fake_graph.called)
        self.assertIsNotNone(result.mail)
        self.assertIn("<form", str(result.mail.body_text))

    def test_get_mail_context_falls_back_to_graph(self) -> None:
        """
        DB miss 시 Graph 조회 결과를 반환하고 DB에 upsert해야 한다.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = self._create_db(root=Path(tmp_dir))
            fake_graph = FakeGraphClient(
                message=GraphMailMessage(
                    message_id="m-2",
                    subject="그래프 제목",
                    from_address="b@example.com",
                    received_date="2026-01-02T00:00:00Z",
                    body_text="그래프 본문",
                    internet_message_id="<m-2@example.com>",
                    web_link="https://example.com/m-2",
                )
            )
            service = MailContextService(db_path=db_path, graph_client=fake_graph)  # type: ignore[arg-type]
            result = service.get_mail_context(message_id="m-2", mailbox_user="user@example.com")

            conn = sqlite3.connect(str(db_path))
            try:
                row = conn.execute(
                    "SELECT subject, from_address FROM emails WHERE message_id = ?",
                    ("m-2",),
                ).fetchone()
            finally:
                conn.close()

        self.assertEqual("completed", result.status)
        self.assertEqual("graph-api", result.source)
        self.assertEqual(1, fake_graph.called)
        self.assertIsNotNone(row)
        self.assertEqual("그래프 제목", row[0])

    def test_get_mail_context_returns_failed_when_missing(self) -> None:
        """
        DB/Graph 모두 miss면 실패 결과를 반환해야 한다.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = self._create_db(root=Path(tmp_dir))
            fake_graph = FakeGraphClient(message=None)
            service = MailContextService(db_path=db_path, graph_client=fake_graph)  # type: ignore[arg-type]
            result = service.get_mail_context(message_id="unknown", mailbox_user="user@example.com")
        self.assertEqual("failed", result.status)
        self.assertEqual("not-found", result.source)
        self.assertEqual(1, fake_graph.called)

    def test_get_mail_context_db_cache_triggers_summary_enrichment_when_summary_empty(self) -> None:
        """
        summary 컬럼이 있고 값이 비어 있으면 cache 경로에서도 summary 보강을 시도해야 한다.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "emails.db"
            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute(
                    "CREATE TABLE emails ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    "message_id TEXT, "
                    "subject TEXT, "
                    "from_address TEXT, "
                    "received_date TEXT, "
                    "body_preview TEXT, "
                    "body_full TEXT, "
                    "body_clean TEXT, "
                    "summary TEXT)"
                )
                conn.execute(
                    "INSERT INTO emails (message_id, subject, from_address, received_date, body_clean, body_full, summary) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ("m-4", "요약 없음 메일", "a@example.com", "2026-01-04T00:00:00Z", "본문", "본문", ""),
                )
                conn.commit()
            finally:
                conn.close()

            fake_graph = FakeGraphClient(message=None)
            service = MailContextService(db_path=db_path, graph_client=fake_graph)  # type: ignore[arg-type]
            with patch.object(
                service._mail_service,
                "ensure_summary_for_message",
                return_value=service._mail_service.read_mail_by_message_id("m-4"),
            ) as mocked_ensure:
                result = service.get_mail_context(message_id="m-4", mailbox_user="user@example.com")

        self.assertEqual("completed", result.status)
        self.assertEqual("db-cache", result.source)
        self.assertIsNotNone(result.mail)
        assert result.mail is not None
        self.assertEqual("", result.mail.summary_text)
        mocked_ensure.assert_called_once_with(
            message_id="m-4",
            requested_by="mail_context",
            max_attempts=3,
        )


if __name__ == "__main__":
    unittest.main()
