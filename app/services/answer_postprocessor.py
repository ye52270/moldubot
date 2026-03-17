from __future__ import annotations
from typing import Any

from app.core.logging_config import get_logger
from app.core.intent_rules import CHAT_MODE_FREEFORM, is_code_review_query, is_mail_summary_skill_query
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
from app.services.current_mail_intent_policy import is_translation_like_request_text
from app.services.format_contract_renderer import render_template_driven_contract
from app.services.format_exception_policy import should_apply_template_driven_contract
from app.services.format_policy_selector import select_format_template
from app.services.format_section_contract import build_format_section_contract
from app.services.format_template_router import render_template_driven_mail_search
from app.services.answer_postprocessor_mail_search import (
    is_mail_search_no_result,
    render_mail_search_no_result_message,
    render_recent_sorted_mail_response,
)
from app.services.answer_postprocessor_guards import (
    is_effectively_empty_contract,
    looks_like_json_contract_text,
    render_forced_section_response,
)
from app.services.answer_postprocessor_rendering import render_contract_answer
from app.services.answer_postprocessor_summary import (
    extract_original_user_message,
    is_current_mail_summary_request,
    is_summary_request,
    normalize_multiline_text,
    sanitize_summary_lines,
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


def postprocess_final_answer(
    user_message: str,
    answer: str,
    tool_payload: dict[str, Any] | None = None,
    raw_model_content: Any | None = None,
    chat_mode: str = "skill",
) -> str:
    """
    사용자 질의 문맥을 반영해 최종 응답 텍스트를 후처리한다.

    Args:
        user_message: 사용자 입력 원문(또는 미들웨어 주입 문자열)
        answer: 모델이 생성한 최종 응답 텍스트
        tool_payload: 직전 도구 호출 결과 payload
        raw_model_content: 모델 content 원문 블록(list/dict/string)
        chat_mode: 후처리 모드(`skill`/`freeform`)

    Returns:
        정규화된 최종 응답 텍스트
    """
    normalized_user_message = extract_original_user_message(user_message=user_message)
    normalized_answer = normalize_multiline_text(text=answer)
    normalized_tool_payload = tool_payload or {}
    if str(chat_mode or "").strip().lower() == CHAT_MODE_FREEFORM:
        freeform_answer = _postprocess_freeform_answer(
            user_message=normalized_user_message,
            answer=normalized_answer,
            tool_payload=normalized_tool_payload,
            raw_model_content=raw_model_content,
        )
        return FinalAnswerContract(answer=freeform_answer).answer
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
    strict_json_parse = is_mail_summary_skill_query(user_message=normalized_user_message)
    skip_contract_parse = (
        (is_code_review_query(user_message=normalized_user_message) and not looks_like_json_contract_text(text=normalized_answer))
        or (is_translation_like_request_text(user_message=normalized_user_message) and not looks_like_json_contract_text(text=normalized_answer))
    )
    if not skip_contract_parse:
        parse_source: Any = raw_model_content if raw_model_content is not None else answer
        if strict_json_parse:
            parsed_contract = parse_llm_response_contract(
                raw_answer=parse_source,
                allow_json_repair=False,
            )
        else:
            parsed_contract = parse_llm_response_contract(raw_answer=parse_source)
    if parsed_contract is not None:
        if (
            is_current_mail_summary_request(user_message=normalized_user_message)
            and '"format_type"' in normalized_answer
            and not looks_like_json_contract_text(text=normalized_answer)
        ):
            parsed_contract = None
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
    logger.info("answer_postprocess.fallback_route: route=%s", fallback_route)
    return FinalAnswerContract(answer=fallback_rendered).answer


def _postprocess_freeform_answer(
    user_message: str,
    answer: str,
    tool_payload: dict[str, Any],
    raw_model_content: Any | None,
) -> str:
    """
    자유질문 모드에서 의미 보존 위주의 최소 후처리를 수행한다.

    Args:
        user_message: 정규화 사용자 입력
        answer: 정규화 모델 응답
        tool_payload: 직전 도구 payload
        raw_model_content: 모델 content 원문 블록

    Returns:
        자연어 우선 최종 응답 문자열
    """
    if answer and not looks_like_json_contract_text(text=answer):
        return answer

    parse_source: Any = raw_model_content if raw_model_content is not None else answer
    parsed_contract = parse_llm_response_contract(raw_answer=parse_source, log_failures=False)
    if parsed_contract is not None:
        parsed_contract = augment_contract_with_tool_payload(
            user_message=user_message,
            contract=parsed_contract,
            tool_payload=tool_payload,
        )
        rendered = _render_freeform_text_from_contract(contract=parsed_contract)
        if rendered:
            logger.info("answer_postprocess.freeform_contract_render: enabled=true")
            return rendered

    fallback_route, fallback_rendered = render_fallback_answer(
        user_message=user_message,
        answer=answer,
        tool_payload=tool_payload,
    )
    logger.info("answer_postprocess.fallback_route: route=%s", fallback_route)
    return fallback_rendered


def _render_freeform_text_from_contract(contract: LLMResponseContract) -> str:
    """
    JSON 계약 객체를 자유형 문장 응답으로 축약 복원한다.

    Args:
        contract: 파싱된 LLM 응답 계약

    Returns:
        복원된 자유형 텍스트. 복원 실패 시 빈 문자열
    """
    direct_candidates = (
        str(contract.answer or "").strip(),
        str(contract.one_line_summary or "").strip(),
        str(contract.core_issue or "").strip(),
    )
    for candidate in direct_candidates:
        if candidate:
            return normalize_multiline_text(text=candidate)

    line_candidates: list[str] = []
    line_candidates.extend(sanitize_summary_lines(lines=list(contract.summary_lines)))
    line_candidates.extend(sanitize_summary_lines(lines=list(contract.major_points)))
    line_candidates.extend(sanitize_summary_lines(lines=list(contract.key_points)))
    line_candidates.extend(sanitize_summary_lines(lines=list(contract.action_items)))
    line_candidates.extend(sanitize_summary_lines(lines=list(contract.required_actions)))
    if line_candidates:
        unique_lines: list[str] = []
        for line in line_candidates:
            if line not in unique_lines:
                unique_lines.append(line)
            if len(unique_lines) >= 4:
                break
        return " ".join(unique_lines).strip()
    return ""


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
    normalized_answer_for_preserve = str(answer or "").strip()
    preserve_llm_code_review_answer = (
        is_code_review_query(user_message=user_message)
        and bool(normalized_answer_for_preserve)
        and not looks_like_json_contract_text(text=normalized_answer_for_preserve)
        and (
            "```" in normalized_answer_for_preserve
            or "## 코드 분석" in normalized_answer_for_preserve
            or "## 코드 리뷰" in normalized_answer_for_preserve
            or "## 주요 Findings" in normalized_answer_for_preserve
            or "심각도" in normalized_answer_for_preserve
            or "리스크" in normalized_answer_for_preserve
        )
    )
    if preserve_llm_code_review_answer:
        logger.info("answer_postprocess.current_mail_code_review: preserve_llm=true")
        return normalized_answer_for_preserve

    annotated_code_review = render_current_mail_code_review_annotated_response(
        user_message=user_message,
        answer=answer,
        tool_payload=tool_payload,
    )
    if annotated_code_review:
        logger.info("answer_postprocess.current_mail_code_review: render_mode=annotated_segments")
        return annotated_code_review

    normalized_answer = str(answer or "")
    has_findings = "## 주요 findings" in normalized_answer.lower() or "findings" in normalized_answer.lower()
    has_review_fields = "심각도" in normalized_answer and ("근거" in normalized_answer or "영향" in normalized_answer)
    if not (has_findings and has_review_fields):
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

    recent_sorted_rendered = render_recent_sorted_mail_response(
        user_message=user_message,
        tool_payload=tool_payload,
    )
    if recent_sorted_rendered:
        logger.info("answer_postprocess.mail_search_template: route=recent_sorted")
        return recent_sorted_rendered

    if is_mail_search_no_result(user_message=user_message, tool_payload=tool_payload):
        logger.info("answer_postprocess.mail_search_template: route=no_result")
        return render_mail_search_no_result_message(user_message=user_message)

    mail_route, mail_rendered = render_template_driven_mail_search(
        user_message=user_message,
        answer=answer,
        tool_payload=tool_payload,
        section_contract=section_contract,
    )
    if mail_rendered:
        logger.info("answer_postprocess.mail_search_template: route=%s", mail_route)
        return mail_rendered

    return ""


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
    format_type = str(contract.format_type or "").strip().lower()
    if enabled:
        if not is_summary_request(user_message=user_message) and format_type not in ("standard_summary", "detailed_summary"):
            template_driven_rendered = render_template_driven_contract(
                contract=contract,
                section_contract=section_contract,
            )
            if template_driven_rendered:
                return template_driven_rendered
    elif reason:
        logger.info("answer_postprocess.template_driven_contract: enabled=false reason=%s", reason)

    logger.info(
        "answer_postprocess.json_parse_success: format_type=%s summary_lines=%s key_points=%s action_items=%s",
        contract.format_type,
        len(contract.summary_lines),
        len(contract.key_points),
        len(contract.action_items),
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
