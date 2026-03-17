from __future__ import annotations
from typing import Any, Callable

from app.agents.intent_schema import (
    DateFilter,
    DateFilterMode,
    ExecutionStep,
    IntentDecomposition,
    IntentFocusTopic,
    IntentOutputFormat,
    IntentTaskType,
)
from app.api.search_chat_response_builders import build_intent_clarification_response
from app.core.logging_config import get_logger

logger = get_logger(__name__)


def build_summary_policy_decomposition(original_query: str) -> IntentDecomposition:
    """
    현재메일 요약 fast-path에서 사용하는 정책 decomposition을 생성한다.
    """
    return IntentDecomposition(
        original_query=str(original_query or "").strip(),
        steps=[ExecutionStep.READ_CURRENT_MAIL, ExecutionStep.SUMMARIZE_MAIL],
        summary_line_target=5,
        date_filter=DateFilter(mode=DateFilterMode.NONE),
        missing_slots=[],
        task_type=IntentTaskType.SUMMARY,
        output_format=IntentOutputFormat.GENERAL,
        focus_topics=[IntentFocusTopic.MAIL_GENERAL],
        confidence=0.99,
        origin="policy_override",
    )


def build_intent_clarification_payload_if_needed(
    *,
    intent_clarification: dict[str, Any] | None,
    log_prefix: str,
    thread_id: str,
    intent_decomposition: IntentDecomposition | None,
    is_current_mail_mode: bool,
    preliminary_scope: str,
    selected_message_id: str,
    scope_metadata_builder: Callable[..., dict[str, Any]],
    build_answer_format_metadata_fn: Callable[..., dict[str, Any]],
    ui_render_mode: str,
) -> dict[str, Any] | None:
    """
    의도 확인 질문이 필요한 경우 응답 payload를 생성한다.
    """
    if intent_clarification is None:
        return None
    logger.info(
        "%s 의도 확인 필요: thread_id=%s confidence=%.2f",
        log_prefix,
        thread_id,
        intent_decomposition.confidence if intent_decomposition is not None else -1.0,
    )
    response_payload = build_intent_clarification_response(
        question=str(intent_clarification.get("question") or "요청 의도를 한 번만 확인해 주세요."),
        clarification=intent_clarification,
        thread_id=thread_id,
        is_current_mail_mode=is_current_mail_mode,
        scope_metadata=scope_metadata_builder(
            resolved_scope=preliminary_scope,
            is_current_mail_mode=is_current_mail_mode,
            selected_message_id=selected_message_id,
            thread_id=thread_id,
        ),
        build_answer_format_metadata=build_answer_format_metadata_fn,
    )
    metadata = response_payload.get("metadata")
    if isinstance(metadata, dict):
        metadata["ui_render_mode"] = ui_render_mode
    return response_payload


def hydrate_selected_mail_context(
    *,
    selected_message_id: str,
    is_current_mail_mode: bool,
    payload_mailbox_user: str,
    preloaded_mail_context: Any,
    mail_context_getter: Callable[..., Any],
    clear_current_mail_fn: Callable[[], None],
    prime_current_mail_fn: Callable[..., None],
    build_evidence_mail_item_fn: Callable[..., dict[str, str]],
    evidence_snippet_builder: Callable[[Any], str],
    prune_cached_step_fn: Callable[..., IntentDecomposition | None],
    intent_decomposition: IntentDecomposition | None,
    log_prefix: str,
) -> dict[str, Any]:
    """
    선택 메일 컨텍스트를 로딩하고 cache-hit 보정을 수행한다.
    """
    evidence_mails: list[dict[str, str]] = []
    selected_mail = None
    did_clear_current_mail = False
    has_cached_current_mail_context = False

    if not selected_message_id:
        if is_current_mail_mode:
            clear_current_mail_fn()
            did_clear_current_mail = True
            logger.warning("%s 선택 메일 식별자 누락: deep-agent 단일 경로로 진행", log_prefix)
        return {
            "evidence_mails": evidence_mails,
            "selected_mail": selected_mail,
            "did_clear_current_mail": did_clear_current_mail,
            "has_cached_current_mail_context": has_cached_current_mail_context,
            "intent_decomposition": intent_decomposition,
        }

    context_result = preloaded_mail_context
    if context_result is None:
        context_result = mail_context_getter(
            message_id=selected_message_id,
            mailbox_user=str(payload_mailbox_user or "").strip(),
        )
    if context_result.mail is not None:
        selected_mail = context_result.mail
        prime_current_mail_fn(mail=context_result.mail)
        evidence_mails = [
            build_evidence_mail_item_fn(
                message_id=context_result.mail.message_id,
                subject=context_result.mail.subject,
                received_date=context_result.mail.received_date,
                from_address=context_result.mail.from_address,
                web_link=context_result.mail.web_link,
                snippet=evidence_snippet_builder(context_result.mail),
            )
        ]
    else:
        clear_current_mail_fn()
        did_clear_current_mail = True
    logger.info(
        "%s 선택 메일 컨텍스트 조회: message_id=%s status=%s source=%s",
        log_prefix,
        selected_message_id,
        context_result.status,
        context_result.source,
    )
    has_cached_current_mail_context = (
        str(context_result.status or "").strip().lower() == "completed"
        and str(context_result.source or "").strip().lower() == "db-cache"
        and context_result.mail is not None
    )
    intent_decomposition = prune_cached_step_fn(
        decomposition=intent_decomposition,
        has_cached_context=has_cached_current_mail_context,
        log_prefix=log_prefix,
    )
    if context_result.mail is None:
        logger.warning("%s 선택 메일 컨텍스트 조회 실패: deep-agent 단일 경로로 진행", log_prefix)
    return {
        "evidence_mails": evidence_mails,
        "selected_mail": selected_mail,
        "did_clear_current_mail": did_clear_current_mail,
        "has_cached_current_mail_context": has_cached_current_mail_context,
        "intent_decomposition": intent_decomposition,
    }
