from __future__ import annotations

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.bootstrap_routes import router


class BootstrapLegacyRoutesTest(unittest.TestCase):
    """legacy 포털 마이그레이션 API 계약을 검증한다."""

    def setUp(self) -> None:
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)

    def test_promise_draft_save_returns_completed(self) -> None:
        response = self.client.post(
            "/api/promise/drafts",
            json={
                "project_number": "30132215-D014",
                "project_name": "테스트 프로젝트",
                "mode": "create",
                "reason": "초기 실행예산 등록",
            },
        )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("completed", payload.get("status"))
        self.assertEqual("30132215-D014", payload.get("draft", {}).get("project_number"))

    def test_promise_draft_list_returns_saved_rows(self) -> None:
        self.client.post(
            "/api/promise/drafts",
            json={
                "project_number": "30132215-D099",
                "project_name": "조회 테스트 프로젝트",
                "mode": "create",
                "reason": "목록 조회 테스트",
            },
        )
        response = self.client.get("/api/promise/drafts")
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertIsInstance(payload.get("drafts"), list)
        rows = payload.get("drafts", [])
        self.assertTrue(any(str(item.get("project_number")) == "30132215-D099" for item in rows))

    def test_promise_summaries_returns_legacy_items(self) -> None:
        response = self.client.get("/api/promise/summaries")
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertIsInstance(payload.get("items"), list)
        self.assertGreaterEqual(int(payload.get("count", 0)), 1)
        first = payload.get("items", [])[0]
        self.assertIn("project_number", first)
        self.assertIn("execution_total", first)

    def test_finance_claim_save_returns_budget(self) -> None:
        response = self.client.post(
            "/api/finance/claims",
            json={
                "project_number": "30132215-D014",
                "expense_category": "식비",
                "amount": 10000,
                "description": "테스트 정산",
                "evidence_files": ["receipt.png"],
            },
        )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("completed", payload.get("status"))
        self.assertIn("budget", payload)

    def test_myhr_request_save_returns_completed(self) -> None:
        response = self.client.post(
            "/api/myhr/requests",
            json={
                "request_type": "휴가신청",
                "request_date": "2026-03-10",
                "reason": "연차 사용",
            },
        )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("completed", payload.get("status"))
        self.assertEqual("휴가신청", payload.get("request", {}).get("request_type"))


if __name__ == "__main__":
    unittest.main()
