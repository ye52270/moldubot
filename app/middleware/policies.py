from __future__ import annotations

from typing import Sequence

from langchain_core.messages import BaseMessage, HumanMessage

from app.agents.intent_parser import get_intent_parser
from app.agents.intent_schema import decomposition_to_context_text
from app.core.logging_config import get_logger

INTENT_CONTEXT_PREFIX = "구조분해 결과:"

logger = get_logger(__name__)


def find_last_human_message(messages: Sequence[BaseMessage]) -> tuple[int, HumanMessage] | None:
    """
    메시지 목록에서 마지막 HumanMessage를 찾는다.

    Args:
        messages: 모델 호출 직전 메시지 목록

    Returns:
        (인덱스, HumanMessage) 튜플 또는 None
    """
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if isinstance(message, HumanMessage):
            return (index, message)
    return None


def normalize_message_text(content: object) -> str:
    """
    메시지 content를 문자열로 정규화한다.

    Args:
        content: 메시지 content 원본 값

    Returns:
        정규화된 문자열
    """
    if isinstance(content, str):
        return content.strip()
    return str(content or "").strip()


def is_intent_context_injected(message_text: str) -> bool:
    """
    사용자 메시지에 구조분해 컨텍스트가 이미 주입되었는지 확인한다.

    Args:
        message_text: 사용자 메시지 텍스트

    Returns:
        이미 주입된 경우 True
    """
    return message_text.startswith(INTENT_CONTEXT_PREFIX)


def compose_intent_augmented_text(user_message: str) -> str:
    """
    사용자 입력을 의도 구조분해 컨텍스트와 결합한다.

    Args:
        user_message: 원본 사용자 입력

    Returns:
        구조분해 컨텍스트 + 원본 입력 문자열
    """
    decomposition = get_intent_parser().parse(user_message=user_message)
    decomposition_json = decomposition.model_dump_json(ensure_ascii=False)
    logger.info("미들웨어 의도 구조분해 결과(JSON): %s", decomposition_json)
    context_text = decomposition_to_context_text(decomposition=decomposition)
    return f"{context_text}\n\n원본 사용자 입력:\n{user_message.strip()}"

