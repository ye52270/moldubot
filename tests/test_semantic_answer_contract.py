from __future__ import annotations

import unittest

from app.models.response_contracts import LLMResponseContract
from app.services.semantic_answer_contract import build_semantic_answer_contract


class SemanticAnswerContractTest(unittest.TestCase):
    """공통 의미 계약(claim/evidence/action/confidence) 생성을 검증한다."""

    def test_builds_semantic_contract_from_llm_contract(self) -> None:
        """계약 필드에서 claim/action/evidence가 정상 추출되어야 한다."""
        contract = LLMResponseContract(
            format_type="general",
            core_issue="DB 인증서 체인 누락으로 연결 실패",
            summary_lines=["서비스 장애 가능성 증가"],
            required_actions=["인증서 체인 설치 여부 점검"],
            action_items=["DB 로그 오류코드 수집"],
        )
        result = build_semantic_answer_contract(
            contract=contract,
            answer="",
            intent_confidence=0.8,
            evidence_mails=[{"subject": "FW: IM DB 연결 오류", "sender_names": "izocuna", "web_link": "https://x"}],
            web_sources=[{"title": "AWS DB 연결 문제 해결", "site_name": "docs.aws.amazon.com", "url": "https://docs.aws.amazon.com"}],
        )
        self.assertIn("DB 인증서 체인 누락으로 연결 실패", result["claims"])
        self.assertIn("인증서 체인 설치 여부 점검", result["actions"])
        self.assertEqual("mail", result["evidence"][0]["type"])
        self.assertEqual("web", result["evidence"][1]["type"])
        self.assertGreaterEqual(float(result["confidence"]), 0.8)


if __name__ == "__main__":
    unittest.main()
