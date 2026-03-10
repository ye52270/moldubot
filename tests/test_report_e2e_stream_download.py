from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from docx import Document
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.report_routes import router


def _parse_sse_payloads(raw_text: str) -> list[dict[str, object]]:
    """
    SSE 응답 텍스트에서 data payload(JSON) 목록을 추출한다.

    Args:
        raw_text: StreamingResponse 전체 텍스트

    Returns:
        역직렬화된 payload 목록
    """
    events: list[dict[str, object]] = []
    for line in str(raw_text or "").splitlines():
        if not line.startswith("data: "):
            continue
        payload = json.loads(line[6:])
        if isinstance(payload, dict):
            events.append(payload)
    return events


class ReportE2EStreamDownloadTest(unittest.TestCase):
    """보고서 생성 SSE와 DOCX 다운로드 E2E 계약을 검증한다."""

    def test_report_generate_stream_and_docx_download_e2e(self) -> None:
        """
        `/report/generate` done 이벤트와 `/report/download/*` 다운로드가 정상 동작하는지 검증한다.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            app = FastAPI()
            app.include_router(router)
            client = TestClient(app)
            report_docx_dir = Path(tmp_dir) / "docx"
            report_html_dir = Path(tmp_dir) / "html"

            with patch(
                "app.api.report_routes.generate_report_html_fast",
                return_value="<html><body><h1>테스트 보고서</h1><p>본문 문장</p></body></html>",
            ):
                with patch("app.services.report_docx_service.REPORT_FILES_DIR", report_docx_dir):
                    with patch("app.services.report_docx_service.REPORT_HTML_DIR", report_html_dir):
                        response = client.post(
                            "/report/generate",
                            json={"email_content": "메일 본문", "email_subject": "제목", "email_sender": "박제영"},
                        )
                        self.assertEqual(200, response.status_code)
                        events = _parse_sse_payloads(response.text)
                        event_types = [str(event.get("type") or "") for event in events]
                        self.assertIn("done", event_types)

                        done_event = next(event for event in events if str(event.get("type") or "") == "done")
                        docx_url = str(done_event.get("docx_url") or "")
                        preview_url = str(done_event.get("preview_url") or "")
                        self.assertTrue(docx_url.startswith("/report/download/"))
                        self.assertTrue(preview_url.startswith("/report/preview/"))

                        download_response = client.get(docx_url)
                        self.assertEqual(200, download_response.status_code)
                        self.assertEqual(
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            str(download_response.headers.get("content-type") or "").split(";")[0],
                        )

                        docx_path = report_docx_dir / Path(docx_url).name
                        self.assertTrue(docx_path.exists())
                        doc = Document(str(docx_path))
                        merged_text = "\n".join(paragraph.text for paragraph in doc.paragraphs).strip()
                        self.assertIn("테스트 보고서", merged_text)
                        self.assertIn("본문 문장", merged_text)


if __name__ == "__main__":
    unittest.main()
