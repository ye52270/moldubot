from __future__ import annotations

import json
from typing import Any

from app.core.logging_config import get_logger
from app.core.intent_rules import is_code_review_query
from app.models.response_contracts import FinalAnswerContract, LLMResponseContract
from app.services.answer_postprocessor_contract_utils import (
    augment_contract_with_tool_payload,
    parse_llm_response_contract,
)
from app.services.answer_postprocessor_code_review_annotated import (
    render_current_mail_code_review_annotated_response,
)
from app.services.answer_postprocessor_code_review import render_current_mail_code_review_response
from app.services.answer_postprocessor_current_mail import (
    render_current_mail_direct_value_from_tool_payload,
    render_current_mail_grounded_safe_response,
    render_current_mail_issue_action_split,
    render_current_mail_manager_single_paragraph,
    render_current_mail_recipients_from_tool_payload,
    render_current_mail_recipients_table,
)
from app.services.answer_postprocessor_fallback import render_fallback_answer
from app.services.format_contract_renderer import render_template_driven_contract
from app.services.format_exception_policy import should_apply_template_driven_contract
from app.services.format_policy_selector import select_format_template
from app.services.format_section_contract import build_format_section_contract
from app.services.format_template_router import render_template_driven_mail_search
from app.services.answer_postprocessor_guards import (
    is_effectively_empty_contract,
    looks_like_json_contract_text,
    render_forced_section_response,
)
from app.services.answer_postprocessor_rendering import render_contract_answer
from app.services.answer_postprocessor_summary import (
    extract_original_user_message,
    is_summary_request,
    normalize_multiline_text,
)
from app.services.answer_table_spec import (
    render_current_mail_people_roles_from_contract,
    render_current_mail_recipient_todos_from_contract,
)
from app.services.answer_postprocessor_table import render_generic_table_from_contract
from app.services.answer_postprocessor_reply_draft import (
    is_reply_draft_request,
    recover_reply_draft_from_plain_text,
    select_reply_body_from_contract,
)
from app.services.mail_search_role_summary import render_mail_search_recipient_role_summary

logger = get_logger(__name__)
CONTRACT_LOG_MAX_CHARS = 4000


def postprocess_final_answer(
    user_message: str,
    answer: str,
    tool_payload: dict[str, Any] | None = None,
    raw_model_content: Any | None = None,
) -> str:
    """
    사용자 질의 문맥을 반영해 최종 응답 텍스트를 후처리한다.

    Args:
        user_message: 사용자 입력 원문(또는 미들웨어 주입 문자열)
        answer: 모델이 생성한 최종 응답 텍스트
        tool_payload: 직전 도구 호출 결과 payload
        raw_model_content: 모델 content 원문 블록(list/dict/string)

    Returns:
        정규화된 최종 응답 텍스트
    """
    normalized_user_message = extract_original_user_message(user_message=user_message)
    normalized_answer = normalize_multiline_text(text=answer)
    normalized_tool_payload = tool_payload or {}
    template_selection = select_format_template(
        user_message=normalized_user_message,
        tool_payload=normalized_tool_payload,
    )
    logger.info(
        "answer_postprocess.format_template_selected: template_id=%s facets=%s",
        template_selection.template_id.value,
        ",".join(template_selection.facets),
    )
    section_contract = build_format_section_contract(
        user_message=normalized_user_message,
        tool_payload=normalized_tool_payload,
    )
    section_ids = [
        str(item.get("id") or "").strip()
        for item in section_contract.get("sections", [])
        if isinstance(item, dict)
    ]
    logger.info(
        "answer_postprocess.format_section_contract: template_id=%s sections=%s",
        str(section_contract.get("template_id") or ""),
        ",".join([item for item in section_ids if item]),
    )

    deterministic_rendered = _try_render_deterministic_answer(
        user_message=normalized_user_message,
        answer=normalized_answer,
        tool_payload=normalized_tool_payload,
        section_contract=section_contract,
    )
    if deterministic_rendered:
        return FinalAnswerContract(answer=deterministic_rendered).answer

    parsed_contract = None
    if _should_try_contract_parse(
        user_message=normalized_user_message,
        answer=normalized_answer,
    ):
        parse_source: Any = raw_model_content if raw_model_content is not None else answer
        parsed_contract = parse_llm_response_contract(raw_answer=parse_source)
    if parsed_contract is not None:
        parsed_contract = augment_contract_with_tool_payload(
            user_message=normalized_user_message,
            contract=parsed_contract,
            tool_payload=normalized_tool_payload,
        )
        contract_rendered = _try_render_contract_variants(
            user_message=normalized_user_message,
            answer=normalized_answer,
            contract=parsed_contract,
            tool_payload=normalized_tool_payload,
            section_contract=section_contract,
        )
        if contract_rendered:
            return FinalAnswerContract(answer=contract_rendered).answer

    grounded_safe_rendered = render_current_mail_grounded_safe_response(
        user_message=normalized_user_message,
        answer=normalized_answer,
        tool_payload=normalized_tool_payload,
    )
    if grounded_safe_rendered:
        logger.info("answer_postprocess.current_mail_grounded_safe: forced_render=true")
        return FinalAnswerContract(answer=grounded_safe_rendered).answer

    fallback_route, fallback_rendered = render_fallback_answer(
        user_message=normalized_user_message,
        answer=normalized_answer,
        tool_payload=normalized_tool_payload,
    )
    _log_fallback_route(route=fallback_route)
    return FinalAnswerContract(answer=fallback_rendered).answer


def _should_try_contract_parse(user_message: str, answer: str) -> bool:
    """
    JSON 계약 파싱 시도 여부를 판단한다.

    Args:
        user_message: 정규화 사용자 입력
        answer: 정규화 모델 응답

    Returns:
        계약 파싱 시도 대상이면 True
    """
    if is_code_review_query(user_message=user_message) and not looks_like_json_contract_text(text=answer):
        return False
    return True


def _try_render_deterministic_answer(
    user_message: str,
    answer: str,
    tool_payload: dict[str, Any],
    section_contract: dict[str, Any],
) -> str:
    """
    계약 파싱 이전에 툴 결과 기반 결정론 렌더링을 시도한다.

    Args:
        user_message: 정규화 사용자 입력
        answer: 정규화 모델 응답
        tool_payload: 툴 payload

    Returns:
        렌더링된 문자열. 미적용 시 빈 문자열
    """
    if _should_preserve_llm_code_review_answer(user_message=user_message, answer=answer):
        logger.info("answer_postprocess.current_mail_code_review: preserve_llm=true")
        return ""

    annotated_code_review = render_current_mail_code_review_annotated_response(
        user_message=user_message,
        answer=answer,
        tool_payload=tool_payload,
    )
    if annotated_code_review:
        logger.info("answer_postprocess.current_mail_code_review: render_mode=annotated_segments")
        return annotated_code_review

    if not _is_expert_code_review_answer(answer=answer):
        code_review_rendered = render_current_mail_code_review_response(
            user_message=user_message,
            answer=answer,
            tool_payload=tool_payload,
        )
        if code_review_rendered:
            logger.info("answer_postprocess.current_mail_code_review: forced_render=true")
            return code_review_rendered

    forced_mail_search_role_summary = render_mail_search_recipient_role_summary(
        user_message=user_message,
        tool_payload=tool_payload,
    )
    if forced_mail_search_role_summary:
        logger.info("answer_postprocess.mail_search_recipient_role_summary: forced_render=true")
        return forced_mail_search_role_summary

    forced_direct_value_rendered = render_current_mail_direct_value_from_tool_payload(
        user_message=user_message,
        tool_payload=tool_payload,
    )
    if forced_direct_value_rendered:
        logger.info("answer_postprocess.current_mail_direct_value: forced_render=true")
        return forced_direct_value_rendered

    forced_recipient_rendered = render_current_mail_recipients_from_tool_payload(
        user_message=user_message,
        tool_payload=tool_payload,
    )
    if forced_recipient_rendered:
        logger.info("answer_postprocess.current_mail_recipients: forced_render=true")
        return forced_recipient_rendered

    mail_route, mail_rendered = render_template_driven_mail_search(
        user_message=user_message,
        answer=answer,
        tool_payload=tool_payload,
        section_contract=section_contract,
    )
    if mail_rendered:
        if mail_route == "recent_sorted":
            logger.info("answer_postprocess.mail_search_recent_sorted: deterministic_render=true")
        elif mail_route == "no_result":
            logger.info("answer_postprocess.mail_search_no_result: summary_template=true")
        elif mail_route == "deterministic":
            logger.info("answer_postprocess.mail_search_deterministic: enabled=true")
        elif mail_route == "overview":
            logger.info("answer_postprocess.mail_search_overview: bullet_render=true")
        return mail_rendered

    return ""


def _is_expert_code_review_answer(answer: str) -> bool:
    """
    전문가형 코드리뷰 출력으로 보이는 응답인지 판별한다.

    Args:
        answer: 모델 응답 원문

    Returns:
        전문가형 코드리뷰 형식이면 True
    """
    text = str(answer or "")
    if not text:
        return False
    has_findings = "## 주요 findings" in text.lower() or "findings" in text.lower()
    has_review_fields = "심각도" in text and ("근거" in text or "영향" in text)
    return has_findings and has_review_fields


def _should_preserve_llm_code_review_answer(user_message: str, answer: str) -> bool:
    """
    코드 리뷰 질의에서 LLM 원문 답변을 그대로 보존할지 판별한다.

    Args:
        user_message: 정규화 사용자 입력
        answer: 정규화 모델 응답

    Returns:
        보존 대상이면 True
    """
    if not is_code_review_query(user_message=user_message):
        return False
    normalized_answer = str(answer or "").strip()
    if not normalized_answer:
        return False
    if looks_like_json_contract_text(text=normalized_answer):
        return False
    return (
        "```" in normalized_answer
        or "## 코드 분석" in normalized_answer
        or "## 코드 리뷰" in normalized_answer
        or "## 주요 Findings" in normalized_answer
        or "심각도" in normalized_answer
        or "리스크" in normalized_answer
    )


def _try_render_contract_variants(
    user_message: str,
    answer: str,
    contract: LLMResponseContract,
    tool_payload: dict[str, Any],
    section_contract: dict[str, Any],
) -> str:
    """
    파싱된 계약을 다양한 특수 포맷으로 렌더링한다.

    Args:
        user_message: 정규화 사용자 입력
        answer: 정규화 모델 응답 원문
        contract: 파싱/보강된 계약
        tool_payload: 툴 payload
        section_contract: 템플릿 섹션 계약

    Returns:
        렌더링된 문자열. 실패 시 빈 문자열
    """
    enabled, reason = should_apply_template_driven_contract(
        user_message=user_message,
        section_contract=section_contract,
    )
    if enabled:
        if not is_summary_request(user_message=user_message):
            template_driven_rendered = render_template_driven_contract(
                contract=contract,
                section_contract=section_contract,
            )
            if template_driven_rendered:
                logger.info("answer_postprocess.template_driven_contract: enabled=true")
                return template_driven_rendered
        else:
            logger.info("answer_postprocess.template_driven_contract: enabled=true but skipped_for=summary_route")
    else:
        logger.info("answer_postprocess.template_driven_contract: enabled=false reason=%s", reason)

    logger.info(
        "answer_postprocess.json_parse_success: format_type=%s summary_lines=%s key_points=%s action_items=%s",
        contract.format_type,
        len(contract.summary_lines),
        len(contract.key_points),
        len(contract.action_items),
    )
    logger.info(
        "answer_postprocess.parsed_contract_json: %s",
        _truncate_contract_log(text=json.dumps(contract.model_dump(mode="json"), ensure_ascii=False)),
    )

    if contract.reply_draft:
        logger.info("answer_postprocess.reply_draft_recovery: source=contract_field_forced")
        return select_reply_body_from_contract(reply_draft=contract.reply_draft, answer="")

    if is_reply_draft_request(user_message=user_message):
        # reply_draft 필드 우선, 없으면 원문 plain 본문 복구를 먼저 시도한다.
        reply_body = select_reply_body_from_contract(reply_draft=contract.reply_draft, answer="")
        if not reply_body:
            reply_body = recover_reply_draft_from_plain_text(
                user_message=user_message,
                answer=answer,
            )
        if not reply_body:
            reply_body = select_reply_body_from_contract(reply_draft="", answer=contract.answer)
        if reply_body:
            logger.info("answer_postprocess.reply_draft_recovery: source=contract_field")
            return reply_body
        logger.warning("answer_postprocess.reply_draft_missing: source=contract_field")
        return ""

    mail_context = tool_payload.get("mail_context")
    contract_people_roles_table = render_current_mail_people_roles_from_contract(
        user_message=user_message,
        contract=contract,
        mail_context=mail_context,
    )
    if contract_people_roles_table:
        logger.info("answer_postprocess.current_mail_people_roles_table: source=contract")
        return contract_people_roles_table

    contract_recipient_todos_table = render_current_mail_recipient_todos_from_contract(
        user_message=user_message,
        contract=contract,
        mail_context=mail_context,
    )
    if contract_recipient_todos_table:
        logger.info("answer_postprocess.current_mail_recipient_todos_table: source=contract")
        return contract_recipient_todos_table

    generic_contract_table = render_generic_table_from_contract(
        user_message=user_message,
        contract=contract,
    )
    if generic_contract_table:
        logger.info("answer_postprocess.generic_table: source=contract")
        return generic_contract_table

    forced_single_paragraph = render_current_mail_manager_single_paragraph(
        user_message=user_message,
        contract=contract,
    )
    if forced_single_paragraph:
        logger.info("answer_postprocess.current_mail_manager_single_paragraph: forced_render=true")
        return forced_single_paragraph

    forced_recipients_table = render_current_mail_recipients_table(
        user_message=user_message,
        contract=contract,
    )
    if forced_recipients_table:
        logger.info("answer_postprocess.current_mail_recipients_table: forced_render=true")
        return forced_recipients_table

    forced_issue_action_split = render_current_mail_issue_action_split(
        user_message=user_message,
        contract=contract,
    )
    if forced_issue_action_split:
        logger.info("answer_postprocess.current_mail_issue_action_split: forced_render=true")
        return forced_issue_action_split

    forced_section_rendered = render_forced_section_response(
        user_message=user_message,
        contract=contract,
    )
    if forced_section_rendered:
        logger.info("answer_postprocess.required_sections: forced_render=true")
        return forced_section_rendered

    if is_effectively_empty_contract(contract=contract):
        logger.warning("answer_postprocess.json_fallback: reason=empty_contract_payload")
        return ""

    rendered = render_contract_answer(user_message=user_message, contract=contract)
    if rendered:
        return rendered

    logger.warning("answer_postprocess.json_fallback: reason=empty_rendered_output")
    return ""


def _log_fallback_route(route: str) -> None:
    """
    fallback 경로별 로그를 표준 메시지로 남긴다.

    Args:
        route: fallback 라우팅 식별자
    """
    if route == "current_mail_people_roles_table":
        logger.info("answer_postprocess.current_mail_people_roles_table: source=fallback_mail_context")
        return
    if route == "reply_draft_json_text":
        logger.info("answer_postprocess.reply_draft_recovery: source=fallback_json_text")
        return
    if route == "reply_draft_plain_text":
        logger.info("answer_postprocess.reply_draft_recovery: source=fallback_plain_text")
        return
    if route == "current_mail_summary_recovery":
        logger.info("answer_postprocess.current_mail_summary_recovery: forced_render=true")
        return
    if route == "code_review_text":
        logger.info("answer_postprocess.fallback_route: route=code_review_text")
        return
    if route == "report_template_guard":
        logger.warning("answer_postprocess.fallback_route: route=report_template_guard")
        return
    if route == "report_text":
        logger.info("answer_postprocess.fallback_route: route=report_text")
        return
    if route in {"summary_json_template_guard_current_mail", "summary_json_template_guard"}:
        logger.warning("answer_postprocess.fallback_route: route=summary_json_template_guard")
        return
    if route == "summary_text":
        logger.info("answer_postprocess.fallback_route: route=summary_text")
        return
    if route == "summary_freeform_text":
        logger.info("answer_postprocess.fallback_route: route=summary_freeform_text")
        return
    if route == "json_template_guard":
        logger.warning("answer_postprocess.fallback_route: route=json_template_guard")
        return
    if route == "generic_json_object_text":
        logger.info("answer_postprocess.fallback_route: route=generic_json_object_text")
        return
    if route == "auto_code_snippet_text":
        logger.info("answer_postprocess.fallback_route: route=auto_code_snippet_text")
        return
    logger.info("answer_postprocess.fallback_route: route=general_text")


def _truncate_contract_log(text: str) -> str:
    """
    계약 JSON 로그 문자열 길이를 제한한다.

    Args:
        text: 로그 출력 대상 문자열

    Returns:
        제한 길이로 잘린 문자열
    """
    normalized = str(text or "")
    if len(normalized) <= CONTRACT_LOG_MAX_CHARS:
        return normalized
    return normalized[:CONTRACT_LOG_MAX_CHARS] + "...(truncated)"
