from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from app.services.mail_vector_index_service import MailVectorIndexService


class MailVectorIndexServiceTest(unittest.TestCase):
    """메일 벡터 인덱싱 서비스 동작을 검증한다."""

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
        with patch("app.services.mail_vector_index_service.chromadb.PersistentClient", return_value=fake_client):
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


if __name__ == "__main__":
    unittest.main()
