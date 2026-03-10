from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.services.chat_eval_case_loader import load_chat_eval_cases, parse_markdown_chat_eval_cases


class ChatEvalCaseLoaderTest(unittest.TestCase):
    """chat-eval 외부 케이스 파일 로더를 검증한다."""

    def test_parse_markdown_chat_eval_cases_extracts_questions(self) -> None:
        """markdown Q/기대결과 블록을 case 목록으로 변환해야 한다."""
        markdown = """
## Q1. 현재 메일에서 이슈를 요약해줘
**기대 결과:**
- 원인 요약
- 영향 요약

## Q2. 전체 메일에서 M365 관련 건 찾아줘
**기대 결과:**
- 조회 결과 제시
""".strip()
        cases = parse_markdown_chat_eval_cases(markdown_text=markdown, file_stem="testprompt")
        self.assertEqual(2, len(cases))
        self.assertEqual("testprompt-q1", cases[0]["case_id"])
        self.assertTrue(cases[0]["requires_current_mail"])
        self.assertIn("원인 요약", cases[0]["expectation"])
        self.assertFalse(cases[1]["requires_current_mail"])

    def test_load_chat_eval_cases_reads_markdown_file(self) -> None:
        """외부 markdown 파일 경로를 지정하면 해당 케이스를 로드해야 한다."""
        markdown = """
## Q1. 현재메일 요약
**기대 결과:**
- 현재메일 기준 요약
""".strip()
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "cases.md"
            path.write_text(markdown, encoding="utf-8")
            cases = load_chat_eval_cases(cases_file=str(path))
        self.assertEqual(1, len(cases))
        self.assertEqual("cases-q1", cases[0]["case_id"])

    def test_parse_markdown_marks_deictic_email_query_as_current_mail(self) -> None:
        """`이 메일/이 견적/이 프로젝트` 질의는 현재메일 케이스로 분류해야 한다."""
        markdown = """
## Q1. 이 메일에서 누락 항목 찾아줘
**기대 결과:**
- 누락 항목 정리

## Q2. 이 견적에서 비용 리스크를 정리해줘
**기대 결과:**
- 비용 리스크

## Q3. 이 프로젝트 보안 이슈를 정리해줘
**기대 결과:**
- 보안 이슈
""".strip()
        cases = parse_markdown_chat_eval_cases(markdown_text=markdown, file_stem="deictic")
        self.assertEqual(3, len(cases))
        self.assertTrue(cases[0]["requires_current_mail"])
        self.assertTrue(cases[1]["requires_current_mail"])
        self.assertTrue(cases[2]["requires_current_mail"])

    def test_parse_markdown_prefers_global_when_query_mentions_full_mailbox(self) -> None:
        """전체 메일함 지시가 있으면 현재메일 힌트가 섞여도 global로 분류해야 한다."""
        markdown = """
## Q1. 이 메일 말고 전체 메일함에서 관련 건 찾아줘
**기대 결과:**
- 전체 검색 결과
""".strip()
        cases = parse_markdown_chat_eval_cases(markdown_text=markdown, file_stem="scope")
        self.assertEqual(1, len(cases))
        self.assertFalse(cases[0]["requires_current_mail"])


if __name__ == "__main__":
    unittest.main()
