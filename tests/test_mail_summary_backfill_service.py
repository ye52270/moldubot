from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.services.mail_summary_backfill_service import MailSummaryBackfillService


class MailSummaryBackfillServiceTest(unittest.TestCase):
    """
    emails.summary 백필 서비스 동작을 검증한다.
    """

    def test_backfill_updates_only_missing_summary_by_default(self) -> None:
        """
        기본 설정에서는 summary가 비어 있는 레코드만 업데이트해야 한다.
        """
        db_path = self._build_sample_db()
        service = MailSummaryBackfillService(db_path=db_path)
        result = service.backfill(dry_run=False, only_missing=True, include_category=True)
        self.assertEqual(3, result.scanned)
        self.assertEqual(2, result.updated)
        self.assertEqual(3, result.category_updated)
        self.assertEqual(0, result.skipped_existing)
        self.assertEqual(0, result.skipped_empty_body)
        summary_rows, category_rows = self._read_values(db_path=db_path)
        self.assertTrue(bool(summary_rows["m-null"].strip()))
        self.assertEqual("기존 요약", summary_rows["m-filled"])
        self.assertEqual("제목 기준 요약: 회신 부탁드립니다", summary_rows["m-empty-body"])
        self.assertEqual("긴급", category_rows["m-null"])
        self.assertEqual("회신필요", category_rows["m-filled"])
        self.assertEqual("회신필요", category_rows["m-empty-body"])

    def test_backfill_dry_run_does_not_write_db(self) -> None:
        """
        dry_run 모드에서는 업데이트 건수를 계산해도 DB 반영은 하지 않아야 한다.
        """
        db_path = self._build_sample_db()
        service = MailSummaryBackfillService(db_path=db_path)
        result = service.backfill(dry_run=True, only_missing=True, include_category=True)
        self.assertEqual(2, result.updated)
        self.assertEqual(3, result.category_updated)
        summary_rows, category_rows = self._read_values(db_path=db_path)
        self.assertEqual("", summary_rows["m-null"])
        self.assertEqual("", category_rows["m-null"])

    def test_backfill_include_existing_overwrites_non_empty_summary(self) -> None:
        """
        include-existing 모드에서는 기존 summary도 재생성되어야 한다.
        """
        db_path = self._build_sample_db()
        service = MailSummaryBackfillService(db_path=db_path)
        result = service.backfill(dry_run=False, only_missing=False, include_category=True)
        self.assertEqual(3, result.updated)
        self.assertEqual(3, result.category_updated)
        summary_rows, category_rows = self._read_values(db_path=db_path)
        self.assertNotEqual("기존 요약", summary_rows["m-filled"])
        self.assertTrue(bool(summary_rows["m-filled"].strip()))
        self.assertEqual("회신필요", category_rows["m-filled"])

    def test_category_classifier_marks_reply_required_for_request_wording(self) -> None:
        """
        요청/문의 성격 문구가 포함되면 category를 회신필요로 분류해야 한다.
        """
        db_path = self._build_sample_db()
        service = MailSummaryBackfillService(db_path=db_path)
        result = service.backfill(dry_run=False, only_missing=False, include_category=True)
        self.assertEqual(3, result.category_updated)
        _, category_rows = self._read_values(db_path=db_path)
        self.assertEqual("회신필요", category_rows["m-filled"])

    def _build_sample_db(self) -> Path:
        """
        테스트용 summary 백필 샘플 DB를 생성한다.

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
                    "m-null",
                    "제목1",
                    "a@example.com",
                    "2026-03-07T00:00:00Z",
                    "",
                    "",
                    "메일 인증 실패 이슈입니다. DNS 설정 점검이 필요합니다. 긴급 조치 바랍니다.",
                    "",
                    "",
                ),
            )
            conn.execute(
                "INSERT INTO emails VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "m-filled",
                    "제목2",
                    "b@example.com",
                    "2026-03-06T00:00:00Z",
                    "",
                    "",
                    "기존 요약이 있어도 재생성 가능해야 합니다. 확인 부탁드립니다.",
                    "기존 요약",
                    "",
                ),
            )
            conn.execute(
                "INSERT INTO emails VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "m-empty-body",
                    "회신 부탁드립니다",
                    "c@example.com",
                    "2026-03-05T00:00:00Z",
                    "",
                    "",
                    "",
                    "",
                    "",
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return db_path

    def _read_values(self, db_path: Path) -> tuple[dict[str, str], dict[str, str]]:
        """
            message_id별 summary/category 값을 읽는다.

        Args:
            db_path: 조회 대상 DB 경로

        Returns:
            (message_id -> summary 매핑, message_id -> category 매핑)
        """
        conn = sqlite3.connect(str(db_path))
        try:
            rows = conn.execute(
                "SELECT message_id, COALESCE(summary, '') AS summary, COALESCE(category, '') AS category FROM emails"
            ).fetchall()
        finally:
            conn.close()
        summaries = {str(row[0]): str(row[1] or "") for row in rows}
        categories = {str(row[0]): str(row[2] or "") for row in rows}
        return summaries, categories


if __name__ == "__main__":
    unittest.main()
