from __future__ import annotations

from typing import Mapping

from app.core.intent_rules import is_code_review_query
from app.services.answer_postprocessor_current_mail import (
    is_current_mail_issue_action_request,
    is_current_mail_manager_single_paragraph_request,
    is_current_mail_recipients_table_request,
)
from app.services.answer_postprocessor_summary import is_report_request
from app.services.current_mail_intent_policy import (
    is_current_mail_cause_analysis_request,
    is_current_mail_solution_request,
)


def should_apply_template_driven_contract(
    user_message: str,
    section_contract: Mapping[str, object] | None,
) -> tuple[bool, str]:
    """
    템플릿 기반 contract 렌더 적용 가능 여부를 판단한다.

    Args:
        user_message: 정규화 사용자 질의
        section_contract: 템플릿 섹션 계약

    Returns:
        (적용 가능 여부, 사유 코드)
    """
    text = str(user_message or "")
    if is_code_review_query(user_message=text):
        return (False, "code_review_exception")
    if is_report_request(user_message=text):
        return (False, "report_exception")
    if is_current_mail_recipients_table_request(user_message=text):
        return (False, "recipients_table_exception")
    if is_current_mail_manager_single_paragraph_request(user_message=text):
        return (False, "manager_single_paragraph_exception")
    if is_current_mail_issue_action_request(user_message=text):
        return (False, "issue_action_split_exception")
    if is_current_mail_cause_analysis_request(user_message=text):
        return (False, "cause_analysis_policy_override")
    if is_current_mail_solution_request(user_message=text):
        return (False, "solution_policy_override")
    if not isinstance(section_contract, Mapping):
        return (False, "missing_section_contract")
    return (True, "enabled")
