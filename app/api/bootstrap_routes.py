from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.agents.deep_chat_agent import get_deep_chat_agent
from app.api.bootstrap_legacy_routes import router as legacy_router
from app.api.bootstrap_meeting_calendar_routes import router as meeting_calendar_router
from app.api.bootstrap_ops_routes import router as ops_router
from app.api.contracts import ConfirmRequest
from app.services.next_action_contract_extractor import resolve_next_actions_from_model_content
from app.services.next_action_recommender import recommend_next_actions

router = APIRouter()
CONFIRM_ACTION_TO_QUERY: dict[str, str] = {
    "create_outlook_todo": "현재메일 기반으로 조치 필요 사항을 ToDo로 등록해줘",
    "book_meeting_room": "현재메일 기준으로 회의실 예약해줘",
    "create_outlook_calendar_event": "현재메일 제안 내용으로 일정 생성해줘",
}


@router.post("/search/chat/confirm")
def search_chat_confirm(payload: ConfirmRequest) -> dict[str, Any]:
    """
    사용자 확인(승인/취소) 이벤트를 처리한다.

    Args:
        payload: 확인 요청 본문

    Returns:
        확인 처리 결과
    """
    prompt_variant = str(payload.prompt_variant or "").strip()
    agent = get_deep_chat_agent(prompt_variant=prompt_variant or None)
    decision_type = _resolve_confirm_decision_type(payload=payload)
    result = agent.resume_pending_actions(
        thread_id=payload.thread_id,
        approved=payload.approved,
        confirm_token=payload.confirm_token,
        decision_type=decision_type,
        edited_action=payload.edited_action,
    )
    tool_payload = agent.get_last_tool_payload() if hasattr(agent, "get_last_tool_payload") else {}
    raw_model_content = (
        agent.get_last_raw_model_content()
        if hasattr(agent, "get_last_raw_model_content")
        else ""
    )
    status = str(result.get("status") or "").strip()
    thread_id = str(result.get("thread_id") or payload.thread_id or "").strip()
    answer = str(result.get("answer") or "").strip()
    interrupts = result.get("interrupts")
    pending = interrupts if isinstance(interrupts, list) else []
    if status == "interrupted":
        first_interrupt = pending[0] if pending else {}
        first_actions = first_interrupt.get("actions") if isinstance(first_interrupt, dict) else []
        return {
            "status": "pending_approval",
            "thread_id": thread_id,
            "answer": answer or "추가 승인 확인이 필요합니다.",
            "metadata": {
                "confirm": {
                    "required": True,
                    "approved": decision_type == "approve",
                    "decision_type": decision_type,
                    "confirm_token": str(first_interrupt.get("interrupt_id") or ""),
                    "prompt_variant": prompt_variant,
                    "actions": first_actions if isinstance(first_actions, list) else [],
                }
            },
        }
    booking_event = _extract_booking_event_metadata(tool_payload=tool_payload)
    todo_task = _extract_todo_task_metadata(tool_payload=tool_payload)
    treated_as_approved = decision_type in {"approve", "edit"}
    confirm_status, confirm_answer = _resolve_confirm_status_and_answer(
        agent_status=status,
        approved=treated_as_approved,
        answer=answer,
        tool_payload=tool_payload,
    )
    next_actions = _resolve_confirm_next_actions(
        approved=treated_as_approved and confirm_status == "completed",
        tool_payload=tool_payload,
        answer=answer,
        raw_model_content=raw_model_content,
    )
    return {
        "status": confirm_status,
        "thread_id": thread_id,
        "answer": confirm_answer,
        "metadata": {
            "confirm": {"approved": decision_type == "approve", "decision_type": decision_type},
            "booking_event": booking_event,
            "todo_task": todo_task,
            "next_actions": next_actions,
        },
    }


def _resolve_confirm_decision_type(payload: ConfirmRequest) -> str:
    """
    confirm 요청의 decision type을 정규화한다.

    Args:
        payload: confirm 요청 본문

    Returns:
        `approve|edit|reject` 중 하나
    """
    normalized = str(payload.decision_type or "").strip().lower()
    if normalized in {"approve", "edit", "reject"}:
        return normalized
    return "approve" if bool(payload.approved) else "reject"


def _resolve_confirm_status_and_answer(
    agent_status: str,
    approved: bool,
    answer: str,
    tool_payload: object,
) -> tuple[str, str]:
    """
    confirm 처리 결과 상태/응답 문구를 확정한다.

    Args:
        agent_status: 에이전트 실행 상태
        approved: 사용자 승인 여부
        answer: 에이전트 응답 문구
        tool_payload: 최신 tool payload

    Returns:
        (상태, 응답 문구) 튜플
    """
    payload = tool_payload if isinstance(tool_payload, dict) else {}
    tool_status = str(payload.get("status") or "").strip().lower()
    tool_reason = str(payload.get("reason") or "").strip()
    if approved and tool_status == "failed":
        return (
            "failed",
            tool_reason or str(answer or "").strip() or "승인된 작업 실행에 실패했습니다.",
        )
    resolved_status = "completed" if str(agent_status or "").strip() == "completed" else "failed"
    if resolved_status == "completed":
        return (
            resolved_status,
            str(answer or "").strip() or ("승인 처리되었습니다." if approved else "요청을 취소했습니다."),
        )
    return (
        resolved_status,
        str(answer or "").strip() or tool_reason or "승인 처리 중 오류가 발생했습니다.",
    )


def _extract_booking_event_metadata(tool_payload: object) -> dict[str, str]:
    """
    tool payload에서 회의실 예약 이벤트 링크를 추출한다.

    Args:
        tool_payload: 에이전트 최신 tool payload

    Returns:
        예약 이벤트 메타데이터(없으면 빈 dict)
    """
    if not isinstance(tool_payload, dict):
        return {}
    action = str(tool_payload.get("action") or "").strip()
    if action not in ("book_meeting_room", "create_outlook_calendar_event"):
        return {}
    event = tool_payload.get("event")
    if not isinstance(event, dict):
        return {}
    web_link = str(event.get("web_link") or "").strip()
    event_id = str(event.get("id") or "").strip()
    if not web_link and not event_id:
        return {}
    return {
        "id": event_id,
        "web_link": web_link,
    }


def _extract_todo_task_metadata(tool_payload: object) -> dict[str, str]:
    """
    tool payload에서 Outlook ToDo 링크를 추출한다.

    Args:
        tool_payload: 에이전트 최신 tool payload

    Returns:
        ToDo 메타데이터(없으면 빈 dict)
    """
    if not isinstance(tool_payload, dict):
        return {}
    action = str(tool_payload.get("action") or "").strip()
    if action != "create_outlook_todo":
        return {}
    task = tool_payload.get("task")
    if not isinstance(task, dict):
        return {}
    web_link = str(task.get("web_link") or "").strip()
    task_id = str(task.get("id") or "").strip()
    title = str(task.get("title") or "").strip()
    due_date = str(task.get("due_date") or "").strip()
    if not web_link and not task_id:
        return {}
    return {
        "id": task_id,
        "web_link": web_link,
        "title": title,
        "due_date": due_date,
    }


def _resolve_confirm_next_actions(
    approved: bool,
    tool_payload: object,
    answer: str,
    raw_model_content: object,
) -> list[dict[str, str]]:
    """
    confirm 완료 응답용 후속 next action 목록을 계산한다.

    Args:
        approved: 사용자 승인 여부
        tool_payload: 최신 tool payload
        answer: agent 답변 텍스트
        raw_model_content: agent raw model content

    Returns:
        추천 next action 목록(없으면 빈 리스트)
    """
    if not approved:
        return []
    payload = tool_payload if isinstance(tool_payload, dict) else {}
    normalized_payload = _normalize_confirm_action_payload(payload=payload)
    contract_actions = _resolve_next_actions_from_contract(
        raw_model_content=raw_model_content,
        tool_payload=normalized_payload,
    )
    if contract_actions:
        return contract_actions
    action = str(normalized_payload.get("action") or "").strip().lower()
    base_query = CONFIRM_ACTION_TO_QUERY.get(action, "")
    if not base_query:
        return []
    resolved_answer = str(answer or "").strip()
    return recommend_next_actions(
        user_message=base_query,
        answer=resolved_answer,
        tool_payload=normalized_payload,
        intent_task_type="action",
        intent_output_format="",
        selector_mode_override="score",
        allow_embeddings=False,
    )


def _resolve_next_actions_from_contract(
    raw_model_content: object,
    tool_payload: dict[str, Any],
) -> list[dict[str, str]]:
    """
    confirm 응답 모델 계약에서 suggested_action_ids를 복원한다.

    Args:
        raw_model_content: 모델 원문 content
        tool_payload: 최신 tool payload

    Returns:
        UI 표시용 next action 목록
    """
    return resolve_next_actions_from_model_content(
        raw_model_content=raw_model_content,
        tool_payload=tool_payload,
    )


def _normalize_confirm_action_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """
    confirm 후속작업 계산용 payload를 정규화한다.

    Args:
        payload: 원본 tool payload

    Returns:
        current_mail 가용성이 보강된 payload
    """
    action = str(payload.get("action") or "").strip().lower()
    if action not in CONFIRM_ACTION_TO_QUERY:
        return payload
    mail_context = payload.get("mail_context")
    if isinstance(mail_context, dict) and str(mail_context.get("message_id") or "").strip():
        return payload
    normalized = dict(payload)
    normalized["mail_context"] = {"message_id": "confirm_context"}
    return normalized


router.include_router(meeting_calendar_router)
router.include_router(legacy_router)
router.include_router(ops_router)
