from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.agents.deep_chat_agent import get_deep_chat_agent
from app.api.bootstrap_legacy_routes import router as legacy_router
from app.api.bootstrap_meeting_calendar_routes import router as meeting_calendar_router
from app.api.bootstrap_ops_routes import router as ops_router
from app.api.contracts import ConfirmRequest, IntentResolveRequest, SearchByIdRequest
from app.core.metrics import get_chat_metrics_tracker
from app.services.next_action_recommender import recommend_next_actions

router = APIRouter()
chat_metrics = get_chat_metrics_tracker()
CONFIRM_ACTION_TO_QUERY: dict[str, str] = {
    "create_outlook_todo": "현재메일 기반으로 조치 필요 사항을 ToDo로 등록해줘",
    "book_meeting_room": "현재메일 기준으로 회의실 예약해줘",
    "create_outlook_calendar_event": "현재메일 제안 내용으로 일정 생성해줘",
}


@router.get("/search/chat/metrics")
def search_chat_metrics() -> dict[str, Any]:
    """
    `/search/chat` 운영 메트릭 스냅샷을 반환한다.

    Returns:
        성공률/지연/폴백 비율을 포함한 메트릭 사전
    """
    return chat_metrics.snapshot()


@router.post("/search/chat/confirm")
def search_chat_confirm(payload: ConfirmRequest) -> dict[str, Any]:
    """
    사용자 확인(승인/취소) 이벤트를 처리한다.

    Args:
        payload: 확인 요청 본문

    Returns:
        확인 처리 결과
    """
    agent = get_deep_chat_agent()
    result = agent.resume_pending_actions(
        thread_id=payload.thread_id,
        approved=payload.approved,
        confirm_token=payload.confirm_token,
    )
    tool_payload = agent.get_last_tool_payload() if hasattr(agent, "get_last_tool_payload") else {}
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
                    "approved": bool(payload.approved),
                    "confirm_token": str(first_interrupt.get("interrupt_id") or ""),
                    "actions": first_actions if isinstance(first_actions, list) else [],
                }
            },
        }
    booking_event = _extract_booking_event_metadata(tool_payload=tool_payload)
    todo_task = _extract_todo_task_metadata(tool_payload=tool_payload)
    confirm_status, confirm_answer = _resolve_confirm_status_and_answer(
        agent_status=status,
        approved=bool(payload.approved),
        answer=answer,
        tool_payload=tool_payload,
    )
    next_actions = _resolve_confirm_next_actions(
        approved=bool(payload.approved) and confirm_status == "completed",
        tool_payload=tool_payload,
        answer=answer,
    )
    return {
        "status": confirm_status,
        "thread_id": thread_id,
        "answer": confirm_answer,
        "metadata": {
            "confirm": {"approved": bool(payload.approved)},
            "booking_event": booking_event,
            "todo_task": todo_task,
            "next_actions": next_actions,
        },
    }


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


@router.post("/intents/resolve")
def intents_resolve(payload: IntentResolveRequest) -> dict[str, Any]:
    """
    단순 키워드 기반 상위 라우팅 의도를 반환한다.

    Args:
        payload: 의도 판별 요청

    Returns:
        라우팅 의도 결과
    """
    text = str(payload.message or "").lower()
    if "회의실" in text or "회의" in text:
        intent = "room_booking"
    elif "근태" in text:
        intent = "hr_apply"
    elif "비용" in text or "정산" in text:
        intent = "finance"
    elif "실행예산" in text or "promise" in text:
        intent = "promise"
    else:
        intent = "chat"
    return {
        "intent": intent,
        "primary_intent": intent,
        "confidence": 0.7,
        "router_version": "bootstrap-v1",
    }


@router.post("/search/id")
def search_by_id(payload: SearchByIdRequest) -> dict[str, Any]:
    """
    전달받은 message_id를 그대로 에코 반환한다.

    Args:
        payload: 식별자 조회 요청

    Returns:
        식별자 매핑 결과
    """
    raw = str(payload.id or "").strip()
    return {
        "found": bool(raw),
        "message_id": raw,
        "open_message_id": raw,
        "resolved_by": "passthrough",
    }


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


def _resolve_confirm_next_actions(approved: bool, tool_payload: object, answer: str) -> list[dict[str, str]]:
    """
    confirm 완료 응답용 후속 next action 목록을 계산한다.

    Args:
        approved: 사용자 승인 여부
        tool_payload: 최신 tool payload
        answer: agent 답변 텍스트

    Returns:
        추천 next action 목록(없으면 빈 리스트)
    """
    if not approved:
        return []
    payload = tool_payload if isinstance(tool_payload, dict) else {}
    action = str(payload.get("action") or "").strip().lower()
    base_query = CONFIRM_ACTION_TO_QUERY.get(action, "")
    if not base_query:
        return []
    resolved_answer = str(answer or "").strip()
    return recommend_next_actions(
        user_message=base_query,
        answer=resolved_answer,
        tool_payload=payload,
        intent_task_type="action",
        intent_output_format="",
    )


router.include_router(meeting_calendar_router)
router.include_router(legacy_router)
router.include_router(ops_router)
