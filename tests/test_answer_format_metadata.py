from __future__ import annotations

import unittest
from unittest.mock import patch

import app.api.answer_format_metadata as answer_format_metadata
from app.api.answer_format_metadata import build_answer_format_metadata


class AnswerFormatMetadataTest(unittest.TestCase):
    """응답 포맷 메타데이터 생성 규칙을 검증한다."""

    def test_build_answer_format_metadata_for_summary(self) -> None:
        """요약 질의는 summary format_type과 블록 목록을 반환해야 한다."""
        metadata = build_answer_format_metadata(
            user_message="메일 요약해줘",
            answer="## 이메일 요약\n\n1. 핵심 내용\n2. 조치 필요",
            status="completed",
        )

        self.assertEqual("v1", metadata["version"])
        self.assertEqual("summary", metadata["format_type"])
        self.assertTrue(isinstance(metadata["blocks"], list))
        self.assertTrue(len(metadata["blocks"]) >= 2)
        self.assertEqual("heading", metadata["blocks"][0]["type"])

    def test_build_answer_format_metadata_for_clarification(self) -> None:
        """범위 확인 상태는 clarification_card 타입이어야 한다."""
        metadata = build_answer_format_metadata(
            user_message="이슈 알려줘",
            answer="질문의 범위를 선택해 주세요.",
            status="needs_clarification",
        )

        self.assertEqual("clarification_card", metadata["format_type"])

    def test_build_answer_format_metadata_extracts_table_and_quote_blocks(self) -> None:
        """표/인용문 markdown은 table/quote 블록으로 추출되어야 한다."""
        metadata = build_answer_format_metadata(
            user_message="현재메일 요약해줘",
            answer=(
                "## 기본 정보\n\n"
                "| 항목 | 내용 |\n"
                "|---|---|\n"
                "| 발신자 | 홍길동 |\n\n"
                "> 이 메일은 긴급 확인이 필요합니다."
            ),
            status="completed",
        )

        block_types = [block.get("type") for block in metadata["blocks"]]
        self.assertIn("table", block_types)
        self.assertIn("quote", block_types)

    def test_build_answer_format_metadata_recovers_collapsed_divider_and_heading(self) -> None:
        """줄바꿈이 망가진 `---###` 패턴에서도 heading/divider 블록을 복원해야 한다."""
        metadata = build_answer_format_metadata(
            user_message="현재메일 요약해줘",
            answer="## 이메일 요약\n### 제목: 테스트---### 📋 기본 정보\n| 항목 | 내용 |\n|---|---|\n| 발신자 | 홍길동 |",
            status="completed",
        )
        blocks = metadata["blocks"]
        block_types = [block.get("type") for block in blocks]
        self.assertIn("heading", block_types)
        self.assertIn("table", block_types)

    def test_build_answer_format_metadata_preserves_table_rows_without_fake_delimiter_header(self) -> None:
        """표 구분선이 헤더로 오인되지 않고 key/value row가 유지되어야 한다."""
        metadata = build_answer_format_metadata(
            user_message="현재메일 요약",
            answer=(
                "### 📋 기본 정보\n\n"
                "| 항목 | 내용 |\n"
                "|------|------|\n"
                "| **최종 발신자** | izocuna@sk.com |\n"
                "| **수신자** | user@outlook.com |"
            ),
            status="completed",
        )
        table_blocks = [block for block in metadata["blocks"] if block.get("type") == "table"]
        self.assertEqual(1, len(table_blocks))
        table_block = table_blocks[0]
        self.assertEqual(["항목", "내용"], table_block.get("headers"))
        rows = table_block.get("rows") or []
        self.assertGreaterEqual(len(rows), 2)
        self.assertEqual("izocuna@sk.com", rows[0][1])

    def test_build_answer_format_metadata_keeps_action_list_when_truncated(self) -> None:
        """블록 상한으로 잘려도 `조치 필요 사항` 헤딩 뒤 목록 1개는 유지되어야 한다."""
        answer = (
            "### 📌 주요 내용\n"
            "1. 항목 A\n"
            "- 상세 A\n"
            "2. 항목 B\n"
            "- 상세 B\n"
            "3. 항목 C\n"
            "- 상세 C\n"
            "### ✅ 조치 필요 사항\n"
            "1. 쿼리 가이드 요청 / 담당:정진식 / 기한:미상\n"
        )
        with patch.object(answer_format_metadata, "MAX_BLOCKS", 8):
            metadata = build_answer_format_metadata(
                user_message="현재메일 요약해줘",
                answer=answer,
                status="completed",
            )
        blocks = metadata["blocks"]
        action_heading_index = -1
        for index, block in enumerate(blocks):
            if block.get("type") != "heading":
                continue
            heading_text = str(block.get("text") or "")
            if "조치 필요 사항" in heading_text:
                action_heading_index = index
                break
        self.assertGreaterEqual(action_heading_index, 0)
        self.assertGreater(len(blocks), action_heading_index + 1)
        self.assertEqual("ordered_list", blocks[action_heading_index + 1].get("type"))


if __name__ == "__main__":
    unittest.main()
