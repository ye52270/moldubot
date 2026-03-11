from __future__ import annotations

from typing import Any

from app.agents.deep_chat_agent import FALLBACK_EMPTY_RESPONSE
from app.agents.intent_schema import ExecutionStep, IntentDecomposition, IntentTaskType
from app.core.intent_rules import is_code_review_query
from app.services.intent_decomposition_service import (
    is_current_mail_scope_value,
    parse_intent_decomposition_safely as _parse_intent_decomposition_safely,
)
from app.services.current_mail_intent_policy import (
    is_current_mail_direct_fact_request,
    is_current_mail_translation_request,
)
from app.services.intent_taxonomy_config import get_intent_taxonomy

INTENT_CLARIFICATION_CONFIDENCE_THRESHOLD = 0.6


def is_non_action_query_for_interrupt_retry(
    decomposition: IntentDecomposition,
    user_message: str,
) -> bool:
    """인터럽트 자동 정리 후 재시도 가능한 비-실행 질의인지 판별한다."""
    action_steps = {ExecutionStep.BOOK_MEETING_ROOM, ExecutionStep.BOOK_CALENDAR_EVENT}
    has_action_step = any(step in action_steps for step in decomposition.steps)
    if decomposition.task_type == IntentTaskType.ACTION or has_action_step:
        return False
    query = str(user_message or "").strip()
    action_keywords = ("예약", "등록", "생성", "실행", "승인", "확정")
    return not any(keyword in query for keyword in action_keywords)


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
    compact_query = query.replace(" ", "")
    if (
        is_current_mail_scope_value(scope_value=resolved_scope)
        and "현재메일" in compact_query
        and ("요약" in compact_query)
    ):
        return "quality_structured_json_strict"
    if (
        is_current_mail_scope_value(scope_value=resolved_scope)
        and "현재메일" in compact_query
        and ("정리" in compact_query or "작업내역" in compact_query or "주요작업" in compact_query)
        and "요약" not in compact_query
    ):
        return "quality_freeform_grounded"
    if is_current_mail_translation_request(
        user_message=query,
        has_current_mail_context=is_current_mail_scope_value(scope_value=resolved_scope),
        decomposition=decomposition,
    ):
        return "quality_translation_grounded"
    if is_current_mail_direct_fact_request(
        user_message=query,
        has_current_mail_context=is_current_mail_scope_value(scope_value=resolved_scope),
        decomposition=decomposition,
    ):
        return "quality_freeform_grounded"
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


def build_intent_clarification(
    user_message: str,
    thread_id: str,
    decomposition: IntentDecomposition | None,
    runtime_options: dict[str, Any],
    is_current_mail_mode: bool = False,
    selected_mail_available: bool = False,
) -> dict[str, Any] | None:
    """low-confidence 의도에 대해 확인 질문 메타데이터를 구성한다."""
    if decomposition is None:
        return None
    if bool(runtime_options.get("skip_intent_clarification")):
        return None
    if str(runtime_options.get("scope") or "").strip():
        return None
    if is_explicit_todo_registration_query(user_message=user_message):
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
    compact = str(user_message or "").replace(" ", "")
    if any(token in compact for token in ("요약", "정리", "조회", "검색")):
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


def is_explicit_todo_registration_query(user_message: str) -> bool:
    """사용자 입력이 ToDo 등록 실행 의도인지 판별한다."""
    compact = str(user_message or "").replace(" ", "").lower()
    if not compact:
        return False
    policy = get_intent_taxonomy().recipient_todo_policy
    has_todo = any(token in compact for token in policy.todo_tokens)
    has_registration = any(token in compact for token in policy.registration_tokens)
    return has_todo and has_registration


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
