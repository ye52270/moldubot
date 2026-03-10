from __future__ import annotations

import os

from deepagents import create_deep_agent
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph

from app.agents.deep_chat_agent import (
    DEFAULT_AGENT_MODEL,
    DEFAULT_PROMPT_VARIANT,
    DEFAULT_SYSTEM_PROMPT,
)
from app.agents.prompts import get_agent_system_prompt
from app.agents.subagents import get_agent_subagents
from app.agents.tools import get_agent_tools
from app.core.llm_runtime import is_model_provider_configured, resolve_env_model
from app.core.logging_config import get_logger
from app.middleware.registry import build_agent_middlewares

logger = get_logger(__name__)
_STUDIO_CHECKPOINTER = InMemorySaver()


def _warn_if_provider_key_missing(model_name: str) -> None:
    """
    LangGraph Studio 부팅 시 모델 provider 키 누락을 경고한다.
    """
    if is_model_provider_configured(model_name=model_name):
        return
    logger.warning("선택된 모델 provider API 키가 없어 그래프 호출 시 실패할 수 있습니다: model=%s", model_name)


def build_graph() -> CompiledStateGraph:
    """
    LangGraph Studio가 사용할 MolduBot 그래프 객체를 생성한다.

    Returns:
        CompiledStateGraph 인스턴스
    """
    model_name = resolve_env_model(
        primary_env="MOLDUBOT_AGENT_MODEL",
        fallback_envs=("DEFAULT_CHAT_MODEL",),
        default_model=DEFAULT_AGENT_MODEL,
    )
    _warn_if_provider_key_missing(model_name=model_name)
    prompt_override = str(os.getenv("MOLDUBOT_AGENT_SYSTEM_PROMPT", "")).strip()
    prompt_variant = str(os.getenv("MOLDUBOT_AGENT_PROMPT_VARIANT", DEFAULT_PROMPT_VARIANT)).strip()
    selected_variant_prompt = get_agent_system_prompt(prompt_variant)
    system_prompt = prompt_override or selected_variant_prompt or DEFAULT_SYSTEM_PROMPT
    logger.info(
        "LangGraph Studio 그래프 초기화: model=%s prompt_variant=%s override=%s",
        model_name,
        prompt_variant or DEFAULT_PROMPT_VARIANT,
        bool(prompt_override),
    )
    return create_deep_agent(
        model=model_name,
        tools=get_agent_tools(),
        system_prompt=system_prompt,
        middleware=build_agent_middlewares(),
        subagents=get_agent_subagents(),
        checkpointer=_STUDIO_CHECKPOINTER,
        name="moldubot-chat-agent",
    )


graph = build_graph()
