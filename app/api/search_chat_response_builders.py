from __future__ import annotations

from typing import Any

from app.api.search_chat_metadata import build_context_enrichment
from app.api.search_chat_next_actions_runtime import build_external_web_search_query, render_external_web_search_answer
from app.core.metrics import get_chat_metrics_tracker
from app.services.next_action_recommender import recommend_next_actions
from app.services.web_source_search_service import search_web_sources

chat_metrics = get_chat_metrics_tracker()


def build_scope_clarification_response(
    question: str,
    clarification: dict[str, Any],
    thread_id: str,
    is_current_mail_mode: bool,
    scope_metadata: dict[str, str],
    build_answer_format_metadata: Any,
) -> dict[str, Any]:
    """
    scope clarification 응답 페이로드를 생성한다.
    """
    return {
        "status": "needs_clarification",
        "thread_id": thread_id,
        "answer": question,
        "metadata": {
            "source": "scope-clarification",
            "raw_answer": question,
            "raw_model_output": question,
            "raw_model_content": question,
            "query_type": "current_mail" if is_current_mail_mode else "general",
            "evidence_mails": [],
            "aggregated_summary": [],
            "search_result_count": None,
            "resolved_scope": "",
            **scope_metadata,
            "clarification": clarification,
            "answer_format": build_answer_format_metadata(
                user_message="",
                answer=question,
                status="needs_clarification",
            ),
        },
    }


def build_intent_clarification_response(
    question: str,
    clarification: dict[str, Any],
    thread_id: str,
    is_current_mail_mode: bool,
    scope_metadata: dict[str, str],
    build_answer_format_metadata: Any,
) -> dict[str, Any]:
    """
    intent clarification 응답 페이로드를 생성한다.
    """
    return {
        "status": "needs_clarification",
        "thread_id": thread_id,
        "answer": question,
        "metadata": {
            "source": "intent-clarification",
            "raw_answer": question,
            "raw_model_output": question,
            "raw_model_content": question,
            "query_type": "current_mail" if is_current_mail_mode else "general",
            "evidence_mails": [],
            "aggregated_summary": [],
            "search_result_count": None,
            "resolved_scope": "",
            **scope_metadata,
            "clarification": clarification,
            "answer_format": build_answer_format_metadata(
                user_message="",
                answer=question,
                status="needs_clarification",
            ),
        },
    }


def build_web_search_direct_response(
    user_message: str,
    thread_id: str,
    is_current_mail_mode: bool,
    resolved_scope: str,
    selected_message_id: str,
    did_clear_current_mail: bool,
    clear_current_mail: Any,
    build_answer_format_metadata: Any,
    selected_mail_subject: str,
    selected_mail_summary: str,
    search_web_sources_fn: Any = search_web_sources,
) -> dict[str, Any]:
    """
    웹 검색 직접 실행(next action) 완료 응답을 생성한다.
    """
    web_query = build_external_web_search_query(
        base_query=user_message,
        current_mail_subject=selected_mail_subject,
        current_mail_summary=selected_mail_summary,
    )
    web_sources = search_web_sources_fn(
        user_message=web_query,
        intent_task_type="analysis",
        tool_payload={"mail_context": {"subject": selected_mail_subject, "summary_text": selected_mail_summary}},
    )
    answer = render_external_web_search_answer(web_query=web_query, web_sources=web_sources)
    source = "web-search-direct"
    elapsed_ms = 0.0
    chat_metrics.record(source=source, success=True, elapsed_ms=elapsed_ms, is_fallback=False)
    if selected_message_id and not did_clear_current_mail:
        clear_current_mail()
    answer_format = build_answer_format_metadata(user_message=user_message, answer=answer, status="completed")
    next_actions = recommend_next_actions(
        user_message=user_message,
        answer=answer,
        tool_payload={},
        intent_task_type="analysis",
        intent_output_format="general",
    )
    context_enrichment = build_context_enrichment(
        answer=answer,
        answer_format=answer_format,
        tool_payload={},
        evidence_mails=[],
        next_actions=next_actions,
    )
    return {
        "status": "completed",
        "thread_id": thread_id,
        "answer": answer,
        "metadata": {
            "source": source,
            "raw_answer": answer,
            "raw_model_output": answer,
            "raw_model_content": answer,
            "query_type": "current_mail" if is_current_mail_mode else "general",
            "evidence_mails": [],
            "aggregated_summary": [],
            "search_result_count": None,
            "resolved_scope": resolved_scope,
            "elapsed_ms": round(elapsed_ms, 1),
            "answer_format": answer_format,
            "intent_task_type": "analysis",
            "intent_output_format": "general",
            "intent_confidence": 1.0,
            "next_actions": next_actions,
            "web_sources": web_sources,
            "major_point_evidence": [],
            "context_enrichment": context_enrichment,
            "code_review_quality": {},
        },
    }


def build_pending_approval_response(
    answer: str,
    thread_id: str,
    is_current_mail_mode: bool,
    evidence_mails: list[dict[str, str]],
    aggregated_summary: list[str],
    search_result_count: int | None,
    resolved_scope: str,
    scope_metadata: dict[str, str],
    confirm_metadata: dict[str, Any],
    build_answer_format_metadata: Any,
    raw_model_output: str = "",
    raw_model_content: str = "",
) -> dict[str, Any]:
    """
    HITL 승인 대기 응답 페이로드를 생성한다.
    """
    return {
        "status": "pending_approval",
        "thread_id": thread_id,
        "answer": answer,
        "metadata": {
            "source": "deep-agent-hitl",
            "raw_answer": answer,
            "raw_model_output": str(raw_model_output or answer).strip(),
            "raw_model_content": str(raw_model_content or raw_model_output or answer).strip(),
            "query_type": "current_mail" if is_current_mail_mode else "general",
            "evidence_mails": evidence_mails,
            "aggregated_summary": aggregated_summary,
            "search_result_count": search_result_count,
            "resolved_scope": resolved_scope,
            **scope_metadata,
            "confirm": confirm_metadata,
            "answer_format": build_answer_format_metadata(
                user_message="",
                answer=answer,
                status="pending_approval",
            ),
        },
    }
