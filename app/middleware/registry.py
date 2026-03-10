from __future__ import annotations

import json
from typing import Any

from langchain.agents.middleware import HumanInTheLoopMiddleware, InterruptOnConfig, SummarizationMiddleware

from app.core.llm_runtime import is_model_provider_configured, resolve_env_model
from app.middleware.agent_middlewares import (
    guard_model_output,
    guard_tool_error,
    inject_intent_decomposition_context,
    log_after_agent,
    log_before_agent,
    postprocess_model_answer,
)
from app.core.logging_config import get_logger

logger = get_logger(__name__)


def build_agent_middlewares() -> list[Any]:
    """
    몰두봇 deep agent에 적용할 공통 미들웨어 순서를 구성한다.

    Returns:
        순서가 고정된 미들웨어 목록
    """
    middlewares: list[Any] = [
        log_before_agent,
        inject_intent_decomposition_context,
        guard_model_output,
        _build_human_in_the_loop_middleware(),
        postprocess_model_answer,
        guard_tool_error,
        log_after_agent,
    ]
    summarization_middleware = _build_summarization_middleware()
    if summarization_middleware is not None:
        middlewares.insert(2, summarization_middleware)
    return middlewares


def _build_summarization_middleware() -> SummarizationMiddleware | None:
    """
    선택된 요약 모델 provider 키가 있을 때만 SummarizationMiddleware를 생성한다.

    Returns:
        생성된 SummarizationMiddleware 또는 None
    """
    summary_model = resolve_env_model(
        primary_env="MOLDUBOT_SUMMARIZATION_MODEL",
        fallback_envs=("SUMMARIZATION_MODEL", "DEFAULT_CHAT_MODEL"),
        default_model="gpt-4o-mini",
    )
    if not is_model_provider_configured(model_name=summary_model):
        logger.info("middleware.registry: provider key 미설정으로 SummarizationMiddleware 비활성화")
        return None
    return SummarizationMiddleware(
        model=summary_model,
        trigger=("tokens", 2000),
        keep=("messages", 20),
    )


def _build_human_in_the_loop_middleware() -> HumanInTheLoopMiddleware:
    """
    회의실/ToDo 생성 도구에 대한 HIL 미들웨어를 구성한다.

    Returns:
        HumanInTheLoopMiddleware 인스턴스
    """
    interrupt_on: dict[str, bool | InterruptOnConfig] = {
        "book_meeting_room": {
            "allowed_decisions": ["approve", "reject"],
            "description": _format_hitl_description,
        },
        "create_outlook_todo": {
            "allowed_decisions": ["approve", "reject"],
            "description": _format_hitl_description,
        },
        "create_outlook_calendar_event": {
            "allowed_decisions": ["approve", "reject"],
            "description": _format_hitl_description,
        },
    }
    return HumanInTheLoopMiddleware(interrupt_on=interrupt_on)


def _format_hitl_description(tool_call: dict[str, Any], state: dict[str, Any], runtime: Any) -> str:
    """
    HIL 승인 카드에 노출할 툴 설명 문자열을 구성한다.

    Args:
        tool_call: 모델이 생성한 tool_call
        state: 에이전트 상태
        runtime: 에이전트 런타임

    Returns:
        승인 요청 설명 문자열
    """
    del state, runtime
    name = str(tool_call.get("name") or "").strip()
    args = tool_call.get("args")
    args_text = json.dumps(args if isinstance(args, dict) else {}, ensure_ascii=False, indent=2)
    return f"HIL 승인 필요\n도구: {name}\n인자:\n{args_text}"
