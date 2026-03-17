from __future__ import annotations

from typing import Any, Callable

from langchain.agents.middleware import (
    ModelResponse,
    after_agent,
    after_model,
    before_agent,
    wrap_model_call,
    wrap_tool_call,
)
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.types import Command

from app.agents.tool_payload_selector import extract_preferred_tool_payload_from_messages
from app.core.intent_rules import is_mail_search_query, resolve_chat_mode
from app.core.logging_config import get_logger
from app.middleware.policies import (
    INTENT_SYSTEM_CONTEXT_PREFIX,
    compose_intent_system_context,
    find_last_human_message,
    is_intent_context_injected,
    normalize_message_text,
    should_inject_intent_context,
)
from app.middleware.search_tool_args import normalize_search_tool_args
from app.services.answer_postprocessor import postprocess_final_answer
from app.services.current_mail_intent_policy import resolve_current_mail_direct_fact_decision

EMPTY_MODEL_RESPONSE_FALLBACK = "응답을 생성하지 못했습니다. 다시 시도해 주세요."
TOOL_CALLS_KEY = "tool_calls"
ORIGINAL_USER_INPUT_MARKER = "원본 사용자 입력:"
SCOPE_PREFIX_MARKER = "[질의 범위]"
RAW_RESPONSE_LOG_MAX_CHARS = 1200
RAW_MODEL_MESSAGE_TEXT_KEY = "raw_model_message_text"
RAW_MODEL_MESSAGE_CONTENT_KEY = "raw_model_message_content"
INTENT_SYSTEM_CONTEXT_CACHE_KEY = "intent_system_context_cache"

logger = get_logger(__name__)


@before_agent
def log_before_agent(state: dict[str, Any], runtime: Any) -> dict[str, Any] | None:
    """에이전트 시작 직전 메시지 개수를 로깅한다."""
    del runtime
    messages = state.get("messages")
    logger.info("middleware.before_agent: message_count=%s", len(messages) if isinstance(messages, list) else 0)
    return None


@after_agent
def log_after_agent(state: dict[str, Any], runtime: Any) -> dict[str, Any] | None:
    """에이전트 종료 직후 메시지 개수를 로깅한다."""
    del runtime
    messages = state.get("messages")
    logger.info("middleware.after_agent: message_count=%s", len(messages) if isinstance(messages, list) else 0)
    return None


def has_tool_call_signal(message: Any) -> bool:
    """메시지에 tool calling 신호가 있는지 판별한다."""
    direct_tool_calls = getattr(message, "tool_calls", None)
    if isinstance(direct_tool_calls, list) and direct_tool_calls:
        return True
    additional_kwargs = getattr(message, "additional_kwargs", None)
    if isinstance(additional_kwargs, dict):
        tool_calls = additional_kwargs.get(TOOL_CALLS_KEY)
        if isinstance(tool_calls, list) and tool_calls:
            return True
    return False


def _inject_intent_decomposition_context_impl(state: dict[str, Any], runtime: Any) -> dict[str, Any] | None:
    """모델 호출 전 의도 system 컨텍스트를 주입한다."""
    del runtime
    messages = state.get("messages")
    if not isinstance(messages, list) or not messages:
        return None

    if _has_intent_system_context(messages):
        return None

    cached_system_context = str(state.get(INTENT_SYSTEM_CONTEXT_CACHE_KEY) or "").strip()
    if cached_system_context:
        state["messages"] = _insert_system_context_at_top_block(messages, cached_system_context)
        logger.info("middleware.before_model: cached intent system 컨텍스트 주입 완료")
        return None

    found = find_last_human_message(messages=messages)
    if found is None:
        return None
    _, human_message = found
    source_text = normalize_message_text(human_message.content)
    if not source_text or is_intent_context_injected(message_text=source_text):
        return None
    if not should_inject_intent_context(user_message=source_text):
        logger.info("middleware.before_model: 단순 조회 질의로 intent 컨텍스트 주입 생략")
        return None

    system_context = compose_intent_system_context(user_message=source_text)
    state["messages"] = _insert_system_context_at_top_block(messages, system_context)
    state[INTENT_SYSTEM_CONTEXT_CACHE_KEY] = system_context
    logger.info("middleware.before_model: 의도 구조분해 system 컨텍스트 주입 완료")
    return None


@wrap_model_call
def guard_model_output(request: Any, handler: Callable[[Any], Any]) -> Any:
    """모델 호출 오류/빈 응답을 보정하고 raw 응답을 state에 저장한다."""
    state = getattr(request, "state", None)
    if isinstance(state, dict):
        _inject_intent_decomposition_context_impl(state=state, runtime=None)

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
    if has_tool_call_signal(last_message):
        logger.info("middleware.wrap_model_call: tool_calls 응답 감지, 빈 content 보정 생략")
        return response

    answer = _extract_text_from_model_content(getattr(last_message, "content", ""))
    if not answer:
        answer = normalize_message_text(getattr(last_message, "content", ""))

    _capture_raw_model_message_on_state(request=request, message=last_message, normalized_text=answer)
    if answer:
        logger.info("llm.raw_response: length=%s content=%s", len(answer), _truncate_for_raw_log(text=answer))
    else:
        logger.warning("middleware.wrap_model_call: 공백 모델 응답 보정")
        result_messages[-1] = AIMessage(content=EMPTY_MODEL_RESPONSE_FALLBACK)
    return response


def _capture_raw_model_message_on_state(request: Any, message: Any, normalized_text: str) -> None:
    """모델 반환 메시지 원문을 state에 저장한다."""
    state = getattr(request, "state", None)
    if not isinstance(state, dict):
        return
    content = getattr(message, "content", "")
    extracted_text = _extract_text_from_model_content(content=content) or str(normalized_text or "").strip()
    state[RAW_MODEL_MESSAGE_TEXT_KEY] = extracted_text
    state[RAW_MODEL_MESSAGE_CONTENT_KEY] = _normalize_raw_model_content(content=content)


@wrap_tool_call
def guard_tool_error(request: Any, handler: Callable[[Any], ToolMessage | Command[Any]]) -> ToolMessage | Command[Any]:
    """도구 호출 예외를 ToolMessage로 변환한다."""
    _normalize_search_tool_call_args(request=request)
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


def _normalize_search_tool_call_args(request: Any) -> None:
    """검색 도구 인자를 사용자 질의 기준으로 보정한다."""
    tool_call = getattr(request, "tool_call", None)
    if not isinstance(tool_call, dict):
        return
    name = str(tool_call.get("name") or "").strip()
    args = tool_call.get("args")
    if not isinstance(args, dict):
        return
    user_message = _extract_request_user_message(request=request)
    if not user_message:
        return
    normalized_args = normalize_search_tool_args(tool_name=name, tool_args=args, user_message=user_message)
    if normalized_args == args:
        return
    tool_call["args"] = normalized_args
    logger.info(
        "middleware.wrap_tool_call: search args normalized name=%s user_message=%s",
        name,
        user_message[:80],
    )


def _extract_request_user_message(request: Any) -> str:
    """도구 요청 state에서 마지막 사용자 입력 원문을 추출한다."""
    state = getattr(request, "state", None)
    if not isinstance(state, dict):
        return ""
    messages = state.get("messages")
    if not isinstance(messages, list):
        return ""
    found_human = _find_last_message(messages=messages, message_type=HumanMessage)
    if found_human is None:
        return ""
    _, human_message = found_human
    return _extract_original_user_message_from_injected_text(
        message_text=normalize_message_text(getattr(human_message, "content", "")),
    )


@after_model
def postprocess_model_answer(state: dict[str, Any], runtime: Any) -> dict[str, Any] | None:
    """마지막 AI 응답을 공통 후처리로 정규화한다."""
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

    original_answer = _extract_text_from_model_content(ai_message.content) or normalize_message_text(ai_message.content)
    if not original_answer:
        return None

    raw_model_output = str(state.get(RAW_MODEL_MESSAGE_TEXT_KEY) or original_answer).strip() or original_answer
    update_payload: dict[str, Any] = {
        "raw_model_output": raw_model_output,
        "raw_model_content": state.get(RAW_MODEL_MESSAGE_CONTENT_KEY),
    }

    found_human = _find_last_message(messages=messages, message_type=HumanMessage)
    if found_human is None:
        return update_payload

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
        raw_model_content=state.get(RAW_MODEL_MESSAGE_CONTENT_KEY),
        chat_mode=resolve_chat_mode(user_message=original_user_message),
    )
    if not processed_answer or processed_answer == original_answer:
        return update_payload

    messages[ai_index].content = processed_answer
    logger.info("middleware.after_model: 최종 응답 후처리 적용")
    update_payload["messages"] = messages
    return update_payload


def _find_last_message(messages: list[Any], message_type: type[BaseMessage]) -> tuple[int, BaseMessage] | None:
    """메시지 목록에서 지정 타입의 마지막 메시지를 찾는다."""
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if isinstance(message, message_type):
            return index, message
    return None


def _has_intent_system_context(messages: list[Any]) -> bool:
    """메시지 목록에 의도 system 컨텍스트가 이미 존재하는지 확인한다."""
    for message in messages:
        if not isinstance(message, SystemMessage):
            continue
        content = normalize_message_text(getattr(message, "content", ""))
        if INTENT_SYSTEM_CONTEXT_PREFIX in content:
            return True
    return False


def _insert_system_context_at_top_block(messages: list[Any], system_context: str) -> list[Any]:
    """system 컨텍스트를 선두 system 블록에 삽입한다."""
    insert_index = 0
    for message in messages:
        if isinstance(message, SystemMessage):
            insert_index += 1
            continue
        break
    updated = list(messages)
    updated.insert(insert_index, SystemMessage(content=system_context))
    return updated


def _extract_latest_tool_payload(messages: list[Any], ai_index: int, user_message: str) -> dict[str, Any]:
    """최종 AI 응답 직전 현재 턴 ToolMessage에서 payload를 추출한다."""
    tool_messages = _collect_tool_messages_for_current_turn(messages=messages, ai_index=ai_index)
    if not tool_messages:
        return {}

    preferred_action = "mail_search" if _should_prefer_mail_search_payload(user_message=user_message) else ""
    selected_payload = extract_preferred_tool_payload_from_messages(
        messages=tool_messages,
        preferred_action=preferred_action,
    )
    return _attach_postprocess_policy(tool_payload=selected_payload, user_message=user_message)


def _attach_postprocess_policy(tool_payload: dict[str, Any], user_message: str) -> dict[str, Any]:
    """current_mail payload에 후처리 정책 메타를 부착한다."""
    if not isinstance(tool_payload, dict) or not tool_payload:
        return {}
    action = str(tool_payload.get("action") or "").strip().lower()
    if action != "current_mail":
        return dict(tool_payload)

    decision = resolve_current_mail_direct_fact_decision(
        user_message=user_message,
        has_current_mail_context=True,
    )
    updated_payload = dict(tool_payload)
    policy = updated_payload.get("postprocess_policy")
    normalized_policy = dict(policy) if isinstance(policy, dict) else {}
    normalized_policy["direct_fact_decision"] = bool(decision.enabled)
    normalized_policy["direct_fact_target_type"] = str(decision.target_type)
    updated_payload["postprocess_policy"] = normalized_policy
    return updated_payload


def _collect_tool_messages_for_current_turn(messages: list[Any], ai_index: int) -> list[ToolMessage]:
    """직전 HumanMessage 이후 현재 턴 ToolMessage만 수집한다."""
    turn_start = 0
    for index in range(ai_index - 1, -1, -1):
        if isinstance(messages[index], HumanMessage):
            turn_start = index + 1
            break
    return [
        message
        for message in messages[turn_start:ai_index]
        if isinstance(message, ToolMessage)
    ]


def _extract_original_user_message_from_injected_text(message_text: str) -> str:
    """의도 주입 문자열에서 원본 사용자 입력을 추출한다."""
    text = str(message_text or "").strip()
    marker_index = text.rfind(ORIGINAL_USER_INPUT_MARKER)
    if marker_index >= 0:
        return text[marker_index + len(ORIGINAL_USER_INPUT_MARKER) :].strip()
    if text.startswith(SCOPE_PREFIX_MARKER):
        lines = text.splitlines()
        if len(lines) > 1:
            return "\n".join(lines[1:]).strip()
    return text


def _should_prefer_mail_search_payload(user_message: str) -> bool:
    """조회형 메일 질의에서 mail_search payload 우선 여부를 결정한다."""
    normalized = str(user_message or "").replace(" ", "").strip()
    if not normalized or "현재메일" in normalized:
        return False
    return is_mail_search_query(text=normalized)


def _normalize_raw_model_content(content: Any) -> Any:
    """raw_model_content 저장용으로 content를 무손실 정규화한다."""
    if isinstance(content, (str, int, float, bool)) or content is None:
        return content
    if isinstance(content, list):
        return [_normalize_raw_model_content(item) for item in content]
    if isinstance(content, dict):
        return {str(key): _normalize_raw_model_content(value) for key, value in content.items()}
    return str(content)


def _extract_text_from_model_content(content: Any) -> str:
    """모델 content에서 텍스트 블록만 추출한다."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        text = content.get("text")
        if isinstance(text, str):
            return text.strip()
        nested = content.get("content")
        if isinstance(nested, str):
            return nested.strip()
        return ""
    if isinstance(content, list):
        lines = [_extract_text_from_model_content(item) for item in content]
        return "\n".join(line for line in lines if line).strip()
    return ""


def _truncate_for_raw_log(text: str) -> str:
    """raw response 로그 길이를 제한한다."""
    normalized = str(text or "")
    if len(normalized) <= RAW_RESPONSE_LOG_MAX_CHARS:
        return normalized
    return normalized[:RAW_RESPONSE_LOG_MAX_CHARS] + "...(truncated)"
