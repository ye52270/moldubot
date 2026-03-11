from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from app.core.intent_rules import infer_steps_from_query, is_mail_summary_skill_query

EXPLICIT_SUMMARY_TOKENS: tuple[str, ...] = ("요약",)
ANALYSIS_TOKENS: tuple[str, ...] = ("정리", "분석", "설명", "원인", "영향", "대응", "비용", "금액", "리스크")


class FormatTemplateId(str, Enum):
    """
    정형 출력 포맷 템플릿 식별자.
    """

    GENERAL = "general"
    CURRENT_MAIL_SUMMARY = "current_mail_summary"
    CURRENT_MAIL_SUMMARY_ISSUE = "current_mail_summary_issue"
    MAIL_SEARCH_SUMMARY = "mail_search_summary"
    MAIL_SEARCH_TECH_ISSUE = "mail_search_tech_issue"
    CURRENT_MAIL_TODO_REGISTER = "current_mail_todo_register"
    CURRENT_MAIL_MEETING_BOOK = "current_mail_meeting_book"
    CALENDAR_REGISTER = "calendar_register"


@dataclass(frozen=True)
class FormatTemplateSelection:
    """
    포맷 선택 결과.

    Attributes:
        template_id: 선택된 템플릿 식별자
        facets: 부가 섹션/의도 태그 목록
    """

    template_id: FormatTemplateId
    facets: tuple[str, ...]


@dataclass(frozen=True)
class IntentSignature:
    """
    템플릿 선택용 의도 시그니처.

    Attributes:
        has_current_mail: 현재메일 범위 질의 여부
        has_mail_search: 조건 기반 메일 조회 의도 여부
        has_summary: 요약/정리 의도 여부
        has_issue: 기술/이슈 정리 의도 여부
        has_todo: todo/할일 관련 의도 여부
        has_register: 등록/생성 실행 의도 여부
        has_meeting: 회의실 예약 의도 여부
        has_calendar: 일정/캘린더 의도 여부
    """

    has_current_mail: bool
    has_mail_search: bool
    has_summary: bool
    has_analysis: bool
    has_issue: bool
    has_todo: bool
    has_register: bool
    has_meeting: bool
    has_calendar: bool


def select_format_template(
    user_message: str,
    tool_payload: Mapping[str, object] | None = None,
) -> FormatTemplateSelection:
    """
    사용자 질의/도구 payload를 기반으로 정형 포맷 템플릿을 선택한다.

    Notes:
        Phase 1에서는 관측 로그용 선택만 수행하며, 실제 렌더 동작은 변경하지 않는다.

    Args:
        user_message: 사용자 질의 텍스트
        tool_payload: 마지막 도구 payload

    Returns:
        템플릿 선택 결과
    """
    text = _normalize_query(user_message=user_message)
    action = _extract_action(tool_payload=tool_payload)
    signature = _build_intent_signature(user_message=user_message, normalized_query=text)
    has_explicit_summary = _is_explicit_summary_request(normalized_query=text)
    is_mail_summary_skill = is_mail_summary_skill_query(user_message=user_message)
    facets = _build_facets(signature=signature)

    if action == "create_outlook_todo" or (
        signature.has_current_mail and signature.has_todo and signature.has_register
    ):
        return _selection(template_id=FormatTemplateId.CURRENT_MAIL_TODO_REGISTER, facets=facets)
    if action == "book_meeting_room" or (
        signature.has_current_mail and signature.has_meeting and (signature.has_register or "예약해" in text)
    ):
        return _selection(template_id=FormatTemplateId.CURRENT_MAIL_MEETING_BOOK, facets=facets)
    if action == "create_outlook_calendar_event" or (signature.has_calendar and signature.has_register):
        return _selection(template_id=FormatTemplateId.CALENDAR_REGISTER, facets=facets)
    if action == "mail_search":
        template_id = (
            FormatTemplateId.MAIL_SEARCH_TECH_ISSUE
            if signature.has_issue
            else FormatTemplateId.MAIL_SEARCH_SUMMARY
        )
        return _selection(template_id=template_id, facets=facets)
    if signature.has_current_mail and is_mail_summary_skill and signature.has_issue:
        return _selection(template_id=FormatTemplateId.CURRENT_MAIL_SUMMARY_ISSUE, facets=facets)
    if signature.has_current_mail and is_mail_summary_skill:
        return _selection(template_id=FormatTemplateId.CURRENT_MAIL_SUMMARY, facets=facets)
    if signature.has_mail_search and has_explicit_summary:
        template_id = (
            FormatTemplateId.MAIL_SEARCH_TECH_ISSUE
            if signature.has_issue
            else FormatTemplateId.MAIL_SEARCH_SUMMARY
        )
        return _selection(template_id=template_id, facets=facets)
    return _selection(template_id=FormatTemplateId.GENERAL, facets=facets)


def _build_intent_signature(user_message: str, normalized_query: str) -> IntentSignature:
    """
    사용자 질의를 템플릿 선택용 시그니처로 변환한다.

    Args:
        user_message: 원본 사용자 질의
        normalized_query: 공백 제거/소문자 정규화 질의

    Returns:
        템플릿 분기용 의도 시그니처
    """
    steps = set(infer_steps_from_query(user_message=user_message))
    has_current_mail = ("read_current_mail" in steps) or ("현재메일" in normalized_query)
    has_mail_search = "search_mails" in steps
    has_summary = ("summarize_mail" in steps) or _is_explicit_summary_request(normalized_query=normalized_query)
    has_analysis = any(token in normalized_query for token in ANALYSIS_TOKENS)
    has_issue = any(token in normalized_query for token in ("이슈", "기술", "장애", "오류", "보안", "api", "ssl"))
    has_todo = any(token in normalized_query for token in ("todo", "할일", "조치", "액션"))
    has_register = any(token in normalized_query for token in ("등록", "생성", "추가", "만들"))
    has_meeting = ("book_meeting_room" in steps) or any(token in normalized_query for token in ("회의실", "예약"))
    has_calendar = ("book_calendar_event" in steps) or any(token in normalized_query for token in ("일정", "캘린더"))
    return IntentSignature(
        has_current_mail=has_current_mail,
        has_mail_search=has_mail_search,
        has_summary=has_summary,
        has_analysis=has_analysis,
        has_issue=has_issue,
        has_todo=has_todo,
        has_register=has_register,
        has_meeting=has_meeting,
        has_calendar=has_calendar,
    )


def _build_facets(signature: IntentSignature) -> list[str]:
    """
    의도 시그니처를 기반으로 facet 목록을 계산한다.

    Args:
        signature: 의도 시그니처

    Returns:
        facet 목록
    """
    facets: list[str] = []
    if signature.has_issue:
        facets.append("tech_issue")
    if signature.has_analysis:
        facets.append("analysis")
    if signature.has_calendar or signature.has_meeting:
        facets.append("schedule")
    if signature.has_todo:
        facets.append("todo")
    if signature.has_mail_search:
        facets.append("evidence")
    return _dedupe(values=facets)


def _is_explicit_summary_request(normalized_query: str) -> bool:
    """
    명시적 요약 요청 여부를 판별한다.

    Notes:
        분석형 `정리/설명/분석` 질의를 요약 템플릿으로 과적용하지 않기 위해
        요약 신호는 `요약` 키워드 중심으로 제한한다.

    Args:
        normalized_query: 공백 제거/소문자 질의

    Returns:
        명시적 요약 요청이면 True
    """
    return any(token in normalized_query for token in EXPLICIT_SUMMARY_TOKENS)


def _selection(template_id: FormatTemplateId, facets: list[str]) -> FormatTemplateSelection:
    """
    선택 결과 객체를 생성한다.

    Args:
        template_id: 템플릿 식별자
        facets: facet 목록

    Returns:
        불변 선택 결과
    """
    return FormatTemplateSelection(template_id=template_id, facets=tuple(_dedupe(values=facets)))


def _normalize_query(user_message: str) -> str:
    """
    템플릿 선택용 질의 문자열을 정규화한다.

    Args:
        user_message: 원본 질의

    Returns:
        공백 제거 + 소문자 문자열
    """
    return str(user_message or "").strip().replace(" ", "").lower()


def _extract_action(tool_payload: Mapping[str, object] | None) -> str:
    """
    payload에서 액션 문자열을 추출한다.

    Args:
        tool_payload: 도구 payload

    Returns:
        소문자 액션 문자열
    """
    if not isinstance(tool_payload, Mapping):
        return ""
    value = tool_payload.get("action")
    return str(value or "").strip().lower()


def _dedupe(values: list[str]) -> list[str]:
    """
    문자열 목록 중복을 제거한다.

    Args:
        values: 원본 문자열 목록

    Returns:
        중복 제거된 목록
    """
    deduped: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in deduped:
            deduped.append(text)
    return deduped
