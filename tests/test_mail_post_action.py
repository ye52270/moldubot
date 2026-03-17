from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.services.mail_service import MailService


class MailPostActionTest(unittest.TestCase):
    """
    메일 후속작업 단일 실행 액션을 검증한다.
    """

    def _build_service(self, root: Path) -> MailService:
        """
        테스트용 SQLite 메일 DB를 생성하고 MailService를 반환한다.

        Args:
            root: 임시 디렉터리 경로

        Returns:
            MailService 인스턴스
        """
        db_path = root / "emails.db"
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
                    "테스트 메일",
                    "sender@example.com",
                    "2099-01-01 10:00:00",
                    "To: alice@example.com; bob@example.com\n회의 일정 공유. 오늘 요청사항 확인 필요.",
                    "<form id=\"loginForm\"><input type=\"password\" name=\"password\" /></form>",
                    None,
                    "요약 사전 텍스트",
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return MailService(db_path=db_path)

    def _build_and_prime_service(self, root: Path) -> MailService:
        """
        테스트 DB 기반 MailService를 생성하고 현재메일 캐시를 초기화한다.

        Args:
            root: 임시 디렉터리 경로

        Returns:
            현재메일이 설정된 MailService
        """
        service = self._build_service(root=root)
        service.read_current_mail()
        return service

    def test_run_post_action_key_facts(self) -> None:
        """
        `key_facts` 액션은 context-only payload를 반환해야 한다.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._build_and_prime_service(Path(tmp_dir))
            payload = service.run_post_action(action="key_facts")
        self.assertEqual("key_facts", payload["action"])
        self.assertEqual("context_only", payload["status"])
        self.assertIn("mail_context", payload)
        self.assertNotIn("key_facts", payload)

    def test_run_post_action_current_mail(self) -> None:
        """
        `current_mail` 액션은 현재 메일 조회 정보를 반환해야 한다.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._build_and_prime_service(Path(tmp_dir))
            payload = service.run_post_action(action="current_mail")
        self.assertEqual("current_mail", payload["action"])
        self.assertEqual("completed", payload["status"])
        self.assertIn("subject", payload)
        self.assertIn("body_preview", payload)

    def test_run_post_action_recipients(self) -> None:
        """
        `recipients` 액션은 context-only payload를 반환해야 한다.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._build_and_prime_service(Path(tmp_dir))
            payload = service.run_post_action(action="recipients")
        self.assertEqual("recipients", payload["action"])
        self.assertEqual("context_only", payload["status"])
        self.assertIn("mail_context", payload)
        self.assertNotIn("recipients", payload)

    def test_run_post_action_summary_with_key_facts(self) -> None:
        """
        `summary_with_key_facts` 액션은 context-only payload를 반환해야 한다.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._build_and_prime_service(Path(tmp_dir))
            payload = service.run_post_action(action="summary_with_key_facts")
        self.assertEqual("summary_with_key_facts", payload["action"])
        self.assertEqual("context_only", payload["status"])
        self.assertNotIn("summary_lines", payload)
        self.assertNotIn("key_facts", payload)
        self.assertIn("mail_context", payload)
        self.assertEqual("테스트 메일", payload["mail_context"]["subject"])

    def test_run_post_action_summary_includes_mail_context(self) -> None:
        """
        `summary` 액션은 context-only payload를 반환해야 한다.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._build_and_prime_service(Path(tmp_dir))
            payload = service.run_post_action(action="summary")
        self.assertEqual("summary", payload["action"])
        self.assertEqual("context_only", payload["status"])
        self.assertIn("mail_context", payload)
        self.assertEqual("테스트 메일", payload["mail_context"]["subject"])
        self.assertEqual("요약 사전 텍스트", payload["mail_context"]["summary_text"])
        self.assertIn("body_excerpt", payload["mail_context"])
        self.assertIn("body_code_excerpt", payload["mail_context"])
        self.assertIn("<form id=\"loginForm\">", payload["mail_context"]["body_code_excerpt"])

    def test_run_post_action_report_includes_mail_context(self) -> None:
        """
        `report` 액션은 context-only payload를 반환해야 한다.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._build_and_prime_service(Path(tmp_dir))
            payload = service.run_post_action(action="report")
        self.assertEqual("report", payload["action"])
        self.assertEqual("context_only", payload["status"])
        self.assertIn("mail_context", payload)

    def test_run_post_action_without_current_mail_returns_empty_context(self) -> None:
        """
        현재메일 캐시가 비어 있으면 context-only 액션은 빈 mail_context를 반환해야 한다.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._build_service(Path(tmp_dir))
            payload = service.run_post_action(action="summary")
        self.assertEqual("summary", payload["action"])
        self.assertEqual("context_only", payload["status"])
        self.assertEqual({}, payload["mail_context"])


if __name__ == "__main__":
    unittest.main()
