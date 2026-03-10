from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.bootstrap_ops_routes import _CODE7000_SUPPRESSION_COUNTS, router


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


if __name__ == "__main__":
    unittest.main()
