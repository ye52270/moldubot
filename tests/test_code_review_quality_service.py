from __future__ import annotations

import json
import unittest
from unittest.mock import Mock, patch

from app.services.code_review_quality_service import refine_code_review_answer, refine_code_review_answer_with_metadata


class CodeReviewQualityServiceTest(unittest.TestCase):
    """
    코드리뷰 critic/revise 품질 보정 서비스 테스트.
    """

    @patch("app.services.code_review_quality_service.is_openai_key_configured", return_value=True)
    @patch("app.services.code_review_quality_service.invoke_json_object")
    def test_refine_code_review_answer_runs_critic_and_revise(
        self,
        mocked_invoke: Mock,
        _mocked_key: Mock,
    ) -> None:
        """
        코드리뷰 질의는 critic/revise를 거쳐 보정된 응답을 반환해야 한다.
        """
        critic_content = json.dumps(
            {
                "verdict": "needs_revision",
                "language": "JSP",
                "issues": [
                    {
                        "id": "L1",
                        "severity": "high",
                        "reason": "언어 표기가 Java로 잘못됨",
                        "suggested_fix": "JSP로 고정",
                    }
                ],
                "must_fix": ["언어를 JSP로 표기"],
            },
            ensure_ascii=False,
        )
        revise_content = json.dumps(
            {
                "answer_markdown": "## 코드 분석\n- 기능 요약: ...\n- 보안 리스크: ...\n\n## 코드 리뷰\n### 언어\n- JSP",
            },
            ensure_ascii=False,
        )

        mocked_invoke.side_effect = [json.loads(critic_content), json.loads(revise_content)]

        tool_payload = {
            "mail_context": {
                "body_code_excerpt": '<%@include file="../../taglibs.jsp" %>\n<input type="password" />'
            }
        }
        result = refine_code_review_answer(
            user_message="현재메일 코드 리뷰해줘",
            answer="## 코드 리뷰\n### 언어\n- Java",
            tool_payload=tool_payload,
        )
        self.assertIn("- JSP", result)
        self.assertEqual(2, mocked_invoke.call_count)

    @patch("app.services.code_review_quality_service.is_openai_key_configured", return_value=False)
    def test_refine_code_review_answer_returns_original_when_no_key(self, _mocked_key: Mock) -> None:
        """
        OpenAI 키가 없으면 원문 응답을 그대로 반환해야 한다.
        """
        original = "## 코드 리뷰\n- 원문"
        result = refine_code_review_answer(
            user_message="현재메일 코드 리뷰해줘",
            answer=original,
            tool_payload={},
        )
        self.assertEqual(original, result)

    @patch("app.services.code_review_quality_service.is_openai_key_configured", return_value=True)
    @patch("app.services.code_review_quality_service.invoke_json_object")
    def test_refine_code_review_answer_with_metadata_reports_revise_applied(
        self,
        mocked_invoke: Mock,
        _mocked_key: Mock,
    ) -> None:
        """
        critic/revise 경로가 실행되면 메타데이터에 적용 여부가 기록되어야 한다.
        """
        critic_content = json.dumps({"verdict": "needs_revision", "issues": []}, ensure_ascii=False)
        revise_content = json.dumps({"answer_markdown": "## 코드 리뷰\n### 언어\n- JSP"}, ensure_ascii=False)
        mocked_invoke.side_effect = [json.loads(critic_content), json.loads(revise_content)]

        refined, metadata = refine_code_review_answer_with_metadata(
            user_message="현재메일 코드 리뷰해줘",
            answer="## 코드 리뷰\n### 언어\n- Java",
            tool_payload={"mail_context": {"body_code_excerpt": '<%@include file="../../taglibs.jsp" %>'}},
        )
        self.assertIn("JSP", refined)
        self.assertTrue(metadata.get("enabled"))
        self.assertTrue(metadata.get("critic_used"))
        self.assertTrue(metadata.get("revise_applied"))


if __name__ == "__main__":
    unittest.main()
