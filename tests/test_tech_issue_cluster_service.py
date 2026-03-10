from __future__ import annotations

import unittest

from app.services.tech_issue_cluster_service import build_tech_issue_clusters


class TechIssueClusterServiceTest(unittest.TestCase):
    """
    기술 이슈 클러스터 생성 서비스 동작을 검증한다.
    """

    def test_build_tech_issue_clusters_extracts_keywords_and_related_mails(self) -> None:
        """
        기술 이슈 라인에서 키워드/유형/관련 메일이 구성되어야 한다.
        """
        payload = {
            "query_summaries": [
                {
                    "query": "기술적 이슈",
                    "lines": ["결재 상태정보변경 API 호출이 되지 않아 확인 요청."],
                }
            ],
            "results": [
                {
                    "message_id": "m-1",
                    "subject": "EAI API 호출 오류",
                    "received_date": "2026-02-25T00:00:00Z",
                    "sender_names": "박제영",
                    "web_link": "https://example.com/m-1",
                    "summary_text": "결재 상태정보변경 API 호출이 되지 않아 확인 요청.",
                }
            ],
        }
        clusters = build_tech_issue_clusters(tool_payload=payload, evidence_mails=[])
        self.assertEqual(1, len(clusters))
        first = clusters[0]
        self.assertIn("API", first["keywords"])
        self.assertEqual("연동/API 이슈", first["issue_type"])
        self.assertEqual("m-1", first["related_mails"][0]["message_id"])


if __name__ == "__main__":
    unittest.main()
