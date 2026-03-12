from __future__ import annotations

import unittest
from datetime import date

from app.middleware.search_tool_args import normalize_search_tool_args


class SearchToolArgsTest(unittest.TestCase):
    """검색 도구 인자 정규화 규칙을 검증한다."""

    def test_month_and_person_query_overrides_wrong_year_range(self) -> None:
        """`1월 조영득` 질의는 사용자 원문 기준 연/월 범위로 보정해야 한다."""
        current_year = date.today().year
        normalized = normalize_search_tool_args(
            tool_name="search_mails",
            tool_args={
                "query": "조영득",
                "person": "",
                "start_date": "2023-01-01",
                "end_date": "2023-01-31",
                "limit": 5,
            },
            user_message="1월 조영득 관련 메일 조회해줘",
        )
        self.assertEqual("조영득", normalized.get("person"))
        self.assertEqual(f"{current_year}-01-01", normalized.get("start_date"))
        self.assertEqual(f"{current_year}-01-31", normalized.get("end_date"))

    def test_explicit_year_month_query_applies_that_year(self) -> None:
        """명시 연도가 있는 월 질의는 해당 연도로 고정해야 한다."""
        normalized = normalize_search_tool_args(
            tool_name="search_mails",
            tool_args={"query": "조영득 관련", "limit": 5},
            user_message="2024년 1월 조영득 관련 메일 조회",
        )
        self.assertEqual("2024-01-01", normalized.get("start_date"))
        self.assertEqual("2024-01-31", normalized.get("end_date"))

    def test_non_search_tool_keeps_original_args(self) -> None:
        """검색 도구가 아니면 인자를 변경하지 않아야 한다."""
        original = {"title": "회의실 예약", "date": "2026-03-12"}
        normalized = normalize_search_tool_args(
            tool_name="book_meeting_room",
            tool_args=original,
            user_message="회의실 예약해줘",
        )
        self.assertEqual(original, normalized)

    def test_relative_last_week_is_converted_to_absolute_range(self) -> None:
        """`지난주` 질의는 검색 인자에서 절대 날짜 범위로 변환되어야 한다."""
        normalized = normalize_search_tool_args(
            tool_name="search_mails",
            tool_args={"query": "지난주 조영득 메일", "person": "", "start_date": "", "end_date": "", "limit": 5},
            user_message="지난주 조영득 관련 메일 조회",
        )
        self.assertRegex(str(normalized.get("start_date") or ""), r"^\d{4}-\d{2}-\d{2}$")
        self.assertRegex(str(normalized.get("end_date") or ""), r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual("조영득", normalized.get("person"))

    def test_query_without_date_clears_hallucinated_dates(self) -> None:
        """날짜 의도가 없는 질의는 임의 start/end_date를 제거해야 한다."""
        normalized = normalize_search_tool_args(
            tool_name="search_mails",
            tool_args={"query": "조영득 메일", "person": "", "start_date": "2023-01-01", "end_date": "2023-01-31", "limit": 5},
            user_message="조영득 메일 찾아줘",
        )
        self.assertEqual("", normalized.get("start_date"))
        self.assertEqual("", normalized.get("end_date"))

    def test_person_fallback_extracts_name_before_mail_keyword(self) -> None:
        """`홍길동 메일` 형태 질의도 person 슬롯으로 보정해야 한다."""
        normalized = normalize_search_tool_args(
            tool_name="search_mails",
            tool_args={"query": "홍길동 메일 찾아줘", "person": "", "limit": 5},
            user_message="홍길동 메일 찾아줘",
        )
        self.assertEqual("홍길동", normalized.get("person"))

    def test_person_slot_does_not_extract_non_person_keyword_with_particle(self) -> None:
        """`일정과 관련된 메일` 질의에서 `일정과`를 person 슬롯으로 오인하면 안 된다."""
        normalized = normalize_search_tool_args(
            tool_name="search_meeting_schedule",
            tool_args={"query": "M365 구축 프로젝트", "person": "", "limit": 5},
            user_message="M365 구축 프로젝트 구축 일정과 관련된 메일을 찾아줘",
        )
        self.assertEqual("", normalized.get("person"))


if __name__ == "__main__":
    unittest.main()
