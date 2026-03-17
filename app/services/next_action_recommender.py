from __future__ import annotations

from typing import Any

from app.services.next_action_recommender_engine import (
    recommend_next_actions as _recommend_next_actions,
    resolve_next_actions_from_action_ids as _resolve_next_actions_from_action_ids,
)


def recommend_next_actions(
    user_message: str,
    answer: str,
    tool_payload: dict[str, Any] | None = None,
    intent_task_type: str = "",
    intent_output_format: str = "",
    selector_mode_override: str | None = None,
    allow_embeddings: bool = True,
) -> list[dict[str, str]]:
    """
    next action 추천기의 파사드 함수.

    Args:
        user_message: 사용자 질의 원문
        answer: 최종 답변 텍스트
        tool_payload: 마지막 tool payload
        intent_task_type: 의도 task type
        intent_output_format: 의도 output format
        selector_mode_override: 추천 모드 강제값(`llm`/`score`)
        allow_embeddings: 임베딩 유사도 계산 허용 여부

    Returns:
        UI 표시용 next action 목록
    """
    return _recommend_next_actions(
        user_message=user_message,
        answer=answer,
        tool_payload=tool_payload,
        intent_task_type=intent_task_type,
        intent_output_format=intent_output_format,
        selector_mode_override=selector_mode_override,
        allow_embeddings=allow_embeddings,
    )


def resolve_next_actions_from_action_ids(
    action_ids: list[str],
    tool_payload: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """
    action_id 목록을 UI next action 카드 목록으로 변환한다.

    Args:
        action_ids: 선택된 액션 식별자 목록
        tool_payload: 현재 툴 payload

    Returns:
        UI 표시용 next action 목록
    """
    return _resolve_next_actions_from_action_ids(
        action_ids=action_ids,
        tool_payload=tool_payload,
    )
