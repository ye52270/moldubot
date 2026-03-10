from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.report_docx_service import convert_html_to_docx, resolve_report_file_path


class ReportDocxServiceTest(unittest.IsolatedAsyncioTestCase):
    """HTML->DOCX 변환 서비스 계약을 검증한다."""

    async def test_convert_html_to_docx_creates_file_and_url(self) -> None:
        html = "<html><body><h1>보고서</h1><p>본문</p><table><tr><th>A</th></tr><tr><td>B</td></tr></table></body></html>"
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir)
            with patch("app.services.report_docx_service.REPORT_FILES_DIR", report_dir):
                url = await convert_html_to_docx(html=html, title="테스트 보고서")
                self.assertTrue(url.startswith("/report/download/"))
                filename = url.split("/")[-1]
                self.assertTrue((report_dir / filename).exists())

    def test_resolve_report_file_path_uses_basename(self) -> None:
        path = resolve_report_file_path("../../etc/passwd")
        self.assertEqual("passwd", path.name)


if __name__ == "__main__":
    unittest.main()
