from __future__ import annotations

import unittest

from app.api.search_chat_metadata import (
    build_context_enrichment,
    build_major_point_evidence,
    extract_aggregated_summary_from_tool_payload,
    extract_evidence_from_tool_payload,
    extract_tool_action,
    read_agent_final_answer,
    read_agent_raw_model_content,
    read_agent_raw_model_output,
)


class SearchChatMetadataTest(unittest.TestCase):
    """search_chat metadata 추출 계약을 검증한다."""

    def test_extract_evidence_from_mail_search_limits_to_top_five(self) -> None:
        """mail_search payload 근거메일은 최대 5건만 노출해야 한다."""
        payload = {
            "action": "mail_search",
            "results": [
                {
                    "message_id": "m-1",
                    "subject": "제목1",
                    "received_date": "2026-03-01",
                    "sender_names": "홍길동",
                    "web_link": "https://example.com/1",
                },
                {
                    "message_id": "m-2",
                    "subject": "제목2",
                    "received_date": "2026-03-02",
                    "sender_names": "김철수",
                    "web_link": "https://example.com/2",
                },
                {
                    "message_id": "m-3",
                    "subject": "제목3",
                    "received_date": "2026-03-03",
                    "sender_names": "이영희",
                    "web_link": "https://example.com/3",
                },
                {
                    "message_id": "m-4",
                    "subject": "제목4",
                    "received_date": "2026-03-04",
                    "sender_names": "박민수",
                    "web_link": "https://example.com/4",
                },
                {
                    "message_id": "m-5",
                    "subject": "제목5",
                    "received_date": "2026-03-05",
                    "sender_names": "최현우",
                    "web_link": "https://example.com/5",
                },
                {
                    "message_id": "m-6",
                    "subject": "제목6",
                    "received_date": "2026-03-06",
                    "sender_names": "장하늘",
                    "web_link": "https://example.com/6",
                },
            ],
        }

        evidence = extract_evidence_from_tool_payload(tool_payload=payload)

        self.assertEqual(5, len(evidence))
        self.assertEqual(["m-1", "m-2", "m-3", "m-4", "m-5"], [item["message_id"] for item in evidence])

    def test_extract_evidence_ignores_non_mail_search_payload(self) -> None:
        """mail_search가 아닌 payload는 근거메일로 해석하면 안 된다."""
        payload = {
            "action": "current_date",
            "today": "2026-03-01",
            "results": [{"message_id": "m-1"}],
        }

        evidence = extract_evidence_from_tool_payload(tool_payload=payload)

        self.assertEqual([], evidence)

    def test_extract_evidence_uses_snippet_fallback_fields(self) -> None:
        """snippet이 비어도 summary/body 필드 fallback으로 근거 스니펫을 채워야 한다."""
        payload = {
            "action": "mail_search",
            "results": [
                {
                    "message_id": "m-1",
                    "subject": "제목1",
                    "received_date": "2026-03-01",
                    "sender_names": "홍길동",
                    "web_link": "https://example.com/1",
                    "snippet": "",
                    "summary_text": "SK.com 구성 17,000,000원은 리버스 프록시 구성 작업입니다.",
                }
            ],
        }

        evidence = extract_evidence_from_tool_payload(tool_payload=payload)

        self.assertEqual(1, len(evidence))
        self.assertIn("리버스 프록시 구성 작업", evidence[0]["snippet"])

    def test_extract_aggregated_summary_normalizes_and_limits(self) -> None:
        """통합 요약은 공백 제거 후 최대 5줄까지만 유지해야 한다."""
        payload = {
            "action": "mail_search",
            "aggregated_summary": ["  첫줄  ", "", "둘째줄", None, "셋째줄", "넷째줄", "다섯째줄", "여섯째줄"],
        }

        lines = extract_aggregated_summary_from_tool_payload(tool_payload=payload)

        self.assertEqual(["첫줄", "둘째줄", "셋째줄", "넷째줄", "다섯째줄"], lines)

    def test_extract_tool_action_normalizes_case(self) -> None:
        """tool action은 소문자 정규화되어야 한다."""
        action = extract_tool_action(tool_payload={"action": "Mail_Search"})
        self.assertEqual("mail_search", action)

    def test_read_agent_final_answer_returns_trimmed_value(self) -> None:
        """agent가 제공한 최종 assistant 답변을 trim해 반환해야 한다."""
        class FakeAgent:
            def get_last_assistant_answer(self) -> str:
                return "  최종 답변  "

        self.assertEqual("최종 답변", read_agent_final_answer(agent=FakeAgent()))

    def test_read_agent_raw_model_output_returns_trimmed_value(self) -> None:
        """agent가 제공한 모델 직출력(raw)을 trim해 반환해야 한다."""
        class FakeAgent:
            def get_last_raw_model_output(self) -> str:
                return "  모델 직출력  "

        self.assertEqual("모델 직출력", read_agent_raw_model_output(agent=FakeAgent()))

    def test_read_agent_raw_model_output_returns_empty_when_getter_missing(self) -> None:
        """raw getter가 없으면 빈 문자열을 반환해야 한다."""
        class FakeAgent:
            pass

        self.assertEqual("", read_agent_raw_model_output(agent=FakeAgent()))

    def test_read_agent_raw_model_content_serializes_non_string(self) -> None:
        """raw model content가 객체면 JSON 문자열로 직렬화해야 한다."""
        class FakeAgent:
            def get_last_raw_model_content(self) -> dict[str, object]:
                return {"type": "text", "text": "원본"}

        serialized = read_agent_raw_model_content(agent=FakeAgent())
        self.assertIn('"type": "text"', serialized)

    def test_read_agent_raw_model_content_returns_empty_when_getter_missing(self) -> None:
        """content getter가 없으면 빈 문자열을 반환해야 한다."""
        class FakeAgent:
            pass

        self.assertEqual("", read_agent_raw_model_content(agent=FakeAgent()))

    def test_build_major_point_evidence_extracts_quote_and_location(self) -> None:
        """주요 내용 항목별로 메일 근거 문구와 단락 라벨을 생성해야 한다."""
        answer_format = {
            "blocks": [
                {"type": "heading", "text": "📌 주요 내용"},
                {
                    "type": "ordered_list",
                    "items": ["Chrome에서 특정 URL을 Edge로 리디렉션하는 정책 검토 필요"],
                },
            ]
        }
        tool_payload = {
            "mail_context": {
                "summary_text": "Chrome에서 특정 URL을 Edge로 리디렉션하는 정책 검토가 필요합니다.",
                "body_excerpt": "1) 정책 검토 요청\n2) 적용 대상 도메인 확인 필요",
            }
        }
        evidence_mails = [{"subject": "Tenant Restriction 검토", "message_id": "m-1"}]
        result = build_major_point_evidence(
            answer_format=answer_format,
            tool_payload=tool_payload,
            evidence_mails=evidence_mails,
        )

        self.assertEqual(1, len(result))
        self.assertIn("리디렉션", result[0]["mail_quote"])
        self.assertTrue(str(result[0]["mail_location"]).startswith("본문"))
        self.assertEqual([], result[0]["related_mails"])

    def test_build_major_point_evidence_initializes_related_mails_as_empty(self) -> None:
        """주요 내용 근거 기본값은 related_mails 빈 배열이어야 한다."""
        answer_format = {
            "blocks": [
                {"type": "heading", "text": "📌 주요 내용"},
                {"type": "ordered_list", "items": ["결재 라인 공유 및 회신 일정 확인"]},
            ]
        }
        result = build_major_point_evidence(
            answer_format=answer_format,
            tool_payload={},
            evidence_mails=[],
        )
        self.assertEqual(1, len(result))
        self.assertEqual([], result[0]["related_mails"])

    def test_build_context_enrichment_contains_alert_timeline_and_stakeholders(self) -> None:
        """컨텍스트 보강 메타데이터는 회신알림/타임라인/관계자를 포함해야 한다."""
        answer_format = {
            "blocks": [
                {"type": "heading", "text": "📌 주요 내용"},
                {"type": "ordered_list", "items": ["이상수가 Chrome 리디렉션 검토 요청"]},
            ]
        }
        tool_payload = {
            "mail_context": {
                "from_display_name": "박정호",
                "received_date": "2026-02-26T07:17:16Z",
                "summary_text": "@이상수 회신 부탁드립니다.",
                "body_excerpt": "To: 이상수; 김태호\nCc: 박제영",
            }
        }
        evidence_mails = [
            {
                "subject": "Tenant Restriction 방안",
                "sender_names": "박정호",
                "received_date": "2026-02-26T07:17:16Z",
            }
        ]
        next_actions = [
            {
                "title": "이상수님께 회신 초안 작성",
                "query": "회신 초안 작성해줘",
            }
        ]

        result = build_context_enrichment(
            answer="회신이 필요합니다.",
            answer_format=answer_format,
            tool_payload=tool_payload,
            evidence_mails=evidence_mails,
            next_actions=next_actions,
        )

        self.assertTrue(result["reply_alert"]["required"])
        self.assertGreaterEqual(len(result["thread_timeline"]), 1)
        self.assertGreaterEqual(len(result["stakeholders"]), 1)

    def test_build_context_enrichment_prefers_llm_stakeholders(self) -> None:
        """LLM recipient_roles가 있으면 관계자 카드는 해당 결과를 우선 반영해야 한다."""
        result = build_context_enrichment(
            answer="역할 분석 결과입니다.",
            answer_format={"blocks": []},
            tool_payload={},
            evidence_mails=[],
            next_actions=[],
            llm_recipient_roles=[
                {
                    "recipient": "이상수",
                    "role": "요청자",
                    "evidence": "@이상수 회신 요청",
                },
                {
                    "recipient": "김태호",
                    "role": "기술담당",
                    "evidence": "@김태호 도메인 검토",
                },
            ],
            llm_recipient_todos=[
                {
                    "recipient": "박정호",
                    "todo": "가이드 확인",
                    "due_date": "미정",
                    "due_date_basis": "메일 요청",
                }
            ],
        )

        stakeholders = result["stakeholders"]
        self.assertEqual(3, len(stakeholders))
        self.assertEqual("이상수", stakeholders[0]["name"])
        self.assertEqual("요청자", stakeholders[0]["role"])
        self.assertIn("회신", stakeholders[0]["evidence"])

    def test_build_context_enrichment_maps_domain_token_to_email_identity(self) -> None:
        """관계자 이름이 도메인 토큰으로 오염된 경우 본문 이메일로 복구해야 한다."""
        tool_payload = {
            "mail_context": {
                "summary_text": "To: 이상수(LEE Sangsoo)/AX Solution서비스4팀/SK <ssl@skcc.com>",
                "body_excerpt": "@이상수 회신 부탁드립니다.",
            }
        }
        result = build_context_enrichment(
            answer="역할 분석",
            answer_format={"blocks": []},
            tool_payload=tool_payload,
            evidence_mails=[],
            next_actions=[],
            llm_recipient_roles=[
                {
                    "recipient": "SK",
                    "role": "요청자",
                    "evidence": "To: 이상수(LEE Sangsoo)/AX Solution서비스4팀/SK <ssl@skcc.com>",
                }
            ],
            llm_recipient_todos=[],
        )
        stakeholders = result["stakeholders"]
        self.assertEqual(1, len(stakeholders))
        self.assertEqual("이상수", stakeholders[0]["name"])

    def test_build_context_enrichment_fallback_stakeholder_has_no_generic_evidence(self) -> None:
        """fallback 관계자 근거에는 고정 플레이스홀더 문구를 넣지 않아야 한다."""
        answer_format = {
            "blocks": [
                {"type": "heading", "text": "📌 주요 내용"},
                {"type": "ordered_list", "items": ["이상수 검토 요청"]},
            ]
        }
        tool_payload = {
            "mail_context": {
                "from_display_name": "박정호",
                "summary_text": "@이상수 회신 부탁드립니다.",
            }
        }
        result = build_context_enrichment(
            answer="확인 필요",
            answer_format=answer_format,
            tool_payload=tool_payload,
            evidence_mails=[],
            next_actions=[],
            llm_recipient_roles=None,
            llm_recipient_todos=None,
        )
        self.assertNotIn("메일 헤더/본문 단서", str(result["stakeholders"]))

    def test_build_context_enrichment_includes_tech_issue_clusters(self) -> None:
        """기술 이슈 query_summaries가 있으면 키워드/유형/관련 메일 클러스터를 포함해야 한다."""
        tool_payload = {
            "action": "mail_search",
            "query_summaries": [
                {
                    "query": "기술적 이슈",
                    "lines": [
                        "결재 상태정보변경 API 호출이 되지 않아 확인 요청.",
                        "다음 주 화요일에 시스템 긴급 이슈 관련 회원 가입 오류.",
                    ],
                }
            ],
            "results": [
                {
                    "message_id": "m-1",
                    "subject": "EAI 연동 API 호출 오류",
                    "received_date": "2026-02-25T01:00:00Z",
                    "sender_names": "박제영",
                    "web_link": "https://example.com/m-1",
                    "summary_text": "결재 상태정보변경 API 호출이 되지 않아 확인 요청.",
                },
                {
                    "message_id": "m-2",
                    "subject": "긴급 회원 가입 오류",
                    "received_date": "2026-02-26T01:00:00Z",
                    "sender_names": "박제영",
                    "web_link": "https://example.com/m-2",
                    "summary_text": "다음 주 화요일에 시스템 긴급 이슈 관련 회원 가입 오류.",
                },
            ],
        }
        result = build_context_enrichment(
            answer="기술 이슈 확인",
            answer_format={"blocks": []},
            tool_payload=tool_payload,
            evidence_mails=[],
            next_actions=[],
            llm_recipient_roles=None,
            llm_recipient_todos=None,
        )
        clusters = result.get("tech_issue_clusters")
        self.assertIsInstance(clusters, list)
        self.assertGreaterEqual(len(clusters), 1)
        first = clusters[0]
        self.assertIn("keywords", first)
        self.assertIn("issue_type", first)
        self.assertIn("related_mails", first)
        self.assertIn("API", str(first.get("keywords")))
        self.assertTrue(str(first.get("issue_type")))

if __name__ == "__main__":
    unittest.main()
