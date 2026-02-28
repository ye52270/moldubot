from __future__ import annotations

from typing import Any, Callable

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
)
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command

from app.core.logging_config import get_logger
from app.middleware.policies import (
    compose_intent_augmented_text,
    find_last_human_message,
    is_intent_context_injected,
    normalize_message_text,
)

EMPTY_MODEL_RESPONSE_FALLBACK = "응답을 생성하지 못했습니다. 다시 시도해 주세요."

logger = get_logger(__name__)


class RequestResponseLogMiddleware(AgentMiddleware):
    """
    에이전트 요청/응답 경계를 공통 로깅하는 미들웨어.
    """

    def before_agent(self, state: dict[str, Any], runtime: Any) -> dict[str, Any] | None:
        """
        에이전트 시작 직전에 메시지 개수를 로깅한다.

        Args:
            state: 에이전트 상태 객체
            runtime: LangGraph 런타임 객체

        Returns:
            상태 변경이 없어 None
        """
        messages = state.get("messages")
        message_count = len(messages) if isinstance(messages, list) else 0
        logger.info("middleware.before_agent: message_count=%s", message_count)
        return None

    def after_agent(self, state: dict[str, Any], runtime: Any) -> dict[str, Any] | None:
        """
        에이전트 종료 직후 메시지 개수를 로깅한다.

        Args:
            state: 에이전트 상태 객체
            runtime: LangGraph 런타임 객체

        Returns:
            상태 변경이 없어 None
        """
        messages = state.get("messages")
        message_count = len(messages) if isinstance(messages, list) else 0
        logger.info("middleware.after_agent: message_count=%s", message_count)
        return None


class IntentDecompositionMiddleware(AgentMiddleware):
    """
    모델 호출 전 사용자 입력에 의도 구조분해 컨텍스트를 주입하는 미들웨어.
    """

    def before_model(self, state: dict[str, Any], runtime: Any) -> dict[str, Any] | None:
        """
        마지막 사용자 메시지를 찾아 구조분해 컨텍스트를 결합한다.

        Args:
            state: 에이전트 상태 객체
            runtime: LangGraph 런타임 객체

        Returns:
            메시지 업데이트가 있으면 {"messages": [...]} 반환
        """
        messages = state.get("messages")
        if not isinstance(messages, list) or not messages:
            return None

        found = find_last_human_message(messages=messages)
        if found is None:
            return None

        message_index, human_message = found
        source_text = normalize_message_text(human_message.content)
        if not source_text:
            return None
        if is_intent_context_injected(message_text=source_text):
            return None

        composed_text = compose_intent_augmented_text(user_message=source_text)
        messages[message_index].content = composed_text
        logger.info("middleware.before_model: 의도 구조분해 컨텍스트 주입 완료")
        return {"messages": messages}


class ModelOutputGuardMiddleware(AgentMiddleware):
    """
    모델 호출 결과를 표준화하고 비정상 응답을 방어하는 미들웨어.
    """

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any]:
        """
        모델 호출 전/후를 감싸서 예외 및 빈 응답을 표준 처리한다.

        Args:
            request: 모델 호출 요청 객체
            handler: 다음 호출 체인 핸들러

        Returns:
            보정된 모델 응답
        """
        try:
            response = handler(request)
        except Exception as exc:
            logger.error("middleware.wrap_model_call: 모델 호출 실패: %s", exc)
            return ModelResponse(result=[AIMessage(content=EMPTY_MODEL_RESPONSE_FALLBACK)])

        if not response.result:
            logger.warning("middleware.wrap_model_call: 빈 모델 응답 보정")
            return ModelResponse(result=[AIMessage(content=EMPTY_MODEL_RESPONSE_FALLBACK)])

        last_message = response.result[-1]
        answer = normalize_message_text(getattr(last_message, "content", ""))
        if not answer:
            logger.warning("middleware.wrap_model_call: 공백 모델 응답 보정")
            response.result[-1] = AIMessage(content=EMPTY_MODEL_RESPONSE_FALLBACK)
        return response


class ToolErrorGuardMiddleware(AgentMiddleware):
    """
    도구 실행 실패를 사용자 가시 메시지로 표준화하는 미들웨어.
    """

    def wrap_tool_call(self, request: Any, handler: Callable[[Any], ToolMessage | Command[Any]]) -> ToolMessage | Command[Any]:
        """
        도구 호출 예외를 ToolMessage로 변환해 에이전트를 중단하지 않도록 처리한다.

        Args:
            request: 도구 호출 요청 객체
            handler: 다음 호출 체인 핸들러

        Returns:
            원본 도구 결과 또는 오류 ToolMessage
        """
        try:
            return handler(request)
        except Exception as exc:
            tool_call_id = ""
            tool_call = getattr(request, "tool_call", {})
            if isinstance(tool_call, dict):
                tool_call_id = str(tool_call.get("id", ""))
            logger.error("middleware.wrap_tool_call: 도구 호출 실패: %s", exc)
            return ToolMessage(
                content=f"도구 호출 중 오류가 발생했습니다: {exc}",
                tool_call_id=tool_call_id,
                status="error",
            )

