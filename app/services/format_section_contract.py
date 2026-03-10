from __future__ import annotations

from typing import Any, Mapping

from app.services.format_policy_selector import FormatTemplateId, select_format_template

TECH_QUERY_TOKENS: tuple[str, ...] = ("기술", "이슈", "오류", "장애", "보안", "api", "ssl")
HIL_ACTIONS: tuple[str, ...] = ("create_outlook_todo", "book_meeting_room", "create_outlook_calendar_event")


def build_format_section_contract(
    user_message: str,
    tool_payload: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    """
    템플릿 선택 결과를 섹션 계약(JSON 친화 dict)으로 변환한다.

    Notes:
        Phase 3에서는 관측/표준화 목적의 계약만 생성하며 렌더 동작은 변경하지 않는다.

    Args:
        user_message: 사용자 질의
        tool_payload: 마지막 도구 payload

    Returns:
        템플릿 ID와 섹션 목록을 포함한 섹션 계약
    """
    selection = select_format_template(user_message=user_message, tool_payload=tool_payload)
    payload = tool_payload if isinstance(tool_payload, Mapping) else {}
    sections: list[dict[str, Any]] = []

    if selection.template_id in {
        FormatTemplateId.CURRENT_MAIL_SUMMARY,
        FormatTemplateId.CURRENT_MAIL_SUMMARY_ISSUE,
    }:
        sections.append(_section(section_id="summary", title="요약", items=[]))

    if selection.template_id in {FormatTemplateId.MAIL_SEARCH_SUMMARY, FormatTemplateId.MAIL_SEARCH_TECH_ISSUE}:
        major_items = _extract_major_items(payload=payload)
        sections.append(_section(section_id="major", title="주요 내용", items=major_items))

    if selection.template_id in {
        FormatTemplateId.MAIL_SEARCH_TECH_ISSUE,
        FormatTemplateId.CURRENT_MAIL_SUMMARY_ISSUE,
    }:
        tech_items = _extract_tech_issue_items(payload=payload)
        sections.append(_section(section_id="tech_issue", title="기술 이슈", items=tech_items))

    if _should_include_evidence_section(selection_template=selection.template_id, payload=payload):
        evidence_items = _extract_evidence_items(payload=payload)
        sections.append(_section(section_id="evidence", title="근거 메일", items=evidence_items))

    action_section = _build_action_section(selection_template=selection.template_id, payload=payload)
    if action_section:
        sections.append(action_section)

    return {
        "template_id": selection.template_id.value,
        "facets": list(selection.facets),
        "sections": sections,
    }


def _section(section_id: str, title: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    """
    섹션 사전을 생성한다.

    Args:
        section_id: 섹션 식별자
        title: 섹션 제목
        items: 섹션 아이템 목록

    Returns:
        섹션 dict
    """
    return {"id": section_id, "title": title, "items": items}


def _extract_major_items(payload: Mapping[str, object]) -> list[dict[str, str]]:
    """
    payload에서 주요 내용 아이템을 추출한다.

    Args:
        payload: 도구 payload

    Returns:
        주요 내용 아이템 목록
    """
    items: list[dict[str, str]] = []
    summaries = payload.get("aggregated_summary")
    if isinstance(summaries, list):
        for value in summaries[:5]:
            text = str(value or "").strip()
            if text:
                items.append({"text": text})
    if items:
        return items
    query_summaries = payload.get("query_summaries")
    if not isinstance(query_summaries, list):
        return items
    for row in query_summaries:
        if not isinstance(row, Mapping):
            continue
        lines = row.get("lines")
        if not isinstance(lines, list):
            continue
        for line in lines:
            text = str(line or "").strip()
            if text and not _is_tech_issue_text(text=text):
                items.append({"text": text})
                if len(items) >= 5:
                    return items
    return items


def _extract_tech_issue_items(payload: Mapping[str, object]) -> list[dict[str, str]]:
    """
    payload에서 기술 이슈 라인을 추출한다.

    Args:
        payload: 도구 payload

    Returns:
        기술 이슈 아이템 목록
    """
    items: list[dict[str, str]] = []
    query_summaries = payload.get("query_summaries")
    if not isinstance(query_summaries, list):
        return items
    for row in query_summaries:
        if not isinstance(row, Mapping):
            continue
        query = str(row.get("query") or "").strip().lower()
        lines = row.get("lines")
        if not isinstance(lines, list):
            continue
        for line in lines:
            text = str(line or "").strip()
            if not text:
                continue
            if _is_tech_query(query=query) or _is_tech_issue_text(text=text):
                items.append({"text": text})
                if len(items) >= 4:
                    return items
    return items


def _extract_evidence_items(payload: Mapping[str, object]) -> list[dict[str, str]]:
    """
    payload의 결과 목록을 근거메일 아이템으로 변환한다.

    Args:
        payload: 도구 payload

    Returns:
        근거메일 아이템 목록
    """
    items: list[dict[str, str]] = []
    results = payload.get("results")
    if not isinstance(results, list):
        return items
    for row in results[:6]:
        if not isinstance(row, Mapping):
            continue
        subject = str(row.get("subject") or "제목 없음").strip() or "제목 없음"
        date = str(row.get("received_date") or "").strip()
        sender = str(row.get("sender_names") or row.get("from_address") or "").strip()
        web_link = str(row.get("web_link") or "").strip()
        items.append(
            {
                "subject": subject,
                "received_date": date,
                "sender": sender,
                "web_link": web_link,
            }
        )
    return items


def _build_action_section(
    selection_template: FormatTemplateId,
    payload: Mapping[str, object],
) -> dict[str, Any] | None:
    """
    실행형 템플릿에 대한 액션 섹션을 생성한다.

    Args:
        selection_template: 선택된 템플릿
        payload: 도구 payload

    Returns:
        액션 섹션 dict 또는 None
    """
    if selection_template not in {
        FormatTemplateId.CURRENT_MAIL_TODO_REGISTER,
        FormatTemplateId.CURRENT_MAIL_MEETING_BOOK,
        FormatTemplateId.CALENDAR_REGISTER,
    }:
        return None
    action = str(payload.get("action") or "").strip().lower()
    return {
        "id": "action",
        "title": "실행",
        "items": [{"action": action}],
        "requires_hil": action in HIL_ACTIONS,
    }


def _should_include_evidence_section(
    selection_template: FormatTemplateId,
    payload: Mapping[str, object],
) -> bool:
    """
    근거메일 섹션 포함 여부를 판단한다.

    Args:
        selection_template: 선택 템플릿
        payload: 도구 payload

    Returns:
        근거 섹션 포함 여부
    """
    if selection_template not in {
        FormatTemplateId.MAIL_SEARCH_SUMMARY,
        FormatTemplateId.MAIL_SEARCH_TECH_ISSUE,
    }:
        return False
    results = payload.get("results")
    return isinstance(results, list) and len(results) > 0


def _is_tech_query(query: str) -> bool:
    """
    기술 이슈 축 질의 여부를 판단한다.

    Args:
        query: query_summaries.query 값

    Returns:
        기술 이슈 질의면 True
    """
    normalized = str(query or "").strip().lower()
    return any(token in normalized for token in TECH_QUERY_TOKENS)


def _is_tech_issue_text(text: str) -> bool:
    """
    문장 자체가 기술 이슈를 나타내는지 판단한다.

    Args:
        text: 문장

    Returns:
        기술 이슈 문장이면 True
    """
    normalized = str(text or "").strip().lower()
    return any(token in normalized for token in TECH_QUERY_TOKENS)
