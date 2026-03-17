from __future__ import annotations

import re


def infer_steps_from_query(user_message: str) -> list[str]:
    """
    사용자 입력에서 실행 단계(step) 후보를 규칙 기반으로 추출한다.
    """
    text = user_message.strip()
    compact = text.replace(" ", "")
    steps: list[str] = []
    is_mail_search = _is_mail_search_query(text=text)
    has_meeting_room_keyword = "회의실" in text or "미팅룸" in text or "meetingroom" in compact.lower()
    has_calendar_register_intent = "일정" in text and ("등록" in text or "추가" in text or "생성" in text or "잡아" in text)
    has_cause_or_solution_intent = any(token in text for token in ("왜", "원인", "이유", "문제", "해결", "해결 방법", "대응", "방안"))

    if ("메일" in text or "현재메일" in compact) and not is_mail_search:
        steps.append("read_current_mail")
    if is_mail_search:
        steps.append("search_mails")
    if "요약" in text or "정리" in text or "보고서" in text:
        steps.append("summarize_mail")
    if any(token in text for token in ("중요", "핵심", "주요", "키워드", "할일", "액션아이템")):
        steps.append("extract_key_facts")
    if "수신자" in text or "받는" in text:
        steps.append("extract_recipients")
    if "체크리스트" in text or "진행안" in text or "템플릿" in text:
        steps.append("extract_key_facts")
    if has_cause_or_solution_intent:
        steps.append("summarize_mail")
        steps.append("extract_key_facts")
    if "회의 일정" in text:
        steps.append("search_meeting_schedule")
    if has_calendar_register_intent and not has_meeting_room_keyword:
        steps.append("book_calendar_event")
    if has_meeting_room_keyword and ("예약" in text or "잡아" in text or "등록" in text):
        steps.append("book_meeting_room")
    if "예약" in text and not has_calendar_register_intent:
        steps.append("book_meeting_room")

    deduped: list[str] = []
    for step in steps:
        if step not in deduped:
            deduped.append(step)
    return deduped


def is_mail_search_query(text: str) -> bool:
    """사용자 입력이 조건 기반 메일 검색 질의인지 공개 API로 판별한다."""
    normalized = str(text or "").strip()
    if not normalized:
        return False
    return _is_mail_search_query(text=normalized)


def is_current_mail_reference(text: str) -> bool:
    """사용자 입력이 현재 선택 메일 문맥을 가리키는지 판별한다."""
    compact = str(text or "").replace(" ", "").lower()
    if not compact:
        return False
    if "현재메일" in compact:
        return True
    return _is_deictic_current_mail_reference(text=str(text or ""))


def build_missing_slots(steps: list[str], user_message: str, required_slots: tuple[str, ...]) -> list[str]:
    """
    회의 예약 단계가 있을 때 필수 슬롯 누락 목록을 계산한다.
    """
    if "book_meeting_room" not in steps:
        return []
    text = user_message.strip()
    missing = set(required_slots)
    has_korean_absolute = re.search(r"\d{1,2}\s*월\s*\d{1,2}\s*일", text) is not None
    has_iso_or_dot_date = re.search(r"\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}\.?", text) is not None
    has_date_key = re.search(r"[\"']?(date|날짜)[\"']?\s*[:=]\s*[\"']?\S+", text, flags=re.IGNORECASE) is not None
    if "오늘" in text or "어제" in text or "내일" in text or "주" in text or has_iso_or_dot_date or has_korean_absolute or has_date_key:
        missing.discard("date")
    has_hhmm_time = re.search(r"(?:^|[\s=:>])(?:[01]?\d|2[0-3]):[0-5]\d", text) is not None
    has_start_key = re.search(r"[\"']?(start_time|시작)[\"']?\s*[:=]\s*[\"']?\S+", text, flags=re.IGNORECASE) is not None
    if re.search(r"(오전|오후)?\s*\d{1,2}\s*시", text) or has_hhmm_time or has_start_key:
        missing.discard("start_time")
    has_end_key = re.search(r"[\"']?(end_time|종료)[\"']?\s*[:=]\s*[\"']?\S+", text, flags=re.IGNORECASE) is not None
    has_time_range = re.search(r"(?:[01]?\d|2[0-3]):[0-5]\d\s*[~\-]\s*(?:[01]?\d|2[0-3]):[0-5]\d", text) is not None
    if has_end_key or has_time_range:
        missing.discard("end_time")
    has_attendee_key = re.search(r"[\"']?(attendee_count|참석\s*인원|인원)[\"']?\s*[:=]\s*[\"']?\d+", text, flags=re.IGNORECASE) is not None
    if re.search(r"\d+\s*명", text) or has_attendee_key:
        missing.discard("attendee_count")
    return sorted(missing)


def _is_mail_search_query(text: str) -> bool:
    has_mail = "메일" in text
    if not has_mail:
        return False
    if "현재메일" in text.replace(" ", ""):
        return False
    if _is_deictic_current_mail_reference(text=text):
        return False
    if "메일에서" in text:
        return True
    if "본문에" in text and ("포함" in text or "들어" in text):
        return True
    search_tokens = ("조회", "관련", "최근", "지난", "찾아", "검색", "보여", "정리")
    if any(token in text for token in search_tokens):
        return True
    return bool(re.search(r"메일(?:을|를)?\s*.*(보고서\s*형식|보고용)", text))


def _is_deictic_current_mail_reference(text: str) -> bool:
    compact = str(text or "").replace(" ", "").lower()
    deictic_tokens = (
        "현재선택메일",
        "현재선택된메일",
        "선택메일",
        "이메일",
        "이메일에서",
        "이메일의",
        "이메일기반",
        "해당메일",
        "이메일본문",
        "이견적",
        "해당견적",
        "이프로젝트",
        "해당프로젝트",
    )
    return any(token in compact for token in deictic_tokens)
