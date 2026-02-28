from __future__ import annotations

from typing import NotRequired, TypedDict


class ExpectedDateFilter(TypedDict):
    """
    날짜 필터 기대값 타입.

    Attributes:
        mode: 기대 날짜 모드
        relative: 기대 상대 날짜 토큰
        start: 기대 시작일(YYYY-MM-DD)
        end: 기대 종료일(YYYY-MM-DD)
    """

    mode: str
    relative: NotRequired[str]
    start: NotRequired[str]
    end: NotRequired[str]


class IntentEdgeCase(TypedDict):
    """
    의도 분해 경계 케이스 테스트 항목 타입.

    Attributes:
        case_id: 케이스 식별자
        utterance: 사용자 발화
        pattern: 검증 포인트 설명
        expected_steps: 기대 실행 단계 목록
        expected_summary_line_target: 기대 요약 줄 수
        expected_date_filter: 기대 날짜 필터(부분 비교)
        expected_missing_slots: 기대 누락 슬롯 목록
    """

    case_id: int
    utterance: str
    pattern: str
    expected_steps: list[str]
    expected_summary_line_target: int
    expected_date_filter: ExpectedDateFilter
    expected_missing_slots: list[str]


INTENT_EDGE_CASES: list[IntentEdgeCase] = [
    {
        "case_id": 1,
        "utterance": "  \"ESG 메일 찾아줘\"  ",
        "pattern": "앞뒤 공백/따옴표 정제",
        "expected_steps": ["read_current_mail"],
        "expected_summary_line_target": 5,
        "expected_date_filter": {"mode": "none"},
        "expected_missing_slots": [],
    },
    {
        "case_id": 2,
        "utterance": "메일 0줄로 요약해",
        "pattern": "요약 줄수 하한 보정",
        "expected_steps": ["read_current_mail", "summarize_mail"],
        "expected_summary_line_target": 5,
        "expected_date_filter": {"mode": "none"},
        "expected_missing_slots": [],
    },
    {
        "case_id": 3,
        "utterance": "메일 30줄로 요약해",
        "pattern": "요약 줄수 상한 보정",
        "expected_steps": ["read_current_mail", "summarize_mail"],
        "expected_summary_line_target": 20,
        "expected_date_filter": {"mode": "none"},
        "expected_missing_slots": [],
    },
    {
        "case_id": 4,
        "utterance": "이번주 메일 보고서로 정리해줘",
        "pattern": "붙여쓰기 상대날짜 + 요약",
        "expected_steps": ["read_current_mail", "summarize_mail"],
        "expected_summary_line_target": 5,
        "expected_date_filter": {"mode": "relative", "relative": "this_week"},
        "expected_missing_slots": [],
    },
    {
        "case_id": 5,
        "utterance": "오늘 받은 메일 핵심만 뽑아줘",
        "pattern": "상대날짜 + 핵심 추출",
        "expected_steps": ["read_current_mail", "extract_key_facts"],
        "expected_summary_line_target": 5,
        "expected_date_filter": {"mode": "relative", "relative": "today"},
        "expected_missing_slots": [],
    },
    {
        "case_id": 6,
        "utterance": "내일 오전 9시 회의 잡아줘",
        "pattern": "예약 의도 + 시작시간만 있음",
        "expected_steps": ["book_meeting_room"],
        "expected_summary_line_target": 5,
        "expected_date_filter": {"mode": "relative", "relative": "tomorrow"},
        "expected_missing_slots": ["attendee_count", "end_time"],
    },
    {
        "case_id": 7,
        "utterance": "2026-03-01부터 2026-03-07까지 메일 찾아줘",
        "pattern": "ISO 절대 날짜 범위",
        "expected_steps": ["read_current_mail"],
        "expected_summary_line_target": 5,
        "expected_date_filter": {"mode": "absolute", "start": "2026-03-01", "end": "2026-03-07"},
        "expected_missing_slots": [],
    },
    {
        "case_id": 8,
        "utterance": "3월 1일부터 3월 7일까지 메일 찾아줘",
        "pattern": "한글 절대 날짜 범위",
        "expected_steps": ["read_current_mail"],
        "expected_summary_line_target": 5,
        "expected_date_filter": {"mode": "absolute", "start": "2026-03-01", "end": "2026-03-07"},
        "expected_missing_slots": [],
    },
    {
        "case_id": 9,
        "utterance": "2주 전부터 지난 주까지 메일 요약해줘",
        "pattern": "상대 날짜 범위 공백 변형",
        "expected_steps": ["read_current_mail", "summarize_mail"],
        "expected_summary_line_target": 5,
        "expected_date_filter": {"mode": "relative", "relative": "2_weeks_ago_to_last_week"},
        "expected_missing_slots": [],
    },
    {
        "case_id": 10,
        "utterance": "최근 메일 액션아이템 정리",
        "pattern": "최근 + 액션아이템 + 요약",
        "expected_steps": ["read_current_mail", "summarize_mail", "extract_key_facts"],
        "expected_summary_line_target": 5,
        "expected_date_filter": {"mode": "relative", "relative": "recent"},
        "expected_missing_slots": [],
    },
    {
        "case_id": 11,
        "utterance": "수신자 정보랑 중요한 내용 추출해줘",
        "pattern": "메일 키워드 없음",
        "expected_steps": ["extract_key_facts", "extract_recipients"],
        "expected_summary_line_target": 5,
        "expected_date_filter": {"mode": "none"},
        "expected_missing_slots": [],
    },
    {
        "case_id": 12,
        "utterance": "이번 주 회의 일정 알려주고 요약해줘",
        "pattern": "회의일정 + 요약 복합",
        "expected_steps": ["summarize_mail", "search_meeting_schedule"],
        "expected_summary_line_target": 5,
        "expected_date_filter": {"mode": "relative", "relative": "this_week"},
        "expected_missing_slots": [],
    },
    {
        "case_id": 13,
        "utterance": "메일 요약하고 회의실 예약해줘",
        "pattern": "예약 필수값 전부 누락",
        "expected_steps": ["read_current_mail", "summarize_mail", "book_meeting_room"],
        "expected_summary_line_target": 5,
        "expected_date_filter": {"mode": "none"},
        "expected_missing_slots": ["attendee_count", "date", "end_time", "start_time"],
    },
    {
        "case_id": 14,
        "utterance": "내일 오후 2시 5명 회의 예약해줘",
        "pattern": "예약 슬롯 일부 충족(종료시간만 누락)",
        "expected_steps": ["book_meeting_room"],
        "expected_summary_line_target": 5,
        "expected_date_filter": {"mode": "relative", "relative": "tomorrow"},
        "expected_missing_slots": ["end_time"],
    },
    {
        "case_id": 15,
        "utterance": "받는 사람 추출하고 4줄 요약해",
        "pattern": "수신자 추출 + 줄수",
        "expected_steps": ["summarize_mail", "extract_recipients"],
        "expected_summary_line_target": 4,
        "expected_date_filter": {"mode": "none"},
        "expected_missing_slots": [],
    },
    {
        "case_id": 16,
        "utterance": "지난주 메일 찾아서 보고서로",
        "pattern": "지난주 + 보고서",
        "expected_steps": ["read_current_mail", "summarize_mail"],
        "expected_summary_line_target": 5,
        "expected_date_filter": {"mode": "relative", "relative": "last_week"},
        "expected_missing_slots": [],
    },
    {
        "case_id": 17,
        "utterance": "메일 찾아줘 그리고 회의 잡아줘",
        "pattern": "메일+예약 병렬 지시",
        "expected_steps": ["read_current_mail", "book_meeting_room"],
        "expected_summary_line_target": 5,
        "expected_date_filter": {"mode": "none"},
        "expected_missing_slots": ["attendee_count", "date", "end_time", "start_time"],
    },
    {
        "case_id": 18,
        "utterance": "어제 메일 2줄 요약하고 수신자 추출",
        "pattern": "상대날짜 + 줄수 + 수신자",
        "expected_steps": ["read_current_mail", "summarize_mail", "extract_recipients"],
        "expected_summary_line_target": 2,
        "expected_date_filter": {"mode": "relative", "relative": "yesterday"},
        "expected_missing_slots": [],
    },
    {
        "case_id": 19,
        "utterance": "회의 일정",
        "pattern": "초단문 회의 일정 의도",
        "expected_steps": ["search_meeting_schedule"],
        "expected_summary_line_target": 5,
        "expected_date_filter": {"mode": "none"},
        "expected_missing_slots": [],
    },
    {
        "case_id": 20,
        "utterance": "예약",
        "pattern": "초단문 예약 의도",
        "expected_steps": ["book_meeting_room"],
        "expected_summary_line_target": 5,
        "expected_date_filter": {"mode": "none"},
        "expected_missing_slots": ["attendee_count", "date", "end_time", "start_time"],
    },
]

