from __future__ import annotations

import os
import re
import json

from app.agents.intent_schema import ExecutionStep, IntentDecomposition, IntentFocusTopic, IntentTaskType


def is_recipient_todo_summary_request(decomposition: IntentDecomposition) -> bool:
    """
    수신자별 ToDo/마감기한을 요약하는 분석 질의인지 판별한다.

    Args:
        decomposition: 의도 구조분해 결과

    Returns:
        요약형 수신자 ToDo 질의면 True
    """
    if is_explicit_todo_registration_request(decomposition=decomposition):
        return False
    if decomposition.task_type != IntentTaskType.EXTRACTION:
        return False
    if ExecutionStep.EXTRACT_RECIPIENTS not in decomposition.steps:
        return False
    if IntentFocusTopic.RECIPIENTS in decomposition.focus_topics:
        return True
    return ExecutionStep.READ_CURRENT_MAIL in decomposition.steps


def is_explicit_todo_registration_request(decomposition: IntentDecomposition) -> bool:
    """
    수신자 요약이 아닌 명시적 ToDo 등록 실행 요청인지 판별한다.

    Args:
        decomposition: 의도 구조분해 결과

    Returns:
        명시적 ToDo 등록 요청이면 True
    """
    return decomposition.task_type == IntentTaskType.ACTION


def is_meeting_room_hil_payload_request(decomposition: IntentDecomposition) -> bool:
    """
    회의실 예약 HIL 페이로드 질의인지 판별한다.

    Args:
        decomposition: 의도 구조분해 결과

    Returns:
        회의실 예약 HIL 페이로드면 True
    """
    return _extract_hil_task_name(query=decomposition.original_query) == "book_meeting_room"


def is_calendar_event_hil_payload_request(decomposition: IntentDecomposition) -> bool:
    """
    일정 등록 HIL 페이로드 질의인지 판별한다.

    Args:
        decomposition: 의도 구조분해 결과

    Returns:
        일정 등록 HIL 페이로드면 True
    """
    return _extract_hil_task_name(query=decomposition.original_query) == "create_outlook_calendar_event"


def is_mail_subagents_enabled() -> bool:
    """
    메일 조회 전용 서브에이전트 활성화 여부를 반환한다.

    Returns:
        환경변수(`MOLDUBOT_ENABLE_MAIL_SUBAGENTS`)가 truthy면 True
    """
    raw_value = str(os.getenv("MOLDUBOT_ENABLE_MAIL_SUBAGENTS", "")).strip().lower()
    return raw_value in {"1", "true", "yes", "on"}


def is_composite_mail_retrieval_request(decomposition: IntentDecomposition) -> bool:
    """
    복합 메일 조회(요약+기술 이슈 동시) 질의인지 판별한다.

    Args:
        decomposition: 의도 구조분해 결과

    Returns:
        복합 조회 질의면 True
    """
    if decomposition.task_type != IntentTaskType.RETRIEVAL:
        return False
    has_search_step = ExecutionStep.SEARCH_MAILS in decomposition.steps
    has_summary_step = ExecutionStep.SUMMARIZE_MAIL in decomposition.steps
    if not has_search_step or not has_summary_step:
        return False
    focus_topics = set(decomposition.focus_topics)
    return IntentFocusTopic.SCHEDULE in focus_topics and IntentFocusTopic.TECH_ISSUE in focus_topics


def _extract_hil_task_name(query: str) -> str:
    """
    HIL 페이로드 형태 문자열에서 task 값을 추출한다.

    Args:
        query: 사용자 입력 원문

    Returns:
        추출된 task 이름(없으면 빈 문자열)
    """
    normalized = str(query or "").strip()
    if not normalized:
        return ""
    maybe_json = _extract_json_task_name(query=normalized)
    if maybe_json:
        return maybe_json
    match = re.search(r"\btask\b\s*[:=]\s*['\"]?([a-zA-Z0-9_\\-]+)", normalized)
    if match is None:
        return ""
    return str(match.group(1) or "").strip().lower()


def _extract_json_task_name(query: str) -> str:
    """
    JSON 문자열에서 task 필드를 추출한다.

    Args:
        query: 사용자 입력 원문

    Returns:
        task 필드 문자열(없거나 파싱 실패 시 빈 문자열)
    """
    if not (query.startswith("{") and query.endswith("}")):
        return ""
    try:
        payload = json.loads(query)
    except (json.JSONDecodeError, ValueError, TypeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("task") or "").strip().lower()
