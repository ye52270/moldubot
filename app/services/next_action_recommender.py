from __future__ import annotations

from typing import Any

from app.services.next_action_recommender_engine import recommend_next_actions as _recommend_next_actions


def recommend_next_actions(
    user_message: str,
    answer: str,
    tool_payload: dict[str, Any] | None = None,
    intent_task_type: str = "",
    intent_output_format: str = "",
) -> list[dict[str, str]]:
    """
    next action 추천기의 파사드 함수.

    Args:
        user_message: 사용자 질의 원문
        answer: 최종 답변 텍스트
        tool_payload: 마지막 tool payload
        intent_task_type: 의도 task type
        intent_output_format: 의도 output format

    Returns:
        UI 표시용 next action 목록
    """
    return _recommend_next_actions(
        user_message=user_message,
        answer=answer,
        tool_payload=tool_payload,
        intent_task_type=intent_task_type,
        intent_output_format=intent_output_format,
    )
