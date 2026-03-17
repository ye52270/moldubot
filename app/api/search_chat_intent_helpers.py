from __future__ import annotations

from typing import Any

from app.agents.deep_chat_agent import FALLBACK_EMPTY_RESPONSE
from app.agents.intent_schema import (
    ExecutionStep,
    IntentDecomposition,
    IntentOutputFormat,
    IntentTaskType,
)
from app.core.intent_rules import (
    CHAT_MODE_SKILL,
    is_code_review_query,
    is_mail_summary_skill_query,
    resolve_chat_mode,
)
from app.services.intent_decomposition_service import (
    is_current_mail_scope_value,
    parse_intent_decomposition_safely as _parse_intent_decomposition_safely,
)
from app.services.current_mail_intent_policy import (
    is_current_mail_direct_fact_request,
    is_current_mail_translation_request,
)

INTENT_CLARIFICATION_CONFIDENCE_THRESHOLD = 0.6


def parse_intent_decomposition_safely(
    user_message: str,
    parser_factory: Any = None,
    has_selected_mail: bool = False,
    selected_message_id_exists: bool = False,
) -> IntentDecomposition | None:
    """라우팅 보조용 intent 구조분해를 안전하게 파싱한다."""
    return _parse_intent_decomposition_safely(
        user_message=user_message,
        parser_factory=parser_factory,
        has_selected_mail=has_selected_mail,
        selected_message_id_exists=selected_message_id_exists,
    )


def select_prompt_variant_from_intent(
    decomposition: IntentDecomposition | None,
    user_message: str = "",
    resolved_scope: str = "",
) -> str:
    """intent task 유형 기반으로 에이전트 prompt variant를 선택한다."""
    query = str(user_message or "").strip()
    if not query and decomposition is not None:
        query = str(decomposition.original_query or "").strip()
    chat_mode = resolve_chat_mode(user_message=query)
    if chat_mode == CHAT_MODE_SKILL:
        if is_mail_summary_skill_query(user_message=query):
            return "quality_structured_json_strict"
        if is_code_review_query(user_message=query):
            return "code_review_expert"
        if decomposition is None:
            return "quality_structured"
        task_type = decomposition.task_type
        if task_type in (IntentTaskType.ANALYSIS, IntentTaskType.SOLUTION):
            return "quality_structured"
        if task_type == IntentTaskType.RETRIEVAL:
            return "fast_compact"
        return "quality_structured"
    is_current_mail_scope = is_current_mail_scope_value(scope_value=resolved_scope)
    if is_current_mail_translation_request(
        user_message=query,
        has_current_mail_context=is_current_mail_scope,
        decomposition=decomposition,
    ):
        return "quality_translation_grounded"
    if is_current_mail_direct_fact_request(
        user_message=query,
        has_current_mail_context=is_current_mail_scope,
        decomposition=decomposition,
    ):
        return "quality_freeform_grounded"
    return "quality_freeform_grounded"


def build_intent_clarification(
    user_message: str,
    thread_id: str,
    decomposition: IntentDecomposition | None,
    runtime_options: dict[str, Any],
    is_current_mail_mode: bool = False,
    selected_mail_available: bool = False,
) -> dict[str, Any] | None:
    """low-confidence 의도에 대해 확인 질문 메타데이터를 구성한다."""
    _ = user_message
    if decomposition is None:
        return None
    if bool(runtime_options.get("skip_intent_clarification")):
        return None
    if str(runtime_options.get("scope") or "").strip():
        return None
    if is_explicit_todo_registration_intent(
        decomposition=decomposition,
    ):
        return None
    if any(
        step in decomposition.steps
        for step in (
            ExecutionStep.BOOK_MEETING_ROOM,
            ExecutionStep.BOOK_CALENDAR_EVENT,
            ExecutionStep.SEARCH_MEETING_SCHEDULE,
        )
    ):
        return None
    if bool(is_current_mail_mode) and bool(selected_mail_available):
        return None
    if decomposition.confidence >= INTENT_CLARIFICATION_CONFIDENCE_THRESHOLD:
        return None
    if decomposition.task_type in (IntentTaskType.SUMMARY, IntentTaskType.RETRIEVAL):
        return None
    if decomposition.output_format in (
        IntentOutputFormat.LINE_SUMMARY,
        IntentOutputFormat.DETAILED_SUMMARY,
        IntentOutputFormat.TABLE,
    ):
        return None
    question = (
        "요청 의도를 확인할게요. 현재메일 기준으로 "
        "1) 요약 2) 원인 분석 3) 해결 방법 중 무엇을 원하시나요?"
    )
    return {
        "required": True,
        "thread_id": thread_id,
        "kind": "intent",
        "task_type": decomposition.task_type.value,
        "confidence": round(decomposition.confidence, 2),
        "question": question,
    }


def is_explicit_todo_registration_intent(
    decomposition: IntentDecomposition | None,
) -> bool:
    """
    ToDo 등록 실행 의도인지 구조화 의도 우선으로 판별한다.

    Args:
        decomposition: 구조화 의도 결과

    Returns:
        명시적 ToDo 등록 의도면 True
    """
    if decomposition is None:
        return False
    return decomposition.task_type == IntentTaskType.ACTION


def build_hitl_confirm_metadata(
    interrupts: object,
    thread_id: str,
    prompt_variant: str = "",
) -> dict[str, Any]:
    """HIL 인터럽트 결과를 UI 확인 카드 메타데이터로 변환한다."""
    normalized_interrupts = interrupts if isinstance(interrupts, list) else []
    first_interrupt = normalized_interrupts[0] if normalized_interrupts else {}
    first_actions = first_interrupt.get("actions") if isinstance(first_interrupt, dict) else []
    confirm_token = first_interrupt.get("interrupt_id") if isinstance(first_interrupt, dict) else ""
    actions = first_actions if isinstance(first_actions, list) else []
    return {
        "required": True,
        "thread_id": thread_id,
        "confirm_token": str(confirm_token or "").strip(),
        "prompt_variant": str(prompt_variant or "").strip(),
        "actions": actions,
    }


def execute_agent_turn(agent: Any, user_message: str, thread_id: str) -> dict[str, Any]:
    """agent 실행 인터페이스 호환 래퍼(`execute_turn` 우선, `respond` fallback)."""
    execute_turn = getattr(agent, "execute_turn", None)
    if callable(execute_turn):
        result = execute_turn(user_message=user_message, thread_id=thread_id)
        if isinstance(result, dict):
            return result
    respond = getattr(agent, "respond", None)
    if callable(respond):
        answer = str(respond(user_message=user_message, thread_id=thread_id) or "").strip() or FALLBACK_EMPTY_RESPONSE
        return {"status": "completed", "answer": answer, "thread_id": thread_id, "interrupts": []}
    return {"status": "failed", "answer": FALLBACK_EMPTY_RESPONSE, "thread_id": thread_id, "interrupts": []}
