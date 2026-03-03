from __future__ import annotations

import json
from typing import Any, Callable

from langchain.agents.middleware import (
    ModelResponse,
    after_agent,
    after_model,
    before_agent,
    before_model,
    wrap_model_call,
    wrap_tool_call,
)
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from app.agents.tool_payload_selector import extract_preferred_tool_payload_from_messages
from app.core.intent_rules import is_mail_search_query
from app.core.logging_config import get_logger, is_prompt_trace_enabled
from app.middleware.policies import (
    compose_intent_augmented_text,
    find_last_human_message,
    is_intent_context_injected,
    normalize_message_text,
    should_inject_intent_context,
)
from app.services.answer_postprocessor import postprocess_final_answer

EMPTY_MODEL_RESPONSE_FALLBACK = "응답을 생성하지 못했습니다. 다시 시도해 주세요."
TOOL_CALLS_KEY = "tool_calls"
ORIGINAL_USER_INPUT_MARKER = "원본 사용자 입력:"
TRACE_MAX_CONTENT_CHARS = 1200
TRACE_TRUNCATION_SUFFIX = "...(truncated)"

logger = get_logger(__name__)


@before_agent
def log_before_agent(state: dict[str, Any], runtime: Any) -> dict[str, Any] | None:
    """
    에이전트 시작 직전에 메시지 개수를 로깅한다.

    Args:
        state: 에이전트 상태 객체
        runtime: LangGraph 런타임 객체

    Returns:
        상태 변경이 없어 None
    """
    del runtime
    messages = state.get("messages")
    message_count = len(messages) if isinstance(messages, list) else 0
    logger.info("middleware.before_agent: message_count=%s", message_count)
    return None


@after_agent
def log_after_agent(state: dict[str, Any], runtime: Any) -> dict[str, Any] | None:
    """
    에이전트 종료 직후 메시지 개수를 로깅한다.

    Args:
        state: 에이전트 상태 객체
        runtime: LangGraph 런타임 객체

    Returns:
        상태 변경이 없어 None
    """
    del runtime
    messages = state.get("messages")
    message_count = len(messages) if isinstance(messages, list) else 0
    logger.info("middleware.after_agent: message_count=%s", message_count)
    return None


def has_tool_call_signal(message: Any) -> bool:
    """
    메시지에 tool calling 신호가 있는지 판별한다.

    Args:
        message: 모델이 반환한 마지막 메시지 객체

    Returns:
        tool_calls 신호가 있으면 True, 아니면 False
    """
    direct_tool_calls = getattr(message, "tool_calls", None)
    if isinstance(direct_tool_calls, list) and direct_tool_calls:
        return True

    additional_kwargs = getattr(message, "additional_kwargs", None)
    if isinstance(additional_kwargs, dict):
        tool_calls = additional_kwargs.get(TOOL_CALLS_KEY)
        if isinstance(tool_calls, list) and tool_calls:
            return True
    return False


@before_model
def inject_intent_decomposition_context(state: dict[str, Any], runtime: Any) -> dict[str, Any] | None:
    """
    모델 호출 전 마지막 사용자 입력에 의도 구조분해 컨텍스트를 주입한다.

    Args:
        state: 에이전트 상태 객체
        runtime: LangGraph 런타임 객체

    Returns:
        메시지 변경이 있으면 {"messages": [...]} 반환
    """
    del runtime
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
    if not should_inject_intent_context(user_message=source_text):
        logger.info("middleware.before_model: 단순 조회 질의로 intent 컨텍스트 주입 생략")
        return None

    composed_text = compose_intent_augmented_text(user_message=source_text)
    messages[message_index].content = composed_text
    logger.info("middleware.before_model: 의도 구조분해 컨텍스트 주입 완료")
    return {"messages": messages}


@wrap_model_call
def guard_model_output(
    request: Any,
    handler: Callable[[Any], Any],
) -> Any:
    """
    모델 호출 전/후를 감싸 예외와 빈 응답을 표준 처리한다.

    Args:
        request: 모델 호출 요청 객체
        handler: 다음 호출 체인 핸들러

    Returns:
        보정된 모델 응답
    """
    if is_prompt_trace_enabled():
        logger.info(
            "prompt_trace.model_request: %s",
            json.dumps(_serialize_model_request_messages(request=request), ensure_ascii=False),
        )

    try:
        response = handler(request)
    except Exception as exc:
        logger.error("middleware.wrap_model_call: 모델 호출 실패: %s", exc)
        return ModelResponse(result=[AIMessage(content=EMPTY_MODEL_RESPONSE_FALLBACK)])

    result_messages = getattr(response, "result", None)
    if not isinstance(result_messages, list) or not result_messages:
        logger.warning("middleware.wrap_model_call: 빈 모델 응답 보정")
        return ModelResponse(result=[AIMessage(content=EMPTY_MODEL_RESPONSE_FALLBACK)])

    last_message = result_messages[-1]
    if is_prompt_trace_enabled():
        logger.info(
            "prompt_trace.model_response: %s",
            json.dumps(_serialize_message_for_trace(message=last_message), ensure_ascii=False),
        )

    if has_tool_call_signal(last_message):
        logger.info("middleware.wrap_model_call: tool_calls 응답 감지, 빈 content 보정 생략")
        return response

    answer = normalize_message_text(getattr(last_message, "content", ""))
    if not answer:
        logger.warning("middleware.wrap_model_call: 공백 모델 응답 보정")
        result_messages[-1] = AIMessage(content=EMPTY_MODEL_RESPONSE_FALLBACK)
    return response


@wrap_tool_call
def guard_tool_error(
    request: Any,
    handler: Callable[[Any], ToolMessage | Command[Any]],
) -> ToolMessage | Command[Any]:
    """
    도구 호출 예외를 ToolMessage로 변환해 에이전트 중단을 방지한다.

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


@after_model
def postprocess_model_answer(state: dict[str, Any], runtime: Any) -> dict[str, Any] | None:
    """
    모델 호출 직후 마지막 AI 응답을 공통 후처리 규칙으로 정규화한다.

    Args:
        state: 에이전트 상태 객체
        runtime: LangGraph 런타임 객체

    Returns:
        메시지 변경이 있으면 {"messages": [...]} 반환
    """
    del runtime
    messages = state.get("messages")
    if not isinstance(messages, list) or not messages:
        return None

    found_ai = _find_last_message(messages=messages, message_type=AIMessage)
    if found_ai is None:
        return None

    ai_index, ai_message = found_ai
    if has_tool_call_signal(ai_message):
        return None
    original_answer = normalize_message_text(ai_message.content)
    if not original_answer:
        return None

    found_human = _find_last_message(messages=messages, message_type=HumanMessage)
    if found_human is None:
        return None
    _, human_message = found_human
    original_user_message = _extract_original_user_message_from_injected_text(
        message_text=normalize_message_text(human_message.content),
    )
    processed_answer = postprocess_final_answer(
        user_message=original_user_message,
        answer=original_answer,
        tool_payload=_extract_latest_tool_payload(
            messages=messages,
            ai_index=ai_index,
            user_message=original_user_message,
        ),
    )
    if not processed_answer or processed_answer == original_answer:
        return None

    messages[ai_index].content = processed_answer
    logger.info("middleware.after_model: 최종 응답 후처리 적용")
    return {"messages": messages}


def _find_last_message(messages: list[Any], message_type: type[BaseMessage]) -> tuple[int, BaseMessage] | None:
    """
    메시지 목록에서 지정 타입의 마지막 메시지를 찾는다.

    Args:
        messages: 상태 메시지 목록
        message_type: 찾을 메시지 클래스 타입

    Returns:
        (인덱스, 메시지) 또는 None
    """
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if isinstance(message, message_type):
            return (index, message)
    return None


def _extract_latest_tool_payload(messages: list[Any], ai_index: int, user_message: str) -> dict[str, Any]:
    """
    최종 AI 응답 직전의 ToolMessage에서 JSON payload를 추출한다.

    Args:
        messages: 상태 메시지 목록
        ai_index: 마지막 AI 메시지 인덱스
        user_message: 원본 사용자 입력

    Returns:
        도구 JSON payload. 없으면 빈 dict
    """
    tool_messages = _collect_tool_messages_for_current_turn(messages=messages, ai_index=ai_index)
    if not tool_messages:
        for index in range(ai_index):
            message = messages[index]
            if isinstance(message, ToolMessage):
                tool_messages.append(message)

    preferred_action = "mail_search" if _should_prefer_mail_search_payload(user_message=user_message) else ""
    return extract_preferred_tool_payload_from_messages(
        messages=tool_messages,
        preferred_action=preferred_action,
    )


def _collect_tool_messages_for_current_turn(messages: list[Any], ai_index: int) -> list[ToolMessage]:
    """
    현재 AI 응답 턴(직전 HumanMessage 이후)에서 생성된 ToolMessage만 수집한다.

    Args:
        messages: 상태 메시지 목록
        ai_index: 마지막 AI 메시지 인덱스

    Returns:
        현재 턴 ToolMessage 목록(시간 순)
    """
    turn_start = 0
    for index in range(ai_index - 1, -1, -1):
        if isinstance(messages[index], HumanMessage):
            turn_start = index + 1
            break

    turn_tools: list[ToolMessage] = []
    for index in range(turn_start, ai_index):
        message = messages[index]
        if isinstance(message, ToolMessage):
            turn_tools.append(message)
    return turn_tools


def _extract_original_user_message_from_injected_text(message_text: str) -> str:
    """
    의도 주입 문자열에서 원본 사용자 입력을 추출한다.

    Args:
        message_text: 주입된 human message 텍스트

    Returns:
        원본 사용자 입력 문자열
    """
    text = str(message_text or "").strip()
    marker_index = text.rfind(ORIGINAL_USER_INPUT_MARKER)
    if marker_index < 0:
        return text
    return text[marker_index + len(ORIGINAL_USER_INPUT_MARKER) :].strip()


def _should_prefer_mail_search_payload(user_message: str) -> bool:
    """
    조회형 메일 질의에서 `mail_search` payload 우선 선택 여부를 결정한다.

    Args:
        user_message: 원본 사용자 입력

    Returns:
        조회형 메일 질의면 True
    """
    normalized = str(user_message or "").replace(" ", "").strip()
    if not normalized or "현재메일" in normalized:
        return False
    return is_mail_search_query(text=normalized)


def _serialize_model_request_messages(request: Any) -> list[dict[str, Any]]:
    """
    모델 요청 객체에서 메시지 목록을 직렬화한다.

    Args:
        request: 모델 요청 객체

    Returns:
        role/content 중심 직렬화 목록
    """
    messages = []
    state = getattr(request, "state", {})
    if isinstance(state, dict):
        raw_messages = state.get("messages", [])
        if isinstance(raw_messages, list):
            messages = raw_messages
    return [_serialize_message_for_trace(message=item) for item in messages]


def _serialize_message_for_trace(message: Any) -> dict[str, Any]:
    """
    메시지 객체를 프롬프트 트레이스용 dict로 직렬화한다.

    Args:
        message: BaseMessage 또는 dict 메시지

    Returns:
        직렬화 결과 dict
    """
    if isinstance(message, BaseMessage):
        return {
            "role": str(getattr(message, "type", "")),
            "content": _normalize_trace_content(content=getattr(message, "content", "")),
        }
    if isinstance(message, dict):
        role = str(message.get("role", message.get("type", "")))
        content = _normalize_trace_content(content=message.get("content", ""))
        return {"role": role, "content": content}
    return {"role": "", "content": _normalize_trace_content(content=message)}


def _normalize_trace_content(content: Any) -> Any:
    """
    메시지 content를 JSON 직렬화 가능한 형태로 정규화한다.

    Args:
        content: 원본 content

    Returns:
        정규화된 content
    """
    if isinstance(content, str):
        text = str(content)
        if len(text) > TRACE_MAX_CONTENT_CHARS:
            return text[:TRACE_MAX_CONTENT_CHARS] + TRACE_TRUNCATION_SUFFIX
        return text
    if isinstance(content, (int, float, bool)) or content is None:
        return content
    if isinstance(content, list):
        return [_normalize_trace_content(item) for item in content]
    if isinstance(content, dict):
        return {str(key): _normalize_trace_content(value) for key, value in content.items()}
    return str(content)
