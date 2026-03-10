from __future__ import annotations

import types
import unittest
from unittest.mock import MagicMock, patch

from app.agents.report_agent import (
    _build_fast_report_messages,
    _build_weekly_report_messages,
    _ensure_weekly_bullet_sublines,
    compute_weekly_windows,
    _normalize_report_date_text,
    generate_report_html_fast,
    generate_weekly_report_html_fast,
)


class ReportAgentTest(unittest.TestCase):
    """보고서 fast path 프롬프트/출력 정규화를 검증한다."""

    def test_normalize_report_date_text_keeps_iso_date_prefix(self) -> None:
        normalized = _normalize_report_date_text("2026-01-16T05:47:10Z")
        self.assertEqual("2026-01-16", normalized)

    def test_build_fast_report_messages_contains_grounding_fields(self) -> None:
        messages = _build_fast_report_messages(
            email_subject="FW: 기타 계정의 메일 발송 차단 관련 문의",
            email_content="본문",
            report_date="2026-01-16T05:47:10Z",
            report_author="박제영",
        )
        self.assertEqual(2, len(messages))
        user_prompt = str(messages[1]["content"])
        self.assertIn("- 제목: FW: 기타 계정의 메일 발송 차단 관련 문의", user_prompt)
        self.assertIn("- 날짜: 2026-01-16", user_prompt)
        self.assertIn("- 작성: 박제영", user_prompt)
        self.assertIn("입력 원문에 없는 사실", str(messages[0]["content"]))

    def test_generate_report_html_fast_strips_code_fence(self) -> None:
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="```html\n<h1>테스트</h1>\n```"))]
        )
        with patch("app.agents.report_agent._get_azure_openai_client", return_value=fake_client):
            with patch("app.agents.report_agent.os.getenv", return_value="gpt-4o-mini"):
                html = generate_report_html_fast(
                    email_subject="제목",
                    email_content="본문",
                    report_date="2026-01-16T05:47:10Z",
                    report_author="박제영",
                )
        self.assertEqual("<h1>테스트</h1>", html)

    def test_compute_weekly_windows_returns_expected_ranges(self) -> None:
        result = compute_weekly_windows(week_offset=1, reference_date="2026-03-02")
        self.assertEqual("2026-02-23", result["actual_start"])
        self.assertEqual("2026-02-27", result["actual_end"])
        self.assertEqual("2026-03-02", result["plan_start"])
        self.assertEqual("2026-03-06", result["plan_end"])

    def test_build_weekly_report_messages_contains_periods(self) -> None:
        messages = _build_weekly_report_messages(
            mail_items=[{"subject": "제목", "received_date": "2026-02-24T01:00:00Z", "summary_text": "요약"}],
            week_offset=1,
            report_author="박제영",
            reference_date="2026-03-02",
        )
        self.assertEqual(2, len(messages))
        prompt = str(messages[1]["content"])
        self.assertIn("- 작성자: 박제영", prompt)
        self.assertIn("- 실적 기간: 2026-02-23 ~ 2026-02-27", prompt)
        self.assertIn("- 계획 기간: 2026-03-02 ~ 2026-03-06", prompt)
        self.assertIn("각 불릿은 반드시 2줄 형식", prompt)

    def test_ensure_weekly_bullet_sublines_adds_hyphen_detail(self) -> None:
        source_html = "<ul><li>지속적인 API 호출 상태 확인</li></ul>"
        normalized_html = _ensure_weekly_bullet_sublines(source_html)
        self.assertIn("<br>- ", normalized_html)

    def test_generate_weekly_report_html_fast_enforces_bullet_subline(self) -> None:
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="<ul><li>API 호출 오류 여부 확인</li></ul>"))]
        )
        with patch("app.agents.report_agent._get_azure_openai_client", return_value=fake_client):
            with patch("app.agents.report_agent.os.getenv", return_value="gpt-4o-mini"):
                html = generate_weekly_report_html_fast(
                    mail_items=[{"subject": "제목", "summary_text": "요약"}],
                    week_offset=1,
                    report_author="박제영",
                    reference_date="2026-03-02",
                )
        self.assertIn("<br>- ", html)


if __name__ == "__main__":
    unittest.main()
