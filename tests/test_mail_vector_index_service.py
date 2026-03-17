from __future__ import annotations

import os
import sqlite3
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.mail_vector_index_service import MailVectorIndexService


class MailVectorIndexServiceTest(unittest.TestCase):
    """메일 벡터 인덱싱 서비스 동작을 검증한다."""

    @patch.dict(os.environ, {"MOLDUBOT_MAIL_VECTOR_INDEX_ENABLED": "1"}, clear=False)
    @patch("app.services.mail_vector_index_service._resolve_runtime_blocker", return_value="python_3_14_unsupported")
    def test_status_reports_runtime_blocker(self, _: MagicMock) -> None:
        """Python/Chroma 런타임 비호환 시 fallback backend 상태가 노출되어야 한다."""
        with patch(
            "app.services.mail_vector_index_service._load_chromadb_module",
            side_effect=AssertionError("chromadb import should be skipped"),
        ):
            service = MailVectorIndexService()
        status = service.get_status()
        self.assertTrue(status.enabled)
        self.assertEqual("sqlite_fallback", status.backend)
        self.assertEqual("python_3_14_unsupported", status.runtime_blocker)
        self.assertFalse(status.chromadb_available)

    @patch.dict(
        os.environ,
        {
            "MOLDUBOT_MAIL_VECTOR_INDEX_ENABLED": "1",
            "MOLDUBOT_MAIL_VECTOR_DIR": "/tmp/moldubot-test-chroma",
            "MOLDUBOT_MAIL_VECTOR_COLLECTION": "test_collection",
        },
        clear=False,
    )
    def test_upsert_mail_document_calls_chroma_with_embedding(self) -> None:
        """메일 문서 upsert 시 id/document/metadata/embedding을 함께 전달해야 한다."""
        fake_collection = MagicMock()
        fake_client = MagicMock()
        fake_client.get_or_create_collection.return_value = fake_collection
        fake_module = types.SimpleNamespace(PersistentClient=MagicMock(return_value=fake_client))
        with patch("app.services.mail_vector_index_service._resolve_runtime_blocker", return_value=""), patch(
            "app.services.mail_vector_index_service._load_chromadb_module",
            return_value=fake_module,
        ):
            service = MailVectorIndexService()
            done = service.upsert_mail_document(
                message_id="m-1",
                subject="메일 제목",
                body_text="본문 내용",
                summary="요약 텍스트",
                category="일반",
                from_address="a@example.com",
                received_date="2026-03-10T00:00:00Z",
            )
        self.assertTrue(done)
        self.assertEqual(1, fake_collection.upsert.call_count)
        kwargs = fake_collection.upsert.call_args.kwargs
        self.assertEqual(["m-1"], kwargs["ids"])
        self.assertEqual(1, len(kwargs["embeddings"]))
        self.assertEqual(1, len(kwargs["documents"]))
        self.assertEqual("일반", kwargs["metadatas"][0]["category"])
        self.assertTrue(service.get_status().enabled)
        self.assertEqual("chromadb", service.get_status().backend)

    @patch.dict(os.environ, {"MOLDUBOT_MAIL_VECTOR_INDEX_ENABLED": "0"}, clear=False)
    def test_upsert_mail_document_returns_false_when_disabled(self) -> None:
        """비활성화 상태에서는 upsert를 수행하지 않아야 한다."""
        service = MailVectorIndexService()
        done = service.upsert_mail_document(
            message_id="m-2",
            subject="제목",
            body_text="본문",
            summary="요약",
            category="일반",
            from_address="b@example.com",
            received_date="2026-03-10T00:00:00Z",
        )
        self.assertFalse(done)

    @patch.dict(os.environ, {"MOLDUBOT_MAIL_VECTOR_INDEX_ENABLED": "1"}, clear=False)
    @patch("app.services.mail_vector_index_service._load_chromadb_module", return_value=None)
    def test_upsert_mail_document_returns_false_when_chromadb_unavailable(self, _: MagicMock) -> None:
        """chromadb import 실패 시에도 sqlite fallback에 저장되어야 한다."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.dict(os.environ, {"MOLDUBOT_MAIL_VECTOR_DIR": tmp_dir}, clear=False):
                service = MailVectorIndexService()
                done = service.upsert_mail_document(
                    message_id="m-3",
                    subject="제목",
                    body_text="본문",
                    summary="요약",
                    category="일반",
                    from_address="c@example.com",
                    received_date="2026-03-10T00:00:00Z",
                )
                status = service.get_status()
                rows = self._read_fallback_rows(Path(tmp_dir) / "mail_vector_fallback.sqlite3")
        self.assertTrue(done)
        self.assertEqual("sqlite_fallback", status.backend)
        self.assertEqual(1, len(rows))
        self.assertEqual("m-3", rows[0][0])

    def _read_fallback_rows(self, db_path: Path) -> list[tuple[str, str]]:
        """sqlite fallback DB에서 저장된 message_id/document를 읽는다."""
        connection = sqlite3.connect(str(db_path))
        try:
            return connection.execute(
                "SELECT message_id, document FROM mail_vector_index ORDER BY message_id"
            ).fetchall()
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
