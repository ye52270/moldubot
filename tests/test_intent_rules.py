from __future__ import annotations

import unittest
from datetime import date, timedelta

from app.core.intent_rules import build_missing_slots, extract_date_filter_fields, infer_steps_from_query, is_code_review_query


class IntentRulesTest(unittest.TestCase):
    """규칙 기반 step 추론의 핵심 분기를 검증한다."""

    def test_checklist_query_infers_extract_key_facts(self) -> None:
        """체크리스트 요청은 핵심 추출 step을 포함해야 한다."""
        result = infer_steps_from_query("회의 준비 체크리스트 만들어줘")
        self.assertIn("extract_key_facts", result)

    def test_template_query_infers_extract_key_facts(self) -> None:
        """템플릿 요청은 핵심 추출 step을 포함해야 한다."""
        result = infer_steps_from_query("회의 결과 공유 메일 템플릿 만들어줘")
        self.assertIn("extract_key_facts", result)

    def test_plan_query_infers_extract_key_facts(self) -> None:
        """진행안 요청은 핵심 추출 step을 포함해야 한다."""
        result = infer_steps_from_query("팀 주간 스탠드업 진행안을 작성해줘")
        self.assertIn("extract_key_facts", result)

    def test_mail_search_query_does_not_add_read_current_mail(self) -> None:
        """조건 조회형 메일 질의는 search_mails만 포함하고 read_current_mail은 제외해야 한다."""
        result = infer_steps_from_query("M365 관련 최근메일 3개 조회후 요약해줘")
        self.assertIn("search_mails", result)
        self.assertNotIn("read_current_mail", result)

    def test_mail_search_query_with_meeting_word_does_not_add_meeting_schedule(self) -> None:
        """메일 조회 문맥의 `회의/일정` 단어는 회의일정 조회 step으로 오탐되면 안 된다."""
        result = infer_steps_from_query("M365 구축 일정, 협의나 회의에 관한 최근 메일 찾아줘")
        self.assertIn("search_mails", result)
        self.assertNotIn("search_meeting_schedule", result)

    def test_mail_from_phrase_query_is_treated_as_search(self) -> None:
        """`메일에서 ...` 질의는 검색형으로 분류되어야 한다."""
        result = infer_steps_from_query("IT Application 위탁운영 1월분 계산서 발행 요청 메일에서 액션 아이템만 뽑아줘")
        self.assertIn("search_mails", result)
        self.assertNotIn("read_current_mail", result)

    def test_body_contains_phrase_query_is_treated_as_search(self) -> None:
        """`본문에 ... 포함` 질의는 검색형으로 분류되어야 한다."""
        result = infer_steps_from_query("본문에 '박준용'이 포함된 메일을 찾아서 조치 필요 사항만 알려줘")
        self.assertIn("search_mails", result)
        self.assertNotIn("read_current_mail", result)

    def test_report_style_mail_query_is_treated_as_search(self) -> None:
        """`메일 ... 보고서 형식으로 정리` 질의는 검색형으로 분류되어야 한다."""
        result = infer_steps_from_query("보안 취약점 조치 요청 메일을 보고서 형식으로 정리해줘")
        self.assertIn("search_mails", result)
        self.assertNotIn("read_current_mail", result)

    def test_current_mail_query_stays_current_mail_even_with_jeongri_token(self) -> None:
        """`현재메일 ... 정리` 질의는 검색형으로 오분류되면 안 된다."""
        result = infer_steps_from_query("현재메일을 보고 보고서 형식으로 정리해줘")
        self.assertIn("read_current_mail", result)

    def test_deictic_mail_query_stays_current_mail_even_with_maileseo_phrase(self) -> None:
        """`이 메일에서 ...` 질의는 search_mails가 아니라 current_mail로 처리되어야 한다."""
        result = infer_steps_from_query("이 메일에서 누락된 항목이 무엇인지 알려줘")
        self.assertIn("read_current_mail", result)
        self.assertNotIn("search_mails", result)

    def test_current_mail_keywords_to_schedule_infers_key_facts_and_calendar_booking(self) -> None:
        """현재메일 키워드 추출 후 일정 등록 질의는 핵심추출+일정등록 step을 포함해야 한다."""
        result = infer_steps_from_query("현재메일 중 주요 키워드 2~3개 뽑아서 일정으로 등록")
        self.assertIn("read_current_mail", result)
        self.assertIn("extract_key_facts", result)
        self.assertIn("book_calendar_event", result)
        self.assertNotIn("book_meeting_room", result)

    def test_current_mail_summary_recipients_then_meeting_room_infers_recipients(self) -> None:
        """현재메일 수신자+요약+회의실 예약 질의는 수신자 추출 step을 포함해야 한다."""
        result = infer_steps_from_query("현재메일 주요 내용과 수신자정보 요약 후 회의실 예약")
        self.assertIn("read_current_mail", result)
        self.assertIn("summarize_mail", result)
        self.assertIn("extract_recipients", result)
        self.assertIn("book_meeting_room", result)

    def test_schedule_registration_query_infers_calendar_booking(self) -> None:
        """회의실 키워드 없는 일정 등록 질의는 calendar booking step으로 분기해야 한다."""
        result = infer_steps_from_query("일정 등록해줘")
        self.assertIn("book_calendar_event", result)
        self.assertNotIn("book_meeting_room", result)

    def test_current_mail_todo_registration_infers_key_facts(self) -> None:
        """현재메일 요약 후 할일 등록 질의는 핵심추출 step을 포함해야 한다."""
        result = infer_steps_from_query("현재메일 주요 내용을 2~3개 요약해서 할일 등록")
        self.assertIn("read_current_mail", result)
        self.assertIn("summarize_mail", result)
        self.assertIn("extract_key_facts", result)

    def test_month_only_mail_query_uses_current_year(self) -> None:
        """연도 없는 `N월` 메일 조회는 현재 연도 절대 범위로 해석해야 한다."""
        current_year = date.today().year
        mode, _, start, end = extract_date_filter_fields("1월달 조영득 관련 메일 조회해줘")
        self.assertEqual("absolute", mode)
        self.assertEqual(f"{current_year}-01-01", start)
        self.assertEqual(f"{current_year}-01-31", end)

    def test_month_only_mail_query_with_last_year(self) -> None:
        """`작년 N월` 메일 조회는 전년도 월 범위로 해석해야 한다."""
        expected_year = date.today().year - 1
        mode, _, start, end = extract_date_filter_fields("작년 1월 조영득 관련 메일 조회")
        self.assertEqual("absolute", mode)
        self.assertEqual(f"{expected_year}-01-01", start)
        self.assertEqual(f"{expected_year}-01-31", end)

    def test_billing_period_month_expression_keeps_date_filter_none(self) -> None:
        """`N월분`은 청구 기간 표현이므로 수신일 date_filter로 해석하면 안 된다."""
        mode, relative, start, end = extract_date_filter_fields(
            "IT Application 위탁운영 1월분 계산서 발행 요청 메일에서 액션 아이템만 뽑아줘"
        )
        self.assertEqual("none", mode)
        self.assertEqual("", relative)
        self.assertEqual("", start)
        self.assertEqual("", end)

    def test_recent_weeks_mail_query_uses_server_absolute_range(self) -> None:
        """`최근 N주 메일 조회`는 서버 오늘 기준 절대 날짜로 해석해야 한다."""
        today = date.today()
        expected_start = (today - timedelta(days=28)).strftime("%Y-%m-%d")
        expected_end = today.strftime("%Y-%m-%d")
        mode, relative, start, end = extract_date_filter_fields("M365 최근 4주 메일 조회해서 요약해줘")
        self.assertEqual("absolute", mode)
        self.assertEqual("", relative)
        self.assertEqual(expected_start, start)
        self.assertEqual(expected_end, end)

    def test_is_code_review_query_detects_code_review_phrases(self) -> None:
        """코드 리뷰 핵심 문구를 포함하면 코드리뷰 질의로 판별해야 한다."""
        self.assertTrue(is_code_review_query("현재메일 코드 리뷰해줘"))
        self.assertTrue(is_code_review_query("코드 스니펫 분석"))
        self.assertTrue(is_code_review_query("/코드분석"))
        self.assertFalse(is_code_review_query("현재메일 요약해줘"))

    def test_build_missing_slots_accepts_hhmm_and_attendee_count_keys(self) -> None:
        """HH:MM/attendee_count 키가 있으면 예약 슬롯 누락으로 오탐하면 안 된다."""
        message = (
            '{"task":"book_meeting_room","booking":{"date":"2026-03-09","start_time":"10:00",'
            '"end_time":"11:00","attendee_count":2,"building":"sku-tower","floor":17,"room_name":"1702-A"}}'
        )
        missing = build_missing_slots(steps=["book_meeting_room"], user_message=message)
        self.assertEqual([], missing)

    def test_build_missing_slots_accepts_korean_labeled_fields(self) -> None:
        """한글 라벨 기반 예약 문장도 date/start/end/attendee를 인식해야 한다."""
        message = "날짜: 2026.03.09. 시작: 오전 10:00 종료: 오전 11:00 참석 인원: 2"
        missing = build_missing_slots(steps=["book_meeting_room"], user_message=message)
        self.assertEqual([], missing)


if __name__ == "__main__":
    unittest.main()
