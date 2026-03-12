from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from langchain_core.messages import BaseMessage

from app.agents.tool_payload_selector import extract_preferred_tool_payload_from_messages
from app.core.intent_rules import is_mail_search_query


def extract_text_from_content(content: object) -> str:
    """
    LangChain 메시지 content 필드에서 사용자에게 보여줄 텍스트를 추출한다.

    Args:
        content: 문자열 또는 블록 배열 형태의 메시지 콘텐츠

    Returns:
        추출된 텍스트. 추출할 수 없으면 빈 문자열
    """
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""

    chunks: list[str] = []
    for block in content:
        if not isinstance(block, Mapping):
            continue
        if str(block.get("type", "")) != "text":
            continue
        text = str(block.get("text", "")).strip()
        if text:
            chunks.append(text)
    return "\n".join(chunks).strip()


def extract_assistant_text(result: Mapping[str, object]) -> str:
    """
    deep agent 실행 결과에서 마지막 AI 답변 텍스트를 추출한다.

    Args:
        result: agent.invoke 결과 객체

    Returns:
        마지막 AI 답변 텍스트. 찾지 못하면 빈 문자열
    """
    messages = result.get("messages")
    if not isinstance(messages, list):
        return ""

    for message in reversed(messages):
        if isinstance(message, BaseMessage):
            if str(getattr(message, "type", "")) != "ai":
                continue
            return extract_text_from_content(getattr(message, "content", ""))
        if isinstance(message, Mapping):
            role = str(message.get("role", "")).strip().lower()
            if role not in {"assistant", "ai"}:
                continue
            return extract_text_from_content(message.get("content", ""))
    return ""


def extract_latest_tool_payload(result: object, user_message: str = "") -> dict[str, Any]:
    """
    agent 실행 결과에서 최신 tool payload(dict)를 추출한다.

    Args:
        result: graph invoke 결과 객체
        user_message: 사용자 입력 원문(검색형 우선 action 결정용)

    Returns:
        추출된 tool payload. 없으면 빈 dict
    """
    if not isinstance(result, Mapping):
        return {}
    messages = result.get("messages")
    if not isinstance(messages, list):
        return {}
    preferred_action = "mail_search" if is_mail_search_query(text=str(user_message or "").strip()) else ""
    return extract_preferred_tool_payload_from_messages(
        messages=messages,
        preferred_action=preferred_action,
    )


def extract_interrupt_requests(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    """
    graph 결과의 `__interrupt__` 정보를 API 메타데이터 구조로 변환한다.

    Args:
        result: graph invoke 결과 객체

    Returns:
        인터럽트 목록
    """
    raw_interrupts = result.get("__interrupt__")
    if not isinstance(raw_interrupts, list):
        return []
    serialized: list[dict[str, Any]] = []
    for interrupt in raw_interrupts:
        interrupt_id = str(getattr(interrupt, "id", "") or "").strip()
        value = getattr(interrupt, "value", None)
        actions = _extract_actions(value=value)
        if actions:
            serialized.append({"interrupt_id": interrupt_id, "actions": actions})
    return serialized


def extract_interrupt_requests_from_state(state_interrupts: list[object]) -> list[dict[str, Any]]:
    """
    graph state.interrupts를 API 메타데이터 구조로 변환한다.

    Args:
        state_interrupts: state에 저장된 인터럽트 목록

    Returns:
        인터럽트 목록
    """
    serialized: list[dict[str, Any]] = []
    for interrupt in state_interrupts:
        interrupt_id = str(getattr(interrupt, "id", "") or "").strip()
        value = getattr(interrupt, "value", None)
        actions = _extract_actions(value=value)
        if actions:
            serialized.append({"interrupt_id": interrupt_id, "actions": actions})
    return serialized


def _extract_actions(value: object) -> list[dict[str, Any]]:
    """
    단일 interrupt value에서 action 요청 목록을 추출한다.

    Args:
        value: interrupt value

    Returns:
        정규화된 action 목록
    """
    if not isinstance(value, dict):
        return []
    action_requests = value.get("action_requests")
    review_configs = value.get("review_configs")
    actions: list[dict[str, Any]] = []
    if isinstance(action_requests, list):
        for index, request in enumerate(action_requests):
            if not isinstance(request, dict):
                continue
            review = review_configs[index] if isinstance(review_configs, list) and index < len(review_configs) else {}
            allowed_decisions = review.get("allowed_decisions") if isinstance(review, dict) else None
            actions.append(
                {
                    "name": str(request.get("name") or "").strip(),
                    "args": request.get("args") if isinstance(request.get("args"), dict) else {},
                    "description": str(request.get("description") or "").strip(),
                    "allowed_decisions": allowed_decisions if isinstance(allowed_decisions, list) else [],
                }
            )
    return actions


def resolve_thread_id(thread_id: str | None) -> str:
    """
    에이전트 호출에 사용할 thread_id를 정규화한다.

    Args:
        thread_id: 외부에서 전달된 스레드 식별자

    Returns:
        비어 있지 않은 스레드 식별자 문자열
    """
    normalized = str(thread_id or "").strip()
    if normalized:
        return normalized
    return f"outlook_{int(datetime.now(tz=timezone.utc).timestamp())}"
