from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.services.mail_search_service import MailSearchService


class MailSearchServiceTest(unittest.TestCase):
    """
    하이브리드 메일 검색 서비스 동작을 검증한다.
    """

    def _create_db(self, root: Path) -> Path:
        """
        테스트용 메일 DB를 생성한다.

        Args:
            root: 임시 디렉터리 경로

        Returns:
            생성된 DB 파일 경로
        """
        db_path = root / "emails.db"
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "CREATE TABLE emails ("
                "message_id TEXT, "
                "subject TEXT, "
                "from_address TEXT, "
                "received_date TEXT, "
                "body_preview TEXT, "
                "body_full TEXT, "
                "body_clean TEXT, "
                "summary TEXT, "
                "web_link TEXT)"
            )
            conn.executemany(
                "INSERT INTO emails VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        "m-1",
                        "KISTI 보안장비 차단 확인 요청",
                        "박제영(PARK Jaeyoung)/AX Solution서비스5팀/SK <izocuna@sk.com>",
                        "2026-02-18T01:00:00Z",
                        "",
                        "",
                        "KISTI 수신 내역 부재. 차단 여부 확인 요청.",
                        "요약1",
                        "https://outlook.office.com/mail/m-1",
                    ),
                    (
                        "m-2",
                        "메일 사서함 자동 비우기 설정 문의",
                        "박정호/AT Infra팀/SKB <eva1397@sk.com>",
                        "2026-02-19T01:00:00Z",
                        "",
                        "",
                        "사서함 가득 참으로 수신/발송 불가. 자동 비우기 정책 문의.",
                        "요약2",
                        "https://outlook.office.com/mail/m-2",
                    ),
                    (
                        "m-3",
                        "FW: 센스메일 통합-APT 설정 관련 메일 드립니다",
                        "박제영(PARK Jaeyoung)/AX Solution서비스5팀/SK <izocuna@sk.com>",
                        "2026-02-20T01:00:00Z",
                        "",
                        "",
                        "설정 관련 일반 안내 메일입니다. 액션 항목 없음.",
                        "요약3",
                        "https://outlook.office.com/mail/m-3",
                    ),
                    (
                        "m-4",
                        "FW: M365 + AD 환경 구축 문의",
                        "홍길동/Infra팀/SK <hong@example.com>",
                        "2026-02-21T01:00:00Z",
                        "",
                        "",
                        "M365 구축 일정 관련 협의 요청 메일입니다.",
                        "요약4",
                        "https://outlook.office.com/mail/m-4",
                    ),
                ],
            )
            conn.commit()
        finally:
            conn.close()
        return db_path

    def test_search_returns_ranked_results(self) -> None:
        """
        질의어 기반 검색 결과가 반환되어야 한다.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = self._create_db(root=Path(tmp_dir))
            service = MailSearchService(db_path=db_path)
            payload = service.search(query="보안장비 차단 메일", limit=3)
        self.assertEqual("mail_search", payload["action"])
        self.assertEqual("completed", payload["status"])
        self.assertIn("aggregated_summary", payload)
        self.assertIn("metrics", payload)
        results = payload["results"]
        self.assertTrue(isinstance(results, list) and len(results) >= 1)
        self.assertEqual("m-1", results[0]["message_id"])
        self.assertEqual("박제영", results[0]["sender_names"])
        self.assertIn("summary_text", results[0])
        self.assertEqual("요약1", results[0]["summary_text"])
        self.assertTrue(isinstance(payload["aggregated_summary"], list) and len(payload["aggregated_summary"]) >= 1)

    def test_search_applies_person_filter(self) -> None:
        """
        person 필터가 적용되어야 한다.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = self._create_db(root=Path(tmp_dir))
            service = MailSearchService(db_path=db_path)
            payload = service.search(query="설정 문의", person="박정호", limit=5)
        results = payload["results"]
        self.assertEqual(1, len(results))
        self.assertEqual("m-2", results[0]["message_id"])
        self.assertTrue(isinstance(payload["aggregated_summary"], list))

    def test_search_filters_irrelevant_rows_by_meaningful_tokens(self) -> None:
        """
        공통 토큰(메일/요청)만 맞는 무관 메일은 핵심 키워드 필터로 제외되어야 한다.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = self._create_db(root=Path(tmp_dir))
            service = MailSearchService(db_path=db_path)
            payload = service.search(
                query="IT Application 위탁운영 1월분 계산서 발행 요청 메일에서 액션 아이템만 뽑아줘",
                limit=3,
            )
        results = payload["results"]
        message_ids = [str(item["message_id"]) for item in results]
        self.assertNotIn("m-3", message_ids)

    def test_search_enforces_strict_body_phrase_filter(self) -> None:
        """
        `본문에 'X' 포함` 질의는 본문에 해당 구문이 없는 메일을 제외해야 한다.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = self._create_db(root=Path(tmp_dir))
            service = MailSearchService(db_path=db_path)
            payload = service.search(
                query="본문에 '자동 비우기'가 포함된 메일 찾아줘",
                limit=5,
            )
        results = payload["results"]
        self.assertEqual(1, len(results))
        self.assertEqual("m-2", results[0]["message_id"])

    def test_search_strict_body_phrase_returns_zero_without_fallback(self) -> None:
        """
        strict 본문 구문 매칭 결과가 없으면 fallback 없이 0건을 반환해야 한다.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = self._create_db(root=Path(tmp_dir))
            service = MailSearchService(db_path=db_path)
            payload = service.search(
                query="본문에 '[존재하지않는테스트메일] 2099년 PoC 검증용 가상 문구'가 포함된 메일 찾아줘",
                limit=5,
            )
        self.assertEqual(0, payload["count"])
        self.assertEqual([], payload["results"])

    def test_search_high_specific_query_returns_zero_when_no_keyword_hits(self) -> None:
        """
        핵심 키워드가 많은 고특이도 질의는 저연관 fallback을 사용하지 않아야 한다.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = self._create_db(root=Path(tmp_dir))
            service = MailSearchService(db_path=db_path)
            payload = service.search(
                query="IT Application 위탁운영 1월분 계산서 발행 액션 아이템 도메인별 사용자 수 확인",
                limit=5,
            )
        self.assertEqual(0, payload["count"])
        self.assertEqual([], payload["results"])

    def test_search_high_specific_query_rejects_low_hit_top_result(self) -> None:
        """
        고특이도 질의에서 상위 결과의 키워드 일치가 낮으면 하드게이트로 0건 처리해야 한다.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = self._create_db(root=Path(tmp_dir))
            service = MailSearchService(db_path=db_path)
            payload = service.search(
                query="설정 드립니다 IT Application 계산서 발행 액션 아이템",
                limit=5,
            )
        self.assertEqual(0, payload["count"])
        self.assertEqual([], payload["results"])

    def test_search_high_specific_query_keeps_identifier_anchor_result(self) -> None:
        """
        고특이도 질의라도 식별자 토큰(M365 등)이 상위 메일과 일치하면 과차단하지 않아야 한다.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = self._create_db(root=Path(tmp_dir))
            service = MailSearchService(db_path=db_path)
            payload = service.search(
                query="M365 구축 일정, 협의나 회의에 관한 최근 메일 찾아줘",
                limit=5,
            )
        self.assertGreaterEqual(payload["count"], 1)
        self.assertEqual("m-4", payload["results"][0]["message_id"])

    def test_candidate_limit_is_reduced_for_person_and_date_scoped_query(self) -> None:
        """
        인물+기간 스코프 질의는 후보 상한을 낮춰 불필요한 재랭크 비용을 줄여야 한다.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = self._create_db(root=Path(tmp_dir))
            service = MailSearchService(db_path=db_path)
            scoped_limit = service._resolve_candidate_limit(
                target_limit=5,
                person="박준용",
                start_date="2026-02-01",
                end_date="2026-02-28",
                query="박준용 관련 2월 메일 요약",
            )
            default_limit = service._resolve_candidate_limit(
                target_limit=5,
                person="",
                start_date="",
                end_date="",
                query="M365 프로젝트 일정관련 최근 2주 메일 찾아줘",
            )
        self.assertLess(scoped_limit, default_limit)
        self.assertEqual(15, scoped_limit)

    def test_build_candidate_query_uses_meaningful_tokens_first(self) -> None:
        """
        SQL 후보 조회 토큰은 공통 단어보다 의미 토큰을 우선 사용해야 한다.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = self._create_db(root=Path(tmp_dir))
            service = MailSearchService(db_path=db_path)
            tokens = service._build_candidate_query_tokens("박준용 관련 2월 메일 요약")
        self.assertEqual(["박준용", "2월"], tokens)


if __name__ == "__main__":
    unittest.main()
