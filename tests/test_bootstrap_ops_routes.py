from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.bootstrap_ops_routes import _CODE7000_SUPPRESSION_COUNTS, router
from app.services.mail_sync_service import MailSyncResult


class BootstrapOpsRoutesTest(unittest.TestCase):
    """addin client log 수집기의 code7000 suppression 동작을 검증한다."""

    def setUp(self) -> None:
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)
        _CODE7000_SUPPRESSION_COUNTS.clear()

    def test_code7000_logs_warning_once_then_suppresses_to_debug(self) -> None:
        payload = {
            "level": "warning",
            "event": "selection_observer_register_failed",
            "payload": {
                "session_id": "sess-1",
                "event_type": "SelectedItemsChanged",
                "code": "7000",
                "message": "권한 없음",
            },
        }
        with (
            patch("app.api.bootstrap_ops_routes.write_ndjson"),
            patch("app.api.bootstrap_ops_routes.logger.warning") as warning_mock,
            patch("app.api.bootstrap_ops_routes.logger.debug") as debug_mock,
            patch("app.api.bootstrap_ops_routes.logger.info") as info_mock,
        ):
            first = self.client.post("/addin/client-logs", json=payload)
            second = self.client.post("/addin/client-logs", json=payload)
        self.assertEqual(204, first.status_code)
        self.assertEqual(204, second.status_code)
        warning_mock.assert_called_once()
        debug_mock.assert_called_once()
        info_mock.assert_not_called()

    def test_mail_sync_recent_dry_run_reports_configuration(self) -> None:
        """dry-run 호출은 Graph 설정 여부와 limit를 그대로 반환해야 한다."""
        with patch("app.api.bootstrap_ops_routes.GraphMailClient") as graph_client_cls:
            graph_client_cls.return_value.is_configured.return_value = False
            response = self.client.post("/ops/mail-sync/recent?limit=15&dry_run=true")
        self.assertEqual(200, response.status_code)
        self.assertEqual(
            {
                "status": "dry-run",
                "limit": 15,
                "dry_run": True,
                "graph_configured": False,
            },
            response.json(),
        )

    def test_mail_sync_recent_runs_sync_service(self) -> None:
        """실제 sync 호출은 MailSyncService 결과를 JSON으로 반환해야 한다."""
        with (
            patch("app.api.bootstrap_ops_routes.GraphMailClient") as graph_client_cls,
            patch("app.api.bootstrap_ops_routes.MailSyncService") as sync_service_cls,
        ):
            graph_client_cls.return_value.is_configured.return_value = True
            sync_service_cls.return_value.sync_recent_messages.return_value = MailSyncResult(
                fetched=5,
                inserted=2,
                updated=1,
                skipped_older=2,
            )
            response = self.client.post("/ops/mail-sync/recent?limit=7")
        self.assertEqual(200, response.status_code)
        self.assertEqual(
            {
                "status": "completed",
                "limit": 7,
                "dry_run": False,
                "result": {
                    "fetched": 5,
                    "inserted": 2,
                    "updated": 1,
                    "skipped_older": 2,
                },
            },
            response.json(),
        )


if __name__ == "__main__":
    unittest.main()
