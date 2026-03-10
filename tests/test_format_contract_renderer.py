from __future__ import annotations

import unittest

from app.models.response_contracts import LLMResponseContract
from app.services.format_contract_renderer import render_template_driven_contract


class FormatContractRendererTest(unittest.TestCase):
    """템플릿 계약 기반 contract 렌더링을 검증한다."""

    def test_render_current_mail_summary_with_sections(self) -> None:
        """현재메일 요약 템플릿은 주요 내용 섹션을 렌더링해야 한다."""
        contract = LLMResponseContract(
            one_line_summary="메일 시스템 검토가 필요합니다.",
            summary_lines=["Grafana Daily Report 수신 차단 이슈가 있습니다."],
            required_actions=["차단 정책 점검 및 조치 필요"],
        )
        rendered = render_template_driven_contract(
            contract=contract,
            section_contract={
                "template_id": "current_mail_summary",
                "sections": [{"id": "summary"}, {"id": "action"}],
            },
        )
        self.assertIn("## 📌 주요 내용", rendered)
        self.assertIn("1. 메일 시스템 검토가 필요합니다.", rendered)
        self.assertIn("### ✅ 조치 필요 사항", rendered)

    def test_render_current_mail_summary_issue_includes_tech_section(self) -> None:
        """현재메일 이슈 템플릿은 기술 키워드 라인을 기술 이슈 섹션으로 분리해야 한다."""
        contract = LLMResponseContract(
            summary_lines=["API 호출 오류로 메일 동기화가 실패했습니다."],
            major_points=["보안 정책 검토가 필요합니다."],
        )
        rendered = render_template_driven_contract(
            contract=contract,
            section_contract={
                "template_id": "current_mail_summary_issue",
                "sections": [{"id": "summary"}, {"id": "tech_issue"}],
            },
        )
        self.assertIn("### 🛠 기술 이슈", rendered)
        self.assertIn("API 호출 오류로 메일 동기화가 실패했습니다.", rendered)

    def test_render_non_target_template_returns_empty(self) -> None:
        """지원하지 않는 템플릿 ID는 렌더링하지 않아야 한다."""
        rendered = render_template_driven_contract(
            contract=LLMResponseContract(summary_lines=["테스트"]),
            section_contract={"template_id": "mail_search_summary", "sections": [{"id": "major"}]},
        )
        self.assertEqual(rendered, "")


if __name__ == "__main__":
    unittest.main()
