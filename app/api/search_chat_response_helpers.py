from __future__ import annotations

from typing import Any, Callable

from app.api.search_chat_metadata import extract_tool_action


def apply_web_direct_metadata(
    *,
    response_payload: dict[str, Any],
    scope_metadata: dict[str, Any],
    elapsed_ms: float,
    intent_task_type: str,
    intent_output_format: str,
    intent_confidence: float,
    ui_render_mode: str,
) -> dict[str, Any]:
    """
    웹 direct 응답 metadata에 공통 필드를 주입한다.
    """
    metadata = response_payload.get("metadata")
    if isinstance(metadata, dict):
        metadata.update(scope_metadata)
        metadata["elapsed_ms"] = round(float(elapsed_ms), 1)
        metadata["intent_task_type"] = str(intent_task_type or "")
        metadata["intent_output_format"] = str(intent_output_format or "")
        metadata["intent_confidence"] = round(float(intent_confidence or 0.0), 2)
        metadata["ui_render_mode"] = str(ui_render_mode or "")
    return response_payload


def build_completed_response_payload(
    *,
    thread_id: str,
    answer: str,
    agent_thread_id: str,
    source: str,
    raw_answer: str,
    raw_model_output: str,
    raw_model_content: str,
    is_current_mail_mode: bool,
    evidence_mails: list[dict[str, str]],
    aggregated_summary: list[str],
    search_result_count: int | None,
    resolved_scope: str,
    scope_metadata: dict[str, Any],
    elapsed_ms: float,
    answer_format: dict[str, Any],
    intent_task_type: str,
    intent_output_format: str,
    intent_confidence: float,
    next_actions: list[dict[str, Any]],
    web_sources: list[dict[str, str]],
    web_verification_reasons: list[str],
    major_point_evidence: list[dict[str, Any]],
    context_enrichment: dict[str, Any],
    semantic_contract: dict[str, Any],
    stage_timings: dict[str, float],
    code_review_quality: dict[str, Any],
    ui_render_mode: str,
    tool_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    `/search/chat` 완료 응답 payload를 생성한다.
    """
    return {
        "status": "completed",
        "thread_id": thread_id,
        "answer": answer,
        "metadata": {
            "agent_thread_id": str(agent_thread_id or thread_id),
            "tool_action": extract_tool_action(tool_payload=tool_payload),
            "source": source,
            "raw_answer": raw_answer or answer,
            "raw_model_output": raw_model_output or raw_answer or answer,
            "raw_model_content": raw_model_content or raw_model_output or raw_answer or answer,
            "query_type": "current_mail" if is_current_mail_mode else "general",
            "evidence_mails": evidence_mails,
            "aggregated_summary": aggregated_summary,
            "search_result_count": search_result_count,
            "resolved_scope": resolved_scope,
            **scope_metadata,
            "elapsed_ms": round(float(elapsed_ms), 1),
            "answer_format": answer_format,
            "intent_task_type": str(intent_task_type or ""),
            "intent_output_format": str(intent_output_format or ""),
            "intent_confidence": round(float(intent_confidence or 0.0), 2),
            "next_actions": next_actions,
            "web_sources": web_sources,
            "web_verification_reasons": web_verification_reasons,
            "major_point_evidence": major_point_evidence,
            "context_enrichment": context_enrichment,
            "semantic_contract": semantic_contract,
            "stage_elapsed_ms": stage_timings,
            "code_review_quality": code_review_quality if isinstance(code_review_quality, dict) else {},
            "ui_render_mode": str(ui_render_mode or ""),
        },
    }


def build_web_direct_response_with_metadata(
    *,
    builder_fn: Callable[..., dict[str, Any]],
    user_message: str,
    thread_id: str,
    is_current_mail_mode: bool,
    resolved_scope: str,
    selected_message_id: str,
    did_clear_current_mail: bool,
    clear_current_mail_fn: Callable[[], None],
    build_answer_format_metadata_fn: Callable[..., dict[str, Any]],
    selected_mail_subject: str,
    selected_mail_summary: str,
    search_web_sources_fn: Callable[..., list[dict[str, str]]],
    scope_metadata: dict[str, Any],
    elapsed_ms: float,
    intent_task_type: str,
    intent_output_format: str,
    intent_confidence: float,
    ui_render_mode: str,
) -> dict[str, Any]:
    """
    웹 direct 응답을 생성하고 공통 metadata를 적용한다.
    """
    response_payload = builder_fn(
        user_message=user_message,
        thread_id=thread_id,
        is_current_mail_mode=is_current_mail_mode,
        resolved_scope=resolved_scope,
        selected_message_id=selected_message_id,
        did_clear_current_mail=did_clear_current_mail,
        clear_current_mail=clear_current_mail_fn,
        build_answer_format_metadata=build_answer_format_metadata_fn,
        selected_mail_subject=selected_mail_subject,
        selected_mail_summary=selected_mail_summary,
        search_web_sources_fn=search_web_sources_fn,
    )
    return apply_web_direct_metadata(
        response_payload=response_payload,
        scope_metadata=scope_metadata,
        elapsed_ms=elapsed_ms,
        intent_task_type=intent_task_type,
        intent_output_format=intent_output_format,
        intent_confidence=intent_confidence,
        ui_render_mode=ui_render_mode,
    )
