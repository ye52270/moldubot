from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services.chat_eval_service_utils import (
    build_default_judge_caller,
    build_judge_context,
    extract_evidence_top_k,
    rule_based_retrieval_grounding_guard,
)


class ChatEvalServiceUtilsTest(unittest.TestCase):
    """Judge LLM 파서 강건화 유틸을 검증한다."""

    def test_judge_parses_markdown_fenced_json(self) -> None:
        """```json 코드블록 응답도 정상 파싱해야 한다."""
        judge = build_default_judge_caller(judge_model="gpt-5-mini")
        fenced = """```json
{"pass": true, "score": 5, "reason": "ok", "checks": {"intent_match": true, "format_match": true, "grounded": true}}
```"""
        with patch("app.services.chat_eval_service_utils.invoke_text_messages", return_value=fenced):
            parsed, _elapsed = judge("q", "a", "e", "s", {})
        self.assertTrue(parsed["pass"])
        self.assertEqual(5, parsed["score"])

    def test_judge_retries_once_when_first_response_invalid(self) -> None:
        """첫 응답이 비JSON이면 1회 재시도 후 성공해야 한다."""
        judge = build_default_judge_caller(judge_model="gpt-5-mini")
        responses = [
            "",
            '{"pass": false, "score": 3, "reason": "partial", "checks": {"intent_match": true, "format_match": false, "grounded": true}}',
        ]
        with patch("app.services.chat_eval_service_utils.invoke_text_messages", side_effect=responses):
            parsed, _elapsed = judge("q", "a", "e", "s", {})
        self.assertFalse(parsed["pass"])
        self.assertEqual(3, parsed["score"])

    def test_judge_returns_failure_when_all_attempts_invalid(self) -> None:
        """재시도 포함 모두 실패하면 judge_llm_error를 반환해야 한다."""
        judge = build_default_judge_caller(judge_model="gpt-5-mini")
        with patch("app.services.chat_eval_service_utils.invoke_text_messages", return_value="not-json"):
            parsed, _elapsed = judge("q", "a", "e", "s", {})
        self.assertFalse(parsed["pass"])
        self.assertIn("judge_llm_error", parsed["reason"])

    def test_extract_evidence_top_k_uses_fallback_snippet_fields(self) -> None:
        """snippet이 비어 있으면 summary/body 필드 순서로 fallback해야 한다."""
        metadata = {
            "evidence_mails": [
                {
                    "subject": "첫 번째",
                    "snippet": "",
                    "summary_text": "요약 텍스트",
                    "received_date": "2026-03-01",
                },
                {
                    "subject": "두 번째",
                    "snippet": "",
                    "summary_text": "",
                    "body_excerpt": "본문 발췌",
                    "received_date": "2026-03-02",
                },
                {
                    "subject": "세 번째",
                    "snippet": "",
                    "summary_text": "",
                    "body_excerpt": "",
                    "body_preview": "본문 프리뷰",
                    "received_date": "2026-03-03",
                },
            ]
        }
        extracted = extract_evidence_top_k(metadata=metadata, top_k=3)
        self.assertEqual("요약 텍스트", extracted[0]["snippet"])
        self.assertEqual("본문 발췌", extracted[1]["snippet"])
        self.assertEqual("본문 프리뷰", extracted[2]["snippet"])

    def test_extract_evidence_top_k_uses_subject_when_all_snippets_empty(self) -> None:
        """모든 snippet fallback이 비어 있으면 subject를 snippet으로 사용해야 한다."""
        metadata = {
            "evidence_mails": [
                {
                    "subject": "FW: M365 + AD 환경 구축 문의",
                    "snippet": "",
                    "summary_text": "",
                    "body_excerpt": "",
                    "body_preview": "",
                    "received_date": "2026-03-01",
                }
            ]
        }
        extracted = extract_evidence_top_k(metadata=metadata, top_k=1)
        self.assertEqual("FW: M365 + AD 환경 구축 문의", extracted[0]["snippet"])

    def test_build_judge_context_includes_scope_fields(self) -> None:
        """judge_context는 query_type/resolved_scope/current_mail 플래그를 포함해야 한다."""
        context = build_judge_context(
            metadata={
                "query_type": "current_mail",
                "resolved_scope": "current_mail",
                "used_current_mail_context": True,
                "search_result_count": 1,
                "evidence_mails": [{"subject": "s", "snippet": "x", "received_date": "2026-03-08"}],
            }
        )
        self.assertEqual("current_mail", context["query_type"])
        self.assertEqual("current_mail", context["resolved_scope"])
        self.assertTrue(context["used_current_mail_context"])

    def test_retrieval_grounding_guard_skips_current_mail_scope(self) -> None:
        """current_mail 스코프는 retrieval hard-fail 선판정을 적용하지 않아야 한다."""
        result = rule_based_retrieval_grounding_guard(
            query="이 메일에서 ESG 프로젝트의 현재 진행 상황은?",
            answer="관련 내용이 없습니다.",
            judge_context={
                "query_type": "current_mail",
                "resolved_scope": "current_mail",
                "used_current_mail_context": True,
                "search_result_count": 1,
                "evidence_top_k": [
                    {
                        "subject": "FW: M365 + AD 환경 구축 문의",
                        "snippet": "총 193,000,000원, 라이선스 확인 필요",
                        "received_date": "2026-02-19T05:30:44Z",
                    }
                ],
            },
        )
        self.assertIsNone(result)

    def test_retrieval_grounding_guard_still_blocks_non_current_mail_mismatch(self) -> None:
        """global retrieval에서 근거 불일치 답변은 hard-fail 처리해야 한다."""
        result = rule_based_retrieval_grounding_guard(
            query="최근 메일에서 비용 이슈를 조회해줘",
            answer="사내 복지포인트 지급일과 휴가 규정 변경 공지입니다.",
            judge_context={
                "query_type": "general",
                "resolved_scope": "global_search",
                "used_current_mail_context": False,
                "search_result_count": 1,
                "evidence_top_k": [
                    {
                        "subject": "FW: M365 + AD 환경 구축 문의",
                        "snippet": "총 193,000,000원, 라이선스 확인 필요",
                        "received_date": "2026-02-19T05:30:44Z",
                    }
                ],
            },
        )
        self.assertIsInstance(result, dict)
        self.assertFalse(bool(result.get("pass")))


if __name__ == "__main__":
    unittest.main()
