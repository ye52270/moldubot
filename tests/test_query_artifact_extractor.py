from __future__ import annotations

import unittest

from app.services.query_artifact_extractor import (
    extract_direct_fact_candidates,
    extract_query_artifact_candidates,
    looks_like_query_artifact_line,
    rank_query_artifact_candidates,
)


class QueryArtifactExtractorTest(unittest.TestCase):
    """query artifact extractor의 기본 추출/판별/정렬 동작을 검증한다."""

    def test_extract_query_artifact_candidates_collects_structured_lines(self) -> None:
        """mail_context에서 구조화된 query/command 라인을 추출해야 한다."""
        candidates = extract_query_artifact_candidates(
            mail_context={
                "body_code_excerpt": 'ldapsearch -x -b "OU=SKB,DC=example,DC=com" "(cn=SKB.ZN997)"',
                "body_excerpt": "SELECT id, name FROM users WHERE enabled = 1",
                "body_preview": "안녕하세요. 요청사항 전달드립니다.",
            }
        )
        self.assertGreaterEqual(len(candidates), 2)
        self.assertIn('ldapsearch -x -b "OU=SKB,DC=example,DC=com" "(cn=SKB.ZN997)"', candidates)
        self.assertIn("SELECT id, name FROM users WHERE enabled = 1", candidates)

    def test_looks_like_query_artifact_line_rejects_plain_sentence(self) -> None:
        """일반 문장 라인은 artifact 패턴으로 판별되면 안 된다."""
        self.assertFalse(looks_like_query_artifact_line("오늘 회의 일정 공유드립니다."))

    def test_rank_query_artifact_candidates_prioritizes_overlap(self) -> None:
        """사용자 질의 토큰과 겹치는 artifact를 우선 정렬해야 한다."""
        ranked = rank_query_artifact_candidates(
            user_message="현재메일 users 조회 쿼리문을 분석해줘",
            candidates=[
                "일반 상태 안내 문장",
                "SELECT id FROM users WHERE enabled = 1",
            ],
        )
        self.assertEqual("SELECT id FROM users WHERE enabled = 1", ranked[0])

    def test_extract_direct_fact_candidates_email_address_only(self) -> None:
        """email_address target은 설명 문장 없이 이메일 값만 추출해야 한다."""
        candidates = extract_direct_fact_candidates(
            target_type="email_address",
            mail_context={
                "body_excerpt": (
                    "Gmail이 보안상의 이유로 차단했습니다.\n"
                    "From: 공재환 <jhkong72@skbroadband.com>\n"
                    "To: 박제영 <izocuna@SKCC.COM>"
                )
            },
        )
        self.assertEqual(["jhkong72@skbroadband.com", "izocuna@skcc.com"], candidates)


if __name__ == "__main__":
    unittest.main()
