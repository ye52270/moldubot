from __future__ import annotations

import os
from functools import lru_cache
from typing import Mapping

from deepagents import create_deep_agent
from langchain_core.messages import BaseMessage

from app.core.logging_config import get_logger
from app.middleware.registry import build_agent_middlewares
from app.agents.tools import get_agent_tools

DEFAULT_AGENT_MODEL = "gpt-4o-mini"
DEFAULT_SYSTEM_PROMPT = (
    "You are MolduBot. Reply in Korean by default unless the user requests another language. "
    "Keep answers practical and concise. "
    "When users ask about current email, summary, key facts, recipients, meeting room search, or booking, "
    "use tools first and answer only with tool-grounded facts."
)
FALLBACK_EMPTY_RESPONSE = "응답을 생성하지 못했습니다. 다시 시도해 주세요."

logger = get_logger(__name__)


def is_openai_key_configured() -> bool:
    """
    OpenAI API 키가 런타임 환경에 설정되어 있는지 확인한다.

    Returns:
        OPENAI_API_KEY가 비어 있지 않으면 True, 아니면 False
    """
    # 공백 문자열을 제거한 뒤 실제 키 값 존재 여부를 판정한다.
    return bool(str(os.getenv("OPENAI_API_KEY", "")).strip())


def _extract_text_from_content(content: object) -> str:
    """
    LangChain 메시지 content 필드에서 사용자에게 보여줄 텍스트를 추출한다.

    Args:
        content: 문자열 또는 블록 배열 형태의 메시지 콘텐츠

    Returns:
        추출된 텍스트. 추출할 수 없으면 빈 문자열
    """
    # 단순 문자열 콘텐츠는 바로 반환한다.
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""

    chunks: list[str] = []
    # 멀티모달 블록 중 text 타입만 연결한다.
    for block in content:
        if not isinstance(block, Mapping):
            continue
        if str(block.get("type", "")) != "text":
            continue
        text = str(block.get("text", "")).strip()
        if text:
            chunks.append(text)
    return "\n".join(chunks).strip()


def _extract_assistant_text(result: Mapping[str, object]) -> str:
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

    # 최신 메시지부터 역순으로 조회해 마지막 AI 응답을 찾는다.
    for message in reversed(messages):
        if isinstance(message, BaseMessage):
            if str(getattr(message, "type", "")) != "ai":
                continue
            return _extract_text_from_content(getattr(message, "content", ""))
        if isinstance(message, Mapping):
            if str(message.get("role", "")) != "assistant":
                continue
            return _extract_text_from_content(message.get("content", ""))
    return ""


class DeepChatAgent:
    """
    단일 deep agent를 생성해 사용자 메시지에 대한 응답을 반환하는 서비스 클래스.
    """

    def __init__(self, model_name: str, system_prompt: str) -> None:
        """
        Deep agent를 초기화한다.

        Args:
            model_name: OpenAI 모델 이름
            system_prompt: 에이전트 기본 시스템 프롬프트
        """
        self._graph = create_deep_agent(
            model=model_name,
            tools=get_agent_tools(),
            system_prompt=system_prompt,
            middleware=build_agent_middlewares(),
            name="moldubot-chat-agent",
        )

    def respond(self, user_message: str) -> str:
        """
        사용자 메시지를 deep agent로 처리해 텍스트 응답을 반환한다.

        Args:
            user_message: 사용자 입력 문장

        Returns:
            모델 응답 텍스트. 비어 있으면 기본 안내 문구 반환
        """
        # 요청 처리는 모델 + tool calling 경로로 일원화한다.
        logger.info("deep agent 응답 생성 시작: input_length=%s", len(user_message))
        payload = {"messages": [{"role": "user", "content": user_message.strip()}]}
        result = self._graph.invoke(payload)

        if not isinstance(result, Mapping):
            logger.warning("deep agent 결과 형식이 예상과 달라 기본 응답을 반환합니다.")
            return FALLBACK_EMPTY_RESPONSE

        answer = _extract_assistant_text(result).strip()
        logger.info("deep agent 응답 생성 완료: answer_length=%s", len(answer))
        return answer or FALLBACK_EMPTY_RESPONSE


@lru_cache(maxsize=1)
def get_deep_chat_agent() -> DeepChatAgent:
    """
    애플리케이션 전역에서 재사용할 단일 deep agent 인스턴스를 반환한다.

    Returns:
        초기화된 DeepChatAgent 객체
    """
    # 운영 환경에서 모델/프롬프트를 주입할 수 있도록 환경변수 우선 정책을 사용한다.
    model_name = str(os.getenv("MOLDUBOT_AGENT_MODEL", DEFAULT_AGENT_MODEL)).strip()
    normalized_model = model_name or DEFAULT_AGENT_MODEL
    system_prompt = str(os.getenv("MOLDUBOT_AGENT_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT)).strip()
    normalized_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
    return DeepChatAgent(model_name=normalized_model, system_prompt=normalized_prompt)
