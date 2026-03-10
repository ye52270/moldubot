from __future__ import annotations

import json
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.report_routes import router


def _parse_sse_events(raw_text: str) -> list[dict[str, object]]:
    """
    SSE 응답 본문에서 JSON payload 목록을 추출한다.

    Args:
        raw_text: StreamingResponse 텍스트

    Returns:
        data 라인의 JSON 객체 목록
    """
    events: list[dict[str, object]] = []
    for line in str(raw_text or "").splitlines():
        if not line.startswith("data: "):
            continue
        payload = json.loads(line[6:])
        if isinstance(payload, dict):
            events.append(payload)
    return events


class ReportRoutesTest(unittest.TestCase):
    """report_routes 엔드포인트 계약을 검증한다."""

    def setUp(self) -> None:
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)

    def test_report_generate_returns_error_when_content_empty(self) -> None:
        response = self.client.post(
            "/report/generate",
            json={"email_content": "", "email_subject": "제목"},
        )
        self.assertEqual(200, response.status_code)
        events = _parse_sse_events(response.text)
        self.assertTrue(events)
        self.assertEqual("error", str(events[0].get("type") or ""))

    def test_report_generate_emits_steps_and_done(self) -> None:
        with patch(
            "app.api.report_routes.generate_report_html_fast",
            return_value="<html><body><h1>테스트</h1></body></html>",
        ):
            with patch(
                "app.api.report_routes.convert_html_to_docx",
                new=AsyncMock(return_value="/report/download/sample.docx"),
            ):
                response = self.client.post(
                    "/report/generate",
                    json={
                        "email_content": "본문",
                        "email_subject": "제목",
                        "email_sender": "박제영",
                    },
                )

        self.assertEqual(200, response.status_code)
        events = _parse_sse_events(response.text)
        event_types = [str(event.get("type") or "") for event in events]
        self.assertIn("step", event_types)
        self.assertIn("done", event_types)
        done_event = next(event for event in events if str(event.get("type") or "") == "done")
        self.assertEqual("/report/download/sample.docx", str(done_event.get("docx_url") or ""))
        self.assertEqual("/report/preview/sample.docx", str(done_event.get("preview_url") or ""))

    def test_report_generate_uses_template_when_model_html_empty(self) -> None:
        converted_payload: dict[str, str] = {}

        async def _fake_convert(html: str, title: str) -> str:
            converted_payload["html"] = html
            converted_payload["title"] = title
            return "/report/download/fallback.docx"

        with patch("app.api.report_routes.generate_report_html_fast", return_value=""):
            with patch("app.api.report_routes.convert_html_to_docx", new=_fake_convert):
                response = self.client.post(
                    "/report/generate",
                    json={"email_content": "본문", "email_subject": "제목"},
                )

        self.assertEqual(200, response.status_code)
        self.assertIn("모델 출력이 비어", converted_payload.get("html", ""))
        self.assertEqual("제목", converted_payload.get("title", ""))

    def test_report_preview_page_renders_inline_html(self) -> None:
        with patch("app.api.report_routes.resolve_report_file_path") as mocked_docx_path:
            with patch("app.api.report_routes.resolve_report_html_path") as mocked_html_path:
                mocked_docx_path.return_value.exists.return_value = True
                mocked_docx_path.return_value.name = "sample.docx"
                mocked_html_path.return_value.exists.return_value = True
                mocked_html_path.return_value.read_text.return_value = "<h1>미리보기</h1>"
                response = self.client.get("/report/preview/sample.docx")

        self.assertEqual(200, response.status_code)
        self.assertIn("보고서 미리보기", response.text)
        self.assertIn("srcdoc=", response.text)
        self.assertIn("/report/download/sample.docx", response.text)

    def test_report_preview_page_404_when_missing(self) -> None:
        with patch("app.api.report_routes.resolve_report_file_path") as mocked_path:
            mocked_path.return_value.exists.return_value = False
            response = self.client.get("/report/preview/missing.docx")

        self.assertEqual(404, response.status_code)

    def test_weekly_report_generate_emits_steps_and_done(self) -> None:
        with patch(
            "app.api.report_routes.generate_weekly_report_html_fast",
            return_value="<html><body><h1>주간보고</h1></body></html>",
        ):
            with patch(
                "app.api.report_routes._fetch_weekly_mail_items",
                return_value=[{"subject": "A", "summary_text": "B"}],
            ):
                with patch(
                    "app.api.report_routes.convert_html_to_docx",
                    new=AsyncMock(return_value="/report/download/weekly.docx"),
                ):
                    response = self.client.post(
                        "/report/weekly/generate",
                        json={"week_offset": 2, "report_author": "박제영"},
                    )

        self.assertEqual(200, response.status_code)
        events = _parse_sse_events(response.text)
        event_types = [str(event.get("type") or "") for event in events]
        self.assertIn("step", event_types)
        self.assertIn("done", event_types)
        done_event = next(event for event in events if str(event.get("type") or "") == "done")
        self.assertEqual("/report/download/weekly.docx", str(done_event.get("docx_url") or ""))
        self.assertEqual("/report/preview/weekly.docx", str(done_event.get("preview_url") or ""))

    def test_weekly_report_generate_uses_template_with_subline_when_model_html_empty(self) -> None:
        converted_payload: dict[str, str] = {}

        async def _fake_convert(html: str, title: str, layout: str = "portrait") -> str:
            converted_payload["html"] = html
            converted_payload["title"] = title
            converted_payload["layout"] = layout
            return "/report/download/weekly-fallback.docx"

        with patch("app.api.report_routes.generate_weekly_report_html_fast", return_value=""):
            with patch("app.api.report_routes._fetch_weekly_mail_items", return_value=[]):
                with patch("app.api.report_routes.convert_html_to_docx", new=_fake_convert):
                    response = self.client.post(
                        "/report/weekly/generate",
                        json={"week_offset": 1, "report_author": "박제영"},
                    )

        self.assertEqual(200, response.status_code)
        self.assertIn("<br>- ", converted_payload.get("html", ""))
        self.assertEqual("landscape_wide", converted_payload.get("layout", ""))


if __name__ == "__main__":
    unittest.main()
