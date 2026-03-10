from __future__ import annotations

import unittest

from app.services.answer_postprocessor_mail_search import (
    collect_mail_search_digest_lines,
    normalize_mail_search_summary_text,
    render_mail_search_deterministic_response,
    render_mail_search_result_items,
    render_recent_sorted_mail_response,
)


class AnswerPostprocessorMailSearchTest(unittest.TestCase):
    """
    mail_search 후처리 렌더링/요약 정규화 규칙을 검증한다.
    """

    def test_normalize_mail_search_summary_text_strips_html_entities(self) -> None:
        """
        summary_text의 HTML 엔티티/태그는 사람이 읽는 평문으로 정리되어야 한다.
        """
        value = "&nbsp; From: 테스트 &lt;test@example.com&gt;<br>Sent: today"
        normalized = normalize_mail_search_summary_text(value)
        self.assertNotIn("&nbsp;", normalized)
        self.assertNotIn("&lt;", normalized)
        self.assertIn("From: 테스트", normalized)
        self.assertIn("test@example.com", normalized)

    def test_render_recent_sorted_mail_response_uses_summary_card_style_heading(self) -> None:
        """
        최근순 조회 렌더는 `## 📌 주요 내용` 헤더 기반 포맷으로 반환해야 한다.
        """
        tool_payload = {
            "action": "mail_search",
            "results": [
                {
                    "message_id": "m-1",
                    "subject": "Grafana Daily Report 미수신 확인 요청",
                    "sender_names": "izocuna@sk.com",
                    "received_date": "2026-03-05T08:28:42Z",
                    "summary_text": "&nbsp; 본문 요약",
                    "web_link": "https://outlook.live.com/owa/?ItemID=m-1",
                }
            ],
        }
        rendered = render_recent_sorted_mail_response(
            user_message="이 주제 관련 메일 최근순으로 5개 조회해줘",
            tool_payload=tool_payload,
        )
        self.assertTrue(rendered.startswith("## 📌 주요 내용"))
        self.assertIn("- 보낸 사람:", rendered)
        self.assertNotIn("&nbsp;", rendered)
        self.assertLess(rendered.find("- 요약:"), rendered.find("- 보낸 사람:"))

    def test_render_mail_search_result_items_places_summary_before_sender(self) -> None:
        """
        주요 내용 카드의 서브라인 우선값은 보낸 사람보다 요약이어야 한다.
        """
        rendered = render_mail_search_result_items(
            user_message="관련 메일 조회해줘",
            results=[
                {
                    "message_id": "m-2",
                    "subject": "FW: NSM 보안진단 관련",
                    "sender_names": "izocuna@sk.com",
                    "received_date": "2026-03-05T06:30:00Z",
                    "summary_text": "보안진단 조치 이력 공유",
                    "web_link": "https://outlook.live.com/owa/?ItemID=m-2",
                }
            ],
        )
        self.assertIn("- 요약: 보안진단 조치 이력 공유", rendered)
        self.assertLess(rendered.find("- 요약:"), rendered.find("- 보낸 사람:"))

    def test_render_mail_search_result_items_does_not_fallback_to_body_snippet(self) -> None:
        """
        DB summary_text가 비어 있으면 body snippet 대신 안내 문구를 노출해야 한다.
        """
        rendered = render_mail_search_result_items(
            user_message="관련 메일 조회해줘",
            results=[
                {
                    "message_id": "m-3",
                    "subject": "FW: 테스트",
                    "sender_names": "tester@sk.com",
                    "received_date": "2026-03-06T10:00:00Z",
                    "summary_text": "",
                    "snippet": "From: someone@example.com Sent: ...",
                    "web_link": "https://outlook.live.com/owa/?ItemID=m-3",
                }
            ],
        )
        self.assertIn("- 요약: 저장된 요약이 없습니다.", rendered)
        self.assertNotIn("From: someone@example.com", rendered)

    def test_collect_mail_search_digest_lines_uses_aggregated_then_db_summary(self) -> None:
        """
        요약 라인은 aggregated_summary와 DB summary_text를 합쳐 중복 없이 최대 3줄만 구성해야 한다.
        """
        lines = collect_mail_search_digest_lines(
            tool_payload={
                "action": "mail_search",
                "aggregated_summary": [
                    "M365 일정 이슈 대응 회의 필요",
                    "M365 일정 이슈 대응 회의 필요",
                    "기술적 오류 재현 및 조치 요청",
                ],
                "results": [
                    {"summary_text": "Cloud PC 정책 변경 영향 검토"},
                    {"summary_text": "Cloud PC 정책 변경 영향 검토"},
                ],
            },
            max_lines=3,
        )
        self.assertEqual(
            lines,
            [
                "M365 일정 이슈 대응 회의 필요",
                "기술적 오류 재현 및 조치 요청",
                "Cloud PC 정책 변경 영향 검토",
            ],
        )

    def test_render_mail_search_deterministic_response_summary_request_renders_digest_only(self) -> None:
        """
        조회+요약 질의는 메일 목록 대신 2~3줄 주요내용 요약만 렌더링해야 한다.
        """
        rendered = render_mail_search_deterministic_response(
            user_message="M365 프로젝트 진행, 일정 관련 메일을 찾아서 요약해줘. 기술적 이슈도 검색해서 같이 알려줘",
            tool_payload={
                "action": "mail_search",
                "query_summaries": [
                    {
                        "query": "M365 프로젝트 진행",
                        "lines": [
                            "M365 일정 협의 메일이 다수 확인되어 일정 압박 리스크가 있습니다.",
                            "Cloud PC 정책/접속 통제 관련 후속 점검이 필요합니다.",
                        ],
                    },
                    {
                        "query": "기술적 이슈",
                        "lines": [
                            "기술적 이슈(시스템 오류) 관련 긴급 회의 요청이 확인되었습니다.",
                        ],
                    },
                ],
                "aggregated_summary": [
                    "M365 일정 협의 메일이 다수 확인되어 일정 압박 리스크가 있습니다.",
                    "Cloud PC 정책/접속 통제 관련 후속 점검이 필요합니다.",
                    "기술적 이슈(시스템 오류) 관련 긴급 회의 요청이 확인되었습니다.",
                ],
                "results": [
                    {
                        "message_id": "m-1",
                        "subject": "[긴급] 회의 요청",
                        "summary_text": "다음 주 화요일에 시스템 긴급 이슈 관련 회의 요청.",
                        "web_link": "https://outlook.live.com/owa/?ItemID=m-1",
                        "sender_names": "izocuna@sk.com",
                        "received_date": "2026-02-26T09:10:51Z",
                    }
                ],
            },
        )
        self.assertTrue(rendered.startswith("## 📌 주요 내용"))
        self.assertIn("1. M365 일정 협의 메일이 다수 확인되어 일정 압박 리스크가 있습니다.", rendered)
        self.assertIn("### 🛠 기술 이슈", rendered)
        self.assertIn("1. 기술적 이슈(시스템 오류) 관련 긴급 회의 요청이 확인되었습니다.", rendered)
        self.assertIn("### 📬 근거 메일", rendered)
        self.assertIn("- [\\[긴급\\] 회의 요청](https://outlook.live.com/owa/?ItemID=m-1&moldubot_mid=m-1)", rendered)
        self.assertNotIn("1. [", rendered)

    def test_render_mail_search_deterministic_response_uses_query_summaries_without_results(self) -> None:
        """
        조회+요약 질의에서 results가 없어도 query_summaries가 있으면 섹션 렌더를 수행해야 한다.
        """
        rendered = render_mail_search_deterministic_response(
            user_message="M365 프로젝트 진행, 일정 관련 메일을 찾아서 요약해줘. 기술적 이슈도 검색해서 같이 알려줘",
            tool_payload={
                "action": "mail_search",
                "query_summaries": [
                    {"query": "M365 프로젝트 진행", "lines": ["일정 압박 리스크가 확인되었습니다."]},
                    {"query": "기술적 이슈", "lines": ["기술 이슈 근거를 찾지 못했습니다."]},
                ],
                "aggregated_summary": [],
                "results": [],
            },
        )
        self.assertIn("## 📌 주요 내용", rendered)
        self.assertIn("1. 일정 압박 리스크가 확인되었습니다.", rendered)
        self.assertIn("### 🛠 기술 이슈", rendered)
        self.assertIn("1. 기술 이슈 근거를 찾지 못했습니다.", rendered)

    def test_render_mail_search_deterministic_response_skips_non_listing_query(self) -> None:
        """
        조회/검색 의도가 없는 질의에서는 mail_search 결과가 있어도 목록 강제 렌더를 수행하면 안 된다.
        """
        rendered = render_mail_search_deterministic_response(
            user_message="조영득 메일에서 언급된 일정 관련 리스크는 무엇인가요?",
            tool_payload={
                "action": "mail_search",
                "results": [
                    {
                        "message_id": "m-1",
                        "subject": "FW: 테스트",
                        "summary_text": "테스트 요약",
                        "sender_names": "박제영",
                        "received_date": "2026-02-15",
                    }
                ],
            },
        )
        self.assertEqual("", rendered)

    def test_render_mail_search_deterministic_response_skips_internal_summary_fallback_line(self) -> None:
        """
        내부 안내용 fallback 문구는 기술 이슈 섹션에 노출되면 안 된다.
        """
        rendered = render_mail_search_deterministic_response(
            user_message="M365 프로젝트 진행, 일정 관련 메일을 찾아서 요약해줘. 기술적 이슈도 검색해서 같이 알려줘",
            tool_payload={
                "action": "mail_search",
                "query_summaries": [
                    {"query": "M365 프로젝트 진행", "lines": ["일정 압박 리스크가 확인되었습니다."]},
                    {
                        "query": "기술적 이슈",
                        "lines": [
                            "기술 이슈 근거를 찾지 못했습니다.",
                            "저장된 메일 요약(summary)이 없어 주요 내용을 표시하지 못했습니다.",
                        ],
                    },
                ],
                "aggregated_summary": [],
                "results": [],
            },
        )
        self.assertIn("1. 기술 이슈 근거를 찾지 못했습니다.", rendered)
        self.assertNotIn("저장된 메일 요약(summary)이 없어 주요 내용을 표시하지 못했습니다.", rendered)

    def test_render_mail_search_deterministic_response_respects_section_contract_without_tech(self) -> None:
        """
        section_contract에 tech_issue 섹션이 없으면 기술 이슈 섹션을 렌더링하지 않아야 한다.
        """
        rendered = render_mail_search_deterministic_response(
            user_message="M365 관련 메일 조회해서 요약해줘",
            tool_payload={
                "action": "mail_search",
                "query_summaries": [
                    {"query": "M365 프로젝트 진행", "lines": ["일정 압박 리스크가 확인되었습니다."]},
                    {"query": "기술적 이슈", "lines": ["API 호출 오류가 발생했습니다."]},
                ],
                "results": [
                    {
                        "message_id": "m-1",
                        "subject": "테스트",
                        "summary_text": "일정 압박 리스크가 확인되었습니다.",
                        "web_link": "https://outlook.live.com/owa/?ItemID=m-1",
                        "sender_names": "izocuna",
                        "received_date": "2026-02-26",
                    }
                ],
            },
            section_contract={
                "template_id": "mail_search_summary",
                "sections": [
                    {"id": "major"},
                    {"id": "evidence"},
                ],
            },
        )
        self.assertIn("## 📌 주요 내용", rendered)
        self.assertNotIn("### 🛠 기술 이슈", rendered)
        self.assertIn("### 📬 근거 메일", rendered)

    def test_render_mail_search_deterministic_response_respects_section_contract_without_evidence(self) -> None:
        """
        section_contract에 evidence 섹션이 없으면 근거 메일 섹션을 렌더링하지 않아야 한다.
        """
        rendered = render_mail_search_deterministic_response(
            user_message="M365 관련 메일에서 기술적 이슈를 검색해서 요약 정리해줘",
            tool_payload={
                "action": "mail_search",
                "query_summaries": [
                    {"query": "M365 프로젝트 진행", "lines": ["일정 압박 리스크가 확인되었습니다."]},
                    {"query": "기술적 이슈", "lines": ["API 호출 오류가 발생했습니다."]},
                ],
                "results": [
                    {
                        "message_id": "m-1",
                        "subject": "테스트",
                        "summary_text": "API 호출 오류가 발생했습니다.",
                        "web_link": "https://outlook.live.com/owa/?ItemID=m-1",
                        "sender_names": "izocuna",
                        "received_date": "2026-02-26",
                    }
                ],
            },
            section_contract={
                "template_id": "mail_search_tech_issue",
                "sections": [
                    {"id": "major"},
                    {"id": "tech_issue"},
                ],
            },
        )
        self.assertIn("### 🛠 기술 이슈", rendered)
        self.assertNotIn("### 📬 근거 메일", rendered)


if __name__ == "__main__":
    unittest.main()
