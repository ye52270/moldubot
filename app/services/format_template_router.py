from __future__ import annotations

from typing import Any, Mapping

from app.services.answer_postprocessor_mail_search import (
    is_mail_search_no_result,
    render_mail_search_deterministic_response,
    render_mail_search_no_result_message,
    render_mail_search_overview_summary,
    render_recent_sorted_mail_response,
)
from app.services.answer_postprocessor_guards import looks_like_json_contract_text

MAIL_SEARCH_TEMPLATE_IDS: tuple[str, ...] = ("mail_search_summary", "mail_search_tech_issue")


def render_template_driven_mail_search(
    user_message: str,
    answer: str,
    tool_payload: dict[str, Any],
    section_contract: Mapping[str, object],
) -> tuple[str, str]:
    """
    템플릿/섹션 계약 기반 mail_search 결정론 렌더링을 수행한다.

    Notes:
        출력 동작을 바꾸지 않고, 기존 분기(최근순/0건/결정론/overview)를
        템플릿 라우터로 집약한다.

    Args:
        user_message: 정규화 사용자 입력
        answer: 정규화 모델 응답
        tool_payload: 툴 payload
        section_contract: 섹션 계약

    Returns:
        (route, rendered) 튜플.
        route는 `recent_sorted|no_result|deterministic|overview|skip`
    """
    _ = answer
    action = str(tool_payload.get("action") or "").strip().lower()
    template_id = str(section_contract.get("template_id") or "").strip().lower()
    if action != "mail_search":
        return ("skip", "")
    if template_id and template_id not in MAIL_SEARCH_TEMPLATE_IDS:
        return ("skip", "")
    if looks_like_json_contract_text(text=answer):
        return ("skip", "")

    recent_sorted_rendered = render_recent_sorted_mail_response(
        user_message=user_message,
        tool_payload=tool_payload,
    )
    if recent_sorted_rendered:
        return ("recent_sorted", recent_sorted_rendered)

    if is_mail_search_no_result(user_message=user_message, tool_payload=tool_payload):
        return ("no_result", render_mail_search_no_result_message(user_message=user_message))

    deterministic_mail_search = render_mail_search_deterministic_response(
        user_message=user_message,
        tool_payload=tool_payload,
        section_contract=section_contract,
    )
    if deterministic_mail_search:
        return ("deterministic", deterministic_mail_search)

    mail_search_overview = render_mail_search_overview_summary(
        user_message=user_message,
        answer=answer,
        tool_payload=tool_payload,
    )
    if mail_search_overview:
        return ("overview", mail_search_overview)
    return ("skip", "")
